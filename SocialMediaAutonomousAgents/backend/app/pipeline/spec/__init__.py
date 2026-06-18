"""Pipeline spec subsystem — tool catalog, validator, compiler.

This package contains:
- catalog.py: tool introspection and lookup (ToolCatalog, get_tool_catalog)
- validator.py: spec validation against tool catalog (doc 05)
- compiler.py: spec → executable runbook steps (doc 05)
"""

from app.pipeline.spec.compiler import compile_spec
from app.pipeline.spec.validator import ValidationError, ValidationReport, validate_spec

__all__ = [
    "validate_spec",
    "ValidationReport",
    "ValidationError",
    "compile_spec",
]
