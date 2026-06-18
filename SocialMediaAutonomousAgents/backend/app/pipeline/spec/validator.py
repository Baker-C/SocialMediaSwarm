"""Pure validator for pipeline specs (doc 05).

validate_spec(doc, catalog) -> ValidationReport

Validates a spec against the tool catalog without I/O, services, or engine.
All seven rules run and report every error (no early exit).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.pipeline.spec.internal_primitives import is_internal
from app.pipeline.types.artifacts import ArtifactKey

if TYPE_CHECKING:
    from app.pipeline.spec.catalog import ToolCatalog


class ValidationError(BaseModel):
    """One validation error with stable machine code."""

    code: str
    step_id: str | None = None
    artifact: str | None = None
    detail: str = ""


class ValidationReport(BaseModel):
    """Summary of validation results."""

    ok: bool
    errors: list[ValidationError] = []

    def codes(self) -> list[str]:
        """Return the list of error codes."""
        return [e.code for e in self.errors]


# ── Accessor helpers (§3.3) ──
# These are the only place sibling-doc field names appear.
# Rename here = one-line change to adapt to doc 03/04 field renames.


def _step_kind(node) -> str:
    """Normalize doc 04 leaf discriminant "step" to internal "leaf"."""
    k = node.kind
    return "leaf" if k == "step" else k  # "parallel" / "chain" pass through


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
    """Adapter for catalog lookup (doc 03's ToolCatalog.get)."""
    return catalog.get(tool_id)


# ── Type checking for config values ──


def _param_type(p) -> str:
    """Normalize annotation string to checkable type name."""
    ann = (p.annotation or "").replace("| None", "").replace("|None", "").strip().lower()
    return {
        "int": "int",
        "float": "float",
        "str": "str",
        "bool": "bool",
        "list[str]": "list[str]",
        "list": "list[str]",
        "dict": "dict",
        "dict[str, any]": "dict",
    }.get(ann, "")


_PY_TYPE = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "list[str]": list,
    "dict": dict,
}


def _typecheck(raw, type_name: str) -> bool:
    """Type-check a config value against a type name."""
    if not type_name:
        return True  # annotation we don't model → don't reject
    py = _PY_TYPE.get(type_name)
    if py is None:
        return True
    # bool IS an int in Python; reject bool where int/float expected
    if type_name in ("int", "float") and isinstance(raw, bool):
        return False
    if not isinstance(raw, py):
        return False
    if type_name == "list[str]":
        return all(isinstance(x, str) for x in raw)
    return True


# ── Flatten spec leaves (mirrors flow.flatten_steps) ──


def _flatten_spec_leaves(
    steps: list, parent_id: str | None = None
) -> list[tuple[str, object]]:
    """Flatten spec tree to (dotted_id, node) pairs for leaves only."""
    out: list[tuple[str, object]] = []
    for node in steps:
        full_id = f"{parent_id}.{node.id}" if parent_id else node.id
        if _step_kind(node) == "leaf":
            out.append((full_id, node))
        else:
            out.extend(_flatten_spec_leaves(_step_children(node), full_id))
    return out


# ── Rule implementations ──


def _check_unknown_tools(
    flat: list[tuple[str, object]], catalog: ToolCatalog
) -> list[ValidationError]:
    """R1: Every leaf's tool_id exists in catalog or is _internal.*."""
    errors: list[ValidationError] = []
    for dotted_id, node in flat:
        tool_id = _step_tool_id(node)
        if tool_id is None:
            errors.append(
                ValidationError(
                    code="missing_tool_id",
                    step_id=dotted_id,
                    detail="Step has no tool_id",
                )
            )
        elif not is_internal(tool_id) and tool_id not in catalog:
            errors.append(
                ValidationError(
                    code="unknown_tool",
                    step_id=dotted_id,
                    detail=f"Unknown tool: {tool_id!r}",
                )
            )
    return errors


