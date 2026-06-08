from app.metrics.derived import (
    compute_rates,
    compute_velocity,
    extract_entities,
    extract_text_features,
    normalized_reference_score,
)


def test_compute_rates_none_without_impressions() -> None:
    rates = compute_rates({"like_count": 10, "reply_count": 2, "retweet_count": 1, "quote_count": 1})
    assert rates["engagement_rate"] is None
    assert rates["reply_rate"] is None
    assert rates["like_rate"] is None


def test_compute_rates_with_impressions() -> None:
    rates = compute_rates(
        {"like_count": 10, "reply_count": 2, "retweet_count": 1, "quote_count": 1, "impression_count": 100}
    )
    assert rates["engagement_rate"] == 0.14
    assert rates["reply_rate"] == 0.02
    assert rates["like_rate"] == 0.10


def test_compute_velocity_requires_progress() -> None:
    assert compute_velocity(None, {"impression_count": 10}) is None
    assert (
        compute_velocity(
            {"like_count": 10, "impression_count": 200},
            {"like_count": 12, "impression_count": 190},
        )
        is None
    )


def test_compute_velocity_value() -> None:
    v = compute_velocity(
        {"like_count": 10, "reply_count": 1, "impression_count": 100},
        {"like_count": 20, "reply_count": 3, "impression_count": 200},
    )
    assert v == 0.12


def test_normalized_reference_score_fallback() -> None:
    raw = normalized_reference_score({"like_count": 10}, None)
    norm = normalized_reference_score({"like_count": 10}, 10000)
    assert raw > norm


def test_extract_text_features_and_entities() -> None:
    features = extract_text_features("WOW #AI is wild @Alice https://x.com/a?")
    assert features["hashtag_count"] == 1
    assert features["mention_count"] == 1
    assert features["url_count"] == 1
    tags = extract_entities({"text": "hello #AI @Bob"})
    assert "ai" in tags
    assert "@bob" in tags
