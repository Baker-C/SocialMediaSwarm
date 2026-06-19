"""Conversational agent-builder API (doc 10).

POST /api/agent-builder/chat — a multi-turn SSE endpoint that drafts specs, validates
them, and on approval writes them to RavenDB alongside optional soul edits.

The builder WIRES + CONFIGURES existing catalog tools; it never writes tool code.
It reuses validate_spec, compile_spec, artifact_graph_mermaid, and PipelineSpecRepository.

Architecture: mirrors force_post.py's worker/queue/SSE pattern — sync code running in
a thread pool executor, marshaling events back to the async loop via call_soon_threadsafe.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.routes.agent_builder_types import (
    BuilderChatMessage,
    BuilderChatRequest,
    BuilderDraft,
    BuilderSoulEdit,
    emit_assistant_message,
    emit_done,
    emit_error,
    emit_spec_preview,
    emit_spec_written,
    emit_validation_errors,
)
from app.infrastructure.claude_client import get_claude_client
from app.models.account import AccountSoul, default_contrast_patterns, default_punctuation_rules, default_system_prompt
from app.models.pipeline_spec import PipelineSpecDocument
from app.models.tool_catalog import ToolCatalogDocument
from app.pipeline.spec import compile_spec, validate_spec
from app.pipeline.spec.catalog import get_tool_catalog, tool_catalog_hash
from app.pipeline.types.flow import artifact_graph_mermaid
from app.services.account_create_service import apply_account_create, AccountCreateBody
from app.services.account_repository import AccountRepository
from app.services.account_update_service import apply_account_update, AccountUpdateBody
from app.services.pipeline_spec_repository import PipelineSpecRepository

logger = logging.getLogger(__name__)

router = APIRouter()

_REPHRASE = "I couldn't parse your intent. Please rephrase your request as a description of the account and pipeline."


# ── Adapter points: isolated single-source-of-truth for sibling-doc imports (§3.6) ──

def _load_catalog() -> Any:
    """Return the ToolCatalog object (CC-1: the one factory)."""
    return get_tool_catalog()


def _catalog_tools() -> list[ToolCatalogDocument]:
    """Return all tools for prompt rendering."""
    return _load_catalog().all()


def _validate(spec: PipelineSpecDocument) -> Any:
    """Validate a spec against the catalog. Returns ValidationReport."""
    return validate_spec(spec, _load_catalog())


def _compile(spec: PipelineSpecDocument) -> tuple[Any, ...]:
    """Compile a spec to executable steps. Returns tuple[Step, ...]."""
    return compile_spec(spec, catalog=_load_catalog())


def _mermaid(spec: PipelineSpecDocument) -> str:
    """Render the compiled spec as a mermaid flowchart."""
    return artifact_graph_mermaid(_compile(spec))


def _baseline_spec(account_id: str) -> PipelineSpecDocument:
    """Load the baseline seed-spec example for the system prompt (10-leaf SENSE+ACT)."""
    from app.models.pipeline_spec import default_pipeline_spec
    return default_pipeline_spec(account_id)


def _save_spec(spec: PipelineSpecDocument) -> str:
    """Write a spec to RavenDB; returns the document id. Bumps version in place."""
    repo = PipelineSpecRepository()
    repo.save(spec)
    return PipelineSpecDocument.document_id(spec.account_id, spec.status)


# ── System prompt assembly (§5) ──

def _render_tool_for_prompt(tool: ToolCatalogDocument) -> str:
    """One tool's entry in the catalog block of the system prompt."""
    writes_str = ", ".join(tool.writes) if tool.writes else "dynamic"
    params = tool.proposable_params if hasattr(tool, 'proposable_params') else [
        p for p in tool.parameters if p.config_origin == "literal"
    ]
    param_lines = []
    for p in params:
        default_str = f", default={p.default}" if p.default is not None else ""
        param_lines.append(f"      - {p.name} ({p.annotation}{default_str})")
    param_block = "\n".join(param_lines) if param_lines else "      (no proposable parameters)"

    return f"""
  - **{tool.tool_id}** ({tool.kind})
    Purpose: {tool.purpose}
    Writes: {writes_str}
    Proposable parameters:
{param_block}
"""


