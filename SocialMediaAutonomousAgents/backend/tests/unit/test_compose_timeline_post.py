"""Formatted timeline post assembly tests."""

from app.hourly.compose_timeline_post import assemble_formatted_body
from app.hourly.tweet_topic_preanalysis import GatheredTweet


def test_assemble_formatted_body_structure() -> None:
    body = assemble_formatted_body(
        "Big headline",
        "Story line one.",
        "https://x.com/i/status/1",
    )
    assert body.startswith("Big headline")
    assert "\n\nStory line one.\n\nhttps://x.com/i/status/1" in body


def test_assemble_truncates_to_fit_280() -> None:
    long_story = "word " * 80
    body = assemble_formatted_body(
        "Headline " * 20,
        long_story,
        "https://x.com/i/status/99",
        max_len=280,
    )
    assert len(body) <= 280
    assert body.endswith("https://x.com/i/status/99")


def test_compose_formatted_post_fallback_without_llm() -> None:
    from unittest.mock import patch

    from app.hourly.compose_timeline_post import compose_formatted_post

    winner = GatheredTweet(
        tweet_id="1",
        text="Breaking news about policy",
        interaction_score=5,
        metrics={
            "tweet_permalink": "https://x.com/i/status/1",
            "media": [
                {
                    "type": "photo",
                    "url": "https://pbs.twimg.com/media/ref.jpg",
                }
            ],
        },
    )
    with patch("app.hourly.compose_timeline_post.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = False
        body = compose_formatted_post(winner, "News")
    assert "https://x.com/i/status/1" in body
    assert "https://pbs.twimg.com/media/ref.jpg" not in body
    assert len(body) <= 280
    assert body.split("\n\n")[0]  # headline line has no leading emoji
