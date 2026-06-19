"""Conversational agent-builder request/response/event shapes (doc 10).

Owns the HTTP contract for POST /api/agent-builder/chat:
- BuilderChatRequest: the client's turn (messages, mode, approval)
- BuilderChatMessage: one turn in the history (role + text + echoed proposal)
- BuilderDraft: what Claude returns (prose reply, optional spec + soul edit)
- SSE event builders: emit helpers for the five event types streamed back
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BuilderChatMessage(BaseModel):
    """One turn in the builder conversation history.

    When role == "assistant" and this message proposed a spec, the client echoes
    the proposed draft + any proposed soul edit + the validation errors it received
    back here, so the next turn's prompt can reference them without a server-side
    session store (mirroring force_post's stateless design).
    """

    role: Literal["user", "assistant"]
    text: str
    # Echoed from the assistant's BuilderDraft when a spec was proposed.
    proposed_spec: dict | None = None
    # Echoed from spec_preview.soul_edit when a soul edit was proposed.
    proposed_soul_edit: dict | None = None
    # Echoed from validation_errors when the proposal failed validation.
    validation_errors: list[dict] | None = None


class BuilderChatRequest(BaseModel):
    """POST /api/agent-builder/chat request.

    The client provides the full message history each turn (stateless server).
    """

    # The account being created or edited.
    account_id: str = Field(min_length=1, max_length=500)
    # "create" provisions a brand-new account; "edit" stages a challenger on a live account.
    mode: Literal["create", "edit"] = "edit"
    # Full message history; each turn the client adds a new user message
    # and echoes the prior assistant's proposals.
    messages: list[BuilderChatMessage] = Field(default_factory=list)
    # When True, this turn does NOT re-draft; it writes the most recent assistant
    # proposed_spec (re-validated first). The client sets approve=True after the user
    # clicks "Approve & write".
    approve: bool = False


class BuilderSoulEdit(BaseModel):
    """Optional soul changes proposed alongside a spec.

    Any subset of these fields; omitted fields are left untouched.
    Maps 1:1 onto AccountUpdateBody and AccountCreateBody.
    """

    posting_prompt: str | None = None
    personality: str | None = None
    contrast_patterns: list | None = None  # list[ContrastPattern]
    punctuation_rules: list | None = None  # list[PunctuationRule]
    category: str | None = None
    pipeline_selections: list[dict] | None = None  # list[{"template_id": str, "weight": float}]


class BuilderDraft(BaseModel):
    """What Claude returns when asked to draft a spec.

    Parsed from the Claude model's response via messages_json_dict (which
    extracts JSON from fenced code blocks or bare braces).
    """

    # Human-readable prose reply (always present; fallback to rephrase on parse fail).
    reply: str = ""
    # A full PipelineSpecDocument-shaped dict, or None when Claude is only chatting.
    # Parsed into PipelineSpecDocument via model_validate before validation.
    spec: dict | None = None
    # Optional soul changes proposed alongside the spec.
    soul_edit: BuilderSoulEdit | None = None
    # Pipeline template selections proposed for create mode.
    # Each entry: {"template_id": str, "weight": float}. Weights should sum to 1.0.
    pipeline_selections: list[dict] | None = None


# ── SSE event builder helpers ──

def emit_assistant_message(text: str) -> dict:
    """Claude's prose reply for this turn (always emitted before any spec handling)."""
    return {"type": "assistant_message", "text": text}


def emit_validation_errors(errors: list[dict]) -> dict:
    """Draft had a spec but validate_spec failed. The repair signal.

    Args:
        errors: list of {code, step_id, artifact, detail} dicts from ValidationError.model_dump()
    """
    return {"type": "validation_errors", "errors": errors}


def emit_spec_preview(
    mermaid: str,
    spec: dict,
    catalog_hash: str,
    soul_edit: dict | None = None,
) -> dict:
    """Draft had a spec and it validated. The approvable proposal.

    Args:
        mermaid: flowchart LR mermaid diagram string.
        spec: PipelineSpecDocument as a dict.
        catalog_hash: tool_catalog_hash() — stamps which catalog this validates against.
        soul_edit: optional BuilderSoulEdit.model_dump(exclude_none=True), or None.
    """
    return {
        "type": "spec_preview",
        "mermaid": mermaid,
        "spec": spec,
        "catalog_hash": catalog_hash,
        "soul_edit": soul_edit,
    }


def emit_spec_written(
    spec_doc_id: str,
    status: Literal["champion", "challenger"],
    version_label: str,
    soul_bumped: bool,
    account_id: str,
) -> dict:
    """The approve path persisted the spec (and optionally bumped the soul).

    Args:
        spec_doc_id: PipelineSpecDocument.document_id() (the RavenDB id).
        status: "champion" (create) or "challenger" (edit).
        version_label: spec.version_label after save().
        soul_bumped: whether the soul was edited/updated.
        account_id: the account that was modified.
    """
    return {
        "type": "spec_written",
        "spec_doc_id": spec_doc_id,
        "status": status,
        "version_label": version_label,
        "soul_bumped": soul_bumped,
        "account_id": account_id,
    }


def emit_error(message: str) -> dict:
    """A hard failure (Claude client raised, write raised, nothing-to-approve).

    Terminal for the turn (followed by done).
    """
    return {"type": "error", "message": message}


def emit_done() -> dict:
    """Always the last frame of every turn. Signals completion."""
    return {"type": "done"}
