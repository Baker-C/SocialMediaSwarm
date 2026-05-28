#!/usr/bin/env python3
"""Persist default negative_semantics on RavenDB accounts that lack the field."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.account import AccountDocument, default_negative_semantics  # noqa: E402
from app.services.account_repository import AccountRepository  # noqa: E402


def main() -> None:
    repo = AccountRepository()
    updated = 0
    for acc in repo.list_all_accounts():
        doc_id = AccountDocument.document_id(acc.account_id)
        raw = repo.client.get_document(doc_id) or {}
        if raw.get("negative_semantics"):
            continue
        acc.negative_semantics = default_negative_semantics()
        repo.save(acc)
        updated += 1
        print(f"updated {acc.account_id}")
    print({"updated": updated, "total": len(repo.list_all_accounts())})


if __name__ == "__main__":
    main()
