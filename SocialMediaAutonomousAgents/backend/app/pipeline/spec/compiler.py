"""Pure compiler: spec → Step tree (doc 05).

compile_spec(doc, *, catalog=None) -> tuple[Step, ...]

Lowers a validated spec into the Step tree using chain()/parallel() helpers,
reproducing the exact flatten_steps dotted-id scheme the frontend couples to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.pipeline.spec.internal_primitives import INTERNAL_PRIMITIVES, is_internal
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.flow import Step, chain, parallel

if TYPE_CHECKING:
    from app.pipeline.spec.catalog import ToolCatalog


# ── Accessor helpers (same as validator.py) ──


def _step_kind(node) -> str:
    k = node.kind
    return "leaf" if k == "step" else k


def _step_tool_id(node) -> str | None:
    return getattr(node, "tool_id", None)


def _step_children(node) -> list:
    return getattr(node, "children", []) or []


def _step_config(node) -> dict:
    return getattr(node, "config", {}) or {}


def _step_reads(node) -> list[str]:
    return getattr(node, "reads", []) or []


def _step_writes(node) -> list[str]:
    return getattr(node, "writes", []) or []


def _step_reads_optional(node) -> list[str]:
    return getattr(node, "reads_optional", []) or []


def _tool(catalog: ToolCatalog, tool_id: str):
    return catalog.get(tool_id)


# ── Config threading through context ──

_STEP_CONFIG_PREFIX = "_step_config:"  # reserved ctx.data namespace


# ── Step ID ↔ wrapper mapping ──


def _import_tool_catalog():
    """Lazy import to avoid circular deps."""
    from app.pipeline.spec.catalog import get_tool_catalog

    return get_tool_catalog


def _wrapper_by_step_id_entry(step_id: str) -> tuple[str, object] | None:
    """Look up wrapper by step id; returns (expected_tool_id, callable) or None."""
    # This is keyed by runbook step id (verified against services/steps.py)
    # to distinguish steps sharing a tool_id (rank_external_references vs rank_own_posts).
    from app.pipeline.services import steps

    mapping = {
        "load_account_bundle": ("data.account_profile", steps.load_account_bundle),
        "fetch_search_references": ("data.search_fetch", steps.fetch_search_references),
        "collect_external_references": (
            "_internal.collect_external",
            steps.collect_external_references,
        ),
        "fetch_own_post_history": ("data.own_posts_fetch", steps.fetch_own_post_history),
        "rank_external_references": (
            "deterministic.reference_rank",
            steps.rank_external_references,
        ),
        "brief_external_references": (
            "llm.reference_pattern_summary",
            steps.brief_external_references,
        ),
        "rank_own_posts": ("deterministic.reference_rank", steps.rank_own_posts),
        "brief_own_posts": ("llm.reference_pattern_summary", steps.brief_own_posts),
        # ACT tail (doc 06 adds these; getattr-guarded for pre-doc-06):
        "compose_until_safe": (
            "llm.compose_until_safe",
            getattr(steps, "compose_step", None),
        ),
        "publish_post": ("data.publish_post", getattr(steps, "publish_step", None)),
        # Reply pipeline (doc 12 adds these; getattr-guarded for pre-doc-12):
        "fetch_mentions": ("data.mentions_fetch", getattr(steps, "fetch_mentions", None)),
        "rank_mentions": (
            "deterministic.reference_rank",
            getattr(steps, "rank_mentions", None),
        ),
        "reply_compose": ("llm.reply_compose", getattr(steps, "reply_compose_step", None)),
        "reply_publish": ("data.reply_publish", getattr(steps, "reply_publish_step", None)),
    }
    return mapping.get(step_id)


def _wrapper_for(node) -> object:
    """Bind the wrapper callable for a leaf node (§6.0 / §6.2)."""
    tool_id = _step_tool_id(node)

    # CC-8: _internal.* leaf → bind from INTERNAL_PRIMITIVES
    if is_internal(tool_id):
        return INTERNAL_PRIMITIVES[tool_id]["run"]

    # Runbook step id → wrapper
    step_id = node.id
    entry = _wrapper_by_step_id_entry(step_id)
    if not entry:
        raise ValueError(f"no wrapper mapping for step {step_id!r} (tool {tool_id!r})")

    expected, wrapper = entry
    if expected != tool_id:
        raise ValueError(
            f"step {step_id!r} maps to {expected!r}, spec says {tool_id!r}"
        )

    cfg = _step_config(node)
    if not cfg:
        return wrapper  # empty config → verbatim wrapper

    # Non-empty config: wrap to thread through ctx.data
    key = _STEP_CONFIG_PREFIX + tool_id

    def _run(ctx, deps):
        ctx.data[key] = dict(cfg)
        try:
            return wrapper(ctx, deps)
        finally:
            ctx.data.pop(key, None)

    return _run


def _keys(values: list[str]) -> tuple[ArtifactKey, ...]:
    """Lift spec artifact key strings back to enum members."""
    return tuple(ArtifactKey(v) for v in values)


def _compile_node(node, cat: ToolCatalog) -> Step:
    """Recursively compile a spec node (leaf or composite) into a Step."""
    kind = _step_kind(node)

    if kind == "leaf":
        tool_id = _step_tool_id(node)
        run = _wrapper_for(node)
        tool_doc = cat.get(tool_id) if tool_id and not is_internal(tool_id) else None

        return Step(
            id=node.id,
            run=run,
            reads=_keys(_step_reads(node)),
            writes=_keys(_step_writes(node)),
            reads_optional=frozenset(_keys(_step_reads_optional(node))),
            purpose=node.purpose or (tool_doc.purpose if tool_doc else ""),
            composite_kind="leaf",
        )

    # Composite: recurse on children
    children = tuple(_compile_node(c, cat) for c in _step_children(node))

    if kind == "parallel":
        return parallel(*children, id=node.id, purpose=node.purpose)

    return chain(*children, id=node.id, purpose=node.purpose)


def compile_spec(doc, *, catalog: ToolCatalog | None = None) -> tuple[Step, ...]:
    """Lower a validated spec into Step tree.

    catalog defaults to get_tool_catalog() (CC-1: single factory) when None.
    Returns tuple[Step, ...] for the top-level steps (leaf or composite).
    """
    if catalog is None:
        catalog = _import_tool_catalog()()

    return tuple(_compile_node(n, catalog) for n in doc.steps)
