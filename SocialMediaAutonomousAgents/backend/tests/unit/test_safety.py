from unittest.mock import patch

from app.agents.safety_guardian import SafetyGuardian, is_niche_mismatch_reject


def test_safety_too_short():
    g = SafetyGuardian()
    ok, reason = g.evaluate("hi")
    assert not ok
    assert reason == "too_short"


def test_safety_ok_without_niche():
    g = SafetyGuardian()
    ok, _ = g.evaluate("This is long enough for a post body.")
    assert ok


def test_safety_ok_with_niche_when_claude_approves():
    g = SafetyGuardian()
    with patch("app.agents.safety_guardian.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.return_value = {
            "fits_niche": True,
            "reason": "political topic",
        }
        ok, reason = g.evaluate(
            "Senate vote on defense bill draws backlash from both parties.\n\n"
            "Lawmakers split ahead of the deadline.\n\nhttps://t.co/abc",
            niche="Political News",
        )
    assert ok
    assert reason is None


def test_safety_niche_mismatch_rejects():
    g = SafetyGuardian()
    with patch("app.agents.safety_guardian.get_claude_client") as mock_claude:
        mock_claude.return_value.enabled = True
        mock_claude.return_value.messages_json_dict.return_value = {
            "fits_niche": False,
            "reason": "sports scores not political news",
        }
        ok, reason = g.evaluate(
            "Lakers win in overtime thriller.\n\n"
            "The game went to double OT.\n\nhttps://t.co/abc",
            niche="Political News",
        )
    assert not ok
    assert reason is not None
    assert is_niche_mismatch_reject(reason)
    assert "sports" in reason


def test_is_niche_mismatch_reject_helper() -> None:
    assert is_niche_mismatch_reject("niche_mismatch:off topic")
    assert not is_niche_mismatch_reject("too_short")
