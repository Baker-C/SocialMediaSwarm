"""Unit tests for reference analysis → compose prompt formatting."""

from app.interval.reference_context import format_reference_context_for_compose


def test_format_reference_context_full_briefs() -> None:
    block = format_reference_context_for_compose(
        {
            "pattern_summary": "Short punchy takes win.",
            "winning_topics": ["elections", "economy"],
            "voice_signals": ["emphatic caps", "loose grammar"],
            "recommended_constraints": ["avoid em dashes"],
        },
        {
            "pattern_summary": "Quips drive replies.",
            "voice_signals": ["question hooks"],
        },
    )
    assert "Short punchy takes win." in block
    assert "elections" in block
    assert "emphatic caps" in block
    assert "Quips drive replies." in block
    assert "question hooks" in block
    assert "do not copy wording" in block.lower()


def test_format_reference_context_skipped_own_posts() -> None:
    block = format_reference_context_for_compose(
        {"pattern_summary": "Trending anger."},
        {"skipped": True, "skip_reason": "insufficient_own_posts"},
    )
    assert "Trending anger." in block
    assert "not enough tracked post history" in block.lower()


def test_format_reference_context_empty() -> None:
    block = format_reference_context_for_compose(None, None)
    assert "No reference analysis available" in block
