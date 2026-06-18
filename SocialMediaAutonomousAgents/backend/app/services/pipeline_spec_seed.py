"""Re-export spec_from_runbook from the seed builder for use by default_pipeline_spec."""

from scripts.seed_pipeline_spec import spec_from_runbook

__all__ = ["spec_from_runbook"]
