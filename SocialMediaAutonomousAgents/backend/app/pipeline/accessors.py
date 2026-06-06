"""Internal accessors (avoids clashing with the ``app.pipeline.tools`` package)."""

from __future__ import annotations

from app.pipeline.service import get_pipeline
from app.pipeline.tools._catalog import ToolCatalog


def tool_catalog() -> ToolCatalog:
    return get_pipeline().tools
