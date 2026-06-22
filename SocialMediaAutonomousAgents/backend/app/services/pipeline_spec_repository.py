"""Persistence for pipeline specs — the live editable spec per account."""

from __future__ import annotations

from app.infrastructure.ravendb_http import RavenDBHttpClient, get_ravendb_client
from app.models.pipeline_spec import PipelineSpecDocument
from app.services.pipeline_version_service import bump_pipeline_version_if_needed, compute_pipeline_hash

PIPELINE_SPEC_COLLECTION = "PipelineSpecs"


class PipelineSpecRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def load(
        self, account_id: str, status: str = "champion", kind: str = "post"
    ) -> PipelineSpecDocument | None:
        doc_id = PipelineSpecDocument.document_id(account_id, status, kind)
        raw = self.client.get_document(doc_id)
        if raw is None:
            return None
        stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
        return PipelineSpecDocument.model_validate(stripped)

    def load_or_default(
        self, account_id: str, status: str = "champion", kind: str = "post"
    ) -> PipelineSpecDocument:
        """The interpreter (doc 07) calls this — the single entry point per CC-5:
        the live `status` spec for this `kind`, or the baseline if no spec doc exists
        yet (graceful default — mirrors how account load folds in a default soul).
        This is the ONE place that decides 'no spec → baseline'. `kind` defaults to
        "post"; "reply" (doc 12) is a separate family (CC-12). The returned baseline is
        version-STAMPED in memory (see note) so its `version_hash` is never None even
        when no spec was ever saved."""
        from app.models.pipeline_spec import default_pipeline_spec

        loaded = self.load(account_id, status, kind)
        if loaded is not None:
            return loaded
        baseline = default_pipeline_spec(account_id)
        # Stamp the in-memory baseline so callers that read .version_hash (attribution,
        # doc 02/07) get the baseline's real hash, not None. This does NOT write to Raven
        # and does NOT archive a revision (revision_repo is a no-op sink): it is a pure
        # in-memory hash so the unsaved baseline still attributes correctly.
        baseline.version_hash = compute_pipeline_hash(baseline)
        return baseline

    def load_all_active(self, account_id: str, kind: str = "post") -> list[PipelineSpecDocument]:
        """Load all active pipeline specs for an account via RQL.

        Returns an empty list if none are found; sorted by name for determinism.
        """
        safe_id = account_id.replace("'", "\\'")
        rql = (
            f"from {PIPELINE_SPEC_COLLECTION} "
            f"where account_id = '{safe_id}' and status = 'active'"
        )
        results = self.client.query(rql)
        if not results:
            return []
        docs: list[PipelineSpecDocument] = []
        for raw in results:
            stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
            docs.append(PipelineSpecDocument.model_validate(stripped))
        docs.sort(key=lambda d: d.name or d.account_id)
        return docs

    def save(self, spec: PipelineSpecDocument, kind: str = "post") -> None:
        # `kind` ("post" default; "reply" is doc 12's family — CC-12) selects the doc-id
        # namespace. The spec model itself carries no `kind` field; the family is a
        # repository-level concern, exactly as `status` namespaces the champion/challenger.
        spec = bump_pipeline_version_if_needed(spec, previous_hash=spec.version_hash)
        doc_id = PipelineSpecDocument.document_id(spec.account_id, spec.status, kind)
        self.client.put_document(
            doc_id, spec.model_dump(exclude_none=True), collection=PIPELINE_SPEC_COLLECTION
        )

    def save_active_template(self, spec: PipelineSpecDocument, kind: str = "post") -> None:
        """Persist one ACTIVE posting template under a template-namespaced doc id, so an
        account can hold SEVERAL active specs at once (the runner's load_all_active selects
        by the `status` field, not the doc id). Distinct from save(), which owns the single
        champion/challenger doc per account."""
        spec = bump_pipeline_version_if_needed(spec, previous_hash=spec.version_hash)
        tid = (spec.template_id or "tpl").strip() or "tpl"
        prefix = "pipelinespecs" if kind == "post" else f"pipelinespecs-{kind}"
        doc_id = f"{prefix}/{spec.account_id}-active-{tid}"
        self.client.put_document(
            doc_id, spec.model_dump(exclude_none=True), collection=PIPELINE_SPEC_COLLECTION
        )


