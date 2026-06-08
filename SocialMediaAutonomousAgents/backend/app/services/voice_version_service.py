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
    prev = (previous_hash or "").strip() or account.voice_version_hash
    if not prev:
        account.voice_version_hash = current_hash
        account.voice_version_seq = max(1, int(account.voice_version_seq or 1))
        account.voice_version_label = account.voice_version_label or f"v{account.voice_version_seq}"
        return account
    if prev == current_hash and not (manual_label or "").strip():
        return account
    if prev != current_hash:
        seq = max(1, int(account.voice_version_seq or 1)) + 1
        account.voice_version_seq = seq
        account.voice_version_label = f"v{seq}"
        account.voice_version_hash = current_hash
    if (manual_label or "").strip():
        account.voice_version_label = manual_label.strip()
    repo = revision_repo or VoiceRevisionRepository()
    repo.save(
        VoiceRevisionDocument(
            account_id=account.account_id,
            seq=max(1, int(account.voice_version_seq or 1)),
            label=account.voice_version_label or f"v{max(1, int(account.voice_version_seq or 1))}",
            version_hash=account.voice_version_hash or current_hash,
            changed_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    return account
