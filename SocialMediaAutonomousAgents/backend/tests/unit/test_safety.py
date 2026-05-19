from app.agents.safety_guardian import SafetyGuardian


def test_safety_too_short():
    g = SafetyGuardian()
    ok, reason = g.evaluate("hi")
    assert not ok
    assert reason == "too_short"


def test_safety_ok():
    g = SafetyGuardian()
    ok, _ = g.evaluate("This is long enough for a post body.")
    assert ok
