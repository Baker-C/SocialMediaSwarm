"""Runner releases post guards when pipeline raises."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.interval.context import TickContext
from app.interval.runner import run_account_pipeline
from app.models.account import AccountDocument


def _ctx() -> TickContext:
    return TickContext(
        repo=MagicMock(),
        twitter=MagicMock(),
        creator=MagicMock(),
        guardian=MagicMock(),
        tick_data=MagicMock(),
        post_registry=None,
        slot="2026-06-13-12-00",
        now_iso=datetime.now(timezone.utc).isoformat(),
        mode="force",
        force_account_ids=frozenset({"acct1"}),
        bypass_post_cooldown=True,
    )


def test_run_account_pipeline_releases_guards_on_exception() -> None:
    acc = AccountDocument(account_id="acct1", niche="T", status="active")
    ctx = _ctx()
    ctx.repo.load.return_value = acc

    reservation = MagicMock()
    reservation.account = acc
    reservation.previous_slot = None

    with (
        patch("app.interval.runner.try_begin_post", return_value=(acc, None)),
        patch("app.interval.runner.try_reserve_interval_slot", return_value=(reservation, None)),
        patch("app.interval.runner.run_reference_phase", side_effect=RuntimeError("boom")),
        patch("app.interval.runner.release_post_pipeline_guards") as release_guards,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            run_account_pipeline(ctx, acc)

    release_guards.assert_called_once_with(ctx, "acct1")
