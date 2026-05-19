"""Match RavenDB accounts to Buffer X channels and persist org + channel ids."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.infrastructure.buffer_api import BufferAPIError, buffer_list_channels
from app.models.account import AccountDocument
from app.services.account_repository import AccountRepository

logger = logging.getLogger(__name__)

_X_SERVICES = frozenset({"twitter", "x"})


def _alnum_lower(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum())


def is_buffer_x_channel(channel: dict[str, Any]) -> bool:
    return str(channel.get("service") or "").lower() in _X_SERVICES


def score_account_to_x_channel(acc: AccountDocument, ch: dict[str, Any]) -> int:
    """Heuristic match: twitter_handle and account_id vs channel name/display/descriptor."""
    handle = _alnum_lower(acc.twitter_handle.lstrip("@"))
    aid = _alnum_lower(acc.account_id)
    if not handle and not aid:
        return 0
    best = 0
    for key in ("displayName", "name", "descriptor"):
        raw = ch.get(key)
        if not raw or not isinstance(raw, str):
            continue
        blob = _alnum_lower(raw)
        if not blob:
            continue
        if handle:
            if handle == blob:
                best = max(best, 100)
            elif len(handle) >= 3 and (handle in blob or blob in handle):
                best = max(best, 75)
        if aid:
            if aid == blob:
                best = max(best, 95)
            elif len(aid) >= 3 and (aid in blob or blob in aid):
                best = max(best, 65)
    return best


def pick_best_x_channel(acc: AccountDocument, channels: list[dict[str, Any]]) -> dict[str, Any] | None:
    x_channels = [c for c in channels if is_buffer_x_channel(c)]
    if not x_channels:
        return None
    scored: list[tuple[int, dict[str, Any]]] = []
    for ch in x_channels:
        s = score_account_to_x_channel(acc, ch)
        if s > 0:
            scored.append((s, ch))
    if not scored:
        return None
    scored.sort(key=lambda t: -t[0])
    top_score = scored[0][0]
    winners = [ch for sc, ch in scored if sc == top_score]
    if len(winners) > 1:
        return None
    return winners[0]


@dataclass
class BufferSyncRow:
    account_id: str
    status: str
    buffer_organization_id: str
    buffer_channel_id: str | None
    channel_name: str | None
    detail: str = ""


def sync_buffer_x_channels_for_accounts(
    *,
    organization_id: str,
    api_key: str,
    repo: AccountRepository | None = None,
    dry_run: bool = False,
) -> list[BufferSyncRow]:
    """
    For each account in RavenDB, pick the best-matching Buffer X channel in ``organization_id``
    and save ``buffer_organization_id`` + ``buffer_channel_id`` (unless ``dry_run``).
    """
    oid = (organization_id or "").strip()
    key = (api_key or "").strip()
    if not oid:
        raise BufferAPIError("organization_id is required")
    if not key:
        raise BufferAPIError("BUFFER_API_KEY is empty")

    channels = buffer_list_channels(key, oid)
    r = repo or AccountRepository()
    accounts = r.list_all_accounts()
    out: list[BufferSyncRow] = []

    for acc in accounts:
        ch = pick_best_x_channel(acc, channels)
        if ch is None:
            out.append(
                BufferSyncRow(
                    account_id=acc.account_id,
                    status="skipped",
                    buffer_organization_id=oid,
                    buffer_channel_id=None,
                    channel_name=None,
                    detail="no confident X/Twitter channel match (check twitter_handle vs Buffer channel names)",
                )
            )
            continue
        cid = str(ch.get("id") or "")
        cname = ch.get("displayName") or ch.get("name")
        cname_s = str(cname) if cname else None
        if not dry_run:
            r.upsert_credentials(
                acc.account_id,
                buffer_organization_id=oid,
                buffer_channel_id=cid,
            )
            logger.info(
                "buffer_sync: account_id=%s buffer_channel_id=%s (channel=%r)",
                acc.account_id,
                cid,
                cname_s,
            )
        out.append(
            BufferSyncRow(
                account_id=acc.account_id,
                status="dry_run" if dry_run else "updated",
                buffer_organization_id=oid,
                buffer_channel_id=cid,
                channel_name=cname_s,
                detail="",
            )
        )
    return out
