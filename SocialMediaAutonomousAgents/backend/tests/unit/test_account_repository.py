"""Repository (de)serialization tests — pure functions, no RavenDB needed.

Regression guard for the bug where ``normalize_account_document`` rebuilt the
document but omitted the ``provisioning`` sub-doc, so every ``load`` reset
provisioning to its default (status="draft") and silently dropped stored
display_name / bio / images / status.
"""

from app.models.account import (
    AccountDocument,
    AccountProvisioning,
    ProvisioningImages,
)
from app.services.account_repository import (
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
