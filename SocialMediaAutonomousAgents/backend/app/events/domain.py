"""Domain event bus.

A deliberately small in-process publish channel for app-wide domain signals
(e.g. an account's niche score changing). It is SEPARATE from the pipeline run
event stream in ``app/pipeline/events`` — those are run-scoped, event-sourced,
and persisted to JetStream; these are coarse domain facts other code can react
to. Sinks are plain callables; a failing sink is logged and never propagates.

A default sink publishes each event to NATS core (subject ``domain.<kind>``),
degrading to a no-op when NATS is unavailable, so emission never breaks callers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DOMAIN_SUBJECT_PREFIX = "domain"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DomainEvent(BaseModel):
    """One immutable domain fact (e.g. ``account.niche.incremented``)."""

    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    occurred_at: str = Field(default_factory=_now_iso)
    kind: str
    aggregate_type: str
    aggregate_id: str
    data: dict[str, Any] = Field(default_factory=dict)

    def subject(self, prefix: str = DOMAIN_SUBJECT_PREFIX) -> str:
        """Core-NATS subject: ``domain.<kind>`` (e.g. ``domain.account.niche.incremented``)."""
        return f"{prefix}.{self.kind}"


DomainEventSink = Callable[[DomainEvent], None]


class InMemoryDomainSink:
    """Collects emitted events for assertions in tests."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def __call__(self, event: DomainEvent) -> None:
        self.events.append(event)


def _nats_sink(event: DomainEvent) -> None:
    """Publish to NATS core; no-op when NATS is disabled/unreachable."""
    from app.infrastructure.nats_client import get_nats_client

    get_nats_client().publish_domain_event(event.subject(), event.model_dump())


class DomainEventBus:
    """Fan-out dispatcher. Sinks run in registration order; failures are isolated."""

    def __init__(self) -> None:
        self._sinks: list[DomainEventSink] = []

    def subscribe(self, sink: DomainEventSink) -> None:
        self._sinks.append(sink)

    def unsubscribe(self, sink: DomainEventSink) -> None:
        try:
            self._sinks.remove(sink)
        except ValueError:
            pass

    def emit(self, event: DomainEvent) -> None:
        for sink in self._sinks:
            try:
                sink(event)
            except Exception:
                logger.exception("domain event sink failed kind=%s", event.kind)


domain_event_bus = DomainEventBus()
domain_event_bus.subscribe(_nats_sink)


def emit_domain_event(
    *,
    kind: str,
    aggregate_type: str,
    aggregate_id: str,
    data: dict[str, Any] | None = None,
) -> DomainEvent:
    """Build and dispatch a :class:`DomainEvent`; returns the emitted event."""
    event = DomainEvent(
        kind=kind,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        data=data or {},
    )
    domain_event_bus.emit(event)
    return event
