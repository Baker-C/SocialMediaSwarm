"""Event sinks: publish to NATS JetStream, or collect in memory for tests."""

from __future__ import annotations

import logging

from app.pipeline.events.types import PipelineEvent

logger = logging.getLogger(__name__)


class InMemorySink:
    """Collects events for assertions in unit/integration tests."""

    def __init__(self) -> None:
        self.events: list[PipelineEvent] = []

    def on_event(self, event: PipelineEvent) -> None:
        self.events.append(event)


class NatsPublishSink:
    """Publishes each event to JetStream.

    Producer code runs in worker threads; the client bridges to the FastAPI
    event loop internally, so ``on_event`` is non-blocking and never raises into
    the pipeline.
    """

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def client(self):
        if self._client is not None:
            return self._client
        from app.infrastructure.nats_client import get_nats_client

        return get_nats_client()

    def on_event(self, event: PipelineEvent) -> None:
        try:
            self.client.publish_event(event)
        except Exception:
            logger.exception(
                "failed to publish pipeline event seq=%s kind=%s", event.seq, event.kind
            )
