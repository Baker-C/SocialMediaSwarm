#!/usr/bin/env python3
"""Rewrite account documents to nested schema and drop legacy flat keys."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.account import AccountDocument  # noqa: E402
from app.services.account_repository import (  # noqa: E402
    account_to_document,
    normalize_account_document,
)
from app.services.account_repository import AccountRepository  # noqa: E402


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
        try:
            norm = normalize_account_document(raw)
            acc = AccountDocument.model_validate(norm)
            doc = account_to_document(acc)
            doc_id = AccountDocument.document_id(acc.account_id)
            current = {k: v for k, v in raw.items() if not str(k).startswith("@")}
            if current == doc:
                skipped += 1
                continue
            migrated += 1
            if not args.dry_run:
                repo.client.put_document(doc_id, doc, collection="Accounts")
        except Exception as exc:
            failed += 1
            aid = raw.get("account_id") if isinstance(raw, dict) else "unknown"
            print(f"FAILED account_id={aid}: {exc}")

    print(f"migrated={migrated} skipped={skipped} failed={failed} dry_run={args.dry_run}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

