"""Readable runbook: ordered steps for reference analysis before compose.

Each entry is a ``Step`` with declared artifact reads/writes. Composites use
``parallel()`` and ``chain()`` for fetch fan-out and rank→brief sequences.

⚠️  KEEP IN SYNC WITH THE FRONTEND FLOW DIAGRAM.
The dashboard mirrors this runbook step-for-step in
``frontend/src/lib/pipeline/flowGraph.ts`` (rendered by
``frontend/src/features/pipeline/PipelineFlowDiagram.tsx``). The node ids there
must equal the dotted step ids ``flatten_steps`` produces from this file. If you
add/rename/reorder a step here, update flowGraph.ts — and vice versa.
"""

from __future__ import annotations

from app.pipeline.services import steps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.flow import Step, chain, parallel

POST_TICK_REFERENCE_STEPS: tuple[Step, ...] = (
    Step(
        "load_account_bundle",
        steps.load_account_bundle,
        writes=(ArtifactKey.ACCOUNT_BUNDLE,),
        purpose="Load X profile and tracked-post engagement metrics",
    ),
    Step(
        "fetch_search_references",
        steps.fetch_search_references,
        reads=(ArtifactKey.ACCOUNT_BUNDLE,),
        writes=(ArtifactKey.SEARCH_REFERENCES,),
        purpose="Fetch X recent-search reference tweets, one query per niche",
    ),
    Step(
        "collect_external_references",
        steps.collect_external_references,
        reads=(ArtifactKey.SEARCH_REFERENCES,),
        writes=(ArtifactKey.TIMELINE_REFERENCES,),
        purpose="Build the external reference pool from per-niche search results",
    ),
    Step(
        "fetch_own_post_history",
        steps.fetch_own_post_history,
        writes=(ArtifactKey.OWN_POSTS,),
        purpose="Load own-post history with engagement metrics",
    ),
    parallel(
        chain(
            Step(
                "rank_external_references",
                steps.rank_external_references,
                reads=(ArtifactKey.TIMELINE_REFERENCES,),
                writes=(ArtifactKey.TIMELINE_RANKED,),
                purpose="Rank top external references by engagement",
            ),
            Step(
                "brief_external_references",
                steps.brief_external_references,
                reads=(ArtifactKey.TIMELINE_RANKED,),
                writes=(ArtifactKey.TIMELINE_ANALYSIS,),
                purpose="LLM pattern brief for external references",
            ),
            id="analyze_external_references",
        ),
        chain(
            Step(
                "rank_own_posts",
                steps.rank_own_posts,
                reads=(ArtifactKey.OWN_POSTS,),
                writes=(ArtifactKey.OWN_POSTS_RANKED,),
                purpose="Rank top own posts by engagement",
            ),
            Step(
                "brief_own_posts",
                steps.brief_own_posts,
                reads=(ArtifactKey.OWN_POSTS_RANKED, ArtifactKey.OWN_POSTS,),
                writes=(ArtifactKey.OWN_POSTS_ANALYSIS,),
                purpose="LLM pattern brief for own-post voice",
            ),
            id="analyze_own_posts",
        ),
        id="summarize_for_compose",
        purpose="Produce compose context briefs for external and own posts",
    ),
    Step(
        "compose_until_safe",
        steps.compose_step,
        reads=(ArtifactKey.TIMELINE_ANALYSIS, ArtifactKey.OWN_POSTS_ANALYSIS, ArtifactKey.TIMELINE_RANKED, ArtifactKey.TIMELINE_REFERENCES),
        writes=(ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT),
        purpose="Compose with guardian feedback + reference fallback until safe",
    ),
    Step(
        "publish_post",
        steps.publish_step,
        reads=(ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT, ArtifactKey.ACCOUNT_BUNDLE),
        writes=(ArtifactKey.PUBLISHED_POST,),
        purpose="Publish to X (idempotent) and finalize state",
    ),
)
