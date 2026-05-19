"""In-memory TTL cache for timeline reference tweet fetches per tick."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _CacheEntry:
    expires_at: float
    payload: dict[str, Any]


_cache: dict[tuple[str, str], _CacheEntry] = {}


def get_cached(account_id: str, slot: str) -> dict[str, Any] | None:
    key = (account_id, slot)
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.monotonic() > entry.expires_at:
        _cache.pop(key, None)
        return None
    return entry.payload


def set_cached(
    account_id: str,
    slot: str,
    payload: dict[str, Any],
    *,
    ttl_seconds: float,
) -> None:
    key = (account_id, slot)
    _cache[key] = _CacheEntry(expires_at=time.monotonic() + ttl_seconds, payload=payload)


def clear_cache() -> None:
    """Test helper."""
    _cache.clear()
