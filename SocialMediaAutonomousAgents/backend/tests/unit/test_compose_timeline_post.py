"""Soul-driven timeline post assembly tests."""

from unittest.mock import patch

from app.interval.compose_timeline_post import (
    COMPOSE_LENGTH_MAX_ATTEMPTS,
    assemble_formatted_body,
    compose_formatted_post,
    compute_post_length_budget,
    fits_post_budget,
)
from app.interval.tweet_topic_preanalysis import GatheredTweet


def test_compute_post_length_budget_reserves_link() -> None:
    budget = compute_post_length_budget("https://t.co/abc123")
    assert budget.link_char_count == len("\n\nhttps://t.co/abc123")
    assert budget.body_char_budget == 280 - budget.link_char_count


def test_assemble_formatted_body_structure() -> None:
    body = assemble_formatted_body(
        "wild take on the whole thing, this is NOT okay",
        "https://x.com/i/status/1",
    )
    assert body.startswith("wild take")
    assert "\n\nhttps://x.com/i/status/1" in body
    assert body.endswith("https://x.com/i/status/1")
    assert len(body) <= 280


def test_fits_post_budget_rejects_long_text() -> None:
    budget = compute_post_length_budget("https://t.co/XY19m932a7")
    assert not fits_post_budget("x" * 300, budget)


def test_compose_retries_until_llm_fits() -> None:
    too_long = {"post": "O" * 300}
    ok = {"post": "Short post that fits just fine."}

    winner = GatheredTweet(
        tweet_id="1",
        text="Source tweet text",
        popularity_score=1.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )

    with patch("app.interval.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.side_effect = [too_long, ok]
        body = compose_formatted_post(winner, "News")

    assert mock_claude.return_value.messages_json_dict.call_count == 2
    assert body is not None
    assert len(body) <= 280
    assert body.startswith("Short post that fits")
    assert body.endswith("https://x.com/i/status/1")


def test_compose_returns_none_without_llm() -> None:
    """No LLM → no fabricated fallback, just skip."""
    winner = GatheredTweet(
        tweet_id="1",
        text="Breaking news about policy",
        popularity_score=5.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )
    with patch("app.interval.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = False
        body = compose_formatted_post(winner, "News")
    assert body is None


def test_compose_returns_none_when_cannot_fit() -> None:
    """Model keeps returning an over-budget post → skip (no truncation fallback)."""
    winner = GatheredTweet(
        tweet_id="1",
        text="Source tweet text",
        popularity_score=1.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )
    with patch("app.interval.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.return_value = {"post": "x" * 500}
        body = compose_formatted_post(winner, "News")
    assert body is None
    assert mock_claude.return_value.messages_json_dict.call_count == COMPOSE_LENGTH_MAX_ATTEMPTS


def test_compose_length_attempt_cap() -> None:
    assert COMPOSE_LENGTH_MAX_ATTEMPTS >= 2


def test_compose_applies_punctuation_polish_to_body() -> None:
    """An em-dash in the model output must be gone from the final assembled body."""
    winner = GatheredTweet(
        tweet_id="1",
        text="Source tweet text",
        popularity_score=1.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )
    with patch("app.interval.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.return_value = {
            "post": "Wild take — the policy shifted again.",
        }
        body = compose_formatted_post(winner, "News")
    assert body is not None
    assert "—" not in body
    assert len(body) <= 280
