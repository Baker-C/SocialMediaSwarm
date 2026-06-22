"""Pipeline template registry: 8 posting preset specs + TEMPLATE_MAP factory dict."""

from __future__ import annotations

from typing import Callable, TypedDict

from app.models.pipeline_spec import PipelineSpecDocument


class TemplateDescription(TypedDict):
    template_id: str
    name: str
    description: str


_TEMPLATES: list[TemplateDescription] = [
    {
        "template_id": "standard",
        "name": "Standard",
        "description": "The full SENSE+ACT pipeline: search references, rank, brief, compose with safety guardian, and publish.",
    },
    {
        "template_id": "lean",
        "name": "Lean",
        "description": "Skips external reference analysis. Composes directly from own-post history and account profile, then publishes.",
    },
    {
        "template_id": "external_focus",
        "name": "External Focus",
        "description": "Weights external search references heavily. Skips own-post history to maximize trend-responsiveness.",
    },
    {
        "template_id": "own_voice",
        "name": "Own Voice",
        "description": "Skips external search entirely. Composes purely from own-post engagement history to reinforce established voice.",
    },
    {
        "template_id": "reply_mode",
        "name": "Reply Mode",
        "description": "Fetches mentions and composes targeted replies. Publishes replies rather than standalone posts.",
    },
    {
        "template_id": "research_heavy",
        "name": "Research Heavy",
        "description": "Runs parallel search across multiple niches, ranks and briefs all reference pools before composing.",
    },
    {
        "template_id": "rapid_fire",
        "name": "Rapid Fire",
        "description": "Minimal pipeline with no reference analysis. Composes from account profile only for high-frequency posting.",
    },
    {
        "template_id": "safe_mode",
        "name": "Safe Mode",
        "description": "Full reference analysis with extended safety guardian iterations and strict compose constraints.",
    },
]


def get_all_template_descriptions() -> list[TemplateDescription]:
    """Return descriptions for all 8 posting pipeline presets."""
    return _TEMPLATES


# ── Factory helpers ──────────────────────────────────────────────────────────


def _from_runbook(
    account_id: str,
    *,
    name: str,
    description: str,
    template_id: str,
    weight: float = 1.0,
) -> PipelineSpecDocument:
    """Build a spec from the default runbook and apply metadata overrides."""
    from scripts.seed_pipeline_spec import spec_from_runbook

    base = spec_from_runbook(account_id)
    return PipelineSpecDocument(
        account_id=account_id,
        steps=base.steps,
        name=name,
        description=description,
        template_id=template_id,
        weight=weight,
        status="active",
    )


# ── 8 posting template factories ─────────────────────────────────────────────


def build_standard_spec(account_id: str) -> PipelineSpecDocument:
    return _from_runbook(
        account_id,
        name="Standard",
        description=_TEMPLATES[0]["description"],
        template_id="standard",
    )


def build_lean_spec(account_id: str) -> PipelineSpecDocument:
    from app.models.pipeline_spec import CompositeSpec, StepSpec

    steps = [
        StepSpec(
            id="load_account_bundle",
            tool_id="data.account_profile",
            writes=["account_bundle"],
            purpose="Load X profile and tracked-post engagement metrics",
        ),
        StepSpec(
            id="fetch_own_post_history",
            tool_id="data.own_posts_fetch",
            writes=["own_posts"],
            purpose="Load own-post history with engagement metrics",
        ),
        CompositeSpec(
            kind="chain",
            id="analyze_own_posts",
            children=[
                StepSpec(
                    id="rank_own_posts",
                    tool_id="deterministic.reference_rank",
                    reads=["own_posts"],
                    writes=["own_posts_ranked"],
                    config={"top_n": 10},
                    purpose="Rank top own posts by engagement",
                ),
                StepSpec(
                    id="brief_own_posts",
                    tool_id="llm.reference_pattern_summary",
                    reads=["own_posts_ranked", "own_posts"],
                    writes=["own_posts_analysis"],
                    purpose="LLM pattern brief for own-post voice",
                ),
            ],
            purpose="Produce own-post voice brief for compose",
        ),
        StepSpec(
            id="compose_until_safe",
            tool_id="llm.compose_until_safe",
            reads=["own_posts_analysis"],
            reads_optional=["timeline_analysis", "timeline_ranked", "timeline_references"],
            writes=["composed_post", "safety_verdict"],
            purpose="Compose with guardian feedback until safe",
        ),
        StepSpec(
            id="publish_post",
            tool_id="data.publish_post",
            reads=["composed_post", "safety_verdict", "account_bundle"],
            writes=["published_post"],
            purpose="Publish to X and finalize state",
        ),
    ]
    return PipelineSpecDocument(
        account_id=account_id,
        steps=steps,
        name="Lean",
        description=_TEMPLATES[1]["description"],
        template_id="lean",
        status="active",
    )


