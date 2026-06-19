"""Load all account documents from the database."""

from __future__ import annotations

from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult
from app.services.account_repository import AccountRepository

TOOL_ID = "data.fetch_all_accounts"
TOOL_KIND = "data"
TOOL_PURPOSE = "Load all account documents from the database"
TOOL_READS: tuple = ()
TOOL_WRITES = (ArtifactKey.ALL_ACCOUNTS,)


def run(
    ctx: TickRunContext,
    *,
    account_repo: AccountRepository | None = None,
) -> StepResult:
    accounts = fetch(account_repo=account_repo)
    ctx.set("all_accounts", accounts)
    return StepResult(ok=True, payload={"account_count": len(accounts)})


def fetch(*, account_repo: AccountRepository | None = None) -> list[dict]:
    repo = account_repo or AccountRepository()
    docs = repo.list_all_accounts()
    return [doc.model_dump(mode="json") for doc in docs]
