"""Internal interpreter primitives (CC-8): pure functions not in the catalog.

These are the closed set of sentinel tool_ids that both validator.py and
compiler.py recognize as built-in interpreter functions, not catalog tools.
"""

from __future__ import annotations

from app.pipeline.services import steps
from app.pipeline.types.artifacts import ArtifactKey

INTERNAL_PRIMITIVES: dict[str, dict] = {
    "_internal.collect_external": {
        "run": steps.collect_external_references,
        "reads": (ArtifactKey.SEARCH_REFERENCES,),
        "writes": (ArtifactKey.TIMELINE_REFERENCES,),
    },
}


def is_internal(tool_id: str | None) -> bool:
    """Check if a tool_id is a recognized internal primitive."""
    return bool(tool_id) and tool_id in INTERNAL_PRIMITIVES
