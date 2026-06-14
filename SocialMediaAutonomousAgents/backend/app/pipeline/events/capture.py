"""Snapshot artifact values flowing in/out of a step.

Metadata (size, presence) is always captured. The full (truncated) body is
captured only when ``settings.pipeline_capture_payloads`` is on. The 8000-char
cap mirrors the existing trace precedent in ``app.interval.pipeline_trace``.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext

_MAX_JSON_CHARS = 8000


def _snapshot(value: Any) -> tuple[int, bool, Any | None]:
    """Return ``(size_bytes, truncated, payload_or_None)`` for an artifact value."""
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        text = repr(value)
    size = len(text.encode("utf-8"))
    if not settings.pipeline_capture_payloads:
        return size, False, None
    if len(text) > _MAX_JSON_CHARS:
        return size, True, f"{text[:_MAX_JSON_CHARS]}\n... [truncated, {len(text)} chars total]"
    return size, False, value


def capture_artifacts(ctx: TickRunContext, keys: tuple[ArtifactKey, ...]) -> list[dict[str, Any]]:
    """Snapshot the named artifacts currently present in the run context."""
    out: list[dict[str, Any]] = []
    for key in keys:
        present = ctx.has_artifact(key)
        entry: dict[str, Any] = {"artifact": key.value, "present": present}
        if present:
            size, truncated, payload = _snapshot(ctx.data.get(key.value))
            entry["size_bytes"] = size
            entry["truncated"] = truncated
            if payload is not None:
                entry["value"] = payload
        out.append(entry)
    return out
