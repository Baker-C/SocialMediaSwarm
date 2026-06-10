"""Version and stamp account voice revisions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.account import AccountDocument
from app.models.voice_revision import VoiceRevisionDocument
from app.services.voice_revision_repository import VoiceRevisionRepository


def compute_voice_hash(*, system_prompt: str, personality: str) -> str:
    payload = {"system_prompt": (system_prompt or "").strip(), "personality": (personality or "").strip()}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bump_voice_version_if_needed(
    account: AccountDocument,
    *,
    previous_hash: str | None,
    manual_label: str | None = None,
    revision_repo: VoiceRevisionRepository | None = None,
) -> AccountDocument:
    current_hash = compute_voice_hash(system_prompt=account.system_prompt, personality=account.personality)
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
        )
    )
    return account
