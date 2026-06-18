"""Popular-niche model: a scored topic an account is observed to ride.

A niche is a topic in the general sense — a person, group, event, or thing that
happened (a protest, a fight, drama, gossip). Each carries a score that rises by
1 every time the niche is seen again, caps at 5, and — when pushed below -2 — is
pruned entirely. See ``app/services/niche_service.py`` for the mutation rules and
the domain event emitted on every change.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

# Score bounds. A niche starts at 0, climbs +1 per sighting up to MAX, and is
# deleted once it would drop below MIN (MIN itself is a retained floor).
NICHE_SCORE_INITIAL = 0
NICHE_SCORE_MAX = 5
NICHE_SCORE_MIN = -2


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Niche(BaseModel):
    """One scored topic on an account's popular-niche list."""

    niche: str
    score: int = NICHE_SCORE_INITIAL
    # How many times the score has been updated since creation (sightings + adjustments).
    times_updated: int = 0
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)
