#!/usr/bin/env python3
"""Move legacy OAuth2 tokens from account documents into OAuthTokens collection."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.oauth_token import OAuthTokenDocument  # noqa: E402
from app.services.account_repository import AccountRepository, normalize_account_document  # noqa: E402
from app.services.oauth_token_repository import OAuthTokenRepository  # noqa: E402


def _legacy_tokens(raw: dict) -> tuple[str | None, str | None]:
    creds = raw.get("credentials") if isinstance(raw.get("credentials"), dict) else {}
    access = creds.get("oauth2_access_token_enc") or raw.get("twitter_oauth2_access_token_enc")
    refresh = creds.get("oauth2_refresh_token_enc") or raw.get("twitter_oauth2_refresh_token_enc")
    return (
        str(access).strip() if access else None,
        str(refresh).strip() if refresh else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    accounts = AccountRepository()
    tokens = OAuthTokenRepository()
    try:
        rows = accounts.client.query("from Accounts")
    except Exception:
        rows = accounts.client.query("from @all where startsWith(id(), 'accounts/')")

    migrated = 0
    skipped = 0
    for raw in rows:
        norm = normalize_account_document(raw)
        account_id = str(norm.get("account_id") or "").strip()
        if not account_id:
            skipped += 1
            continue
        access_enc, refresh_enc = _legacy_tokens(raw if isinstance(raw, dict) else {})
        if not access_enc:
            skipped += 1
            continue
        if tokens.load_token(account_id) is not None:
            skipped += 1
            continue
        now = datetime.now(timezone.utc).isoformat()
        doc = OAuthTokenDocument(
            account_id=account_id,
            access_token_enc=access_enc,
            refresh_token_enc=refresh_enc,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            scopes="",
            updated_at=now,
        )
        migrated += 1
        if not args.dry_run:
            tokens.save_token(doc)

    print(f"migrated={migrated} skipped={skipped} dry_run={args.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
