#!/usr/bin/env python3
"""Soft-retire (or un-retire) accounts via ``AccountRepository.set_retired``. Run from backend/.

Retired accounts are EXCLUDED BY DEFAULT from the posting scheduler and account
listings, but their documents are KEPT (never deleted) for historical-data accuracy.
Dry-run by default; pass --apply to write. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.account_repository import AccountRepository  # noqa: E402


@click.command()
@click.option("--ids", required=True, help="Comma-separated account ids, e.g. a,b,c")
@click.option(
    "--retired",
    type=click.BOOL,
    default=True,
    help="true to retire (default), false to un-retire.",
)
@click.option("--dry-run/--apply", "dry_run", default=True, help="Preview (default) vs write.")
def main(ids: str, retired: bool, dry_run: bool) -> None:
    account_ids = [a.strip() for a in ids.split(",") if a.strip()]
    if not account_ids:
        raise click.ClickException("--ids must contain at least one account id.")

    repo = AccountRepository()
    action = "retire" if retired else "un-retire"
    click.echo(f"{'DRY-RUN' if dry_run else 'APPLY'}: {action} {len(account_ids)} account(s)")

    changed = 0
    skipped = 0
    missing = 0
    for aid in account_ids:
        acc = repo.load(aid)
        if acc is None:
            click.echo(f"  MISSING  {aid}")
            missing += 1
            continue
        if acc.retired == retired:
            click.echo(f"  no-op    {aid} (already retired={retired})")
            skipped += 1
            continue
        if dry_run:
            click.echo(f"  would    {aid} (retired {acc.retired} -> {retired})")
            changed += 1
            continue
        repo.set_retired(aid, retired)
        click.echo(f"  set      {aid} (retired {acc.retired} -> {retired})")
        changed += 1

    verb = "would change" if dry_run else "changed"
    click.echo(f"Summary: {verb}={changed}, no-op={skipped}, missing={missing}")
    if dry_run and changed:
        click.echo("Re-run with --apply to write.")


if __name__ == "__main__":
    main()
