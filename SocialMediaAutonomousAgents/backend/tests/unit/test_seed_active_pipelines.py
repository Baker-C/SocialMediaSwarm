"""seed_active_pipelines: choose 1-3 valid posting templates as active specs."""

from __future__ import annotations

from app.services.pipeline_spec_repository import seed_active_pipelines


class _FakeSpecRepo:
    def __init__(self) -> None:
        self.saved: list = []

    def save_active_template(self, spec, kind: str = "post") -> None:
        self.saved.append(spec)


def test_seed_persists_chosen_and_clamps_to_three():
    repo = _FakeSpecRepo()
    out = seed_active_pipelines("acct", ["standard", "lean", "own_voice", "rapid_fire"], repo=repo)
    assert out == ["standard", "lean", "own_voice"]  # 4th dropped by the clamp
    assert [s.template_id for s in repo.saved] == ["standard", "lean", "own_voice"]
    assert all(s.status == "active" and s.account_id == "acct" for s in repo.saved)


def test_seed_dedupes_repeats():
    repo = _FakeSpecRepo()
    out = seed_active_pipelines("acct", ["lean", "lean"], repo=repo)
    assert out == ["lean"]
    assert [s.template_id for s in repo.saved] == ["lean"]


def test_seed_drops_unknown_or_non_posting_templates_and_falls_back():
    # "reply_mode" is a kind="reply" spec, excluded from the posting set; "bogus" is unknown.
    repo = _FakeSpecRepo()
    out = seed_active_pipelines("acct", ["bogus", "reply_mode"], repo=repo)
    assert out == ["standard"]
    assert [s.template_id for s in repo.saved] == ["standard"]


def test_seed_empty_defaults_to_standard():
    repo = _FakeSpecRepo()
    out = seed_active_pipelines("acct", [], repo=repo)
    assert out == ["standard"]
    assert [s.template_id for s in repo.saved] == ["standard"]
