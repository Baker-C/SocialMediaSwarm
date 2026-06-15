"""Deterministic punctuation polish (pure, parameterized)."""

from app.interval.orchestration.voice_polish import polish_post, polish_text
from app.models.account import default_punctuation_rules


def test_em_dash_becomes_comma():
    out = polish_text("Wait, this is wild — the White House moved again.")
    assert "—" not in out.polished
    assert out.changed


def test_double_hyphen_between_words_becomes_comma():
    out = polish_text("They messaged again -- loudly.")
    assert "--" not in out.polished
    assert out.changed


def test_collapses_multiple_spaces():
    out = polish_text("Seriously?   That   again.")
    assert "  " not in out.polished


def test_strips_leading_punctuation_and_space():
    out = polish_text("  , and then it happened.")
    assert not out.polished.startswith(",")
    assert not out.polished.startswith(" ")


def test_replacement_none_deletes_match():
    rules = [{"pattern": r"\bDELETEME\b", "replacement": None}]
    out = polish_text("keep DELETEME this", rules)
    assert "DELETEME" not in out.polished


def test_empty_input_is_noop():
    out = polish_text("")
    assert out.polished == ""
    assert not out.changed


def test_clean_text_unchanged():
    rules = default_punctuation_rules()
    out = polish_text("Wild how this keeps happening, same loop every week.", rules)
    assert not out.changed


def test_polish_post_is_alias_of_polish_text():
    a = polish_post("a — b")
    b = polish_text("a — b")
    assert a.polished == b.polished
