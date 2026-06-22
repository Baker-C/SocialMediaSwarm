"""Conversational persona-design API (doc 03).

POST /api/persona/chat — a multi-turn SSE endpoint that designs an X account
persona, returns a structured editable spec, and on approval generates avatar +
header images and writes the account + AccountProvisioning(status="draft").

POST /api/persona/regenerate-images — regenerate avatar/header before approving.

Near-clone of agent_builder.py: same stateless multi-turn (full history echoed
each turn, flattened by _render_messages), same worker/queue/SSE pattern with a
buffered JSON fallback, same prompt-for-JSON structured output. Deviates only in
the draft schema and the approve side-effects (images + provisioning sub-doc).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.routes.persona_types import (
    PersonaChatMessage,
    PersonaChatRequest,
    PersonaDraft,
    PersonaSpec,
    emit_account_written,
    emit_assistant_message,
    emit_done,
    emit_error,
    emit_images_generating,
    emit_images_ready,
    emit_persona_preview,
    emit_validation_errors,
)
from app.infrastructure.claude_client import ClaudeClient
from app.models.niche import Niche
from app.pipeline.runbooks.templates import get_offerable_template_descriptions
from app.services.account_create_service import (
    AccountAlreadyExistsError,
    AccountCreateBody,
    apply_account_create,
)
from app.models.account import AccountDocument
from app.models.account_secrets import AccountSecretsDocument
from app.services.account_repository import AccountRepository
from app.services.account_secrets_service import AccountSecretsService
from app.services.persona_image_service import (
    generate_persona_image,
    generate_persona_images,
)
from app.services.pipeline_spec_repository import seed_active_pipelines

logger = logging.getLogger(__name__)

router = APIRouter()

# Project default for this feature is opus-4-8 (the configured default is sonnet).
claude = ClaudeClient(model="claude-opus-4-8")

repo = AccountRepository()
secrets = AccountSecretsService()

_REPHRASE = "Tell me more about the account — niche, audience, voice, name."

# Catalog of posting pipelines the LLM may choose 1-3 from (validate-clean subset).
_PIPELINE_CATALOG = "\n".join(
    f"  - {t['template_id']}: {t['description']}" for t in get_offerable_template_descriptions()
)
_PIPELINE_IDS = ", ".join(t["template_id"] for t in get_offerable_template_descriptions())

SYSTEM_PROMPT = (
    "You design X (Twitter) account personas. Converse with the operator to nail down the "
    "niche, audience, voice, name and bio. Ask questions until you and the operator are on the "
    "same page. Also discuss the account's VISUAL identity — what the profile picture (avatar) "
    "and banner (header) should look like — and capture that in avatar_prompt / header_prompt.\n\n"
    "Every account runs 1-3 POSTING PIPELINES and rotates between them so it can post in "
    "different ways. Pick the 1-3 that best fit the persona from this catalog:\n"
    + _PIPELINE_CATALOG
    + "\n\nWhen you have enough, return JSON:\n"
    '{"reply": "<message>", "spec": {"handle","display_name","bio","category","personality",'
    '"posting_prompt","niches","pipelines","avatar_prompt","header_prompt"} | null}. '
    "When you are only chatting or clarifying, set spec to null. Keep handle <=15 chars, "
    "alphanumeric/underscore (no '@').\n"
    'category is the account\'s kind in a few words (e.g. "Global News Commentary") — always set it.\n'
    'niches is a NON-EMPTY array of short topic strings the account rides (e.g. ["Trump news", "political scandals"]).\n'
    "pipelines is an array of 1-3 ids chosen from: " + _PIPELINE_IDS + ".\n"
    "avatar_prompt/header_prompt are vivid image-gen prompts (square avatar, wide banner)."
)


def _render_messages(history: list[PersonaChatMessage], proposal: PersonaSpec | None) -> str:
    """Flatten the message history into a single user turn for Claude.

    Echoes the prior proposal so the model can refine it across turns (stateless server).
    """
    lines: list[str] = []
    for msg in history:
        prefix = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{prefix}: {msg.content}")
    if proposal is not None:
        lines.append("Current proposed persona (refine it as the conversation evolves):")
        lines.append(json.dumps(proposal.model_dump(mode="json"), indent=2))
    return "\n".join(lines)


def _run_turn(req: PersonaChatRequest, emit: Callable[[dict], None]) -> None:
    """One drafting turn: ask Claude, parse a PersonaDraft, emit reply + preview."""
    if not claude.enabled:
        emit(emit_assistant_message("Persona designer needs ANTHROPIC_API_KEY configured."))
        return

    raw = claude.messages_json_dict(
        system=SYSTEM_PROMPT,
        user=_render_messages(req.messages, req.proposal),
        max_tokens=4096,
    )
    draft = PersonaDraft.model_validate(raw or {"reply": _REPHRASE})
    emit(emit_assistant_message(draft.reply or _REPHRASE))
    if draft.spec is not None:
        emit(emit_persona_preview(draft.spec))


def _account_has_phone(account_id: str) -> bool:
    """True when the account already holds a disposable phone number. Checks the
    ENCRYPTED secrets doc directly (no decryption / no ENCRYPTION_KEY needed)."""
    doc = secrets.repo.load(account_id)
    return bool(doc and (doc.disposable_phone_enc or "").strip())


def _eligible_slots() -> list[AccountDocument]:
    """Active, un-retired, soul-less accounts that already hold a phone number — the
    slots a new persona can take over. Sorted by account_id (stable, lowest first)."""
    return [
        a for a in sorted(repo.list_all_accounts(include_retired=True), key=lambda a: a.account_id)
        if not a.retired and not a.provisioning.persona_assigned and _account_has_phone(a.account_id)
    ]


def _do_approve(req: PersonaChatRequest, emit: Callable[[dict], None]) -> None:
    """Assign the persona to a chosen open phone slot (renamed to its handle), carrying the
    slot's number + password. The operator picks the slot (req.slot_account_id); empty ->
    lowest-id eligible. No eligible slot -> park it as a retired account. No X registration
    here — signup happens separately in the desktop app."""
    spec = req.proposal
    if spec is None:
        emit(emit_validation_errors(["No persona to approve — propose one first."]))
        return
    handle = (spec.handle or "").strip()
    if not handle:
        emit(emit_validation_errors(["Persona needs a handle."]))
        return

    # Seed niche + category from the persona — never silently create a blank-souled
    # account (an empty category otherwise falls back to the handle; niches to []).
    category = (spec.category or "").strip()
    niches = [n.strip() for n in (spec.niches or []) if n and n.strip()]
    if not category:
        emit(emit_validation_errors(["Persona needs a category."]))
        return
    if not niches:
        emit(emit_validation_errors(["Persona needs at least one niche."]))
        return

    if repo.load(handle) is not None:
        emit(emit_validation_errors([f"An account '{handle}' already exists."]))
        return

    # Pick the phone slot to take over: operator-chosen if given, else the lowest-id
    # eligible. Validated here (before image gen) so a bad pick fails fast.
    slots = _eligible_slots()
    chosen_id = (req.slot_account_id or "").strip()
    if chosen_id:
        slot = next((a for a in slots if a.account_id == chosen_id), None)
        if slot is None:
            emit(emit_validation_errors(
                [f"'{chosen_id}' is not an available phone slot (must be un-souled, active, with a phone)."]))
            return
    else:
        slot = slots[0] if slots else None

    emit(emit_images_generating())
    avatar_id, header_id = generate_persona_images(spec.avatar_prompt, spec.header_prompt)
    emit(emit_images_ready(avatar_id, header_id))

    apply_account_create(AccountCreateBody(
        account_id=handle, category=category, twitter_handle=handle,
        personality=spec.personality, posting_prompt=spec.posting_prompt,
    ))
    acc = repo.load(handle)
    acc.soul.niches = [Niche(niche=n) for n in niches]
    acc.provisioning.display_name = spec.display_name
    acc.provisioning.bio = spec.bio
    acc.provisioning.images.avatar_asset_id = avatar_id
    acc.provisioning.images.header_asset_id = header_id
    acc.provisioning.status = "draft"
    acc.provisioning.persona_assigned = True
    acc.retired = slot is None  # no open slot -> park as retired
    repo.save(acc)

    # Seed 1-3 active posting pipelines the runner rotates between (LLM-chosen, validated).
    seed_active_pipelines(handle, spec.pipelines)

    if slot is not None:
        sec = secrets.get(slot.account_id)
        if sec:
            secrets.upsert(
                handle,
                disposable_phone=sec.disposable_phone,
                disposable_phone_lease=sec.disposable_phone_lease,
                password=sec.password,
            )
        secrets.repo.client.delete_document(AccountSecretsDocument.document_id(slot.account_id))
        repo.client.delete_document(AccountDocument.document_id(slot.account_id))

    emit(emit_account_written(handle))


def _run_persona_turn(req: PersonaChatRequest, emit: Callable[[dict], None]) -> None:
    """Dispatch a turn to the approve or draft handler. Never raises (caller wraps)."""
    if req.approve:
        _do_approve(req, emit)
    else:
        _run_turn(req, emit)


# ── HTTP endpoints ──

async def _sse_persona(req: PersonaChatRequest):
    """Generator that yields SSE frames. Mirrors agent_builder/force_post's pattern."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def emit(event: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    def worker() -> None:
        try:
            _run_persona_turn(req, emit)
        except AccountAlreadyExistsError as exc:
            loop.call_soon_threadsafe(queue.put_nowait, emit_error(str(exc)))
        except Exception as exc:
            logger.exception("Persona turn failed")
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


