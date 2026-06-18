"""Unit tests for the AccountProvisioning sub-document on AccountDocument."""

import pytest
from pydantic import ValidationError

from app.models.account import (
    AccountDocument,
    AccountProvisioning,
    ProvisioningImages,
)


def _minimal_doc(**provisioning_kwargs) -> AccountDocument:
    kwargs = {"account_id": "acct-1", "profile": {"twitter_handle": ""}}
    if provisioning_kwargs:
        kwargs["provisioning"] = AccountProvisioning(**provisioning_kwargs)
    return AccountDocument.model_validate(kwargs)


def test_default_provisioning_status_is_draft():
    acc = _minimal_doc()
    assert acc.provisioning.status == "draft"
    assert acc.provisioning_status == "draft"
    assert acc.provisioning.images.avatar_asset_id is None
    assert acc.provisioning.images.header_asset_id is None


def test_legacy_dict_without_provisioning_validates_to_default():
    legacy = {
        "account_id": "acct-legacy",
        "profile": {"twitter_handle": "legacy", "status": "active"},
        "soul": {"category": "news"},
    }
    acc = AccountDocument.model_validate(legacy)
    assert acc.provisioning.status == "draft"
    assert acc.provisioning == AccountProvisioning()


def test_round_trip_preserves_populated_provisioning():
    acc = _minimal_doc(
        display_name="John James",
        bio="news commentary",
        images=ProvisioningImages(avatar_asset_id="media/avatar-1"),
        status="x_account_created",
        x_user_id="1234567890",
        attempt_count=2,
    )
    restored = AccountDocument.model_validate(acc.model_dump(exclude_none=True))
    assert restored.provisioning.status == "x_account_created"
    assert restored.provisioning.display_name == "John James"
    assert restored.provisioning.bio == "news commentary"
    assert restored.provisioning.images.avatar_asset_id == "media/avatar-1"
    assert restored.provisioning.x_user_id == "1234567890"
    assert restored.provisioning.attempt_count == 2


def test_invalid_status_raises_validation_error():
    with pytest.raises(ValidationError):
        AccountProvisioning(status="not-a-real-status")
