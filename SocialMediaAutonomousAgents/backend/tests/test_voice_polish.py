from unittest.mock import patch

from app.hourly.orchestration.voice_polish import (
    apply_casual_sentence_starts,
    detect_voice_violations,
    polish_post,
)


def test_removes_em_dash_and_banned_phrase():
    raw = (
        "Wait, this is wild. Furthermore, the White House moved again "
        "and it's worth noting that Congress sat out."
    )
    out = polish_post(raw)
    assert "—" not in out.polished
    assert "furthermore" not in out.polished.lower()
    assert "worth noting" not in out.polished.lower()
    assert out.changed
    assert not out.soft_flag


def test_replaces_utilize_and_collapses_spaces():
    raw = "Seriously? They utilize robust messaging -- again."
    out = polish_post(raw)
    assert "utilize" not in out.polished.lower()
    assert "robust" not in out.polished.lower()
    assert "--" not in out.polished
    assert "  " not in out.polished
    assert not out.soft_flag


def test_soft_flag_contrast_not_x_its_y():
    raw = (
        "Wild take: it's not about immigration policy, it's about who holds power "
        "when Congress refuses to legislate."
    )
    out = polish_post(raw)
    assert out.soft_flag
    assert any("contrast" in v for v in out.violations)


def test_soft_flag_were_not_were():
    raw = "We're not having a policy debate, we're having a power struggle and everyone knows it."
    out = polish_post(raw)
    assert out.soft_flag
    assert "contrast_were_not" in out.violations


def test_soft_flag_no_no_staccato():
    raw = (
        "Seriously? No law passes. No fix sticks. And voters keep being told "
        "the other side is the whole problem."
    )
    out = polish_post(raw)
    assert out.soft_flag
    assert "contrast_no_no_staccato" in out.violations


def test_soft_flag_not_not_staccato():
    raw = "Wild. Not a policy fight. Not a budget fight. Just power theater."
    out = polish_post(raw)
    assert out.soft_flag
    assert "contrast_not_not_staccato" in out.violations


@patch("app.hourly.orchestration.voice_polish.random.random", return_value=1.0)
def test_clean_post_no_soft_flag(_mock_random):
    raw = "Wild how this keeps happening. Same loop, new headline every week."
    out = polish_post(raw)
    assert out.polished == raw
    assert not out.changed
    assert not out.soft_flag
    assert not out.violations


def test_casual_sentence_starts_lowercases_selected_sentences():
    text, notes = apply_casual_sentence_starts(
        "Wild how this keeps happening. Same loop, new headline every week.",
        probability=1.0,
    )
    assert text == "wild how this keeps happening. same loop, new headline every week."
    assert notes.count("casual:sentence_start_lower") == 2


def test_casual_sentence_starts_can_leave_caps():
    text, notes = apply_casual_sentence_starts(
        "Wild how. Same loop.",
        probability=0.0,
    )
    assert text == "Wild how. Same loop."
    assert notes == []


@patch(
    "app.hourly.orchestration.voice_polish.random.random",
    side_effect=[0.0, 1.0, 1.0],
)
def test_polish_applies_casual_starts_after_passing_soft_flag(_mock_random):
    raw = "Wild how this keeps happening. Same loop, new headline every week."
    out = polish_post(raw)
    assert not out.soft_flag
    assert out.polished.startswith("wild how")
    assert "Same loop" in out.polished


def test_detect_violations_independent():
    assert detect_voice_violations("Furthermore, moreover.") == [
        "phrase_furthermore",
        "phrase_moreover",
    ]
