"""Propose a NEW pipeline spec (catalog tools only) and stage it as a challenger."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.infrastructure.claude_client import ClaudeClient, get_claude_client
from app.models.pipeline_spec import PipelineSpecDocument
from app.pipeline.spec.catalog import get_tool_catalog
from app.pipeline.spec.validator import validate_spec
from app.services.account_repository import AccountRepository
from app.services.pipeline_spec_repository import PipelineSpecRepository
from app.services.pipeline_version_service import compute_pipeline_hash

logger = logging.getLogger(__name__)


def propose_and_stage_challenger(
    account_id: str,
    *,
    repo: PipelineSpecRepository | None = None,
) -> PipelineSpecDocument | None:
    """Build a challenger from the current champion, validate it with the SAME gate
    the runner uses, and stage it as status='challenger'. Returns the staged spec, or
    None if no valid distinct proposal was produced (nothing is written on failure).
    Only needs account_id — the champion spec (not the AccountDocument) is the input."""
    repo = repo or PipelineSpecRepository()
    champion = repo.load(account_id, "champion") or PipelineSpecDocument(account_id=account_id)
    catalog = get_tool_catalog()

    proposal = _propose_spec(champion, catalog)
    if proposal is None:
        return None

    # Identity guard: a proposal byte-identical to the champion is not a challenger.
    # compute_pipeline_hash hashes ONLY the steps tree, so a top_n change always
    # yields a different hash; champion.version_hash may be None pre-first-save,
    # so fall back to hashing the champion's steps directly.
    if compute_pipeline_hash(proposal) == (champion.version_hash or compute_pipeline_hash(champion)):
        return None

    # THE GATE — same validator the runner runs. unknown_tool / non-literal config /
    # dangling reads / bypassed invariants all reject here, before staging.
    report = validate_spec(proposal, catalog)
    if not report.ok:
        logger.debug("Challenger proposal invalid: %s", report.codes())
        return None

    proposal.account_id = account_id
    proposal.status = "challenger"
    proposal.parent_hash = champion.version_hash  # lineage for promote/rollback
    proposal.version_hash = None  # force a fresh challenger version on save
    repo.save(proposal)
    return proposal


def _propose_spec(champion: PipelineSpecDocument, catalog: Any) -> PipelineSpecDocument | None:
    """Dispatch: the LLM proposer when learn_use_builder_llm is on, else the
    deterministic knob-tweak below. Returns a NEW PipelineSpecDocument or None."""
    if settings.learn_use_builder_llm:
        return _propose_spec_llm(champion, catalog)
    # ── DEFAULT: clone the champion, bump the `rank_external_references` leaf's top_n
    #    by one rung on a fixed ladder. None if that leaf is absent.
    proposal = PipelineSpecDocument.model_validate(champion.model_dump())
    leaf = _find_leaf(proposal, step_id="rank_external_references")
    if leaf is None:
        return None
    ladder = [8, 10, 12, 15]
    cur = int(leaf.config.get("top_n", 10))
    leaf.config["top_n"] = ladder[(ladder.index(cur) + 1) % len(ladder)] if cur in ladder else 10
    return proposal


def _find_leaf(spec: PipelineSpecDocument, *, step_id: str) -> Any | None:
    """Depth-first walk of the steps tree; return the first StepSpec whose id == step_id,
    or None. Recurses into CompositeSpec.children."""

    def walk(nodes: list[Any]) -> Any | None:
        for n in nodes:
            if getattr(n, "kind", None) == "step" and n.id == step_id:
                return n
            children = getattr(n, "children", None)
            if children:
                hit = walk(children)
                if hit is not None:
                    return hit
        return None

    return walk(spec.steps)


def _propose_spec_llm(champion: PipelineSpecDocument, catalog: Any) -> PipelineSpecDocument | None:
    """Ask Claude for a JSON proposal, parse it, and return a PipelineSpecDocument or None."""
    claude = get_claude_client()
    if not claude.enabled:
        return None
    system = _render_builder_system_prompt(catalog)
    user = _render_current_spec(champion)
    raw = claude.messages_json_dict(system=system, user=user, max_tokens=2048)
    if raw is None:
        return None
    try:
        return PipelineSpecDocument.model_validate({**raw, "account_id": champion.account_id})
    except Exception as exc:
        logger.debug("Challenger proposal parsing failed: %s", exc)
        return None


def _render_builder_system_prompt(catalog: Any) -> str:
    """Render the system prompt that tells Claude what tools and knobs are available."""
    tools_text = []
    for tool in catalog.all():
        proposable = [p.name for p in tool.parameters if p.config_origin == "literal"]
        tools_text.append(f"  - {tool.tool_id}: {tool.purpose or 'N/A'}")
        if proposable:
            tools_text.append(f"    proposable_params: {', '.join(proposable)}")
    tools_section = "\n".join(tools_text) if tools_text else "  (none)"

    spec_json_desc = """{
  "steps": [
    {
      "kind": "step",
      "id": "step_id_string",
      "tool_id": "tool.id.string",
      "reads": ["artifact_key_1"],
      "writes": ["artifact_key_2"],
      "config": { "param_name": "value", ... },
      "purpose": "human description"
    },
    {
      "kind": "parallel" | "chain",
      "id": "composite_id",
      "children": [ /* nested steps or composites */ ],
      "purpose": "human description"
    }
  ]
}"""

    return f"""You are a pipeline specification rewriter. The user will give you the current
