"""Tool catalog introspection — builds ToolCatalogDocument entries from six SENSE tools."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any, Callable

from app.models.tool_catalog import ConfigOrigin, ToolCatalogDocument, ToolParameter, config_type
from app.pipeline.tools.data import account_profile, own_posts_fetch, search_fetch
from app.pipeline.tools.deterministic import reference_rank
from app.pipeline.tools.llm import compose_timeline_post, reference_pattern_summary

# Optional imports for doc 12 reply tools (imported with guard for pre-doc-12):
try:
    from app.pipeline.tools.data import mentions_fetch, reply_publish
    from app.pipeline.tools.llm import reply_compose
    _REPLY_TOOLS = (mentions_fetch, reply_compose, reply_publish)
except ImportError:
    _REPLY_TOOLS = ()

# Order is the catalog's canonical order (stable hash input).
_TOOL_MODULES = (
    account_profile,
    search_fetch,
    own_posts_fetch,
    reference_rank,
    reference_pattern_summary,
    compose_timeline_post,
) + _REPLY_TOOLS

# Parameter NAME -> the live dep it is injected from.
# These are NEVER proposable; the engine wires them around every leaf.
# Present on PostRunDeps (deps.py:18-22) and forward-looking (doc 06 extension).
ENGINE_INJECTED_DEPS: dict[str, str] = {
    # ── present on PostRunDeps today (deps.py:18-22) ──
    "tick_data": "PostRunDeps.tick_data",  # TickDataService (composite)
    "repo": "PostRunDeps.repo",  # AccountRepository
    "post_registry": "PostRunDeps.post_registry",  # TrackedPostRepository | None
    "pulled_tweets": "PostRunDeps.pulled_tweets",  # PulledTweetRepository | None
    "twitter": "PostRunDeps.twitter",  # TwitterService | None
    # ── added by doc 06's PostRunDeps extension (NOT on today's dataclass) ──
    "guardian": "PostRunDeps.guardian",  # SafetyGuardian — arrives via deps.guardian (doc 06)
}

# Names the ENGINE supplies from the live tick, not from a spec literal and not a dep object.
RUNTIME_SUPPLIED: frozenset[str] = frozenset({"account_id", "slot", "niche"})

# Names the WRAPPER derives from upstream artifacts/context (an LLM may NOT set these).
WIRED_FROM_CONTEXT: frozenset[str] = frozenset({
    "rows",
    "top_posts",
    "winner",
    "queries",
    "features",
    "authenticated_user_id",
    "exclude_ids",
    "store_key",
    "source",
    "reference_context_block",
    "regeneration_round",
    "safety_reject_reason",
})


def _introspect_param(p: inspect.Parameter) -> ToolParameter:
    """Classify one parameter into kind/config_origin."""
    name = p.name
    annotation = "" if p.annotation is inspect._empty else str(p.annotation)
    required = p.default is inspect._empty
    default = None if p.default is inspect._empty else p.default

    if name in ENGINE_INJECTED_DEPS:
        kind = "injected"
        origin: ConfigOrigin = "injected"
    elif name in RUNTIME_SUPPLIED:
        kind = "config"
        origin = "runtime"
    elif name in WIRED_FROM_CONTEXT:
        kind = "config"
        origin = "wired"
    else:
        kind = "config"
        origin = "literal"  # the genuinely LLM-tunable scalars

    return ToolParameter(
        name=name,
        annotation=annotation,
        required=required,
        default=_json_safe(default),
        kind=kind,  # type: ignore
        config_origin=origin,
    )


def _json_safe(value: Any) -> Any:
    """Coerce defaults to JSON-storable values."""
    if value is inspect._empty:
        return None
    if isinstance(value, frozenset):
        return list(value)
    if callable(value):
        return value.__name__
    return value


def _introspect(m: Any) -> ToolCatalogDocument:
    """Introspect one tool module into a ToolCatalogDocument."""
    run = getattr(m, "run", None)
    if not callable(run):
        raise ValueError(f"Catalog module {m.__name__} has no run()")

    sig = inspect.signature(run)
    params = list(sig.parameters.values())
    if not params or params[0].name != "ctx":
        raise ValueError(f"{m.__name__}.run must take ctx first")

    tool_id = getattr(m, "TOOL_ID", m.__name__)
    kind = getattr(m, "TOOL_KIND", "")
    purpose = getattr(m, "TOOL_PURPOSE", "")
    source = getattr(m, "TOOL_SOURCE", None)
    prompt_stem = getattr(m, "PROMPT_STEM", None)

    output_model = getattr(m, "OUTPUT_MODEL", None)
    output_model_name = output_model.__name__ if output_model is not None else None

    writes_const = getattr(m, "TOOL_WRITES", None)  # tuple[ArtifactKey] | None
    writes = [k.value for k in writes_const] if writes_const else None  # None ⇒ dynamic

    reads_const = getattr(m, "TOOL_READS", None)  # tuple[ArtifactKey] | None
    reads = [k.value for k in reads_const] if reads_const is not None else None  # None ⇒ dynamic

    # Skip ctx (always first) AND a literal `deps` param (doc 06 ACT tools take ctx+deps;
    # the SENSE tools have no `deps` param, so this skip is a no-op for them and correctly
    # empties the ACT tools' surface).
    rest = [p for p in params[1:] if p.name != "deps"]
    parameters = [_introspect_param(p) for p in rest]

    return ToolCatalogDocument(
        tool_id=tool_id,
        kind=kind,
        purpose=purpose,
        source=source,
        prompt_stem=prompt_stem,
        output_model=output_model_name,
        writes=writes,
        reads=reads,
        parameters=parameters,
    )


def build_tool_catalog() -> list[ToolCatalogDocument]:
    """Build the complete tool catalog from _TOOL_MODULES.

    INTERNAL: raw list, _TOOL_MODULES order (used to construct ToolCatalog).
    Callers consume the catalog object, not this list directly.
    """
    return [_introspect(m) for m in _TOOL_MODULES]


def get_tool(tool_id: str) -> ToolCatalogDocument | None:
    """Convenience free function to retrieve a tool from the default catalog."""
    return get_tool_catalog().get(tool_id)


def tool_catalog_hash() -> str:
    """SHA256 hash of the tool catalog (mirror of voice_version_service.compute_voice_hash).

    Canonical JSON (sorted keys) so a spec can stamp the catalog version it validated against.
    Hash changes whenever tool id, kind, output model, reads, writes, or any parameter changes.
    """
    payload = [d.model_dump(mode="json") for d in build_tool_catalog()]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# The wrapper that actually runs for each tool_id. Verified: every runbook leaf is a
# steps.py wrapper of shape (ctx, deps) -> StepResult, exactly one per tool_id today.
# For shared tools (reference_rank, reference_pattern_summary), run_for returns None
# and the compiler resolves the wrapper per-step (carries resolved store_key).
from app.pipeline.services import steps

_TOOL_RUN: dict[str, Callable | None] = {
    "data.account_profile": steps.load_account_bundle,
    "data.search_fetch": steps.fetch_search_references,
    "data.own_posts_fetch": steps.fetch_own_post_history,
    "deterministic.reference_rank": None,  # shared by 2+ steps → resolved per-step by compiler
    "llm.reference_pattern_summary": None,  # shared by 2 steps → likewise
    "llm.compose_timeline_post": None,  # informational only; never spec-wired (§4.3a)
    # doc 06 adds: "llm.compose_until_safe": steps.compose_step,
    #              "data.publish_post":      steps.publish_step,
    # doc 12 adds (reply pipeline):
    "data.mentions_fetch": getattr(steps, "fetch_mentions", None),
    "llm.reply_compose": getattr(steps, "reply_compose_step", None),
    "data.reply_publish": getattr(steps, "reply_publish_step", None),
}


class ToolCatalog:
    """The lookup OBJECT docs 05 (validator/compiler) and 10 (builder) consume.

    Docs 05/10 were authored against `catalog.get(tool_id)` / `tool_id in catalog`,
    returning a single entry — NOT the raw list `build_tool_catalog()` returns.
    This thin wrapper IS that object.
    """

    def __init__(self, tools: list[ToolCatalogDocument] | None = None) -> None:
        """Initialize from a tool list (or build from _TOOL_MODULES if None)."""
        self._by_id = {
            t.tool_id: t for t in (tools if tools is not None else build_tool_catalog())
        }

    def get(self, tool_id: str) -> ToolCatalogDocument | None:
        """Retrieve a tool entry by tool_id, or None if not found."""
        return self._by_id.get(tool_id)

    def __contains__(self, tool_id: str) -> bool:
        """Check membership: 'tool_id' in catalog."""
        return tool_id in self._by_id

    def all(self) -> list[ToolCatalogDocument]:
        """Return all tools in _TOOL_MODULES order."""
        return list(self._by_id.values())

    def run_for(self, tool_id: str) -> Callable | None:
        """The bound (ctx, deps) -> StepResult wrapper for a tool_id, or None.

        Returns None when the tool is shared across steps (compiler resolves per-step).
        """
        return _TOOL_RUN.get(tool_id)


# Module-level singleton (lazily built, cheap, pure).
_default_catalog: ToolCatalog | None = None


def get_tool_catalog() -> ToolCatalog:
    """Module-level default catalog object. Built fresh from code (cheap, pure).

    This is the symbol doc 05's compiler defaults its `catalog` arg to, and doc 10's
    builder `_load_catalog()` returns. `validate_spec(doc, get_tool_catalog())`.
    """
    global _default_catalog
    if _default_catalog is None:
        _default_catalog = ToolCatalog()
    return _default_catalog
