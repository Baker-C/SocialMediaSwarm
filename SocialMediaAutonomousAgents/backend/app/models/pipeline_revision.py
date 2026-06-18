"""Pipeline spec revision history. One immutable document per spec version.

Mirrors VoiceRevisionDocument: each revision captures the COMPLETE spec at a
version bump so the dashboard timeline and the attribution join (doc 02 stamps
TrackedPost.creation_metrics.pipeline_hash = this version_hash) can reconstruct
the exact pipeline that produced a post.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.pipeline_spec import CompositeSpec, StepSpec


class PipelineRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str

    # ── Full spec snapshot (canonical going forward) ──
    # List defaults EMPTY (not a default factory): a revision is an immutable
    # archive, so filling a missing `steps` with today's baseline would FABRICATE
    # history. Mirrors voice_revision.py's empty-default discipline.
    steps: list[StepSpec | CompositeSpec] = Field(default_factory=list)
    status: str = "champion"  # status this revision was in when archived
    parent_hash: str | None = None  # lineage: what it was forked from

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"pipelinerevisions/{account_id}-v{seq}"
