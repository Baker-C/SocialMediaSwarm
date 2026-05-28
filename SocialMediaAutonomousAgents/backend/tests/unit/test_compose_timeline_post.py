"""Formatted timeline post assembly tests."""

from unittest.mock import patch

from app.hourly.compose_timeline_post import (
    COMPOSE_LENGTH_MAX_ATTEMPTS,
    assemble_formatted_body,
    compose_formatted_post,
    compute_post_length_budget,
    fits_post_budget,
)
from app.hourly.tweet_topic_preanalysis import GatheredTweet


def test_compute_post_length_budget_reserves_link() -> None:
    budget = compute_post_length_budget("https://t.co/abc123")
    assert budget.link_char_count == len("\n\nhttps://t.co/abc123")
    assert budget.body_char_budget == 280 - budget.link_char_count
    text_budget = budget.body_char_budget - budget.text_separator_char_count
    assert budget.opinion_char_max + budget.quip_char_max <= text_budget


def test_assemble_formatted_body_structure() -> None:
    body = assemble_formatted_body(
        "Opinion line one.",
        "Follow for Breaking News Commentary within Minutes",
        "https://x.com/i/status/1",
    )
    assert body.startswith("Opinion line one.")
    assert "\n\nFollow for Breaking News" in body
    assert body.endswith("https://x.com/i/status/1")
    assert len(body) <= 280


def test_fits_post_budget_rejects_long_opinion() -> None:
    link = "https://t.co/XY19m932a7"
    budget = compute_post_length_budget(link)
    opinion = "x" * 300
    quip = "Follow for updates"
    assert not fits_post_budget(opinion, quip, budget)


def test_compose_retries_until_llm_fits() -> None:
    too_long = {"opinion": "O" * 200, "quip": "Q" * 80}
    ok = {
        "opinion": "Short opinion that fits.",
        "quip": "Follow for Breaking News Commentary within Minutes",
    }

    winner = GatheredTweet(
        tweet_id="1",
        text="Source tweet text",
        popularity_score=1.0,
        metrics={"tweet_permalink": "https://x.com/i/status/1"},
    )

    with patch("app.hourly.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.side_effect = [too_long, ok]
        body = compose_formatted_post(winner, "News")

    assert mock_claude.return_value.messages_json_dict.call_count == 2
    assert len(body) <= 280
    assert body.endswith("https://x.com/i/status/1")
    assert "Follow for Breaking News" in body


def test_compose_fallback_without_llm() -> None:
    winner = GatheredTweet(
        tweet_id="1",
        text="Breaking news about policy",
        popularity_score=5.0,
        metrics={
            "tweet_permalink": "https://x.com/i/status/1",
            "media": [{"type": "photo", "url": "https://pbs.twimg.com/media/ref.jpg"}],
        },
    )
    with patch("app.hourly.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = False
        body = compose_formatted_post(winner, "News")
    assert "https://x.com/i/status/1" in body
    assert len(body) <= 280
    parts = body.split("\n\n")
    assert len(parts) >= 2


def test_compose_length_attempt_cap() -> None:
    assert COMPOSE_LENGTH_MAX_ATTEMPTS >= 2
