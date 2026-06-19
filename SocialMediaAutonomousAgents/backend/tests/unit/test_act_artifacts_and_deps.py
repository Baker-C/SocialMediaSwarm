"""Unit tests for ACT-phase artifacts (COMPOSED_POST, SAFETY_VERDICT, PUBLISHED_POST) and ActLive."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.account import AccountDocument
from app.pipeline.services.deps import ActLive, PostRunDeps
from app.pipeline.types.artifacts import (
    ARTIFACTS,
    ArtifactKey,
    ComposedPost,
    PublishedPost,
    SafetyVerdict,
)


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_account() -> AccountDocument:
    """Mock AccountDocument for ActLive construction."""
    return AccountDocument(
        account_id="test_acct",
        category="news",
        posting_prompt="Post about breaking news.",
        personality="direct",
        contrast_patterns=[],
        punctuation_rules=[],
        voice_version_hash="v1",
        voice_version_seq=1,
        voice_version_label="base",
    )


# ──────────────────────────────────────────────────────────────────
# ComposedPost Tests
# ──────────────────────────────────────────────────────────────────


def test_composed_post_minimal():
    """ComposedPost requires only 'body'."""
    post = ComposedPost.model_validate({"body": "Test post"})
    assert post.body == "Test post"
    assert post.reference_index == 0
    assert post.regeneration_round == 0
    assert post.source_reference_tweet_id is None


def test_composed_post_full():
    """ComposedPost with all fields."""
    data = {
        "body": "Test post with source",
        "reference_index": 2,
        "references_tried": 5,
        "regeneration_round": 1,
        "source_reference_tweet_id": "12345",
        "chosen_embed_url": "https://example.com/embed",
        "source_reference_metrics_at_pick": {"tweet_id": "12345", "popularity_score": 9.5},
        "tweets_pulled": 100,
        "tweets_pulled_new": 50,
        "tweets_pulled_duplicates": 50,
    }
    post = ComposedPost.model_validate(data)
    assert post.body == "Test post with source"
    assert post.reference_index == 2
    assert post.regeneration_round == 1
    assert post.tweets_pulled == 100


def test_composed_post_extra_fields_allowed():
    """ComposedPost allows extra fields (extra='allow')."""
    data = {
        "body": "Test",
        "custom_field": "custom_value",
        "another_field": 123,
    }
    post = ComposedPost.model_validate(data)
    assert post.body == "Test"
    # Extra fields are stored in __pydantic_extra__
    assert post.__pydantic_extra__["custom_field"] == "custom_value"


def test_composed_post_registered_in_artifacts():
    """ComposedPost is registered in ARTIFACTS."""
    assert ArtifactKey.COMPOSED_POST in ARTIFACTS
    assert ARTIFACTS[ArtifactKey.COMPOSED_POST].model == ComposedPost
    assert "compose-loop provenance" in ARTIFACTS[ArtifactKey.COMPOSED_POST].purpose


# ──────────────────────────────────────────────────────────────────
# SafetyVerdict Tests
# ──────────────────────────────────────────────────────────────────


def test_safety_verdict_approved():
    """SafetyVerdict when approved=True."""
    verdict = SafetyVerdict.model_validate(
        {
            "approved": True,
            "last_reject": None,
            "references_tried": 3,
            "regeneration_round": 1,
        }
    )
    assert verdict.approved is True
    assert verdict.last_reject is None
    assert verdict.regeneration_round == 1


def test_safety_verdict_rejected():
    """SafetyVerdict when approved=False with reject reason."""
    verdict = SafetyVerdict.model_validate(
        {
            "approved": False,
            "last_reject": "niche_mismatch",
            "references_tried": 5,
            "regeneration_round": 0,
        }
    )
    assert verdict.approved is False
    assert verdict.last_reject == "niche_mismatch"
    assert verdict.regeneration_round == 0


def test_safety_verdict_defaults():
    """SafetyVerdict with only required field (approved)."""
    verdict = SafetyVerdict.model_validate({"approved": False})
    assert verdict.approved is False
    assert verdict.last_reject is None
    assert verdict.references_tried == 0
    assert verdict.regeneration_round == 0


def test_safety_verdict_registered_in_artifacts():
    """SafetyVerdict is registered in ARTIFACTS."""
    assert ArtifactKey.SAFETY_VERDICT in ARTIFACTS
    assert ARTIFACTS[ArtifactKey.SAFETY_VERDICT].model == SafetyVerdict


# ──────────────────────────────────────────────────────────────────
# PublishedPost Tests
# ──────────────────────────────────────────────────────────────────


def test_published_post_minimal():
    """PublishedPost requires only account_id."""
    post = PublishedPost.model_validate({"account_id": "acct1"})
    assert post.account_id == "acct1"
    assert post.posted is False
    assert post.tweet_id is None
    assert post.result == {}


def test_published_post_success():
    """PublishedPost on successful post to X."""
    data = {
        "account_id": "acct1",
        "posted": True,
        "tweet_id": "9876543210",
        "regeneration_round": 0,
        "idempotency_key": "run123:acct1",
        "note": None,
        "result": {
            "account_id": "acct1",
            "tweet": {"id": "9876543210", "text": "Posted tweet"},
            "regeneration_round": 0,
            "creation_metrics": {"candidates_created": 1},
        },
    }
    post = PublishedPost.model_validate(data)
    assert post.posted is True
    assert post.tweet_id == "9876543210"
    assert "tweet" in post.result
    assert post.result["tweet"]["id"] == "9876543210"


def test_published_post_skipped():
    """PublishedPost when skipped (no approved body)."""
    post = PublishedPost.model_validate(
        {
            "account_id": "acct1",
            "posted": False,
            "skipped_reason": "niche_mismatch",
        }
    )
    assert post.posted is False
    assert post.skipped_reason == "niche_mismatch"


def test_published_post_idempotent_replay():
    """PublishedPost on idempotent replay."""
    data = {
        "account_id": "acct1",
        "tweet_id": "existing_tweet_id",
        "posted": True,
        "idempotency_key": "run123:acct1",
        "note": "idempotent_replay",
        "result": {
            "account_id": "acct1",
            "tweet": {"id": "existing_tweet_id"},
            "note": "idempotent_replay",
        },
    }
    post = PublishedPost.model_validate(data)
    assert post.note == "idempotent_replay"
    assert "tweet" in post.result


def test_published_post_result_field_required():
    """PublishedPost.result carries the full finalize_post dict."""
    finalize_dict = {
        "account_id": "acct1",
        "tweet": {"id": "123", "text": "test"},
        "regeneration_round": 0,
        "creation_metrics": {"candidates_created": 1, "voice_version_hash": "v1"},
    }
    post = PublishedPost.model_validate(
        {
            "account_id": "acct1",
            "posted": True,
            "tweet_id": "123",
            "result": finalize_dict,
        }
    )
    assert post.result == finalize_dict
    assert "'tweet' in post.result" and "tweet" in post.result


def test_published_post_registered_in_artifacts():
    """PublishedPost is registered in ARTIFACTS."""
    assert ArtifactKey.PUBLISHED_POST in ARTIFACTS
    assert ARTIFACTS[ArtifactKey.PUBLISHED_POST].model == PublishedPost


# ──────────────────────────────────────────────────────────────────
# ActLive Tests
# ──────────────────────────────────────────────────────────────────


def test_act_live_minimal(mock_account: AccountDocument):
    """ActLive requires account, tick_ctx, guardian, twitter, post_registry, run_id."""
    live = ActLive(
        account=mock_account,
        tick_ctx="mock_tick_ctx",
        guardian="mock_guardian",
        twitter="mock_twitter",
        post_registry="mock_post_registry",
        run_id="run123",
    )
    assert live.account.account_id == "test_acct"
    assert live.run_id == "run123"
    assert live.pipeline_hash is None
    assert live.copied_exclude == frozenset()
    assert live.max_regeneration_rounds == 10
    assert live.bypass_post_cooldown is False


def test_act_live_with_all_fields(mock_account: AccountDocument):
    """ActLive with all optional fields set."""
    excluded = frozenset(["tweet1", "tweet2"])
    live = ActLive(
        account=mock_account,
        tick_ctx="mock_tick_ctx",
        guardian="mock_guardian",
        twitter="mock_twitter",
        post_registry="mock_post_registry",
        run_id="run123",
        pipeline_hash="spec_v1_hash",
        copied_exclude=excluded,
        max_regeneration_rounds=5,
        bypass_post_cooldown=True,
    )
    assert live.pipeline_hash == "spec_v1_hash"
    assert live.copied_exclude == excluded
    assert live.max_regeneration_rounds == 5
    assert live.bypass_post_cooldown is True


# ──────────────────────────────────────────────────────────────────
# PostRunDeps Tests
# ──────────────────────────────────────────────────────────────────


def test_post_run_deps_build_without_live():
    """PostRunDeps.build() works without live kwarg (backward compatible)."""
    deps = PostRunDeps.build()
    assert deps.tick_data is not None
    assert deps.repo is not None
    assert deps.live is None


def test_post_run_deps_with_live(mock_account: AccountDocument):
    """PostRunDeps can be constructed with live kwarg."""
    live = ActLive(
        account=mock_account,
        tick_ctx="mock_ctx",
        guardian="mock_guardian",
        twitter="mock_twitter",
        post_registry="mock_registry",
        run_id="run123",
    )
    deps = PostRunDeps.build()
    deps.live = live
    assert deps.live.account.account_id == "test_acct"
    assert deps.live.run_id == "run123"


# ──────────────────────────────────────────────────────────────────
# ArtifactKey Enum Tests
# ──────────────────────────────────────────────────────────────────


def test_artifact_keys_include_act_tail():
    """ArtifactKey enum includes all ACT artifacts."""
    assert ArtifactKey.COMPOSED_POST.value == "composed_post"
    assert ArtifactKey.SAFETY_VERDICT.value == "safety_verdict"
    assert ArtifactKey.PUBLISHED_POST.value == "published_post"


def test_artifacts_dict_has_16_entries():
    """ARTIFACTS dict has 16 entries: 8 SENSE + 3 post-ACT + 5 reply-family (doc 12)."""
    assert len(ARTIFACTS) == 16
    assert len(ArtifactKey) == 16


def test_all_artifact_keys_in_artifacts_dict():
    """All ArtifactKey enum members have ARTIFACTS entries."""
    for key in ArtifactKey:
        assert key in ARTIFACTS, f"Missing ARTIFACTS entry for {key}"
