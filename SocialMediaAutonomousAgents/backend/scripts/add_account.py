#!/usr/bin/env python3
"""Upsert an account via ``run_create_account_job`` (CLI flags or JSON). Run from backend/."""

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
@click.option("--twitter-api-key", default=None, help="OAuth1 consumer / API key")
@click.option("--twitter-api-secret", default=None)
@click.option("--twitter-access-token", default=None)
@click.option("--twitter-access-token-secret", default=None)
@click.option(
    "--twitter-oauth2-access-token",
    default=None,
    help="OAuth 2.0 user access token (Bearer). When set, OAuth1 flags are not required.",
)
@click.option("--twitter-oauth2-refresh-token", default=None, help="OAuth 2.0 refresh token (optional)")
@click.option("--json-file", type=click.Path(exists=True, dir_okay=False), default=None)
def main(
    account_id: str | None,
    niche: str | None,
    twitter_handle: str,
    twitter_api_key: str | None,
    twitter_api_secret: str | None,
    twitter_access_token: str | None,
    twitter_access_token_secret: str | None,
    twitter_oauth2_access_token: str | None,
    twitter_oauth2_refresh_token: str | None,
    json_file: str | None,
) -> None:
    if json_file:
        with open(json_file, encoding="utf-8") as f:
            payload = json.load(f)
        account_id = payload["account_id"]
        niche = payload.get("niche")
        twitter_handle = payload.get("twitter_handle", "")
        twitter_api_key = payload.get("twitter_api_key")
        twitter_api_secret = payload.get("twitter_api_secret")
        twitter_access_token = payload.get("twitter_access_token")
        twitter_access_token_secret = payload.get("twitter_access_token_secret")
        twitter_oauth2_access_token = payload.get("twitter_oauth2_access_token")
        twitter_oauth2_refresh_token = payload.get("twitter_oauth2_refresh_token")
    if not account_id:
        raise click.ClickException("--account-id is required (or use --json-file).")
    try:
        acc = run_create_account_job(
            account_id=account_id,
            niche=niche,
            twitter_handle=twitter_handle or "",
            twitter_api_key=twitter_api_key,
            twitter_api_secret=twitter_api_secret,
            twitter_access_token=twitter_access_token,
            twitter_access_token_secret=twitter_access_token_secret,
            twitter_oauth2_access_token=twitter_oauth2_access_token,
            twitter_oauth2_refresh_token=twitter_oauth2_refresh_token,
        )
    except CreateAccountJobError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Saved account {acc.account_id}")


if __name__ == "__main__":
    main()
