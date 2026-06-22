#!/usr/bin/env python3
"""Seed the FIXED fleet of 10 X accounts (persistent rental numbers + shared password).

Idempotent and safe to re-run. Never deletes accounts.

  - johnjames_news is EXISTING: we ONLY set its persistent rental number. We do NOT
    recreate the account doc and do NOT change its password.
  - acct_01..acct_09 are NEW: create the account doc idempotently, then store the
    persistent rental number + the shared fleet password.

Run from backend/.  Default is --dry-run (prints the planned roster); pass --apply to write.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.jobs.create_account_job import run_create_account_job  # noqa: E402
from app.services.account_secrets_service import AccountSecretsService  # noqa: E402

FLEET_PASSWORD = "Password!!0000"

# account_id -> persistent rental number. johnjames_news is the existing account.
EXISTING_ID = "johnjames_news"
ROSTER: dict[str, str] = {
    "johnjames_news": "2092789534",  # EXISTING — only set its number, never recreate
    "acct_01": "3466445896",
    "acct_02": "3523545670",
    "acct_03": "3134138548",
    "acct_04": "6186817413",
    "acct_05": "4236470446",
    "acct_06": "3252961060",
    "acct_07": "7634431088",
    "acct_08": "3075330696",
    "acct_09": "5022951174",
}


def _print_plan() -> None:
    click.echo(f"{'account_id':<18} {'number':<12} {'action':<10} password-set?")
    click.echo("-" * 60)
    for aid, num in ROSTER.items():
        if aid == EXISTING_ID:
            click.echo(f"{aid:<18} {num:<12} {'phone-only':<10} no (keep existing)")
        else:
            click.echo(f"{aid:<18} {num:<12} {'create':<10} yes ({FLEET_PASSWORD})")


@click.command()
@click.option("--apply", "do_apply", is_flag=True, default=False, help="Write changes (default is dry-run).")
def main(do_apply: bool) -> None:
    click.echo("=== FIXED fleet seed ===")
    _print_plan()

    if not do_apply:
        click.echo("\n(dry-run) Nothing written. Re-run with --apply to seed.")
        return

    secrets = AccountSecretsService()
    click.echo("\nApplying…")
    for aid, num in ROSTER.items():
        if aid == EXISTING_ID:
            # Existing account: only persist its rental number; never touch the doc/password.
            secrets.upsert(aid, disposable_phone=num)
            click.echo(f"  {aid}: phone set ({num}); password unchanged")
        else:
            # New account: idempotent doc create, then store number + shared password.
            run_create_account_job(account_id=aid, category="general", twitter_handle=aid)
            secrets.upsert(aid, disposable_phone=num, password=FLEET_PASSWORD)
            click.echo(f"  {aid}: doc upserted; phone set ({num}); password set")

    click.echo("\nDone. Fleet seeded (idempotent).")


if __name__ == "__main__":
    main()
