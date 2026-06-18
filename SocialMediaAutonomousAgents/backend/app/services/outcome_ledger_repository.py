"""Persistence for the outcome ledger (RavenDB collection OutcomeLedger)."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from app.infrastructure.ravendb_http import (
    RavenDBHttpClient,
    RavenDBHttpError,
    get_ravendb_client,
)
from app.models.outcome_ledger import OutcomeLedgerDocument, compute_reward

logger = logging.getLogger(__name__)

OUTCOME_LEDGER_COLLECTION = "OutcomeLedger"


def _safe_rql_string(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value)


def _strip_meta(raw: dict) -> dict:
    return {k: v for k, v in raw.items() if not str(k).startswith("@")}


class OutcomeLedgerRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def stamp(
        self,
        *,
        account_id: str,
        post_id: str,
        run_id: str | None,
        soul_hash: str | None,
        pipeline_hash: str | None,
    ) -> None:
        """Create the ledger row at publish time. reward stays None / raw_metrics empty
        until the engagement jobs fill them. Idempotent: re-stamping the same post just
        overwrites the (still empty) header — it does NOT clobber metrics, because at
        publish there are none yet. (A real re-publish is prevented upstream by post locks.)"""
        doc = OutcomeLedgerDocument(
            account_id=account_id,
            post_id=post_id,
            run_id=run_id,
            soul_hash=soul_hash,
            pipeline_hash=pipeline_hash,
            recorded_at=datetime.now(timezone.utc).isoformat(),
        )
        doc_id = OutcomeLedgerDocument.document_id(account_id, post_id)
        self.client.put_document(
            doc_id, doc.model_dump(exclude_none=True), collection=OUTCOME_LEDGER_COLLECTION
        )

    def update_outcome(self, account_id: str, post_id: str, metrics: dict) -> None:
        """Refresh reward + raw_metrics from the latest poll. Last-writer-wins.
        No-op if the row was never stamped (a post made before this feature shipped):
        we do NOT fabricate attribution we never captured."""
        doc_id = OutcomeLedgerDocument.document_id(account_id, post_id)
        raw = self.client.get_document(doc_id)
        if raw is None:
            return  # never stamped → no attribution header to attach metrics to; skip silently
        try:
            base = OutcomeLedgerDocument.model_validate(_strip_meta(raw))
        except Exception as exc:
            logger.debug("OutcomeLedger invalid row %s: %s", doc_id, exc)
            return
        base.raw_metrics = dict(metrics)
        base.reward = compute_reward(metrics)
        base.recorded_at = datetime.now(timezone.utc).isoformat()
        self.client.put_document(
            doc_id, base.model_dump(exclude_none=True), collection=OUTCOME_LEDGER_COLLECTION
        )

    def list_for_pipeline_hash(
        self, pipeline_hash: str, *, account_id: str | None = None, limit: int = 500
    ) -> list[OutcomeLedgerDocument]:
        """The evaluator's read path: every scored outcome for a given pipeline version."""
        ph = _safe_rql_string(pipeline_hash)
        if not ph:
            return []
        clauses = [f'pipeline_hash == "{ph}"']
        if account_id:
            aid = _safe_rql_string(account_id)
            if aid:
                clauses.append(f'account_id == "{aid}"')
        cap = max(1, min(int(limit), 500))
        rql = (
            f"from {OUTCOME_LEDGER_COLLECTION} where "
            + " and ".join(clauses)
            + f" order by recorded_at desc limit {cap}"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError as exc:
            logger.warning("OutcomeLedger query failed: %s", exc)
            return []
        out: list[OutcomeLedgerDocument] = []
        for raw in rows:
            try:
                out.append(OutcomeLedgerDocument.model_validate(_strip_meta(raw)))
            except Exception as exc:
                logger.debug("OutcomeLedger skip invalid row: %s", exc)
        return out

    def list_for_soul_hash(
        self, soul_hash: str, *, account_id: str | None = None, limit: int = 500
    ) -> list[OutcomeLedgerDocument]:
        """Soul A/B read path: every scored outcome for a given soul version.
        Mirror of list_for_pipeline_hash with soul_hash column."""
        sh = _safe_rql_string(soul_hash)
        if not sh:
            return []
        clauses = [f'soul_hash == "{sh}"']
        if account_id:
            aid = _safe_rql_string(account_id)
            if aid:
                clauses.append(f'account_id == "{aid}"')
        cap = max(1, min(int(limit), 500))
        rql = (
            f"from {OUTCOME_LEDGER_COLLECTION} where "
            + " and ".join(clauses)
            + f" order by recorded_at desc limit {cap}"
        )
        try:
            rows = self.client.query(rql)
        except RavenDBHttpError as exc:
            logger.warning("OutcomeLedger query failed: %s", exc)
            return []
        out: list[OutcomeLedgerDocument] = []
        for raw in rows:
            try:
                out.append(OutcomeLedgerDocument.model_validate(_strip_meta(raw)))
            except Exception as exc:
                logger.debug("OutcomeLedger skip invalid row: %s", exc)
        return out
