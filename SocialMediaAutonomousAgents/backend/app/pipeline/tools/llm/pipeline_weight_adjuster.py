"""LLM reasoning to propose updated pipeline weights based on engagement performance."""

from __future__ import annotations

import json
from typing import Any

from app.infrastructure.claude_client import get_claude_client
from app.interval_crew import prompt_loader
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

from app.pipeline.types.artifacts import ArtifactKey

TOOL_ID = "llm.pipeline_weight_adjuster"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Reason about pipeline performance and propose updated weights"
TOOL_READS = (ArtifactKey.PIPELINE_METRICS, ArtifactKey.ALL_ACCOUNTS)
TOOL_WRITES = (ArtifactKey.PIPELINE_WEIGHT_PROPOSALS,)
PROMPT_STEM = "pipeline_weight_adjuster"


def run(
    ctx: TickRunContext,
    *,
    all_accounts: list[dict[str, Any]],
) -> StepResult:
    pipeline_metrics: dict[str, dict[str, dict[str, Any]]] = ctx.data.get("pipeline_metrics") or {}
    proposals: dict[str, dict[str, float]] = {}
    for account in all_accounts:
        account_id = str(account.get("id") or account.get("account_id") or "")
        if not account_id:
            continue
        soul = account.get("soul") or {}
        pipelines = soul.get("pipelines") or []
        metrics = pipeline_metrics.get(account_id) or {}
        proposals[account_id] = propose_weights(pipelines=pipelines, metrics=metrics)
    ctx.set("pipeline_weight_proposals", proposals)
    return StepResult(ok=True, payload={"account_count": len(proposals)})


def propose_weights(
    *,
    pipelines: list[dict[str, Any]],
    metrics: dict[str, dict[str, Any]],
) -> dict[str, float]:
    """Return {pipeline_name: new_weight} proposals that sum to 1.0."""
    if not pipelines:
        return {}

    current_weights = {
        str(p.get("name") or ""): float(p.get("weight") or 1.0)
        for p in pipelines
        if isinstance(p, dict) and p.get("name")
    }
    if not current_weights:
        return {}

    if len(current_weights) == 1:
        name = next(iter(current_weights))
        return {name: 1.0}

    claude = get_claude_client()
    if not claude.enabled:
        return _normalize(current_weights)

    system = _load_prompt("system")
    user = _load_prompt("user").format(
        current_weights_json=json.dumps(current_weights, indent=2, default=str),
        metrics_json=json.dumps(metrics, indent=2, default=str),
        pipeline_count=len(current_weights),
    )
    try:
        data = claude.messages_json_dict(system=system, user=user, max_tokens=512)
    except Exception:
        return _normalize(current_weights)

    if not isinstance(data, dict):
        return _normalize(current_weights)

    proposed: dict[str, float] = {}
    for pipeline_name, weight in data.items():
        try:
            proposed[str(pipeline_name)] = max(0.0, float(weight))
        except (TypeError, ValueError):
            continue

    # Fill in missing pipelines with their current weight before normalizing
    for name, weight in current_weights.items():
        if name not in proposed:
            proposed[name] = weight

    return _normalize(proposed)


def _normalize(weights: dict[str, float]) -> dict[str, float]:
    """Normalize weights so they sum to 1.0. If all zero, distribute evenly."""
    total = sum(weights.values())
    if total <= 0:
        count = len(weights)
        even = 1.0 / count if count > 0 else 1.0
        return {k: even for k in weights}
    return {k: v / total for k, v in weights.items()}


def _load_prompt(suffix: str) -> str:
    path = f"tasks/{PROMPT_STEM}.{suffix}.md"
    try:
        return prompt_loader.load(path)
    except FileNotFoundError:
        if suffix == "system":
            return (
                "You are a social media strategy optimizer. Given current pipeline weights and "
                "engagement metrics per pipeline, propose updated weights for each pipeline. "
                "Weights MUST sum to 1.0. If only 1 pipeline exists, weight stays 1.0. "
                "Return JSON: {pipeline_name: new_weight}."
            )
        return (
            "Current pipeline weights ({pipeline_count} pipelines):\n{current_weights_json}\n\n"
            "Engagement metrics per pipeline:\n{metrics_json}\n\n"
            "Propose updated weights that sum to 1.0. "
            "Return JSON: {{pipeline_name: new_weight}}"
        )
