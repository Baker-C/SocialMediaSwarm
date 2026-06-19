"""One-time builder: POST_TICK_REFERENCE_STEPS (8 SENSE) + the two ACT-tail leaves
→ a champion PipelineSpecDocument. Exported as app/services/pipeline_spec_seed.py
for default_pipeline_spec (§3c)."""

from __future__ import annotations

from app.models.pipeline_spec import CompositeSpec, PipelineSpecDocument, StepSpec
from app.pipeline.types.flow import Step  # Runbook step type

# Each runbook leaf wrapper calls exactly ONE catalog tool (or the internal primitive).
# Verified in app/pipeline/services/steps.py (line numbers are the real ones in the live file).
# 10 entries (CC-6): the 8 SENSE leaves PLUS the two ACT-tail leaves, so that once doc 06
# appends compose_until_safe/publish_post INTO POST_TICK_REFERENCE_STEPS, the runbook walk
# in spec_from_runbook (which looks up STEP_TOOL_MAP[step.id]) resolves them instead of
# raising KeyError. Pre-06, ACT_TAIL_SPECS (below) supplies the same two leaves by literal.
STEP_TOOL_MAP = {
    "load_account_bundle": "data.account_profile",  # steps.py:38
    "fetch_search_references": "data.search_fetch",  # steps.py:81
    "collect_external_references": "_internal.collect_external",  # steps.py:90 — internal primitive
    "fetch_own_post_history": "data.own_posts_fetch",  # steps.py:120
    "rank_external_references": "deterministic.reference_rank",  # steps.py:135
    "brief_external_references": "llm.reference_pattern_summary",  # steps.py:160
    "rank_own_posts": "deterministic.reference_rank",  # steps.py:211
    "brief_own_posts": "llm.reference_pattern_summary",  # steps.py:249
    # ── ACT tail (CC-6): the two leaves doc 06 appends to the runbook ──
    "compose_until_safe": "llm.compose_until_safe",  # doc 06 §7.1 Step
    "publish_post": "data.publish_post",  # doc 06 §7.1 Step (terminal — writes PUBLISHED_POST)
}

# PROPOSABLE config ONLY — keys whose catalog config_origin == "literal" (doc 03 §4.4).
# store_key / source are config_origin == "wired" (engine-computed, NOT spec config), so
# they are DELIBERATELY ABSENT here: doc 05 R2 (config_unknown_key) rejects any non-literal
# key in StepSpec.config, and the wrapper still computes store_key/source itself.
# Values copied from the hardcoded constants in services/steps.py.
STEP_CONFIG = {
    "fetch_search_references": {"max_results_per_query": 50},  # SEARCH_RESULTS_PER_NICHE, steps.py:35,86
    "rank_external_references": {"top_n": 10},  # MIN_TOP_N, steps.py:32,138
    "rank_own_posts": {"top_n": 10},  # MIN_TOP_N, steps.py:32,214
    # brief_external_references / brief_own_posts carry NO proposable config:
    #   their only signature-config (source, store_key) are both "wired", not "literal".
}

# The two ACT-tail leaves the runbook does NOT yet contain. doc 06 appends the same Steps
# to POST_TICK_REFERENCE_STEPS; the seed wires them by string so the baseline is COMPLETE
# and validator-passing even before that runbook edit lands. reads/writes are the ACT
# ArtifactKey .value strings doc 06 §3 defines; they match doc 06 §7.1's Step declarations.
# The canonical publish artifact key is PUBLISHED_POST (doc 06 §3.1; doc 05 R6 checks
# PUBLISHED_POST) — NOT "publish_result".
ACT_TAIL_SPECS: list[StepSpec] = [
    StepSpec(
        id="compose_until_safe",
        tool_id="llm.compose_until_safe",
        reads=[
            "timeline_analysis",
            "own_posts_analysis",
            "timeline_ranked",
            "timeline_references",
        ],  # CC-7: compose reads TIMELINE_RANKED to build ranked_refs internally + TIMELINE_REFERENCES for the reference pool; MUST match doc 06 TOOL_READS / doc 07 §2.3
        writes=["composed_post", "safety_verdict"],  # ArtifactKey.COMPOSED_POST / SAFETY_VERDICT
        config={},  # coarse ACT tool exposes NO proposable config (doc 06 §5.1)
        purpose="Compose with guardian feedback + reference fallback until safe",
    ),
    StepSpec(
        id="publish_post",
        tool_id="data.publish_post",
        reads=["composed_post", "safety_verdict", "account_bundle"],  # ArtifactKey.COMPOSED_POST / SAFETY_VERDICT / ACCOUNT_BUNDLE (followers_at_post)
        writes=["published_post"],  # ArtifactKey.PUBLISHED_POST (terminal — R6)
        config={},
        purpose="Publish to X (idempotent) and finalize state",
    ),
]


def spec_from_runbook(account_id: str) -> PipelineSpecDocument:
    """Walk POST_TICK_REFERENCE_STEPS → nested StepSpec/CompositeSpec, then append the two
    ACT-tail leaves so the baseline is a COMPLETE SENSE+ACT graph (10 flattened leaves).
    The single canonical baseline (also backs default_pipeline_spec, 04 §3c)."""
    from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS

    sense = [_node_to_spec(s) for s in POST_TICK_REFERENCE_STEPS]
    # Once doc 06 appends compose_until_safe/publish_post INTO POST_TICK_REFERENCE_STEPS, the
    # walk already yields them (and STEP_TOOL_MAP gains the two tool ids). The guard below
    # prevents a double-add in that post-06 world; pre-06 it appends the literals so the seed
    # is complete on its own.
    have = {s.id for s in sense}
    tail = [s for s in ACT_TAIL_SPECS if s.id not in have]
    spec = PipelineSpecDocument(account_id=account_id, steps=sense + tail, status="active")
    return spec  # version stamp is applied by repo.save → bump_pipeline_version_if_needed


def _node_to_spec(step) -> StepSpec | CompositeSpec:
    """Recursively walk a Step tree and convert to StepSpec/CompositeSpec."""
    if step.is_composite:  # flow.py:32 (is_composite); composite_kind ∈ {"parallel","chain"}
        return CompositeSpec(
            kind=step.composite_kind,  # "parallel" | "chain"
            id=step.id,
            children=[_node_to_spec(c) for c in step.children],
            purpose=step.purpose,
        )
    return StepSpec(
        id=step.id,
        tool_id=STEP_TOOL_MAP[step.id],
        reads=[k.value for k in step.reads],
        writes=[k.value for k in step.writes],
        reads_optional=[k.value for k in step.reads_optional],
        config=STEP_CONFIG.get(step.id, {}),
        purpose=step.purpose,
    )


def main():
    """One-time seed: load the runbook, build a spec, save it."""
    from app.services.pipeline_spec_repository import PipelineSpecRepository

    account_id = "JohnJames_News"
    spec = spec_from_runbook(account_id)
    PipelineSpecRepository().save(spec)
    print(f"Seeded pipeline spec for {account_id}: v{spec.version_label} ({spec.version_hash})")


if __name__ == "__main__":
    main()
