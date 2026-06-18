"""Roll a regressed champion back to the version it replaced. Sequential put,
no CAS (RavenDB has none). One mutating write to the champion doc; a crash before
it leaves the regressed champion live (safe: the next LEARN tick re-detects and retries)."""

from __future__ import annotations

from app.models.pipeline_spec import PipelineSpecDocument
from app.services.pipeline_revision_repository import PipelineRevisionRepository
from app.services.pipeline_spec_repository import PipelineSpecRepository


def rollback_to_parent(
    account_id: str,
    *,
    parent_hash: str,
    repo: PipelineSpecRepository | None = None,
    revisions: PipelineRevisionRepository | None = None,
) -> PipelineSpecDocument | None:
    """Re-promote the parent (identified by version_hash) as champion. Returns the
    new champion spec, or None if the parent revision cannot be found (no fabrication)."""
    repo = repo or PipelineSpecRepository()
    revisions = revisions or PipelineRevisionRepository()

    rev = next(
        (r for r in revisions.list_for_account(account_id) if r.version_hash == parent_hash),
        None,
    )
    if rev is None:
        return None  # parent not archived → cannot honestly reconstruct; skip (logged by caller)

    current = repo.load(account_id, "champion")
    # Seed the restored doc with the OUTGOING champion's version stamp so repo.save's
    # bump_pipeline_version_if_needed takes the "hash changed" branch and INCREMENTS the
    # seq (current.version_seq → +1), minting a NEW revision for the rollback. If we left
    # version_hash=None and version_seq=1 (the model defaults), the bump's `if not prev:`
    # branch would re-stamp seq=1 and OVERWRITE the original v1 revision (data loss).
    # Carrying the current stamp forward is what makes the timeline honestly read
    # "v5 (rollback of v4 to v3's steps)" rather than resetting to v1.
    restored = PipelineSpecDocument(
        account_id=account_id,
        steps=list(rev.steps),  # the parent's exact step tree (immutable archive)
        status="champion",
        parent_hash=(current.version_hash if current else None),  # lineage: forked from the regressed one
        version_seq=(current.version_seq if current else 1),  # continue the lineage, not reset to 1
        version_hash=(current.version_hash if current else None),  # non-empty prev → bump takes the increment branch
    )
    repo.save(restored)  # PUT: champion = restored parent steps; bump mints v{current.seq+1}
    return restored
