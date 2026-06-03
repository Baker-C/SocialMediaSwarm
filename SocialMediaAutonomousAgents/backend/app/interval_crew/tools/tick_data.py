"""Tick data access for tools and orchestration (via TickDataService only)."""

from __future__ import annotations

from typing import Any

from app.services.tick_data_service import TickDataService


def compile_account_bundle(tick_data: TickDataService, account_id: str) -> dict[str, Any]:
    return tick_data.compile_account_bundle(account_id)


def compile_niche_discourse(
    tick_data: TickDataService,
    account_id: str,
    niche: str,
) -> dict[str, Any]:
    return tick_data.compile_niche_discourse(account_id, niche)


def merge_for_prompt(
    tick_data: TickDataService,
    account_bundle: dict[str, Any],
    niche_bundle: dict[str, Any],
) -> str:
    return tick_data.merge_for_prompt(account_bundle, niche_bundle)


def compile_timeline_reference_tweets(
    tick_data: TickDataService,
    account_id: str,
    *,
    authenticated_user_id: str | None,
    slot: str,
) -> dict[str, Any]:
    return tick_data.compile_timeline_reference_tweets(
        account_id,
        authenticated_user_id=authenticated_user_id,
        slot=slot,
    )


def merge_reference_pool(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return TickDataService.merge_reference_pool(payload)