def build_external_focus_spec(account_id: str) -> PipelineSpecDocument:
    from app.models.pipeline_spec import CompositeSpec, StepSpec

    steps = [
        StepSpec(
            id="load_account_bundle",
            tool_id="data.account_profile",
            writes=["account_bundle"],
            purpose="Load X profile and engagement metrics",
        ),
        StepSpec(
            id="fetch_search_references",
            tool_id="data.search_fetch",
            reads=["account_bundle"],
            writes=["search_references"],
            config={"max_results_per_query": 50},
            purpose="Fetch reference tweets from X search",
        ),
        StepSpec(
            id="collect_external_references",
            tool_id="_internal.collect_external",
            reads=["search_references"],
            writes=["timeline_references"],
            purpose="Build the external reference pool from search results",
        ),
        CompositeSpec(
            kind="chain",
            id="analyze_external_references",
            children=[
                StepSpec(
                    id="rank_external_references",
                    tool_id="deterministic.reference_rank",
                    reads=["timeline_references"],
                    writes=["timeline_ranked"],
                    config={"top_n": 15},
                    purpose="Rank top external references by engagement",
                ),
                StepSpec(
                    id="brief_external_references",
                    tool_id="llm.reference_pattern_summary",
                    reads=["timeline_ranked"],
                    writes=["timeline_analysis"],
                    purpose="LLM pattern brief for external references",
                ),
            ],
            purpose="Produce external reference brief for compose",
        ),
        StepSpec(
            id="compose_until_safe",
            tool_id="llm.compose_until_safe",
            reads=["timeline_analysis", "timeline_ranked", "timeline_references"],
            writes=["composed_post", "safety_verdict"],
            purpose="Compose from external references with guardian feedback",
        ),
        StepSpec(
            id="publish_post",
            tool_id="data.publish_post",
            reads=["composed_post", "safety_verdict", "account_bundle"],
            writes=["published_post"],
            purpose="Publish to X and finalize state",
        ),
    ]
    return PipelineSpecDocument(
        account_id=account_id,
        steps=steps,
        name="External Focus",
        description=_TEMPLATES[2]["description"],
        template_id="external_focus",
        status="active",
    )


def build_own_voice_spec(account_id: str) -> PipelineSpecDocument:
    # Own Voice is structurally identical to Lean (no external references).
    spec = build_lean_spec(account_id)
    return PipelineSpecDocument(
        account_id=account_id,
        steps=spec.steps,
        name="Own Voice",
        description=_TEMPLATES[3]["description"],
        template_id="own_voice",
        status="active",
    )


def build_reply_mode_spec(account_id: str) -> PipelineSpecDocument:
    from app.models.pipeline_spec import StepSpec

    steps = [
        StepSpec(
            id="load_account_bundle",
            tool_id="data.account_profile",
            writes=["account_bundle"],
            purpose="Load X profile",
        ),
        StepSpec(
            id="fetch_mentions",
            tool_id="data.mentions_fetch",
            reads=["account_bundle"],
            writes=["mentions"],
            purpose="Fetch recent mentions for reply candidacy",
        ),
        StepSpec(
            id="reply_compose",
            tool_id="llm.reply_compose",
            reads=["mentions", "account_bundle"],
            writes=["reply_draft", "reply_verdict"],
            purpose="Compose targeted reply with guardian feedback",
        ),
        StepSpec(
            id="reply_publish",
            tool_id="data.reply_publish",
            reads=["reply_draft", "reply_verdict", "account_bundle"],
            writes=["reply_result"],
            purpose="Publish reply to X",
        ),
    ]
    return PipelineSpecDocument(
        account_id=account_id,
        steps=steps,
        name="Reply Mode",
        description=_TEMPLATES[4]["description"],
        template_id="reply_mode",
        status="active",
    )


