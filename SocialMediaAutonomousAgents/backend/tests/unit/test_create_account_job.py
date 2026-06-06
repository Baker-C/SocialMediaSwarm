from unittest.mock import MagicMock

import pytest

from app.jobs.create_account_job import CreateAccountJobError, run_create_account_job


def test_raises_empty_account_id() -> None:
    repo = MagicMock()
    with pytest.raises(CreateAccountJobError, match="account_id"):
        run_create_account_job(account_id="   ", repo=repo)


def test_upserts_profile_only() -> None:
    repo = MagicMock()
    saved = MagicMock(account_id="live")
    repo.upsert_profile.return_value = saved
    out = run_create_account_job(
        account_id="live",
        niche="news",
        twitter_handle="@live",
        repo=repo,
    )
    assert out is saved
    repo.upsert_profile.assert_called_once()
    kw = repo.upsert_profile.call_args[1]
    assert kw["niche"] == "news"
    assert kw["twitter_handle"] == "@live"
