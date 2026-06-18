"""Version and stamp pipeline spec revisions. Verbatim mirror of
voice_version_service.py — only the hash inputs and revision payload differ."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.pipeline_spec import PipelineSpecDocument
from app.models.pipeline_revision import PipelineRevisionDocument
from app.services.pipeline_revision_repository import PipelineRevisionRepository


def compute_pipeline_hash(spec: PipelineSpecDocument) -> str:
    """SHA256 over the steps tree only. Canonical JSON (sorted keys) → stable digest.
    ORDER-SENSITIVE on `steps` and `children` by design: reordering steps is a real,
    auditable behavior change (mirrors voice_version_service._normalize_patterns)."""
    payload = [s.model_dump(mode="json") for s in spec.steps]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bump_pipeline_version_if_needed(
    spec: PipelineSpecDocument,
    *,
    previous_hash: str | None,
    manual_label: str | None = None,
    revision_repo: PipelineRevisionRepository | None = None,
) -> PipelineSpecDocument:
    current_hash = compute_pipeline_hash(spec)
    prev = (previous_hash or "").strip() or (spec.version_hash or "").strip()
    manual = (manual_label or "").strip()
    changed = False

    if not prev:
        seq = max(1, int(spec.version_seq or 1))
        spec.version_seq = seq
        spec.version_hash = current_hash
        spec.version_label = manual or (spec.version_label or "").strip() or f"v{seq}"
        changed = True
    elif prev == current_hash and not manual:
        return spec
    else:
        if prev != current_hash:
            seq = max(1, int(spec.version_seq or 1)) + 1
            spec.version_seq = seq
            spec.version_label = f"v{seq}"
            spec.version_hash = current_hash
            changed = True
        if manual:
            spec.version_label = manual
            changed = True

    if not changed:
        return spec

    seq = max(1, int(spec.version_seq or 1))
    repo = revision_repo or PipelineRevisionRepository()
    repo.save(
        PipelineRevisionDocument(
            account_id=spec.account_id,
            seq=seq,
            label=spec.version_label or f"v{seq}",
            version_hash=spec.version_hash or current_hash,
            changed_at=datetime.now(timezone.utc).isoformat(),
            steps=list(spec.steps),
            status=spec.status,
            parent_hash=spec.parent_hash,
        )
    )
    return spec
