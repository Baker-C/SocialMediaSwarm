"""OAuth binding sentinel: atomic claim, lookup, and release."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.oauth_token_repository import OAuthTokenRepository


def test_claim_binding_creates_when_absent() -> None:
    client = MagicMock()
    client.put_document.return_value = True  # create-if-absent succeeded
    repo = OAuthTokenRepository(client=client)

    assert repo.claim_binding("uid-1", "aid-1") is True
    args, kwargs = client.put_document.call_args
    assert args[0] == "oauth-bindings/uid-1"
    assert kwargs["create_if_absent"] is True
    assert kwargs["collection"] == "OAuthBindings"


def test_claim_binding_blocks_concurrent_second_claim() -> None:
    client = MagicMock()
    # Second claim: create-if-absent fails (doc already exists) and a DIFFERENT account owns it.
    client.put_document.return_value = False
    client.get_document.return_value = {"x_user_id": "uid-1", "account_id": "aid-1"}
    repo = OAuthTokenRepository(client=client)

    assert repo.claim_binding("uid-1", "aid-2") is False


def test_claim_binding_idempotent_for_same_owner() -> None:
    client = MagicMock()
    client.put_document.return_value = False
    client.get_document.return_value = {"x_user_id": "uid-1", "account_id": "aid-1"}
    repo = OAuthTokenRepository(client=client)

    assert repo.claim_binding("uid-1", "aid-1") is True


def test_find_account_by_x_user_id() -> None:
    client = MagicMock()
    client.get_document.return_value = {"x_user_id": "uid-1", "account_id": "aid-1"}
    repo = OAuthTokenRepository(client=client)

    assert repo.find_account_by_x_user_id("uid-1") == "aid-1"
    client.get_document.return_value = None
    assert repo.find_account_by_x_user_id("uid-x") is None


def test_delete_token_releases_binding() -> None:
    from datetime import datetime, timezone

    from app.models.oauth_token import OAuthTokenDocument

    client = MagicMock()
    token_doc = OAuthTokenDocument(
        account_id="aid-1",
        x_user_id="uid-1",
        access_token_enc="enc",
        expires_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    client.get_document.return_value = token_doc.model_dump()
    repo = OAuthTokenRepository(client=client)

    repo.delete_token("aid-1")

    deleted_ids = [c.args[0] for c in client.delete_document.call_args_list]
    assert "oauth-tokens/aid-1" in deleted_ids
    assert "oauth-bindings/uid-1" in deleted_ids
