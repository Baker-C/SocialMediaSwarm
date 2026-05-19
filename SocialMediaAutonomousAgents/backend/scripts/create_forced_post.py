#!/usr/bin/env python3
"""Force a full posting tick for specific account IDs.

Prefer Docker (single backend + scheduler):

  docker compose exec backend python scripts/create_forced_post.py JohnJames_News

Use --force-now only when you intentionally want to bypass the post cooldown guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator import Orchestrator  # noqa: E402


@click.command()
@click.argument("account_ids", nargs=-1, required=True)
@click.option(
    "--force-now",
    is_flag=True,
    help="Bypass post cooldown (POST_COOLDOWN_MINUTES); still uses RavenDB + file locks.",
)
def main(account_ids: tuple[str, ...], force_now: bool) -> None:
    ids = [a.strip() for a in account_ids if a.strip()]
    if not ids:
        raise click.ClickException("Provide at least one account_id.")
    orch = Orchestrator()
    out = orch.run_tick(
        mode="force",
        account_ids=ids,
        bypass_post_cooldown=force_now,
    )
    click.echo(out)


if __name__ == "__main__":
    main()