def _build_system_prompt(account_id: str, mode: str = "edit") -> str:
    """Assemble the full system prompt: role + rules + catalog + soul schema + baseline.

    Rebuilt per turn so it includes live catalog and current soul defaults.
    """
    tools = _catalog_tools()

    # ── Tool catalog block ──
    tool_block = "## Tool Catalog\n\n"
    tool_block += "You may WIRE + CONFIGURE ONLY the tools below. You may NOT:\n"
    tool_block += "- Invent a new tool or write tool code.\n"
    tool_block += "- Set config keys not marked 'proposable' in the catalog.\n\n"
    for tool in tools:
        tool_block += _render_tool_for_prompt(tool)

    # ── Soul schema block ──
    soul_block = "## Account Soul Schema\n\n"
    soul_block += """When you propose a soul_edit, you may set any subset of these fields:
- **category**: the account's niche/persona (string, max 2000 chars)
- **posting_prompt**: structural instructions for composing posts (string, max 32000 chars)
- **personality**: prose describing character, quirks, voice (string, max 16000 chars)
- **contrast_patterns**: list of {text, correlation: "positive"|"negative"} — writing patterns to avoid or favor
- **punctuation_rules**: list of {pattern: regex, replacement: str|null} — deterministic post-generation fixes

Default contrast patterns:
"""
    for pattern in default_contrast_patterns():
        soul_block += f"- '{pattern['text']}'\n"

    soul_block += "\nDefault punctuation rules (auto-applied after generation):\n"
    for rule in default_punctuation_rules():
        soul_block += f"- {rule['pattern']} → {rule['replacement']}\n"

    # ── Baseline spec example ──
    baseline = _baseline_spec(account_id)
    baseline_json = baseline.model_dump(mode="json")
    spec_block = """## Baseline Spec Example

This is the current default pipeline spec — the full SENSE+ACT graph (10 leaves).
Any new spec you draft MUST conform to this vocabulary (same step ids, reads/writes):

```json
"""
    spec_block += json.dumps(baseline_json, indent=2)
    spec_block += "\n```\n"

    # ── Pipeline template block + conversation awareness (create mode only) ──
    pipeline_block = ""
    if mode == "create":
        from app.pipeline.runbooks.templates import get_all_template_descriptions
        template_list = get_all_template_descriptions()
        pipeline_block = "\n\nAVAILABLE PIPELINE TEMPLATES (use these when creating accounts):\n"
        for t in template_list:
            pipeline_block += f"- {t['template_id']}: {t['description']}\n"
        pipeline_block += "\nAfter understanding the account purpose and niche, suggest 1-3 pipeline templates. Include a weight for each that sums to 1.0. Default to equal weights. Return your suggestions in pipeline_selections within soul_edit."

        pipeline_block += """

## Conversation Awareness

At the start of every response, silently review the full conversation history above.
Identify which of the following you still need from the user:
  - Account concept or name idea
  - Content niche and category
  - Target audience
  - Posting style, tone, and personality traits
  - Content strategy (text commentary / images / video / mix)
  - Preferred pipeline type(s) and relative frequency

Ask ONLY for information that is not already present in prior turns.
Do not re-ask for anything the user has already answered.
Once you have enough to propose a soul and pipeline selection, do so immediately — \
do not ask follow-up questions about information you already have."""

    # ── Full prompt ──
    prompt = """You are an agent-builder assistant. You help users describe their social media posting strategy in prose and draft a PipelineSpecDocument that implements it.

## Your Rules

1. You WIRE + CONFIGURE existing tools. You never invent a tool or write tool code.
2. You may only set config keys the catalog marks proposable. Setting anything else will be rejected.
3. Every pipeline MUST contain:
   - A step that produces a safety verdict (writes `safety_verdict`)
   - Exactly one terminal step that publishes (writes `published_post`)
   These are non-negotiable invariants enforced by validation.
4. When you propose a spec, emit it as JSON in the EXACT BuilderDraft shape:
   ```json
   {
     "reply": "<human-readable prose>",
     "spec": { ... PipelineSpecDocument dict ... },
     "soul_edit": { ... optional soul changes ... } or null
   }
   ```
   When you are only chatting or clarifying, set spec to null.

"""
    prompt += tool_block + "\n\n" + soul_block + "\n\n" + spec_block + pipeline_block

    return prompt


