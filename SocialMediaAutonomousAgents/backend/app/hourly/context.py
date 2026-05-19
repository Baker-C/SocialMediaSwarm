"""Per-slot execution context (services + tick metadata)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.hourly.schemas import TickMode
from app.models.account import AccountDocument

if TYPE_CHECKING:
    from app.agents.content_creator import ContentCreator
    from app.agents.safety_guardian import SafetyGuardian
    from app.services.account_repository import AccountRepository
    from app.services.post_registry import TrackedPostRepository
    from app.services.tick_data_service import TickDataService
    from app.services.twitter_service import TwitterService


@dataclass
class TickContext:
    repo: AccountRepository
    twitter: TwitterService
    creator: ContentCreator
    guardian: SafetyGuardian
    tick_data: TickDataService
    post_registry: TrackedPostRepository | None
    slot: str
    now_iso: str
    mode: TickMode
    force_account_ids: frozenset[str] | None
    max_candidates: int = 5
    max_regeneration_rounds: int = 3
    bypass_post_cooldown: bool = False
    accounts: list[AccountDocument] = field(default_factory=list)
    # account_id -> last_post_slot before this tick's reservation (scheduled mode)
    slot_reservations: dict[str, str | None] = field(default_factory=dict)
    active_post_locks: dict[str, str] = field(default_factory=dict)
    active_post_file_locks: dict[str, object] = field(default_factory=dict)
