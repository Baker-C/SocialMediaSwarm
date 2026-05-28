"""Account negative semantics defaults and compose prompt wiring."""

from unittest.mock import patch

from app.hourly.compose_timeline_post import compose_formatted_post
from app.hourly.tweet_topic_preanalysis import GatheredTweet
from app.models.account import (
    AccountDocument,
    default_negative_semantics,
    format_negative_semantics_for_prompt,
)
from app.services.account_repository import document_to_account


def test_default_negative_semantics_includes_ai_tells() -> None:
    items = default_negative_semantics()
    joined = " ".join(items).lower()
    assert "it's not that" in joined or "it's not x" in joined
    assert "em dash" in joined
    assert "same this" in joined or "same x" in joined


def test_format_negative_semantics_for_prompt_bullets() -> None:
    block = format_negative_semantics_for_prompt(["No em dash", "No thread voice"])
    assert block.startswith("- No em dash")
    assert "- No thread voice" in block


def test_document_to_account_backfills_empty_negative_semantics() -> None:
    acc = document_to_account({"account_id": "x", "niche": "News"})
    assert len(acc.negative_semantics) >= 3


def test_compose_user_prompt_includes_negative_semantics() -> None:
    winner = GatheredTweet(
        tweet_id="1",
        text="Source",
        popularity_score=1.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )
    custom = ["Custom banned phrase"]

    with patch("app.hourly.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.return_value = {
            "headline": "Head",
            "opinion": "Sharp take on the story.",
            "quip": "Follow for updates",
        }
        compose_formatted_post(
            winner,
            "News",
            account_system_prompt="Structure rules",
            account_personality="Provocative left-leaning voice",
            negative_semantics=custom,
        )
        user = mock_claude.return_value.messages_json_dict.call_args.kwargs["user"]
        assert "Custom banned phrase" in user
        assert "Structure rules" in user
        assert "Provocative left-leaning voice" in user
        assert "Banned semantics" in user
