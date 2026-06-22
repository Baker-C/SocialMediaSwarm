"""Repository (de)serialization tests — pure functions, no RavenDB needed.

Regression guard for the bug where ``normalize_account_document`` rebuilt the
document but omitted the ``provisioning`` sub-doc, so every ``load`` reset
provisioning to its default (status="draft") and silently dropped stored
display_name / bio / images / status.
"""

import pytest

from app.models.account import (
    AccountDocument,
    AccountProvisioning,
    ProvisioningImages,
)
from app.services.account_repository import (
    AccountRepository,
    account_to_document,
    document_to_account,
    normalize_account_document,
)


def test_normalize_preserves_provisioning_subdoc():
    raw = {
        "account_id": "acct-1",
        "profile": {"twitter_handle": "acct1", "status": "active"},
        "soul": {"category": "news"},
        "provisioning": {
            "display_name": "John James",
            "bio": "news commentary",
            "images": {"avatar_asset_id": "media/avatar-1"},
            "status": "in_progress",
            "attempt_count": 2,
        },
    }
    normalized = normalize_account_document(raw)
    assert normalized["provisioning"]["status"] == "in_progress"
    assert normalized["provisioning"]["attempt_count"] == 2
    assert normalized["provisioning"]["display_name"] == "John James"


def test_round_trip_preserves_provisioning():
    acc = AccountDocument.model_validate(
        {
            "account_id": "acct-1",
            "profile": {"twitter_handle": "acct1"},
            "provisioning": AccountProvisioning(
                display_name="John James",
                bio="news commentary",
                images=ProvisioningImages(avatar_asset_id="media/avatar-1"),
                status="in_progress",
                x_user_id="1234567890",
                attempt_count=2,
            ),
        }
    )
    restored = document_to_account(account_to_document(acc))
    assert restored.provisioning.status == "in_progress"
    assert restored.provisioning.display_name == "John James"
    assert restored.provisioning.bio == "news commentary"
    assert restored.provisioning.images.avatar_asset_id == "media/avatar-1"
    assert restored.provisioning.x_user_id == "1234567890"
    assert restored.provisioning.attempt_count == 2


def test_legacy_doc_without_provisioning_defaults_to_draft():
    legacy = {
        "account_id": "acct-legacy",
        "twitter_handle": "legacy",
        "status": "active",
        "system_prompt": "post about news",
    }
    restored = document_to_account(legacy)
    assert restored.provisioning == AccountProvisioning()
    assert restored.provisioning.status == "draft"


def test_legacy_doc_defaults_retired_false():
    """Docs without the field load fine and default retired=False."""
    legacy = {"account_id": "acct-legacy", "twitter_handle": "legacy", "status": "active"}
    restored = document_to_account(legacy)
    assert restored.retired is False


# ── Soft-retire: list filtering + set_retired ──────────────────────────────────

class _FakeClient:
    """In-memory stand-in for RavenDBHttpClient backing the retire/list tests."""

    def __init__(self, docs: dict[str, dict]) -> None:
        self._docs = docs  # {doc_id: stored dict}

    def query(self, rql: str) -> list[dict]:
        # Tests only filter on retired, so return every account row regardless of RQL.
        return list(self._docs.values())

    def get_document(self, doc_id: str) -> dict | None:
        return self._docs.get(doc_id)

    def put_document(self, doc_id: str, doc: dict, collection: str | None = None) -> None:
        self._docs[doc_id] = doc


def _make_repo() -> AccountRepository:
    docs = {
        "accounts/keep": {
            "account_id": "keep",
            "profile": {"twitter_handle": "keep", "status": "active", "retired": False},
        },
        "accounts/gone": {
            "account_id": "gone",
            "profile": {"twitter_handle": "gone", "status": "active", "retired": True},
        },
    }
    return AccountRepository(client=_FakeClient(docs))


def test_list_active_excludes_retired_by_default():
    repo = _make_repo()
    ids = {a.account_id for a in repo.list_active()}
    assert ids == {"keep"}


def test_list_active_includes_retired_with_flag():
    repo = _make_repo()
    ids = {a.account_id for a in repo.list_active(include_retired=True)}
    assert ids == {"keep", "gone"}


def test_list_all_accounts_excludes_retired_by_default():
    repo = _make_repo()
    ids = {a.account_id for a in repo.list_all_accounts()}
    assert ids == {"keep"}


def test_list_all_accounts_includes_retired_with_flag():
    repo = _make_repo()
    ids = {a.account_id for a in repo.list_all_accounts(include_retired=True)}
    assert ids == {"keep", "gone"}


def test_set_retired_flips_flag_and_persists():
    repo = _make_repo()
    repo.set_retired("keep", True)
    # Now excluded by default, but still present (not deleted) and visible with the flag.
    assert {a.account_id for a in repo.list_active()} == set()
    assert repo.load("keep").retired is True
    # Idempotent un-retire round-trip.
    repo.set_retired("keep", False)
    assert repo.load("keep").retired is False


def test_set_retired_missing_account_raises():
    repo = _make_repo()
    with pytest.raises(LookupError):
        repo.set_retired("nope", True)
