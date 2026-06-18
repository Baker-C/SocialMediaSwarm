"""Domain events — lightweight, app-wide signals decoupled from the pipeline run
stream (``app/pipeline/events``). Emit with :func:`emit_domain_event`."""

from app.events.domain import (
    DomainEvent,
    InMemoryDomainSink,
    domain_event_bus,
    emit_domain_event,
)

__all__ = [
    "DomainEvent",
    "InMemoryDomainSink",
    "domain_event_bus",
    "emit_domain_event",
]
