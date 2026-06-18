"""Niche scoring capability.

Mutates an account's popular-niche list and emits a domain event per change.
Rules (see app/models/niche.py for bounds):

- A niche starts at 0 the first time it is seen.
- Every subsequent sighting bumps its score by +1, capped at NICHE_SCORE_MAX (5).
- An adjustment that pushes the score below NICHE_SCORE_MIN (-2) deletes the niche.

This is a standalone backend capability — it is NOT wired into the posting
pipeline. Callers load nothing themselves: pass an ``account_id`` and a repo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from app.events.domain import DomainEvent, emit_domain_event
from app.models.account import AccountDocument
from app.models.niche import (
    NICHE_SCORE_INITIAL,
    NICHE_SCORE_MAX,
    NICHE_SCORE_MIN,
    Niche,
)
from app.services.account_repository import AccountRepository

NicheAction = Literal["created", "incremented", "decremented", "capped", "deleted", "noop"]


@dataclass
class NicheChange:
    """Outcome of one niche mutation (also the domain-event payload source)."""

    action: NicheAction
    niche: str
    old_score: int | None
    new_score: int | None
    times_updated: int


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find(niches: list[Niche], text: str) -> Niche | None:
    key = text.strip().casefold()
    for n in niches:
        if n.niche.strip().casefold() == key:
            return n
    return None


def apply_niche_delta(
    niches: list[Niche],
    text: str,
    delta: int,
    *,
    create_at_initial: bool = False,
) -> NicheChange:
    """Pure mutation of ``niches`` in place. Returns what happened.

    ``create_at_initial`` controls the absent case: a sighting creates the niche
    at the initial score (delta is not applied on creation); a bare adjustment of
    an unknown niche is a no-op.
    """
    text = text.strip()
    if not text:
        return NicheChange("noop", text, None, None, 0)

    existing = _find(niches, text)

    if existing is None:
        if not create_at_initial:
            return NicheChange("noop", text, None, None, 0)
        created = Niche(niche=text, score=NICHE_SCORE_INITIAL)
        niches.append(created)
        return NicheChange("created", created.niche, None, created.score, created.times_updated)

    old = existing.score
    raw = old + delta
    new = min(NICHE_SCORE_MAX, raw)
    existing.times_updated += 1
    existing.updated_at = _now_iso()

    if new < NICHE_SCORE_MIN:
        niches.remove(existing)
        return NicheChange("deleted", existing.niche, old, new, existing.times_updated)

    existing.score = new
    if raw > NICHE_SCORE_MAX:
        action: NicheAction = "capped"
    elif delta >= 0:
        action = "incremented"
    else:
        action = "decremented"
    return NicheChange(action, existing.niche, old, new, existing.times_updated)


def _emit(account_id: str, change: NicheChange) -> DomainEvent:
    return emit_domain_event(
        kind=f"account.niche.{change.action}",
        aggregate_type="account",
        aggregate_id=account_id,
        data={
            "niche": change.niche,
            "old_score": change.old_score,
            "new_score": change.new_score,
            "times_updated": change.times_updated,
        },
    )


def _mutate(account_id: str, text: str, delta: int, create_at_initial: bool, repo: AccountRepository) -> NicheChange:
    account = repo.load(account_id)
    if account is None:
        raise LookupError(f"Account not found: {account_id}")
    change = apply_niche_delta(
        account.soul.niches, text, delta, create_at_initial=create_at_initial
    )
    if change.action != "noop":
        repo.save(account)
        _emit(account_id, change)
    return change


def record_niche_sighting(
    account_id: str, niche_text: str, *, repo: AccountRepository | None = None
) -> NicheChange:
    """Register that ``niche_text`` was seen: create it at 0, or bump +1 (cap 5)."""
    return _mutate(account_id, niche_text, +1, True, repo or AccountRepository())


def adjust_niche_score(
    account_id: str, niche_text: str, delta: int, *, repo: AccountRepository | None = None
) -> NicheChange:
    """Apply an arbitrary score delta to an existing niche (no-op if unknown).

    Caps at 5; deletes the niche if the result would fall below -2.
    """
    return _mutate(account_id, niche_text, delta, False, repo or AccountRepository())