def seed_active_pipelines(
    account_id: str,
    template_ids: list[str],
    repo: PipelineSpecRepository | None = None,
) -> list[str]:
    """Persist 1-3 chosen posting templates as ACTIVE specs the runner rotates between.

    Unknown / structurally-invalid template ids are dropped; the list is de-duplicated and
    clamped to 3. Falls back to ["standard"] so a new account always has at least one
    runnable pipeline. Returns the template ids actually saved.
    """
    from app.pipeline.runbooks.templates import TEMPLATE_MAP, VALID_POSTING_TEMPLATE_IDS
    from app.pipeline.spec.catalog import get_tool_catalog
    from app.pipeline.spec.validator import validate_spec

    repo = repo or PipelineSpecRepository()

    wanted: list[str] = []
    for tid in template_ids or []:
        if tid in VALID_POSTING_TEMPLATE_IDS and tid not in wanted:
            wanted.append(tid)
    wanted = wanted[:3] or ["standard"]

    catalog = get_tool_catalog()
    saved: list[str] = []
    for tid in wanted:
        spec = TEMPLATE_MAP[tid](account_id)
        if validate_spec(spec, catalog).ok:
            repo.save_active_template(spec)
            saved.append(tid)

    if not saved:  # backstop — "standard" is the canonical known-good baseline
        repo.save_active_template(TEMPLATE_MAP["standard"](account_id))
        saved.append("standard")
    return saved


def promote_challenger(
    account_id: str, repo: PipelineSpecRepository | None = None, kind: str = "post"
) -> PipelineSpecDocument:
    """Promote the challenger to champion. Champion/challenger status is per
    (account_id, kind) (CC-12), so `kind` ("post" default) selects the family.
    NO CAS available, so this is a validate-then-activate sequence of plain puts.
    Ordering is chosen so a crash mid-promotion leaves the OLD champion intact
    (fail-safe), never a half-built one."""
    repo = repo or PipelineSpecRepository()
    challenger = repo.load(account_id, "challenger", kind)
    if challenger is None:
        raise ValueError(f"no challenger to promote for {account_id}")

    # 1. VALIDATE first (doc 05's validate_spec must pass) — never activate an
    #    unexecutable spec. If this raises/returns errors, nothing was written.
    from app.pipeline.spec import validate_spec, compile_spec  # doc 05 (re-exported from spec/__init__.py)
    from app.pipeline.spec.catalog import get_tool_catalog  # doc 03 (the ToolCatalog object — CC-1)

    report = validate_spec(challenger, get_tool_catalog())  # ValidationReport (doc 05 §5.2)
    if not report.ok:
        raise ValueError(f"challenger invalid: {[e.code for e in report.errors]}")
    compile_spec(challenger)  # final lowering check (raises on a catalog/shape defect validate missed)

    # 2. ACTIVATE: write champion (status flips to "champion", parent_hash set to
    #    the OUTGOING champion's hash for lineage). save() versions + archives it.
    outgoing = repo.load(account_id, "champion", kind)
    challenger.status = "champion"
    challenger.parent_hash = outgoing.version_hash if outgoing else None
    challenger.version_hash = None  # force a fresh bump/revision for the promotion
    repo.save(challenger, kind)  # PUT #1: champion doc is now the new spec

    # 3. CLEAN UP the challenger doc (best-effort). If this delete fails, the only
    #    residue is a stale challenger doc identical to the new champion — harmless;
    #    it never executes (the interpreter reads status="champion" only).
    repo.client.delete_document(PipelineSpecDocument.document_id(account_id, "challenger", kind))
    return challenger
