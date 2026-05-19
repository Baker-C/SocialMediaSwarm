#!/usr/bin/env python3
"""Smoke-test X credentials per active account (posts a short test tweet). Run from backend/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.account_repository import AccountRepository  # noqa: E402
from app.services.twitter_service import TwitterService  # noqa: E402


def main() -> None:
    repo = AccountRepository()
    tw = TwitterService(repo)
    for acc in repo.list_active():
        label = acc.account_id
        try:
            out = tw.post_tweet(acc.account_id, f"Smoke test {label}")
            print(f"OK  {label}: {out}")
        except Exception as exc:
            print(f"ERR {label}: {exc}")


if __name__ == "__main__":
    main()