def _run_buffered(req: PersonaChatRequest, events: list[dict]) -> None:
    """Buffered (non-SSE) variant: collect events, mapping known failures to error events."""
    try:
        _run_persona_turn(req, events.append)
    except AccountAlreadyExistsError as exc:
        events.append(emit_error(str(exc)))
    except Exception as exc:
        logger.exception("Persona turn failed")
        events.append(emit_error(str(exc)))


@router.post("/persona/chat")
async def persona_chat(req: PersonaChatRequest, request: Request):
    """Conversational persona-design endpoint.

    Accepts text/event-stream for SSE, otherwise returns a buffered JSON array.
    """
    accept = (request.headers.get("accept") or "").lower()
    if "text/event-stream" in accept:
        return StreamingResponse(_sse_persona(req), media_type="text/event-stream")

    events: list[dict] = []
    await asyncio.to_thread(_run_buffered, req, events)
    events.append(emit_done())
    return {"events": events}


class RegenImagesBody(BaseModel):
    avatar_prompt: str | None = None
    header_prompt: str | None = None


@router.post("/persona/regenerate-images")
def regenerate_images(body: RegenImagesBody) -> dict:
    """Regenerate avatar and/or header before approving.

    Generates an image only for each non-empty prompt provided; the response
    contains only the keys actually produced.
    """
    result: dict[str, str] = {}
    if body.avatar_prompt:
        result["avatar_asset_id"] = generate_persona_image("avatar", body.avatar_prompt)
    if body.header_prompt:
        result["header_asset_id"] = generate_persona_image("header", body.header_prompt)
    return result


@router.get("/persona/slots")
def list_persona_slots() -> dict:
    """Un-souled, active, phone-bearing accounts a new persona can be attached to.
    The operator picks one in the Initialize-account flow; phone is masked to last 4."""
    slots: list[dict] = []
    for a in _eligible_slots():
        sec = secrets.get(a.account_id)
        phone = (sec.disposable_phone if sec else None) or ""
        slots.append({
            "account_id": a.account_id,
            "twitter_handle": a.twitter_handle or "",
            "phone_last4": phone[-4:] if phone else "",
        })
    return {"slots": slots}
