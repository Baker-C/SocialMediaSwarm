"""Version and stamp account soul revisions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.account import AccountDocument
from app.models.voice_revision import VoiceRevisionDocument
from app.services.voice_revision_repository import VoiceRevisionRepository


def _normalize_patterns(patterns) -> list[dict]:
    """Stable, comparable representation of a list of pydantic models or dicts,
    used both for hashing and for archiving.

    The digest is intentionally ORDER-SENSITIVE: list order is preserved here, so
    reordering patterns is treated as a real (auditable) change and bumps the version.
    Determinism across Python dict-ordering comes from json.dumps(sort_keys=True) in
    compute_voice_hash sorting the *dict keys* — NOT from sorting this list."""
    out: list[dict] = []
    for p in patterns or []:
        d = p.model_dump() if hasattr(p, "model_dump") else dict(p)
        out.append(d)
    return out


def compute_voice_hash(
    *,
    posting_prompt: str,
    personality: str,
    contrast_patterns=None,      # list[ContrastPattern] | list[dict]
    punctuation_rules=None,      # list[PunctuationRule] | list[dict]
) -> str:
    """SHA256 over the FULL soul so any edit (prompt, personality, a single pattern,
    a single rule) produces a new version. Canonical JSON (sorted keys) → stable digest."""
    payload = {
        "posting_prompt": (posting_prompt or "").strip(),
        "personality": (personality or "").strip(),
        "contrast_patterns": _normalize_patterns(contrast_patterns),
        "punctuation_rules": _normalize_patterns(punctuation_rules),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bump_voice_version_if_needed(
    account: AccountDocument,
    *,
    previous_hash: str | None,
    manual_label: str | None = None,
    revision_repo: VoiceRevisionRepository | None = None,
) -> AccountDocument:
    # Hash the whole soul (accessors proxy to account.soul.*).
    current_hash = compute_voice_hash(
        posting_prompt=account.posting_prompt,
        personality=account.personality,
        contrast_patterns=account.contrast_patterns,
        punctuation_rules=account.punctuation_rules,
    )
    prev = (previous_hash or "").strip() or (account.voice_version_hash or "").strip()
    manual = (manual_label or "").strip()
    changed = False

    if not prev:
        seq = max(1, int(account.voice_version_seq or 1))
        account.voice_version_seq = seq
        account.voice_version_hash = current_hash
        account.voice_version_label = manual or (account.voice_version_label or "").strip() or f"v{seq}"
        changed = True
    elif prev == current_hash and not manual:
        return account
    else:
        if prev != current_hash:
            seq = max(1, int(account.voice_version_seq or 1)) + 1
            account.voice_version_seq = seq
            account.voice_version_label = f"v{seq}"
            account.voice_version_hash = current_hash
            changed = True
        if manual:
            account.voice_version_label = manual
            changed = True

    if not changed:
        return account

    seq = max(1, int(account.voice_version_seq or 1))
    repo = revision_repo or VoiceRevisionRepository()
    repo.save(
        VoiceRevisionDocument(
            account_id=account.account_id,
            seq=seq,
            label=account.voice_version_label or f"v{seq}",
            version_hash=account.voice_version_hash or current_hash,
            changed_at=datetime.now(timezone.utc).isoformat(),
            # Full soul snapshot:
            personality=(account.personality or "").strip(),
            posting_prompt=(account.posting_prompt or "").strip(),
            contrast_patterns=list(account.contrast_patterns or []),
            punctuation_rules=list(account.punctuation_rules or []),
        )
    )
    return account