def _check_config_types(
    flat: list[tuple[str, object]], catalog: ToolCatalog
) -> list[ValidationError]:
    """R2: Config values type-check; unknown/non-proposable keys are flagged."""
    errors: list[ValidationError] = []
    for dotted_id, node in flat:
        tool_id = _step_tool_id(node)
        cfg = _step_config(node)

        # Skip if no config or tool is unknown (already reported by R1)
        if not cfg:
            continue
        if tool_id is None or (not is_internal(tool_id) and tool_id not in catalog):
            continue

        # Internal tools have no proposable config
        if is_internal(tool_id):
            for key in cfg.keys():
                errors.append(
                    ValidationError(
                        code="config_unknown_key",
                        step_id=dotted_id,
                        detail=f"Internal tool {tool_id!r} has no proposable config; key {key!r} is not allowed",
                    )
                )
            continue

        # Check proposable params from catalog
        tool_doc = _tool(catalog, tool_id)
        props = {p.name: p for p in (tool_doc.proposable_params or [])} if tool_doc else {}

        for key, raw in cfg.items():
            if key not in props:
                errors.append(
                    ValidationError(
                        code="config_unknown_key",
                        step_id=dotted_id,
                        detail=f"Config key {key!r} is not proposable for tool {tool_id!r}",
                    )
                )
                continue

            param = props[key]
            type_name = _param_type(param)
            if not _typecheck(raw, type_name):
                errors.append(
                    ValidationError(
                        code="config_type_mismatch",
                        step_id=dotted_id,
                        detail=f"Config {key!r} value {raw!r} does not match type {type_name!r}",
                    )
                )

        # Check for missing required proposable fields
        for key, param in props.items():
            if param.required and key not in cfg and param.default is None:
                errors.append(
                    ValidationError(
                        code="config_missing_required",
                        step_id=dotted_id,
                        detail=f"Required config field {key!r} is missing",
                    )
                )

    return errors


def _check_dangling_reads(flat: list[tuple[str, object]]) -> list[ValidationError]:
    """R3: Every leaf reads only artifacts in union of upstream writes."""
    errors: list[ValidationError] = []
    produced: set[str] = set()

    # Track valid artifact keys for existence check
    valid_keys = {k.value for k in ArtifactKey}

    for dotted_id, node in flat:
        reads = _step_reads(node)
        reads_opt = set(_step_reads_optional(node))

        for r in reads:
            # Check if artifact key exists
            if r not in valid_keys:
                errors.append(
                    ValidationError(
                        code="dangling_read",
                        step_id=dotted_id,
                        artifact=r,
                        detail=f"Reads unknown artifact {r!r}",
                    )
                )
                continue

            # Check if produced by upstream step (or optional)
            if r not in produced and r not in reads_opt:
                errors.append(
                    ValidationError(
                        code="dangling_read",
                        step_id=dotted_id,
                        artifact=r,
                        detail=f"Reads {r!r} but no upstream step writes it",
                    )
                )

        # Add writes to produced set for next iterations
        writes = _step_writes(node)
        produced.update(writes)

    return errors


def _check_no_cycles(flat: list[tuple[str, object]]) -> list[ValidationError]:
    """R4: No artifact dependency cycle (catches forward references)."""
    errors: list[ValidationError] = []

    # Build producer index: first step that writes each artifact
    first_writer: dict[str, int] = {}
    for idx, (_, node) in enumerate(flat):
        for w in _step_writes(node):
            if w not in first_writer:
                first_writer[w] = idx

    # Check for forward references (artifact only written by self-or-later)
    for idx, (dotted_id, node) in enumerate(flat):
        reads = _step_reads(node)
        for r in reads:
            writer_idx = first_writer.get(r, float("inf"))
            if writer_idx >= idx:  # writer is self or later
                errors.append(
                    ValidationError(
                        code="cycle",
                        step_id=dotted_id,
                        artifact=r,
                        detail=f"Reads {r!r} but only self or later steps produce it",
                    )
                )

    return errors


def _check_unique_ids(flat: list[tuple[str, object]]) -> list[ValidationError]:
    """R5: Dotted leaf ids are unique."""
    errors: list[ValidationError] = []
    seen: set[str] = set()

    for dotted_id, _ in flat:
        if dotted_id in seen:
            errors.append(
                ValidationError(
                    code="duplicate_step_id",
                    step_id=dotted_id,
                    detail=f"Duplicate step id: {dotted_id!r}",
                )
            )
        seen.add(dotted_id)

    return errors


def _check_terminal_published(
    flat: list[tuple[str, object]], terminal_key: str
) -> list[ValidationError]:
    """R6: Exactly one terminal step writes the terminal artifact key, and it is last.

    terminal_key is the artifact (e.g., "published_post" for posts, "reply_result" for replies).
    """
    errors: list[ValidationError] = []

    # Find all leaves that write the terminal artifact
    publishers: list[int] = []
    for idx, (_, node) in enumerate(flat):
        if terminal_key in _step_writes(node):
            publishers.append(idx)

    if not publishers:
        errors.append(
            ValidationError(
                code="no_terminal_published",
                step_id=None,
                detail=f"No step writes {terminal_key}",
            )
        )
        return errors

    # Terminal publisher must be the last leaf
    terminal_idx = publishers[-1]
    if terminal_idx != len(flat) - 1:
        # Find the leaf that comes after publish
        for idx in range(terminal_idx + 1, len(flat)):
            dotted_id, _ = flat[idx]
            errors.append(
                ValidationError(
                    code="step_after_publish",
                    step_id=dotted_id,
                    detail=f"Step {dotted_id!r} executes after publishing",
                )
            )

    return errors


