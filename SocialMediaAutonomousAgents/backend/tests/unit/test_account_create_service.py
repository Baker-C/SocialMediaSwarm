from unittest.mock import MagicMock

import pytest

from app.models.account import AccountDocument
from app.services.account_create_service import (
    AccountAlreadyExistsError,
    AccountCreateBody,
    apply_account_create,
)


def test_create_rejects_duplicate() -> None:
    existing = AccountDocument(account_id="dup", niche="n", twitter_handle="", status="active")

    class R:
        def load(self, account_id: str) -> AccountDocument | None:
            return existing if account_id == "dup" else None

    body = AccountCreateBody(account_id="dup")
    with pytest.raises(AccountAlreadyExistsError, match="already exists"):
        apply_account_create(body, repo=R())


def test_create_profile_then_applies_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import account_update_service as aus

    saved: list[AccountDocument] = []

    class R:
        def load(self, account_id: str) -> AccountDocument | None:
            for a in saved:
                if a.account_id == account_id:
                    return a
            return None

        def upsert_profile(self, account_id: str, **kwargs: object) -> AccountDocument:
            acc = AccountDocument(
                account_id=account_id,
                niche=str(kwargs.get("niche") or account_id),
                twitter_handle=str(kwargs.get("twitter_handle") or ""),
                status="active",
            )
            saved.append(acc)
            return acc

        def save(self, a: AccountDocument) -> None:
            saved[:] = [x for x in saved if x.account_id != a.account_id]
            saved.append(a)

    body = AccountCreateBody(
        account_id="fresh",
        niche="AI news",
        twitter_handle="@fresh",
        personality="witty analyst",
        status="inactive",
    )
    out = apply_account_create(body, repo=R())
    assert out.account_id == "fresh"
    assert out.niche == "AI news"
    assert out.personality == "witty analyst"
    assert out.status == "inactive"
