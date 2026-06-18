from app.agents.safety_guardian import SafetyGuardian


def test_safety_rejects_json_leak_and_fallback_markers():
    g = SafetyGuardian()
    bad_json = 'Political News — { "account": { "account_id": "JohnJames_News"'
    ok, reason = g.evaluate(bad_json)
    assert not ok
    assert reason == "prompt_json_leak"

    bad_fb = "Political News — seed angle 1 #automation"
    ok2, reason2 = g.evaluate(bad_fb.ljust(150, "."))
    assert not ok2
    assert reason2 == "fallback_template_leak"
