"""Step-by-step data passed between interval pipeline stages (console + log)."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_JSON_CHARS = 8000


def _serialize(data: Any) -> str:
    if data is None:
        return "null"
    try:
        if hasattr(data, "model_dump"):
            payload = data.model_dump()
        elif isinstance(data, dict):
            payload = data
        elif isinstance(data, list):
            payload = data
        else:
            payload = data
        text = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(data)
    if len(text) > _MAX_JSON_CHARS:
        return f"{text[:_MAX_JSON_CHARS]}\n... [truncated, {len(text)} chars total]"
    return text


def trace_step(
    account_id: str,
    step: str,
    data: Any,
    *,
    handoff_to: str | None = None,
) -> None:
    """Print and log the payload handed off after ``step`` (when tracing enabled)."""
    if not settings.tick_pipeline_trace:
        return
    header = f"=== tick_pipeline | account={account_id} | {step} ==="
    if handoff_to:
        header += f"  ->  next: {handoff_to}"
    body = _serialize(data)
    block = f"{header}\n{body}\n"
    print(block, flush=True)
    logger.info("%s\n%s", header, body)
