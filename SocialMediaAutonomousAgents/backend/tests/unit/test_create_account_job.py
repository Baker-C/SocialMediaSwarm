from cryptography.fernet import Fernet
from unittest.mock import MagicMock

import pytest

from app.jobs import create_account_job as job_mod
from app.jobs.create_account_job import CreateAccountJobError, run_create_account_job


def test_raises_empty_account_id() -> None:
    repo = MagicMock()
    with pytest.raises(CreateAccountJobError, match="account_id"):
        run_create_account_job(account_id="   ", repo=repo)


def test_requires_all_oauth1_secrets_when_no_oauth2() -> None:
    with pytest.raises(CreateAccountJobError, match="OAuth1"):
        run_create_account_job(
            account_id="x",
            twitter_api_key="a",
            twitter_api_secret=None,
            twitter_access_token="c",
            twitter_access_token_secret="d",
            repo=MagicMock(),
        )


def test_requires_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(job_mod.settings, "encryption_key", "")
    with pytest.raises(CreateAccountJobError, match="ENCRYPTION_KEY"):
        run_create_account_job(
            account_id="x",
            twitter_api_key="a",
            twitter_api_secret="b",
            twitter_access_token="c",
            twitter_access_token_secret="d",
            repo=MagicMock(),
        )


def test_passes_encrypted_oauth1_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(job_mod.settings, "encryption_key", key)
    repo = MagicMock()
    saved = MagicMock(account_id="live")
    repo.upsert_credentials.return_value = saved
    out = run_create_account_job(
        account_id="live",
        twitter_api_key="k",
        twitter_api_secret="s",
        twitter_access_token="t",
        twitter_access_token_secret="ts",
        repo=repo,
    )
    assert out is saved
    kw = repo.upsert_credentials.call_args[1]
    assert kw["twitter_api_key_enc"]
    assert kw["twitter_api_secret_enc"]
    assert kw["twitter_access_token_enc"]
    assert kw["twitter_access_token_secret_enc"]
    assert kw.get("clear_twitter_oauth2") is True


def test_oauth2_mode_encrypts_and_clears_oauth1(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(job_mod.settings, "encryption_key", key)
    repo = MagicMock()
    saved = MagicMock(account_id="o2")
    repo.upsert_credentials.return_value = saved
    out = run_create_account_job(
        account_id="o2",
        twitter_oauth2_access_token="user-access-token",
        twitter_oauth2_refresh_token="refresh-xyz",
        repo=repo,
    )
    assert out is saved
    kw = repo.upsert_credentials.call_args[1]
    assert kw["twitter_oauth2_access_token_enc"]
    assert kw["twitter_oauth2_refresh_token_enc"]
    assert kw.get("clear_twitter_oauth1") is True
