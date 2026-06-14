"""Durable JetStream consumer that folds events into the PipelineRuns projection.

Runs as an asyncio task on the FastAPI loop. The durable consumer survives
restarts and replays from its last ack, so projections catch up automatically.
RavenDB writes are offloaded to a thread so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging

from app.infrastructure.nats_client import get_nats_client
from app.pipeline.events.projection import build_run_document
from app.pipeline.events.types import EVENT_SUBJECT_PREFIX, PipelineEvent
from app.services.pipeline_run_repository import PipelineRunRepository

logger = logging.getLogger(__name__)

_DURABLE = "pipeline-run-projection"


class ProjectionConsumer:
    def __init__(self, repo: PipelineRunRepository | None = None) -> None:
        self._repo = repo or PipelineRunRepository()
        self._task: asyncio.Task | None = None
        self._sub = None
        self._runs: dict[str, list[PipelineEvent]] = {}

    async def start(self) -> None:
        client = get_nats_client()
        if not client.connected or client.js is None:
            logger.info("ProjectionConsumer not started (NATS unavailable)")
            return
        from nats.js.api import AckPolicy, ConsumerConfig, DeliverPolicy

        self._sub = await client.js.subscribe(
            f"{EVENT_SUBJECT_PREFIX}.>",
            durable=_DURABLE,
            manual_ack=True,
            config=ConsumerConfig(
                deliver_policy=DeliverPolicy.ALL, ack_policy=AckPolicy.EXPLICIT
            ),
        )
        self._task = asyncio.create_task(self._run(), name="pipeline-run-projection")
        logger.info("ProjectionConsumer started")

    async def _run(self) -> None:
        assert self._sub is not None
        try:
            while True:
                try:
                    msg = await self._sub.next_msg(timeout=5)
                except Exception:
                    # timeout / transient error — keep polling (CancelledError still propagates)
                    continue
                try:
                    event = PipelineEvent.model_validate_json(msg.data)
                    await self._apply(event)
                except Exception:
                    logger.exception("projection: failed to apply event")
                finally:
                    try:
                        await msg.ack()
                    except Exception:
                        pass
        except asyncio.CancelledError:
            pass

    async def _apply(self, event: PipelineEvent) -> None:
        bucket = self._runs.setdefault(event.run_id, [])
        bucket.append(event)
        doc = build_run_document(bucket)
        if doc is not None:
            try:
                await asyncio.to_thread(self._repo.save, doc)
            except Exception:
                logger.exception("projection: failed to save run %s", event.run_id)
        if event.kind == "run_completed":
            self._runs.pop(event.run_id, None)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None
        if self._sub is not None:
            try:
                await self._sub.unsubscribe()
            except Exception:
                pass
            self._sub = None
