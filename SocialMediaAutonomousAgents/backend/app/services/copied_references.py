"""Track timeline source tweets an account has already reposted."""

from __future__ import annotations

from app.models.account import AccountDocument

MAX_COPIED_REFERENCES = 2000


def copied_reference_exclude_set(account: AccountDocument) -> frozenset[str]:
    """Tweet ids to skip when picking the next timeline reference."""
    out: set[str] = set()
    for raw in account.copied_reference_tweet_ids or []:
        tid = str(raw or "").strip()
        if tid.isdigit():
            out.add(tid)
    return frozenset(out)


def record_copied_reference(account: AccountDocument, source_tweet_id: str | None) -> None:
    """Append a source reference tweet id after a successful repost."""
    tid = str(source_tweet_id or "").strip()
    if not tid.isdigit():
        return
    existing = [str(x).strip() for x in (account.copied_reference_tweet_ids or []) if str(x).strip()]
    if tid in existing:
        return
    existing.append(tid)
    if len(existing) > MAX_COPIED_REFERENCES:
        existing = existing[-MAX_COPIED_REFERENCES:]
    account.copied_reference_tweet_ids = existing