def build_research_heavy_spec(account_id: str) -> PipelineSpecDocument:
    # Research Heavy: larger reference pool + full dual-analysis, identical structure
    # to Standard but with higher search result limits.
    from app.models.pipeline_spec import CompositeSpec, StepSpec

    steps = [
        StepSpec(
            id="load_account_bundle",
            tool_id="data.account_profile",
            writes=["account_bundle"],
            purpose="Load X profile and engagement metrics",
        ),
        StepSpec(
            id="fetch_search_references",
            tool_id="data.search_fetch",
            reads=["account_bundle"],
            writes=["search_references"],
            config={"max_results_per_query": 100},
            purpose="Fetch reference tweets — larger pool for research",
        ),
        StepSpec(
            id="collect_external_references",
            tool_id="_internal.collect_external",
            reads=["search_references"],
            writes=["timeline_references"],
            purpose="Build the external reference pool from search results",
        ),
        StepSpec(
            id="fetch_own_post_history",
            tool_id="data.own_posts_fetch",
            writes=["own_posts"],
            purpose="Load own-post history with engagement metrics",
        ),
        CompositeSpec(
            kind="parallel",
            id="summarize_for_compose",
            children=[
                CompositeSpec(
                    kind="chain",
                    id="analyze_external_references",
                    children=[
                        StepSpec(
                            id="rank_external_references",
                            tool_id="deterministic.reference_rank",
                            reads=["timeline_references"],
                            writes=["timeline_ranked"],
                            config={"top_n": 20},
                            purpose="Rank top external references — deeper pool",
                        ),
                        StepSpec(
                            id="brief_external_references",
                            tool_id="llm.reference_pattern_summary",
                            reads=["timeline_ranked"],
                            writes=["timeline_analysis"],
                            purpose="LLM pattern brief for external references",
                        ),
                    ],
                ),
                CompositeSpec(
                    kind="chain",
                    id="analyze_own_posts",
                    children=[
                        StepSpec(
                            id="rank_own_posts",
                            tool_id="deterministic.reference_rank",
                            reads=["own_posts"],
                            writes=["own_posts_ranked"],
                            config={"top_n": 20},
                            purpose="Rank top own posts — deeper pool",
                        ),
                        StepSpec(
                            id="brief_own_posts",
                            tool_id="llm.reference_pattern_summary",
                            reads=["own_posts_ranked", "own_posts"],
                            writes=["own_posts_analysis"],
                            purpose="LLM pattern brief for own-post voice",
                        ),
                    ],
                ),
            ],
            purpose="Deep dual-source research before compose",
        ),
        StepSpec(
            id="compose_until_safe",
            tool_id="llm.compose_until_safe",
            reads=["timeline_analysis", "own_posts_analysis", "timeline_ranked", "timeline_references"],
            writes=["composed_post", "safety_verdict"],
            purpose="Compose with deep research context and guardian feedback",
        ),
        StepSpec(
            id="publish_post",
            tool_id="data.publish_post",
            reads=["composed_post", "safety_verdict", "account_bundle"],
            writes=["published_post"],
            purpose="Publish to X and finalize state",
        ),
    ]
    return PipelineSpecDocument(
        account_id=account_id,
        steps=steps,
        name="Research Heavy",
        description=_TEMPLATES[5]["description"],
        template_id="research_heavy",
        status="active",
    )


def build_rapid_fire_spec(account_id: str) -> PipelineSpecDocument:
    from app.models.pipeline_spec import StepSpec

    steps = [
        StepSpec(
            id="load_account_bundle",
            tool_id="data.account_profile",
            writes=["account_bundle"],
            purpose="Load X profile",
        ),
        StepSpec(
            id="compose_until_safe",
            tool_id="llm.compose_until_safe",
            reads=["account_bundle"],
            reads_optional=["own_posts_analysis", "timeline_analysis", "timeline_ranked", "timeline_references"],
            writes=["composed_post", "safety_verdict"],
            purpose="Compose directly from account profile with guardian feedback",
        ),
        StepSpec(
            id="publish_post",
            tool_id="data.publish_post",
            reads=["composed_post", "safety_verdict", "account_bundle"],
            writes=["published_post"],
            purpose="Publish to X and finalize state",
        ),
    ]
    return PipelineSpecDocument(
        account_id=account_id,
        steps=steps,
        name="Rapid Fire",
        description=_TEMPLATES[6]["description"],
        template_id="rapid_fire",
        status="active",
    )


def build_safe_mode_spec(account_id: str) -> PipelineSpecDocument:
    # Safe Mode: same step graph as Standard; safety strictness comes from compose config.
    spec = build_standard_spec(account_id)
    return PipelineSpecDocument(
        account_id=account_id,
        steps=spec.steps,
        name="Safe Mode",
        description=_TEMPLATES[7]["description"],
        template_id="safe_mode",
        status="active",
    )


# ── Registry ─────────────────────────────────────────────────────────────────

TEMPLATE_MAP: dict[str, Callable[[str], PipelineSpecDocument]] = {
    "standard": build_standard_spec,
    "lean": build_lean_spec,
    "external_focus": build_external_focus_spec,
    "own_voice": build_own_voice_spec,
    "reply_mode": build_reply_mode_spec,
    "research_heavy": build_research_heavy_spec,
    "rapid_fire": build_rapid_fire_spec,
    "safe_mode": build_safe_mode_spec,
}

# Templates valid as live POSTING pipelines (kind="post"). reply_mode is excluded:
# it is a kind="reply" spec family (terminal reply_result / verdict reply_verdict) and
# must not be seeded or offered as a posting pipeline.
VALID_POSTING_TEMPLATE_IDS: frozenset[str] = frozenset(
    {"standard", "lean", "external_focus", "own_voice", "research_heavy", "rapid_fire", "safe_mode"}
)
