import json

from app.agents.safety_guardian import SafetyGuardian
from app.hourly_crew.context_extract import extract_context_hints
from app.hourly_crew.llm_pipeline import _fallback_candidates


def test_extract_context_from_bundle_json():
    bundle = json.dumps(
        {
            "account": {
                "topic_preanalysis": {"selected_topic_label": "Congressional stock trading"},
                "post_engagements": [{"text": "Members trade stocks while legislating."}],
            },
            "niche_context": {
                "discourse_summary": "Account niche: Political News.",
                "trend_names": ["#Election2026"],
            },
        }
    )
    hints = extract_context_hints(bundle, "Political News")
    assert hints["topic"] == "Congressional stock trading"
    assert "Members trade" in hints["sample_post"]


def test_fallback_never_includes_raw_json():
    bundle = json.dumps({"account": {"account_id": "x", "profile": {"username": "u"}}})
    posts = _fallback_candidates("Political News", bundle, 3)
    assert len(posts) == 3
    for p in posts:
        assert "{" not in p
        assert '"account_id"' not in p
        assert "#automation" not in p
        assert "angle 1" not in p.lower()
        assert len(p) >= 50


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