def _build_messages_array(messages: list[BuilderChatMessage]) -> list[dict]:
    """Convert BuilderChatMessage history to Claude's native messages array format.

    Validation errors are appended to the assistant turn that produced them so
    Claude can see what went wrong without losing the role structure.
    The array must end on a user turn — guaranteed by the client always appending
    a new user message before posting.
    """
    result = []
    for msg in messages:
        if msg.role == "user":
            result.append({"role": "user", "content": msg.text})
        else:  # assistant
            content = msg.text
            if msg.validation_errors:
                content += "\n\nValidation errors from last proposal:\n"
                for err in msg.validation_errors:
                    code = err.get("code", "unknown")
                    detail = err.get("detail", "")
                    step = err.get("step_id", "")
                    line = f"  - {code}"
                    if step:
                        line += f" (step: {step})"
                    if detail:
                        line += f": {detail}"
                    content += line + "\n"
            result.append({"role": "assistant", "content": content})
    return result


# ── Helpers for the approve path (§7.3) ──

def _last_soul_edit(messages: list[BuilderChatMessage]) -> BuilderSoulEdit | None:
    """Extract the echoed soul_edit from the last assistant proposal."""
    for msg in reversed(messages):
        if msg.role == "assistant" and msg.proposed_spec is not None:
            if msg.proposed_soul_edit is not None:
                try:
                    return BuilderSoulEdit.model_validate(msg.proposed_soul_edit)
                except ValidationError:
                    return None
            return None
    return None


def _update_body(soul_edit: BuilderSoulEdit) -> AccountUpdateBody:
    """Map a BuilderSoulEdit to AccountUpdateBody for the dashboard's update path."""
    return AccountUpdateBody(**soul_edit.model_dump(exclude_none=True))


def _create_body(account_id: str, soul_edit: BuilderSoulEdit | None) -> AccountCreateBody:
    """Map a BuilderSoulEdit to AccountCreateBody for new-account provisioning."""
    fields = soul_edit.model_dump(exclude_none=True) if soul_edit else {}
    return AccountCreateBody(account_id=account_id, **fields)


# ── State machine (§7.2 & §7.3) ──

def _run_builder_turn(req: BuilderChatRequest, emit: Callable[[dict], None]) -> None:
    """One turn of the builder state machine.

    If approve=True, writes the last proposal. Otherwise, drafts a new spec.
    Never raises; emits error + done on exception.
    """
    if req.approve:
        _do_approve(req, emit)
        return

    # ── Build system prompt (held in context every turn) ──
    system = _build_system_prompt(req.account_id, mode=req.mode)
    messages_array = _build_messages_array(req.messages)

    # ── Call Claude ──
    claude = get_claude_client()
    if not claude.enabled:
        emit(emit_assistant_message("Agent builder needs ANTHROPIC_API_KEY configured."))
        return

    raw = claude.messages_json_dict_multi(system=system, messages=messages_array, max_tokens=4096)
    draft = BuilderDraft.model_validate(raw or {"reply": _REPHRASE})
    emit(emit_assistant_message(draft.reply or _REPHRASE))

    # ── If no spec proposed, we're done (pure chat turn) ──
    if draft.spec is None:
        return

    # ── Parse the proposed spec ──
    try:
        spec = PipelineSpecDocument.model_validate({**draft.spec, "account_id": req.account_id})
    except ValidationError as exc:
        emit(emit_validation_errors([{
            "code": "spec_parse_error",
            "step_id": None,
            "artifact": None,
            "detail": str(exc),
        }]))
        return

    # ── Validate against the catalog ──
    report = _validate(spec)
    if not report.ok:
        emit(emit_validation_errors([e.model_dump() for e in report.errors]))
        return

    # ── Validation passed: emit the preview ──
    mermaid = _mermaid(spec)
    emit(emit_spec_preview(
        mermaid=mermaid,
        spec=spec.model_dump(mode="json"),
        catalog_hash=tool_catalog_hash(),
        soul_edit=draft.soul_edit.model_dump(exclude_none=True) if draft.soul_edit else None,
    ))