def _check_invariants_present(
    flat: list[tuple[str, object]], catalog: ToolCatalog, verdict_key: str, terminal_key: str
) -> list[ValidationError]:
    """R7: Guardian and publish tools are present and not bypassed (by artifact writes).

    verdict_key is the verdict artifact (e.g., "safety_verdict" for posts, "reply_verdict" for replies).
    terminal_key is the terminal artifact (e.g., "published_post" for posts, "reply_result" for replies).
    """
    errors: list[ValidationError] = []

    # Check for safety guardian: at least one leaf whose catalog tool writes the verdict artifact
    has_safety = False
    for _, node in flat:
        tool_id = _step_tool_id(node)
        if is_internal(tool_id) or not tool_id:
            continue
        tool_doc = _tool(catalog, tool_id)
        if tool_doc and tool_doc.writes and verdict_key in tool_doc.writes:
            has_safety = True
            break

    if not has_safety:
        errors.append(
            ValidationError(
                code="missing_safety_invariant",
                step_id=None,
                detail=f"No step writes {verdict_key} (missing guardian-bearing compose tool)",
            )
        )

    # Check for publish invariant: terminal writer must be catalog tool
    # that statically declares the terminal artifact in its writes
    for idx, (dotted_id, node) in enumerate(flat):
        if terminal_key not in _step_writes(node):
            continue
        # This writes the terminal artifact; check if it's the last one
        is_terminal = not any(
            terminal_key in _step_writes(flat[j][1])
            for j in range(idx + 1, len(flat))
        )
        if not is_terminal:
            continue

        # Terminal publisher: verify it's from catalog with static terminal write
        tool_id = _step_tool_id(node)
        if is_internal(tool_id) or not tool_id or tool_id not in catalog:
            errors.append(
                ValidationError(
                    code="missing_publish_invariant",
                    step_id=dotted_id,
                    detail=f"Terminal {terminal_key} writer {tool_id!r} is not a catalog tool with static {terminal_key} write",
                )
            )
            break

        tool_doc = _tool(catalog, tool_id)
        if not tool_doc or not tool_doc.writes or terminal_key not in tool_doc.writes:
            errors.append(
                ValidationError(
                    code="missing_publish_invariant",
                    step_id=dotted_id,
                    detail=f"Terminal {terminal_key} writer {tool_id!r} does not statically declare {terminal_key}",
                )
            )
            break

    return errors


def validate_spec(doc, catalog: ToolCatalog, *, kind: str = "post") -> ValidationReport:
    """Validate a spec against the catalog, returning all errors.

    catalog is doc 03's ToolCatalog object (CC-1), looked up via
    catalog.get(tool_id) / `tool_id in catalog`.

    kind selects the family: "post" (default) or "reply" (doc 12). Determines which
    terminal/verdict artifacts R6/R7 check for.

    Returns ValidationReport with ok=True iff no errors.
    """
    # Map kind to (verdict_key, terminal_key) for R6/R7
    _KIND_TERMINALS = {
        "post": (ArtifactKey.SAFETY_VERDICT.value, ArtifactKey.PUBLISHED_POST.value),
        "reply": (ArtifactKey.REPLY_VERDICT.value, ArtifactKey.REPLY_RESULT.value),
    }
    if kind not in _KIND_TERMINALS:
        return ValidationReport(
            ok=False,
            errors=[
                ValidationError(
                    code="invalid_kind",
                    step_id=None,
                    detail=f"Unknown kind {kind!r}; must be one of {list(_KIND_TERMINALS.keys())}",
                )
            ],
        )

    verdict_key, terminal_key = _KIND_TERMINALS[kind]

    flat = _flatten_spec_leaves(doc.steps)
    errors: list[ValidationError] = []

    errors += _check_unknown_tools(flat, catalog)
    errors += _check_config_types(flat, catalog)
    errors += _check_dangling_reads(flat)
    errors += _check_no_cycles(flat)
    errors += _check_unique_ids(flat)
    errors += _check_terminal_published(flat, terminal_key)
    errors += _check_invariants_present(flat, catalog, verdict_key, terminal_key)

    return ValidationReport(ok=not errors, errors=errors)
