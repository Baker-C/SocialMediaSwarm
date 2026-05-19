from app.agents.safety_guardian import SafetyGuardian
from app.hourly.orchestration.voice_select import select_polished_from_ranked


def test_skips_soft_flag_candidate_and_uses_clean_one():
    guardian = SafetyGuardian()
    ranked = [
        "It's not about the border, it's about power plays in an election year.",
        "Seriously? They delayed the vote again. Same circus, new week.",
    ]
    body, reject, trace = select_polished_from_ranked(guardian, ranked)
    assert body is not None
    assert "it's not about" not in body.lower()
    assert trace is not None
    assert trace.get("soft_flag") is False
