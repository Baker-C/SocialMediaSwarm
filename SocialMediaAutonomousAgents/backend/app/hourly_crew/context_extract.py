"""Extract human-readable context from tick prompt JSON (for fallbacks)."""

from __future__ import annotations

import json
from typing import Any


def extract_context_hints(prompt_bundle: str, niche: str) -> dict[str, str]:
    """Pull short strings from merged tick JSON; never return raw JSON slices."""
    niche_s = (niche or "general").strip()
    hints: dict[str, str] = {"niche": niche_s}

    try:
        data = json.loads(prompt_bundle)
    except (json.JSONDecodeError, TypeError):
        hints["topic"] = niche_s
        return hints

    if not isinstance(data, dict):
        hints["topic"] = niche_s
        return hints

    account = data.get("account")
    if isinstance(account, dict):
        pre = account.get("topic_preanalysis")
        if isinstance(pre, dict):
            label = pre.get("selected_topic_label")
            if isinstance(label, str) and label.strip():
                hints["topic"] = label.strip()[:120]
        for key in ("reference_engagements", "post_engagements"):
            engagements = account.get(key)
            if not isinstance(engagements, list):
                continue
            for row in engagements:
                if not isinstance(row, dict):
                    continue
                text = str(row.get("text") or "").strip()
                if text and not text.startswith("{"):
                    hints["sample_post"] = text[:280]
                    break
            if "sample_post" in hints:
                break

    niche_ctx = data.get("niche_context")
    if isinstance(niche_ctx, dict):
        summary = niche_ctx.get("discourse_summary")
        if isinstance(summary, str) and summary.strip():
            hints["discourse"] = summary.strip()[:400]
        trends = niche_ctx.get("trend_names")
        if isinstance(trends, list) and trends:
            names = [str(t).strip() for t in trends[:5] if str(t).strip()]
            if names:
                hints["trends"] = ", ".join(names)

    if "topic" not in hints:
        hints["topic"] = hints.get("discourse", niche_s)[:120]
    return hints
