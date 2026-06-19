"""LLM reasoning to propose updated niche scores based on engagement performance."""

from __future__ import annotations

import json
from typing import Any

from app.infrastructure.claude_client import get_claude_client
from app.interval_crew import prompt_loader
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

from app.pipeline.types.artifacts import ArtifactKey

TOOL_ID = "llm.niche_weight_adjuster"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Reason about niche performance and propose updated niche scores"
TOOL_READS = (ArtifactKey.NICHE_METRICS, ArtifactKey.ALL_ACCOUNTS)
TOOL_WRITES = (ArtifactKey.NICHE_WEIGHT_PROPOSALS,)
PROMPT_STEM = "niche_weight_adjuster"


def run(
    ctx: TickRunContext,
    *,
    all_accounts: list[dict[str, Any]],
) -> StepResult:
    niche_metrics: dict[str, dict[str, dict[str, Any]]] = ctx.data.get("niche_metrics") or {}
    proposals: dict[str, dict[str, float]] = {}
    for account in all_accounts:
        account_id = str(account.get("id") or account.get("account_id") or "")
        if not account_id:
            continue
        soul = account.get("soul") or {}
        niches = soul.get("niches") or []
        metrics = niche_metrics.get(account_id) or {}
        proposals[account_id] = propose_scores(niches=niches, metrics=metrics)
    ctx.set("niche_weight_proposals", proposals)
    return StepResult(ok=True, payload={"account_count": len(proposals)})


def propose_scores(
    *,
    niches: list[dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Return {niche_id: new_score} proposals (0.0–1.0, independent)."""
    if not niches:
        return {}

    current_scores = {
        str(n.get("name") or ""): float(n.get("score") or 0.5)
        for n in niches
        if isinstance(n, dict) and n.get("name")
    }
    if not current_scores:
        return {}

    claude = get_claude_client()
    if not claude.enabled:
        return dict(current_scores)

    system = _load_prompt("system")
    user = _load_prompt("user").format(
        current_scores_json=json.dumps(current_scores, indent=2, default=str),
        metrics_json=json.dumps(metrics, indent=2, default=str),
    )
    try:
        data = claude.messages_json_dict(system=system, user=user, max_tokens=512)
    except Exception:
        return dict(current_scores)

    if not isinstance(data, dict):
        return dict(current_scores)

    proposed: dict[str, float] = {}
    for niche_id, score in data.items():
        try:
            clamped = max(0.0, min(1.0, float(score)))
            proposed[str(niche_id)] = clamped
        except (TypeError, ValueError):
            continue

    # Fall back to current score for any niche missing from response
    for niche_id, score in current_scores.items():
        if niche_id not in proposed:
            proposed[niche_id] = score

    return proposed


def _load_prompt(suffix: str) -> str:
    path = f"tasks/{PROMPT_STEM}.{suffix}.md"
    try:
        return prompt_loader.load(path)
    except FileNotFoundError:
        if suffix == "system":
            return (
                "You are a social media strategy optimizer. Given current niche scores and "
                "engagement metrics per niche, propose updated scores (0.0–1.0) for each niche. "
                "Higher engagement should yield higher scores. Scores are independent and do not "
                "need to sum to 1.0. Return JSON: {niche_id: new_score}."
            )
        return (
            "Current niche scores:\n{current_scores_json}\n\n"
            "Engagement metrics per niche:\n{metrics_json}\n\n"
            "Propose updated scores (0.0–1.0) for each niche based on the engagement data. "
            "Return JSON: {{niche_id: new_score}}"
        )
