"""One-time migration: rewrite every account document so `voice` → `soul`.

Idempotent (converges after the first run): loading applies the validator
(voice→soul) and saving drops `voice` and stamps the soul version. The FIRST run
bumps the version once and writes a single `soul-migration` revision because the
hash payload changed (the full soul is now hashed); re-runs are no-ops. Safe to
re-run. Run inside the backend container:

    docker exec -it social-media-backend python -m scripts.migrate_voice_to_soul
"""

from __future__ import annotations

import logging

from app.services.account_repository import AccountRepository
from app.services.voice_version_service import (
    bump_voice_version_if_needed,
    compute_voice_hash,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("migrate_voice_to_soul")


def main() -> None:
    repo = AccountRepository()
    accounts = repo.list_all_accounts(include_retired=True)  # migrate every doc, retired included
    log.info("Found %d account(s) to migrate", len(accounts))
    for acc in accounts:
        # load() already ran the validator → acc.soul is populated, voice dropped.
        # Label the version bump ONLY when one is genuinely pending; a manual label
        # forces changed=True on every call, which would write a duplicate revision
        # on each re-run and break idempotency.
        pending = (acc.voice_version_hash or "") != compute_voice_hash(
            posting_prompt=acc.posting_prompt,
            personality=acc.personality,
            contrast_patterns=acc.contrast_patterns,
            punctuation_rules=acc.punctuation_rules,
        )
        bump_voice_version_if_needed(
            acc,
            previous_hash=acc.voice_version_hash,
            manual_label="soul-migration" if pending else None,
        )
        repo.save(acc)  # serializer omits `voice`; save() also calls bump (now a no-op).
        log.info(
            "Migrated %s → soul (version=%s seq=%s, %d contrast, %d punctuation)",
            acc.account_id,
            acc.voice_version_label,
            acc.voice_version_seq,
            len(acc.contrast_patterns or []),
            len(acc.punctuation_rules or []),
        )
    log.info("Migration complete.")


if __name__ == "__main__":
    main()
