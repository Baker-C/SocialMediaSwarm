"""NATS JetStream client singleton for pipeline event sourcing.

The pipeline produces events from synchronous worker threads, while the FastAPI
app (consumers, SSE) runs on the main asyncio loop. A single NATS connection lives
on the main loop; synchronous producers publish via ``run_coroutine_threadsafe``
against that loop. If NATS is disabled or unreachable, publishing degrades to a
logged no-op so the pipeline never breaks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, AsyncIterator

from app.core.config import settings
from app.pipeline.events.types import EVENT_SUBJECT_PREFIX, PipelineEvent

if TYPE_CHECKING:
    from nats.aio.client import Client as NATSClient
    from nats.js import JetStreamContext

logger = logging.getLogger(__name__)


class NatsClient:
    def __init__(self) -> None:
        self._nc: "NATSClient | None" = None
        self._js: "JetStreamContext | None" = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._warned_unavailable = False

    @property
    def connected(self) -> bool:
        return self._js is not None

    @property
    def js(self) -> "JetStreamContext | None":
        return self._js

    async def connect(self) -> None:
        """Connect on the current loop and ensure the events stream exists."""
        if not settings.nats_enabled:
            logger.info("NATS disabled (NATS_ENABLED=false); pipeline events not published")
            return
        import nats as nats_mod

        self._loop = asyncio.get_running_loop()
        try:
            self._nc = await nats_mod.connect(
                settings.nats_url,
                name="social-media-backend",
                max_reconnect_attempts=-1,
            )
        except Exception as exc:
            logger.warning(
                "NATS connect failed at %s: %s (pipeline events disabled)", settings.nats_url, exc
            )
            self._nc = None
            self._js = None
            return
        self._js = self._nc.jetstream()
        await self.ensure_stream()
        logger.info(
            "NATS connected at %s; JetStream stream=%s ready",
            settings.nats_url,
            settings.pipeline_events_stream,
        )

    async def ensure_stream(self) -> None:
        if self._js is None:
            return
        from nats.js.api import DiscardPolicy, RetentionPolicy, StorageType, StreamConfig

        cfg = StreamConfig(
            name=settings.pipeline_events_stream,
            subjects=[f"{EVENT_SUBJECT_PREFIX}.>"],
            storage=StorageType.FILE,
            retention=RetentionPolicy.LIMITS,
            discard=DiscardPolicy.OLD,
            max_age=float(settings.pipeline_events_max_age_days) * 24 * 3600,
        )
        try:
            await self._js.add_stream(cfg)
        except Exception:
            try:
                await self._js.update_stream(cfg)
            except Exception:
                logger.debug(
                    "ensure_stream: stream %s already present", settings.pipeline_events_stream
                )

    # --- producer (sync, called from worker threads) ----------------------

    def publish_event(self, event: PipelineEvent) -> None:
        if self._js is None or self._loop is None:
            if not self._warned_unavailable:
                logger.warning("NATS unavailable; dropping pipeline events")
                self._warned_unavailable = True
            return
        asyncio.run_coroutine_threadsafe(self._publish(event), self._loop)

    async def _publish(self, event: PipelineEvent) -> None:
        if self._js is None:
            return
        try:
            await self._js.publish(
                event.subject(),
                event.model_dump_json().encode("utf-8"),
                headers={"Nats-Msg-Id": event.msg_id()},
            )
        except Exception:
            logger.exception("JetStream publish failed seq=%s kind=%s", event.seq, event.kind)

    def publish_domain_event(self, subject: str, payload: dict) -> None:
        """Publish a domain event via NATS core (not the JetStream run stream).

        Fire-and-forget from sync callers; degrades to a no-op when NATS is
        unavailable so domain emission never breaks business logic.
        """
        if self._nc is None or self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._publish_domain(subject, payload), self._loop)

    async def _publish_domain(self, subject: str, payload: dict) -> None:
        if self._nc is None:
            return
        import json

        try:
            await self._nc.publish(subject, json.dumps(payload, default=str).encode("utf-8"))
        except Exception:
            logger.exception("domain publish failed subject=%s", subject)

    # --- consumer / read helpers (async, run on the main loop) -------------

    async def replay_run_events(self, run_id: str) -> list[PipelineEvent]:
        """Fetch all persisted events for one run, ordered by sequence."""
        if self._js is None:
            return []
        from nats.js.api import ConsumerConfig, DeliverPolicy

        subject = f"{EVENT_SUBJECT_PREFIX}.{run_id}.>"
        try:
            sub = await self._js.pull_subscribe(
                subject,
                durable=None,
                config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
            )
        except Exception:
            logger.exception("replay_run_events subscribe failed for %s", run_id)
            return []
        events: list[PipelineEvent] = []
        try:
            while True:
                try:
                    msgs = await sub.fetch(batch=100, timeout=1.0)
                except Exception:
                    break
                if not msgs:
                    break
                for msg in msgs:
                    try:
                        events.append(PipelineEvent.model_validate_json(msg.data))
                    except Exception:
                        logger.debug("replay_run_events: skipping unparseable message")
                    await msg.ack()
                if len(msgs) < 100:
                    break
        finally:
            try:
                await sub.unsubscribe()
            except Exception:
                pass
        events.sort(key=lambda e: e.seq)
        return events

    async def subscribe_run(self, run_id: str) -> "AsyncIterator[PipelineEvent]":
        """Yield events for one run live (ephemeral consumer, delivers all + new)."""
        if self._js is None:
            return
        from nats.js.api import ConsumerConfig, DeliverPolicy

        subject = f"{EVENT_SUBJECT_PREFIX}.{run_id}.>"
        sub = await self._js.subscribe(
            subject,
            config=ConsumerConfig(deliver_policy=DeliverPolicy.ALL),
        )
        try:
            while True:
                msg = await sub.next_msg(timeout=None)
                try:
                    event = PipelineEvent.model_validate_json(msg.data)
                except Exception:
                    await msg.ack()
                    continue
                await msg.ack()
                yield event
                if event.kind == "run_completed":
                    break
        finally:
            try:
                await sub.unsubscribe()
            except Exception:
                pass

    async def close(self) -> None:
        if self._nc is not None:
            try:
                await self._nc.drain()
            except Exception:
                pass
        self._nc = None
        self._js = None


_client: NatsClient | None = None


def get_nats_client() -> NatsClient:
    global _client
    if _client is None:
        _client = NatsClient()
    return _client
