"""LLM caption composer for media posts with safety guardian loop.

Detects which media artifacts (image/video, single/comparison) are present in
ctx.data, builds an appropriate prompt, and runs the guardian regeneration loop
until a caption passes or all rounds are exhausted.

Writes COMPOSED_POST_WITH_MEDIA and SAFETY_VERDICT.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.safety_guardian import is_niche_mismatch_reject
from app.infrastructure.claude_client import get_claude_client
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

logger = logging.getLogger(__name__)

TOOL_ID = "llm.compose_with_media"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Compose a tweet caption for a media post with safety guardian loop"
TOOL_READS = (
    ArtifactKey.ACCOUNT_BUNDLE,
    ArtifactKey.GENERATED_IMAGE,
    ArtifactKey.GENERATED_IMAGE_A,
    ArtifactKey.GENERATED_IMAGE_B,
    ArtifactKey.GENERATED_VIDEO,
    ArtifactKey.GENERATED_VIDEO_A,
    ArtifactKey.GENERATED_VIDEO_B,
)
TOOL_WRITES = (ArtifactKey.COMPOSED_POST_WITH_MEDIA, ArtifactKey.SAFETY_VERDICT)

_MAX_REGENERATION_ROUNDS = 5

# Media artifact keys in detection order (single variants before A/B variants)
_SINGLE_IMAGE_KEY = "generated_image"
_SINGLE_VIDEO_KEY = "generated_video"
_IMAGE_A_KEY = "generated_image_a"
_IMAGE_B_KEY = "generated_image_b"
_VIDEO_A_KEY = "generated_video_a"
_VIDEO_B_KEY = "generated_video_b"


def _detect_media(ctx: TickRunContext) -> tuple[str, list[str]]:
    """Return (media_situation, present_keys) where media_situation is one of:
    'single_image', 'dual_image', 'single_video', 'dual_video', or 'none'.
    present_keys is the ordered list of artifact keys that are present.
    """
    has_image = bool(ctx.data.get(_SINGLE_IMAGE_KEY))
    has_image_a = bool(ctx.data.get(_IMAGE_A_KEY))
    has_image_b = bool(ctx.data.get(_IMAGE_B_KEY))
    has_video = bool(ctx.data.get(_SINGLE_VIDEO_KEY))
    has_video_a = bool(ctx.data.get(_VIDEO_A_KEY))
    has_video_b = bool(ctx.data.get(_VIDEO_B_KEY))

    if has_image_a and has_image_b:
        return "dual_image", [_IMAGE_A_KEY, _IMAGE_B_KEY]
    if has_video_a and has_video_b:
        return "dual_video", [_VIDEO_A_KEY, _VIDEO_B_KEY]
    if has_image:
        return "single_image", [_SINGLE_IMAGE_KEY]
    if has_video:
        return "single_video", [_SINGLE_VIDEO_KEY]
    # Partial A/B — treat lone variant as a single
    if has_image_a:
        return "single_image", [_IMAGE_A_KEY]
    if has_image_b:
        return "single_image", [_IMAGE_B_KEY]
    if has_video_a:
        return "single_video", [_VIDEO_A_KEY]
    if has_video_b:
        return "single_video", [_VIDEO_B_KEY]
    return "none", []


def _situation_prompt(situation: str) -> str:
    """Return the media-situation preamble for the compose prompt."""
    if situation == "dual_image":
        return (
            "You are composing a tweet for a comparison post with two images. "
            "Frame it as a 'Which do you prefer?' or similar pick-one engagement question."
        )
    if situation == "dual_video":
        return (
            "You are composing a tweet for a video comparison post with two clips. "
            "Frame it as a pick-one engagement question."
        )
    if situation == "single_video":
        return (
            "You are composing a tweet to accompany an AI-generated video clip. "
            "Write a short engaging caption."
        )
    # single_image (default)
    return (
        "You are composing a tweet to accompany an AI-generated image. "
        "Write a caption that complements the visual."
    )


def _build_prompt(
    *,
    situation: str,
    niche: str,
    personality: str,
    posting_prompt: str,
    reject_reason: str | None,
    regeneration_round: int,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the caption LLM call."""
    situation_line = _situation_prompt(situation)

    system_parts = [
        situation_line,
        f"The account niche is: {niche}." if niche else "",
        f"Account personality: {personality}" if personality else "",
        f"Posting guidelines: {posting_prompt}" if posting_prompt else "",
        "Reply with only the tweet text. No hashtags unless they fit naturally. "
        "Keep it under 280 characters.",
    ]
    system = "\n".join(p for p in system_parts if p)

    user_parts = ["Write a caption for this media post."]
    if regeneration_round > 0 and reject_reason:
        user_parts.append(
            f"Your previous draft was rejected for: {reject_reason}. "
            "Please rewrite it, fixing that issue."
        )
    user = " ".join(user_parts)
    return system, user


