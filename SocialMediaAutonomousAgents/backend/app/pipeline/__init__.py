"""Post pipeline: reference-analysis steps run before compose.

Tools live under ``app.pipeline.tools`` (data / deterministic / llm) and are
imported directly. ``app.pipeline.runbook`` holds the run-context factory; the
ordered steps are in ``app.pipeline.runbooks.post_tick``.
"""

from __future__ import annotations

from app.pipeline import runbook

__all__ = ["runbook"]