pipeline spec and ask you to propose a modified version.

AVAILABLE TOOLS:
{tools_section}

CONSTRAINT: You may only rewire or reconfigure existing tools by changing their
`config` parameters (particularly the proposable_params listed above). You CANNOT:
- Add tools that don't exist in the list
- Remove required tools
- Write new tool code
- Bypass safety or publication invariants

Return a JSON object matching this structure:
{spec_json_desc}

Return ONLY the JSON object, no other text."""


def _render_current_spec(champion: PipelineSpecDocument) -> str:
    """Render the current champion spec as JSON for the LLM to edit."""
    return f"""Please propose a modification to this pipeline spec:

{json.dumps(champion.model_dump(mode='json'), indent=2)}

Consider:
- Changing proposable_params values (e.g., top_n, max_results_per_query)
- Reordering steps for different priorities
- Adjusting the config of existing tools

Return the full modified spec as JSON."""


def propose_and_apply_soul_rewrite(
    account: Any, *, repo: AccountRepository | None = None, claude: ClaudeClient | None = None
) -> bool:
    """Propose a soul edit (personality/contrast tweak) and apply it. Versioning +
    revision archive are handled by AccountRepository.save → bump_voice_version_if_needed
    (soul plan). Returns True if a change was applied (version bumped), else False."""
    repo = repo or AccountRepository()
    before = account.voice_version_hash
    _apply_soul_proposal(account, claude)
    repo.save(account)  # bumps voice_version_* + archives if soul changed
    return account.voice_version_hash != before


def _apply_soul_proposal(account: Any, claude: ClaudeClient | None = None) -> None:
    """Default (learn_use_builder_llm off): no-op — no deterministic soul ladder exists.
    LLM on: ask Claude for revised personality/posting_prompt/contrast_patterns and
    assign them onto account.soul."""
    if not settings.learn_use_builder_llm:
        return
    claude = claude or get_claude_client()
    if not claude.enabled:
        return
    proposal = claude.messages_json_dict(
        system=_render_soul_rewrite_system_prompt(account),
        user=_render_current_soul(account),
        max_tokens=2048,
    )
    if not proposal:
        return
    for field in ("personality", "posting_prompt", "contrast_patterns", "punctuation_rules"):
        if field in proposal:
            setattr(account.soul, field, proposal[field])


def _render_soul_rewrite_system_prompt(account: Any) -> str:
    """System prompt for soul rewrite: describes the editable soul fields."""
    return """You are a personality editor. The user will give you the current account soul
(personality traits, posting voice, contrast patterns, punctuation rules) and ask you
to propose a modified version.

CONSTRAINTS: You may only edit these soul fields:
- personality: a short description of the account's personality traits
- posting_prompt: the voice instruction for composing posts
- contrast_patterns: a list of patterns to contrast against (list of objects)
- punctuation_rules: a list of punctuation/emphasis rules (list of objects)

Return a JSON object with ONLY the fields you wish to change. Example:
{
  "personality": "New personality description",
  "posting_prompt": "New voice instruction..."
}

Return ONLY valid JSON, no other text."""


def _render_current_soul(account: Any) -> str:
    """Render the current account soul fields as JSON for the LLM to edit."""
    soul_data = {
        "personality": account.personality or "",
        "posting_prompt": account.posting_prompt or "",
        "contrast_patterns": [
            p.model_dump(mode="json") if hasattr(p, "model_dump") else dict(p)
            for p in (account.contrast_patterns or [])
        ],
        "punctuation_rules": [
            r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r)
            for r in (account.punctuation_rules or [])
        ],
    }
    return f"""Please propose a modification to this account soul:

{json.dumps(soul_data, indent=2)}

Consider refining the personality to better match recent post performance, or
adjusting the posting voice for clarity or engagement. Return the modified
soul fields as JSON."""
