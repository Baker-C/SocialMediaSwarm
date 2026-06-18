"""Read API for the per-account pipeline spec (doc 14, CC-11).

Two thin reads the frontend graph + builder consume (doc 11 §3.1):
  GET  /accounts/{id}/pipeline/spec[?status]   → the loaded champion/challenger spec
  POST /accounts/{id}/pipeline/spec/validate   → validate_spec over that loaded spec

No business logic lives here — both handlers wrap repo/pure functions docs 04/05/03 ship.
Mirrors pipeline_runs.py exactly (router + module-level repo + asyncio.to_thread).
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Query

from app.pipeline.spec.catalog import get_tool_catalog          # doc 03 (CC-1: the only factory)
from app.pipeline.spec.validator import validate_spec           # doc 05 §5.2 (pure)
from app.services.pipeline_spec_repository import PipelineSpecRepository  # doc 04 §6b (CC-5)

router = APIRouter()
repo = PipelineSpecRepository()

SpecStatus = Literal["champion", "challenger"]


@router.get("/accounts/{account_id}/pipeline/spec")
async def get_account_spec(
    account_id: str, status: SpecStatus = Query("champion")
) -> dict[str, Any]:
    # load_or_default never returns None (CC-5: no doc → version-stamped baseline),
    # so this never 404s — the graph always renders (doc 11 §3.1).
    spec = await asyncio.to_thread(repo.load_or_default, account_id, status, "post")
    return spec.model_dump()


@router.post("/accounts/{account_id}/pipeline/spec/validate")
async def validate_account_spec(
    account_id: str, status: SpecStatus = Query("champion")
) -> dict[str, Any]:
    # Validate the SERVER's loaded spec (no client body — see §4.2 Decision Defense).
    spec = await asyncio.to_thread(repo.load_or_default, account_id, status, "post")
    report = validate_spec(spec, get_tool_catalog())   # CC-1 catalog object; pure, no to_thread needed
    return report.model_dump()
