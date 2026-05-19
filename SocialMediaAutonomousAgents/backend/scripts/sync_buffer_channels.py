"""Sync Buffer organization + X channel ids onto all RavenDB accounts (CLI)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings
from app.infrastructure.buffer_api import BufferAPIError
from app.services.buffer_channel_sync import sync_buffer_x_channels_for_accounts


def main() -> int:
    p = argparse.ArgumentParser(description="Map Buffer X channels to accounts and save org + channel ids.")
    p.add_argument(
        "--organization-id",
        "-o",
        help="Buffer organization id (defaults to BUFFER_ORGANIZATION_ID in .env; required — no API org discovery)",
    )
    p.add_argument("--dry-run", action="store_true", help="Print matches without writing RavenDB")
    args = p.parse_args()

    api_key = (settings.buffer_api_key or "").strip()
    if not api_key:
        print("Set BUFFER_API_KEY in backend/.env", file=sys.stderr)
        return 1

    org_id = (args.organization_id or settings.buffer_organization_id or "").strip()
    if not org_id:
        print(
            "No organization id: set BUFFER_ORGANIZATION_ID in .env or pass --organization-id "
            "(runtime does not query Buffer for organizations).",
            file=sys.stderr,
        )
        return 1

    try:
        rows = sync_buffer_x_channels_for_accounts(
            organization_id=org_id,
            api_key=api_key,
            dry_run=args.dry_run,
        )
    except BufferAPIError as exc:
        print(f"Buffer API error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps([r.__dict__ for r in rows], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
