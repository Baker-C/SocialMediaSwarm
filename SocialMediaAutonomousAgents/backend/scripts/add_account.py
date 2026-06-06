#!/usr/bin/env python3
"""Upsert an account profile via ``run_create_account_job`` (CLI flags or JSON). Run from backend/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.jobs.create_account_job import CreateAccountJobError, run_create_account_job  # noqa: E402


@click.command()
@click.option("--account-id", default=None)
@click.option("--niche", default=None)
@click.option("--twitter-handle", default="")
@click.option("--json-file", type=click.Path(exists=True, dir_okay=False), default=None)
def main(
    account_id: str | None,
    niche: str | None,
    twitter_handle: str,
    json_file: str | None,
) -> None:
    if json_file:
        with open(json_file, encoding="utf-8") as f:
            payload = json.load(f)
        account_id = payload["account_id"]
        niche = payload.get("niche")
        twitter_handle = payload.get("twitter_handle", "")
    if not account_id:
        raise click.ClickException("--account-id is required (or use --json-file).")
    try:
        acc = run_create_account_job(
            account_id=account_id,
            niche=niche,
            twitter_handle=twitter_handle or "",
        )
    except CreateAccountJobError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Saved account {acc.account_id}")
    click.echo(f"Connect OAuth: GET /api/oauth/x/authorize?account_id={acc.account_id}")


if __name__ == "__main__":
    main()
