"""Niche scoring rules and domain-event emission."""

from __future__ import annotations

import pytest

from app.events.domain import InMemoryDomainSink, domain_event_bus
from app.models.account import AccountDocument
from app.models.niche import NICHE_SCORE_MAX, Niche
from app.services import niche_service
from app.services.niche_service import apply_niche_delta


# ── pure list mutation ────────────────────────────────────────────────────────

def test_first_sighting_creates_at_zero():
    niches: list[Niche] = []
    change = apply_niche_delta(niches, "Congress stock trading", +1, create_at_initial=True)
    assert change.action == "created"
    assert change.new_score == 0
    assert len(niches) == 1 and niches[0].score == 0


def test_subsequent_sightings_increment_and_cap_at_five():
    niches: list[Niche] = []
    apply_niche_delta(niches, "drama", +1, create_at_initial=True)  # created at 0
    for _ in range(10):
        apply_niche_delta(niches, "drama", +1, create_at_initial=True)
    assert niches[0].score == NICHE_SCORE_MAX
    # the update that hit the ceiling reports "capped"
    last = apply_niche_delta(niches, "drama", +1, create_at_initial=True)
    assert last.action == "capped"
    assert last.new_score == NICHE_SCORE_MAX


def test_matching_is_case_and_whitespace_insensitive():
    niches: list[Niche] = []
    apply_niche_delta(niches, "Protest", +1, create_at_initial=True)
    change = apply_niche_delta(niches, "  protest ", +1, create_at_initial=True)
    assert change.action == "incremented"
    assert len(niches) == 1 and niches[0].score == 1


def test_drop_below_min_deletes_niche():
    niches = [Niche(niche="gossip", score=-2)]
    change = apply_niche_delta(niches, "gossip", -1, create_at_initial=False)
    assert change.action == "deleted"
    assert niches == []


def test_adjusting_unknown_niche_is_noop():
    niches: list[Niche] = []
    change = apply_niche_delta(niches, "unknown", -1, create_at_initial=False)
    assert change.action == "noop"
    assert niches == []


# ── service: persistence + domain event ───────────────────────────────────────

class _FakeRepo:
    def __init__(self, account: AccountDocument) -> None:
        self.account = account
        self.saved = 0

    def load(self, account_id: str) -> AccountDocument | None:
        return self.account if account_id == self.account.account_id else None

    def save(self, account: AccountDocument) -> None:
        self.account = account
        self.saved += 1


@pytest.fixture
def captured_events():
    sink = InMemoryDomainSink()
    domain_event_bus.subscribe(sink)
    yield sink.events
    domain_event_bus.unsubscribe(sink)


def _account() -> AccountDocument:
    return AccountDocument(account_id="acct1", category="News")


def test_record_sighting_persists_and_emits(captured_events):
    repo = _FakeRepo(_account())

    niche_service.record_niche_sighting("acct1", "Election fraud claims", repo=repo)
    niche_service.record_niche_sighting("acct1", "Election fraud claims", repo=repo)

    assert repo.account.niches[0].score == 1
    assert repo.saved == 2

    kinds = [e.kind for e in captured_events]
    assert kinds == ["account.niche.created", "account.niche.incremented"]
    assert captured_events[-1].aggregate_id == "acct1"
    assert captured_events[-1].data["new_score"] == 1


def test_noop_does_not_save_or_emit(captured_events):
    repo = _FakeRepo(_account())
    change = niche_service.adjust_niche_score("acct1", "never-seen", -1, repo=repo)
    assert change.action == "noop"
    assert repo.saved == 0
    assert captured_events == []
