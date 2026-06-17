#!/usr/bin/env python3
"""Transfer the legacy account ``niche`` field into ``category``.

Existing account documents stored the account theme under ``profile.niche`` (or a
top-level ``niche`` on very old flat docs). The field has been renamed to
``category``; loading folds the legacy key in via an alias, and re-saving writes
``category`` and drops ``niche``. This script does that re-save for every account.

Idempotent: accounts already stored with ``category`` and no ``niche`` are skipped.
Run with --dry-run first to preview.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.account import AccountDocument  # noqa: E402
from app.services.account_repository import (  # noqa: E402
    AccountRepository,
    account_to_document,
    normalize_account_document,
)


def _has_legacy_niche(raw: dict) -> bool:
    if "niche" in raw:
        return True
    profile = raw.get("profile")
    return isinstance(profile, dict) and "niche" in profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = AccountRepository()
    try:
        rows = repo.client.query("from Accounts")
    except Exception:
        rows = repo.client.query("from @all where startsWith(id(), 'accounts/')")

    migrated = 0
    skipped = 0
    failed = 0
    for raw in rows:
        aid = raw.get("account_id") if isinstance(raw, dict) else "unknown"
        if not _has_legacy_niche(raw):
            skipped += 1
            continue
        try:
            acc = AccountDocument.model_validate(normalize_account_document(raw))
            doc = account_to_document(acc)
            print(f"{aid}: niche -> category = {acc.category!r}")
            migrated += 1
            if not args.dry_run:
                repo.client.put_document(
                    AccountDocument.document_id(acc.account_id), doc, collection="Accounts"
                )
        except Exception as exc:
            failed += 1
            print(f"FAILED account_id={aid}: {exc}")

    print(f"migrated={migrated} skipped={skipped} failed={failed} dry_run={args.dry_run}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
