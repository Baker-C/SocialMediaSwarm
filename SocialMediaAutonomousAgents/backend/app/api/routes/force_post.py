"""Force-post API: run the posting pipeline on demand with live progress."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.infrastructure.ravendb_http import RavenDBHttpError
from app.services.account_repository import AccountRepository
from app.services.force_post_service import run_force_post

router = APIRouter()
repo = AccountRepository()


def _serialize_result(result: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(result, default=str))


def _pipeline_failure_message(result: dict[str, Any]) -> str | None:
    for row in result.get("results") or []:
        if not isinstance(row, dict):
            continue
        skipped = row.get("skipped")
        if isinstance(skipped, str) and skipped.strip():
            return skipped.strip()
        rejected = row.get("rejected")
        if isinstance(rejected, str) and rejected.strip():
            return rejected.strip()
        err = row.get("error")
        if isinstance(err, str) and err.strip():
            return err.strip()
    return None


async def _sse_force_post(account_id: str):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def emit(step_id: str, label: str, status: str) -> None:
        loop.call_soon_threadsafe(
            queue.put_nowait,
            {"type": "progress", "step_id": step_id, "label": label, "status": status},
        )

    def worker() -> None:
        try:
            result = run_force_post(account_id, on_progress=emit)
            serialized = _serialize_result(result)
            failure = _pipeline_failure_message(result)
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "complete", "result": serialized, "failure": failure},
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "message": str(exc)},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    loop.run_in_executor(None, worker)

    while True:
        item = await queue.get()
        if item is None:
            break
        yield f"data: {json.dumps(item)}\n\n"


@router.post("/accounts/{account_id}/force-post")
async def force_post(account_id: str, request: Request):
    """Run a force post for one account. Accept `text/event-stream` for live step updates."""
    aid = (account_id or "").strip()
    if not aid:
        raise HTTPException(status_code=400, detail="account_id is required")
    try:
        acc = repo.load(aid)
    except RavenDBHttpError as exc:
        raise HTTPException(status_code=503, detail=f"RavenDB unavailable: {exc}") from exc
    if acc is None:
        raise HTTPException(status_code=404, detail="Account not found")

    accept = (request.headers.get("accept") or "").lower()
    if "text/event-stream" in accept:
        return StreamingResponse(_sse_force_post(aid), media_type="text/event-stream")

    try:
        result = await asyncio.to_thread(run_force_post, aid)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    failure = _pipeline_failure_message(result)
    payload: dict[str, Any] = {"ok": failure is None, "result": _serialize_result(result)}
    if failure:
        payload["failure"] = failure
    return payload
