"""Deterministic pre phase setup: load accounts, slot idempotency."""

from __future__ import annotations

from app.interval.context import TickContext
from app.models.account import AccountDocument


def phase1_global_setup(ctx: TickContext) -> None:
    if ctx.mode == "force" and ctx.force_account_ids:
        seen: list[AccountDocument] = []
        for aid in sorted(ctx.force_account_ids):
            acc = ctx.repo.load(aid)
            if acc is None:
                continue
            if acc.status == "active" and not acc.retired:
                seen.append(acc)
        ctx.accounts = seen
    else:
        ctx.accounts = list(ctx.repo.list_active())


def should_skip_account(ctx: TickContext, account: AccountDocument) -> str | None:
    if account.status != "active":
        return "inactive_account"
    if account.retired:
        return "retired_account"
    return None
