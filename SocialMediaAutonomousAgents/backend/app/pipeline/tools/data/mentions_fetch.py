"""Fetch recent X mentions of the account; write the MENTIONS artifact (doc 12)."""

from __future__ import annotations

from app.pipeline.types.artifacts import ArtifactKey, MentionsPayload
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.twitter_service import TwitterService

TOOL_ID = "data.mentions_fetch"
TOOL_KIND = "data"
TOOL_SOURCE = "x_mentions"
TOOL_PURPOSE = "Acquire recent mentions of the account from X for reply candidacy"
TOOL_WRITES = (ArtifactKey.MENTIONS,)
OUTPUT_MODEL = MentionsPayload


def run(
    ctx: TickRunContext,
    *,
    twitter: TwitterService,
    account_id: str | None = None,
    max_results: int | None = None,
) -> StepResult:
    aid = (account_id or ctx.account_id).strip()
    rows = twitter.get_mentions(aid, max_results=max_results)
    payload = {"account_id": aid, "mentions": rows}
    ctx.set_artifact(ArtifactKey.MENTIONS, payload)
    return StepResult(ok=True, payload={"mention_count": len(rows)})