def _compose_caption(
    *,
    situation: str,
    niche: str,
    personality: str,
    posting_prompt: str,
    reject_reason: str | None,
    regeneration_round: int,
) -> str | None:
    """Call the LLM to produce a raw caption string. Returns None when LLM is disabled."""
    claude = get_claude_client()
    if not claude.enabled:
        return None
    system, user = _build_prompt(
        situation=situation,
        niche=niche,
        personality=personality,
        posting_prompt=posting_prompt,
        reject_reason=reject_reason,
        regeneration_round=regeneration_round,
    )
    try:
        return claude.messages(system=system, user=user, max_tokens=256)
    except Exception as exc:
        logger.warning("compose_with_media: LLM call failed: %s", exc)
        return None


def run(ctx: TickRunContext, deps: Any) -> StepResult:
    live = deps.live
    guardian = live.guardian
    account = live.account
    niche: str = (account.category or "").strip()
    personality: str = (account.personality or "").strip()
    posting_prompt: str = (account.posting_prompt or "").strip()
    max_rounds: int = max(1, int(live.max_regeneration_rounds or _MAX_REGENERATION_ROUNDS))

    situation, media_keys = _detect_media(ctx)

    if situation == "none":
        ctx.data["composed_post_with_media"] = {"text": None, "media_keys": []}
        ctx.set_artifact(
            ArtifactKey.SAFETY_VERDICT,
            {"approved": False, "last_reject": "no_media_present", "references_tried": 0,
             "regeneration_round": 0},
        )
        return StepResult(ok=True, skipped=True, skip_reason="no_media_present")

    selected_body: str | None = None
    selected_round: int = 0
    last_reject: str | None = None
    candidate_reject: str | None = None

    for reg_round in range(max_rounds):
        draft = _compose_caption(
            situation=situation,
            niche=niche,
            personality=personality,
            posting_prompt=posting_prompt,
            reject_reason=candidate_reject if reg_round > 0 else None,
            regeneration_round=reg_round,
        )

        if draft is None:
            # LLM disabled — write a deterministic stub and treat it as approved
            stub = f"Check out this {situation.replace('_', ' ')}!"
            ctx.data["composed_post_with_media"] = {"text": stub, "media_keys": media_keys}
            ctx.set_artifact(
                ArtifactKey.SAFETY_VERDICT,
                {"approved": True, "last_reject": None, "references_tried": 0,
                 "regeneration_round": 0},
            )
            return StepResult(ok=True, payload={"text": stub, "media_keys": media_keys})

        approved, reject = guardian.evaluate(draft, niche=niche)
        if approved:
            selected_body = draft
            selected_round = reg_round
            break

        candidate_reject = reject or "safety_rejected"
        last_reject = candidate_reject
        if is_niche_mismatch_reject(candidate_reject):
            break

    if selected_body is None:
        ctx.data["composed_post_with_media"] = {"text": None, "media_keys": media_keys}
        ctx.set_artifact(
            ArtifactKey.SAFETY_VERDICT,
            {"approved": False,
             "last_reject": last_reject or "all_compose_attempts_failed",
             "references_tried": 0,
             "regeneration_round": 0},
        )
        return StepResult(
            ok=True,
            skipped=True,
            skip_reason=last_reject or "all_compose_attempts_failed",
        )

    ctx.data["composed_post_with_media"] = {"text": selected_body, "media_keys": media_keys}
    ctx.set_artifact(
        ArtifactKey.SAFETY_VERDICT,
        {"approved": True,
         "last_reject": last_reject,
         "references_tried": 0,
         "regeneration_round": selected_round},
    )
    return StepResult(
        ok=True,
        payload={"text": selected_body, "media_keys": media_keys},
    )
