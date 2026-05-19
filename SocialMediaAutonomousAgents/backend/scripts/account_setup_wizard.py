#!/usr/bin/env python3
"""Interactive prompts to upsert one account via ``run_create_account_job``. Run from backend/."""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.jobs.create_account_job import CreateAccountJobError, run_create_account_job  # noqa: E402


@click.command()
def main() -> None:
    account_id = click.prompt("account_id")
    niche = click.prompt("niche", default=account_id, show_default=True)
    handle = click.prompt("twitter_handle", default="", show_default=False)
    key = click.prompt("twitter_api_key", hide_input=True)
    secret = click.prompt("twitter_api_secret", hide_input=True)
    token = click.prompt("twitter_access_token", hide_input=True)
    token_secret = click.prompt("twitter_access_token_secret", hide_input=True)
    try:
        acc = run_create_account_job(
            account_id=account_id,
            niche=niche,
            twitter_handle=handle or "",
            twitter_api_key=key,
            twitter_api_secret=secret,
            twitter_access_token=token,
            twitter_access_token_secret=token_secret,
        )
    except CreateAccountJobError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Saved {acc.account_id}")


if __name__ == "__main__":
    main()
