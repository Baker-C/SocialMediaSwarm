"""Topic-tailored fallback quips."""

from app.interval.compose_timeline_post import _topic_tailored_quip


def test_crypto_quip() -> None:
    q = _topic_tailored_quip("Bitcoin surges past $100k on ETF flows", "News", max_len=65)
    assert "crypto" in q.lower()


def test_political_quip() -> None:
    q = _topic_tailored_quip("Senate vote on defense bill splits both parties", "News", max_len=65)
    assert "political" in q.lower()


def test_generic_uses_niche() -> None:
    q = _topic_tailored_quip("Local bakery wins pie contest", "Broad News", max_len=65)
    assert "broad news" in q.lower() or "follow" in q.lower()
