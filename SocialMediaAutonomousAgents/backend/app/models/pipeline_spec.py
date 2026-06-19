"""Canonical editable pipeline spec. One per account; compiled by doc 05 and executed by the interpreter (doc 07).

A spec is DATA describing which catalog tools run, in what order/shape, with what
PROPOSABLE config. It NEVER carries engine-injected service objects (tick_data, repo,
post_registry, twitter) — those are wired by the interpreter at run time exactly as
services/steps.py wires them today. See 04 §3a.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ── A single leaf step: one catalog tool + its proposable config ──
class StepSpec(BaseModel):
    """A leaf step. `tool_id` resolves to a catalog tool (doc 03 catalog).
    The discriminant `kind` is the literal "step" (NOT "leaf") — this is the
    canonical value the validator/compiler (doc 05) and frontend (doc 11) switch on.
    `config` holds ONLY proposable scalars the catalog marks config_origin=="literal"
    (today just top_n and max_results_per_query; the coarse ACT tools expose none).
    It NEVER carries `store_key`/`source`: those are COMPILE-TIME WIRING
    (config_origin=="wired" — the compiler/wrapper computes them, never proposed in the
    spec; see §7) — so doc 05's R2 (config_unknown_key) rejects them as keys here and
    does NOT reject the baseline for omitting them."""

    kind: Literal["step"] = "step"
    id: str  # step id, e.g. "rank_external_references"
    tool_id: str  # catalog id, e.g. "deterministic.reference_rank"
    reads: list[str] = Field(default_factory=list)  # ArtifactKey .value strings
    writes: list[str] = Field(default_factory=list)  # ArtifactKey .value strings
    reads_optional: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)  # proposable, LLM/builder-tunable
    purpose: str = ""


# ── A composite: parallel or chain over children (recursive) ──
class CompositeSpec(BaseModel):
    """parallel | chain over children. Mirrors flow.parallel()/flow.chain().
    children may be StepSpec or nested CompositeSpec (matches the runbook's
    parallel(chain(...), chain(...))). reads/writes are DERIVED at compile time
    by the compiler (doc 05) exactly as flow.py unions them, so they are NOT
    stored here — storing them would risk drift from the children."""

    kind: Literal["parallel", "chain"]
    id: str
    children: list[StepSpec | CompositeSpec] = Field(default_factory=list)
    purpose: str = ""


# ── The whole spec document for one account ──
class PipelineSpecDocument(BaseModel):
    """The per-account posting pipeline as data. Document id:
    pipelinespecs/{account_id}. The CHAMPION is the live spec; a CHALLENGER is a
    staged variant awaiting promotion (see 04 §7)."""

    account_id: str
    # Ordered top-level steps; each entry is a leaf or a composite. This is the
    # exact analogue of POST_TICK_REFERENCE_STEPS: tuple[Step, ...].
    steps: list[StepSpec | CompositeSpec] = Field(default_factory=list)

    # ── metadata ──
    name: str = ""
    description: str = ""
    template_id: str = ""
    weight: float = 1.0

    # ── champion/challenger ──
    status: Literal["active", "paused"] = "active"
    parent_hash: str | None = None  # version_hash this spec was forked from

    # ── version stamp (bumps when `steps` changes; see pipeline_version_service) ──
    version_hash: str | None = None
    version_seq: int = 1
    version_label: str | None = "v1"

    @staticmethod
    def document_id(account_id: str, status: str = "champion", kind: str = "post") -> str:
        # One live doc per (account, kind, status). A challenger lives alongside the
        # champion until promoted; promotion overwrites the champion doc. `kind`
        # ("post" default; "reply" is doc 12's separate family — CC-12) namespaces
        # the id so the two spec families never collide.
        prefix = "pipelinespecs" if kind == "post" else f"pipelinespecs-{kind}"
        suffix = "" if status == "champion" else f"-{status}"
        return f"{prefix}/{account_id}{suffix}"


CompositeSpec.model_rebuild()  # resolve the forward ref in children


def default_pipeline_spec(account_id: str) -> "PipelineSpecDocument":
    """Baseline champion spec = the current hardcoded runbook + the ACT tail, as data.
    Delegates to the seed builder so there is ONE canonical baseline (04 §7).
    Flattens to the 10 dotted ids the frontend baseline fixture (doc 11 §4.3) locks."""
    from app.services.pipeline_spec_seed import spec_from_runbook  # avoid import cycle

    return spec_from_runbook(account_id)
