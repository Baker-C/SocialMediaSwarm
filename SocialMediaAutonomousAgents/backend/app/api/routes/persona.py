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
from app.services.account_create_service import (
    AccountAlreadyExistsError,
    AccountCreateBody,
    apply_account_create,
)
from app.services.account_repository import AccountRepository
from app.services.persona_image_service import (
    generate_persona_image,
    generate_persona_images,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Project default for this feature is opus-4-8 (the configured default is sonnet).
claude = ClaudeClient(model="claude-opus-4-8")

repo = AccountRepository()

_REPHRASE = "Tell me more about the account — niche, audience, voice, name."

SYSTEM_PROMPT = """You design X (Twitter) account personas. Converse with the operator to nail
down niches.
, audience, voice, name and bio. Ask the operator about options and questions until you 
and the operator are on the same page. Also discuss the account's VISUAL identity — what the
profile picture (avatar) and banner (header) should look like — and capture that discussion in
avatar_prompt / header_prompt. When you have enough, return JSON:
{"reply": "<message>", "spec": {"handle","display_name","bio","category","personality",
"posting_prompt","niches","avatar_prompt","header_prompt"} | null}. When you are only chatting or
clarifying, set spec to null. Keep handle <=15 chars, alphanumeric/underscore (no '@').
niches is an array of short topic strings the account will ride (e.g. ["Trump news", "political scandals"]).
avatar_prompt/header_prompt are vivid image-gen prompts (square avatar, wide banner)."""


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


def _do_approve(req: PersonaChatRequest, emit: Callable[[dict], None]) -> None:
    """The approve path: generate images, write the account, stamp the provisioning sub-doc."""
    spec = req.proposal
    if spec is None:
        emit(emit_validation_errors(["No persona to approve — propose one first."]))
        return
    if not (req.account_id or "").strip():
        emit(emit_validation_errors(["Account ID is required to provision — set it before approving."]))
        return

    # 1) Images (04). generate_persona_images may raise; surfaced as an error event.
    emit(emit_images_generating())
    avatar_id, header_id = generate_persona_images(spec.avatar_prompt, spec.header_prompt)
    emit(emit_images_ready(avatar_id, header_id))

    # 2) Write the account via the existing create path. display_name/bio are NOT
    #    create-body fields — they go on the provisioning sub-doc below (step 3).
    body = AccountCreateBody(
        account_id=req.account_id,
        category=spec.category,
        twitter_handle=spec.handle,
        personality=spec.personality,
        posting_prompt=spec.posting_prompt,
    )
    apply_account_create(body)

    # 3) Provisioning sub-doc: identity + image refs + status="draft".
    acc = repo.load(req.account_id)
    if spec.niches:
        acc.soul.niches = [Niche(niche=n.strip()) for n in spec.niches if n and n.strip()]
    acc.provisioning.display_name = spec.display_name
    acc.provisioning.bio = spec.bio
    acc.provisioning.images.avatar_asset_id = avatar_id
    acc.provisioning.images.header_asset_id = header_id
    acc.provisioning.status = "draft"
    repo.save(acc)

    emit(emit_account_written(req.account_id))


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
