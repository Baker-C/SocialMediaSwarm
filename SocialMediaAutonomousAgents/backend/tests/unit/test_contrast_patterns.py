"""Account contrast-pattern defaults and compose prompt wiring (was test_negative_semantics)."""

from unittest.mock import patch

from app.interval.compose_timeline_post import compose_formatted_post
from app.interval.tweet_topic_preanalysis import GatheredTweet
from app.models.account import (
    default_contrast_patterns,
    format_contrast_patterns_for_prompt,
)
from app.services.account_repository import document_to_account


def test_default_contrast_patterns_are_negative_by_default() -> None:
    pats = default_contrast_patterns()
    assert pats and all(p["correlation"] == "negative" for p in pats)
    joined = " ".join(p["text"] for p in pats).lower()
    assert "em dash" in joined


def test_format_contrast_patterns_splits_avoid_and_lean() -> None:
    block = format_contrast_patterns_for_prompt(
        [
            {"text": "hedge words", "correlation": "negative"},
            {"text": "punchy openers", "correlation": "positive"},
        ]
    )
    assert "Avoid these patterns" in block and "hedge words" in block
    assert "Lean into these patterns" in block and "punchy openers" in block


def test_document_to_account_backfills_contrast_patterns() -> None:
    acc = document_to_account({"account_id": "x", "niche": "News"})
    assert len(acc.contrast_patterns) >= 3


def test_compose_user_prompt_includes_contrast_guidance() -> None:
    winner = GatheredTweet(
        tweet_id="1",
        text="Source",
        popularity_score=1.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )
    custom = [{"text": "Custom avoided phrase", "correlation": "negative"}]

    with patch("app.interval.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.return_value = {
            "post": "Sharp take on the story.",
        }
        compose_formatted_post(
            winner,
            "News",
            account_posting_prompt="Structure rules",
            account_personality="Provocative left-leaning voice",
            contrast_patterns=custom,
        )
        user = mock_claude.return_value.messages_json_dict.call_args.kwargs["user"]
        assert "Custom avoided phrase" in user
        assert "Structure rules" in user
        assert "Provocative left-leaning voice" in user
        assert "Avoid these patterns" in user
