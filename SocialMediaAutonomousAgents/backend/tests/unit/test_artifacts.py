"""Contract tests for pipeline artifact Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.pipeline.types.artifacts import (
    ARTIFACTS,
    AccountBundle,
    ArtifactKey,
    OwnPostsPayload,
    RankedReferencesPayload,
    ReferencePatternBrief,
    SearchReferencesPayload,
    TimelineReferencesPayload,
)

ACCOUNT_BUNDLE_FIXTURE = {
    "account_id": "acct1",
    "profile": {"id": "99", "username": "test"},
    "tracked_tweet_ids": ["1"],
    "post_engagements": [],
    "errors": [],
}

TIMELINE_REFERENCES_FIXTURE = {
    "timeline_reference_tweets": [{"id": "t1", "text": "hello https://x.com/1"}],
    "reference_errors": [],
}

SEARCH_REFERENCES_FIXTURE = {
    "search_reference_tweets": [{"id": "s1", "text": "search hit", "source": "search_recent"}],
    "search_queries": ["news"],
    "per_query_counts": {"news": 1},
    "reference_errors": [],
}

OWN_POSTS_FIXTURE = {
    "account_id": "acct1",
    "tweet_ids": ["p1"],
    "posts": [{"account_id": "acct1", "tweet_id": "p1", "like_count": 5}],
}

RANKED_FIXTURE = {
    "ranked": [
        {
            "tweet_id": "t1",
            "text": "one",
            "popularity_score": 10.0,
            "metrics": {},
        }
    ],
    "winner": {
        "tweet_id": "t1",
        "text": "one",
        "popularity_score": 10.0,
        "metrics": {},
    },
}

BRIEF_FIXTURE = {
    "source": "timeline",
    "post_count": 1,
    "pattern_summary": "Political news hooks perform well.",
    "winning_topics": ["politics"],
    "voice_signals": ["direct"],
    "recommended_constraints": ["avoid hype"],
    "features": {"top_n": 1},
}


@pytest.mark.parametrize(
    "key,fixture",
    [
        (ArtifactKey.ACCOUNT_BUNDLE, ACCOUNT_BUNDLE_FIXTURE),
        (ArtifactKey.TIMELINE_REFERENCES, TIMELINE_REFERENCES_FIXTURE),
        (ArtifactKey.SEARCH_REFERENCES, SEARCH_REFERENCES_FIXTURE),
        (ArtifactKey.OWN_POSTS, OWN_POSTS_FIXTURE),
        (ArtifactKey.TIMELINE_RANKED, RANKED_FIXTURE),
        (ArtifactKey.OWN_POSTS_RANKED, RANKED_FIXTURE),
        (ArtifactKey.TIMELINE_ANALYSIS, BRIEF_FIXTURE),
        (ArtifactKey.OWN_POSTS_ANALYSIS, {**BRIEF_FIXTURE, "source": "own_posts"}),
    ],
)
def test_artifact_fixture_validates(key: ArtifactKey, fixture: dict) -> None:
    model = ARTIFACTS[key].model
    validated = model.model_validate(fixture)
    assert validated is not None


def test_account_bundle_requires_account_id() -> None:
    with pytest.raises(ValidationError):
        AccountBundle.model_validate({"profile": {}})


def test_timeline_references_accepts_merge_metadata() -> None:
    payload = TimelineReferencesPayload.model_validate(
        {
            **TIMELINE_REFERENCES_FIXTURE,
            "search_merged_count": 2,
            "search_queries_run": ["q1"],
        }
    )
    assert payload.search_merged_count == 2


def test_reference_pattern_brief_skipped_shape() -> None:
    brief = ReferencePatternBrief.model_validate(
        {"skipped": True, "skip_reason": "no_reference_with_urls", "source": "timeline"}
    )
    assert brief.skipped is True


def test_search_references_empty_queries() -> None:
    payload = SearchReferencesPayload.model_validate(
        {"search_reference_tweets": [], "search_queries": [], "reference_errors": []}
    )
    assert payload.search_queries == []


def test_ranked_empty_winner() -> None:
    payload = RankedReferencesPayload.model_validate({"ranked": [], "winner": None})
    assert payload.winner is None


def test_own_posts_payload() -> None:
    payload = OwnPostsPayload.model_validate(OWN_POSTS_FIXTURE)
    assert payload.account_id == "acct1"