def _do_approve(req: BuilderChatRequest, emit: Callable[[dict], None]) -> None:
    """The approve path: write the last proposal to RavenDB.

    Re-validates before writing (never persist unvalidated specs).
    """
    # ── Extract the last proposal ──
    proposal = req.messages[-1].proposed_spec if req.messages else None
    if not proposal:
        emit(emit_error("Nothing to approve — propose a spec first."))
        return

    # ── Parse and re-validate ──
    try:
        spec = PipelineSpecDocument.model_validate({**proposal, "account_id": req.account_id})
    except ValidationError as exc:
        emit(emit_validation_errors([{
            "code": "spec_parse_error",
            "step_id": None,
            "artifact": None,
            "detail": str(exc),
        }]))
        return

    report = _validate(spec)
    if not report.ok:
        emit(emit_validation_errors([e.model_dump() for e in report.errors]))
        return

    # ── Extract echoed soul edit (if any) ──
    soul_edit = _last_soul_edit(req.messages)
    soul_bumped = False

    # ── Create or edit: write the spec and optionally the soul ──
    if req.mode == "create":
        apply_account_create(_create_body(req.account_id, soul_edit))
        spec.status = "champion"
        soul_bumped = soul_edit is not None
    else:  # edit
        if soul_edit is not None:
            apply_account_update(req.account_id, _update_body(soul_edit))
            soul_bumped = True
        spec.status = "challenger"
        spec.version_hash = None  # force a fresh bump on save

    # ── Save the spec (bumps version in place) ──
    doc_id = _save_spec(spec)

    # ── Save pipeline template specs if pipeline_selections were proposed (create mode) ──
    if req.mode == "create" and soul_edit is not None and soul_edit.pipeline_selections:
        from app.pipeline.runbooks.templates import get_all_template_descriptions
        from app.models.pipeline_spec import default_pipeline_spec
        valid_template_ids = {t["template_id"] for t in get_all_template_descriptions()}
        spec_repo = PipelineSpecRepository()
        for selection in soul_edit.pipeline_selections:
            template_id = selection.get("template_id")
            weight = float(selection.get("weight", 1.0))
            if template_id not in valid_template_ids:
                continue
            template_spec = default_pipeline_spec(req.account_id)
            template_spec.template_id = template_id
            template_spec.weight = weight
            template_spec.status = "active"
            template_spec.name = template_id
            template_spec.version_hash = None  # force fresh version stamp
            spec_repo.save(template_spec)

    emit(emit_spec_written(
        spec_doc_id=doc_id,
        status=spec.status,
        version_label=spec.version_label or "v1",
        soul_bumped=soul_bumped,
        account_id=req.account_id,
    ))


# ── HTTP endpoints (§7.1) ──

async def _sse_builder(req: BuilderChatRequest):
    """Generator that yields SSE frames. Mirrors force_post.py's pattern."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker() -> None:
        try:
            _run_builder_turn(req, emit)
        except Exception as exc:
            logger.exception("Builder turn failed")
            loop.call_soon_threadsafe(queue.put_nowait, emit_error(str(exc)))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, emit_done())
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    loop.run_in_executor(None, worker)

    while True:
        item = await queue.get()
        if item is None:
            break
        yield f"data: {json.dumps(item, default=str)}\n\n"


@router.post("/agent-builder/chat")
async def agent_builder_chat(req: BuilderChatRequest, request: Request):
    """Conversational agent-builder endpoint.

    Accepts text/event-stream for SSE, otherwise returns buffered JSON array.
    """
    accept = (request.headers.get("accept") or "").lower()
    if "text/event-stream" in accept:
        return StreamingResponse(_sse_builder(req), media_type="text/event-stream")

    # ── Non-SSE fallback: buffer events and return as JSON ──
    events: list[dict] = []
    await asyncio.to_thread(_run_builder_turn, req, events.append)
    events.append(emit_done())
    return {"events": events}
