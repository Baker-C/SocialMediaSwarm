"""Read API for event-sourced pipeline runs.

List/detail are served from the RavenDB ``PipelineRuns`` projection. Raw events
and the live stream are served directly from the JetStream event log (source of
truth), so run detail is accurate even if the projection lagged.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.infrastructure.nats_client import get_nats_client
from app.pipeline.events.projection import build_run_document
from app.services.pipeline_run_repository import PipelineRunRepository

router = APIRouter()
repo = PipelineRunRepository()


@router.get("/pipeline/runs")
async def list_fleet_runs(
    limit: int = Query(100, ge=1, le=500),
    account_id: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    runs = await asyncio.to_thread(
        repo.list_fleet, limit=limit, account_id=account_id, status=status
    )
    return {"count": len(runs), "runs": [r.model_dump() for r in runs]}


@router.get("/accounts/{account_id}/pipeline/runs")
async def list_account_runs(
    account_id: str, limit: int = Query(100, ge=1, le=500)
) -> dict[str, Any]:
    runs = await asyncio.to_thread(repo.list_for_account, account_id, limit=limit)
    return {"count": len(runs), "runs": [r.model_dump() for r in runs]}


@router.get("/pipeline/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = await asyncio.to_thread(repo.get, run_id)
    if run is None:
        # Fall back to folding the run live from the JetStream event log.
        events = await get_nats_client().replay_run_events(run_id)
        run = build_run_document(events)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run.model_dump()


@router.get("/pipeline/runs/{run_id}/events")
async def get_run_events(run_id: str) -> dict[str, Any]:
    events = await get_nats_client().replay_run_events(run_id)
    return {"run_id": run_id, "count": len(events), "events": [e.model_dump() for e in events]}


@router.get("/pipeline/runs/{run_id}/stream")
async def stream_run(run_id: str) -> StreamingResponse:
    async def _gen():
        client = get_nats_client()
        async for event in client.subscribe_run(run_id):
            yield f"data: {json.dumps(event.model_dump(), default=str)}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'run_id': run_id})}\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")
