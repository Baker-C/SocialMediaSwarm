"""Persona-design chat request/response/event shapes (doc 03).

Owns the HTTP contract for POST /api/persona/chat:
- PersonaChatRequest: the client's turn (account_id, messages, echoed proposal, approval)
- PersonaChatMessage: one turn in the history (role + content)
- PersonaSpec: the structured identity Claude proposes (operator-editable)
- PersonaDraft: what Claude returns (prose reply + optional spec)
- SSE event builders: emit helpers for the event types streamed back

Near-clone of agent_builder_types.py; deviates only in the draft schema and events.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PersonaChatMessage(BaseModel):
    """One turn in the persona-design conversation history."""

    role: Literal["user", "assistant"]
    content: str


class PersonaSpec(BaseModel):
    """The structured identity Claude proposes; all fields operator-editable in the UI.

    Field names mirror the soul vocabulary so the spec maps cleanly onto
    AccountCreateBody / AccountUpdateBody and AccountProvisioning.
    """

    handle: str = ""            # @handle (no '@'); availability checked at signup, not here
    display_name: str = ""
    bio: str = ""
    category: str = ""          # -> AccountSoul.category
    personality: str = ""       # -> AccountSoul.personality
    posting_prompt: str = ""    # -> AccountSoul.posting_prompt
    avatar_prompt: str = ""     # -> fal image gen (04)
    header_prompt: str = ""     # -> fal image gen (04)


class PersonaChatRequest(BaseModel):
    """POST /api/persona/chat request.

    The client provides the full message history each turn (stateless server)
    and echoes the prior assistant's proposal back so the next turn can reference it.
    """

    account_id: str = Field(min_length=1, max_length=500)
    messages: list[PersonaChatMessage] = Field(default_factory=list)
    # The prior proposal echoed back; on approve, this is what gets written.
    proposal: "PersonaSpec | None" = None
    # When True, this turn does NOT re-draft; it generates images + writes the account.
    approve: bool = False


class PersonaDraft(BaseModel):
    """What Claude returns when asked to design a persona.

    Parsed from the model's response via messages_json_dict (which extracts JSON
    from fenced code blocks or bare braces). Defensive: every field has a default
    so model_validate({}) never raises.
    """

    reply: str = ""                   # assistant's chat message
    spec: PersonaSpec | None = None   # present once enough is known to propose


# ── SSE event builder helpers ──

def emit_assistant_message(text: str) -> dict:
    """Claude's prose reply for this turn (always emitted before any spec handling)."""
    return {"type": "assistant_message", "text": text}


def emit_persona_preview(spec: PersonaSpec) -> dict:
    """Draft proposed a spec. The right-pane review payload (approvable proposal)."""
    return {"type": "persona_preview", "spec": spec.model_dump(mode="json")}


def emit_images_generating() -> dict:
    """Approve path started fal image generation (avatar + header)."""
    return {"type": "images_generating"}


def emit_images_ready(avatar_asset_id: str, header_asset_id: str) -> dict:
    """Approve path finished image generation; asset ids are servable by the frontend."""
    return {
        "type": "images_ready",
        "avatar_asset_id": avatar_asset_id,
        "header_asset_id": header_asset_id,
    }


def emit_account_written(account_id: str) -> dict:
    """Approve path wrote the account + AccountProvisioning(status="draft")."""
    return {"type": "account_written", "account_id": account_id}


def emit_validation_errors(errors: list[str]) -> dict:
    """Approve path could not proceed (e.g. nothing to approve)."""
    return {"type": "validation_errors", "errors": errors}


def emit_error(message: str) -> dict:
    """A hard failure (Claude raised, image gen raised, duplicate account id).

    Terminal for the turn (followed by done).
    """
    return {"type": "error", "message": message}


def emit_done() -> dict:
    """Always the last frame of every turn. Signals completion."""
    return {"type": "done"}
