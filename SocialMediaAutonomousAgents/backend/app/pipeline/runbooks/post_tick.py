"""Readable runbook: ordered steps for reference analysis before compose.

Each entry is a ``Step`` with declared artifact reads/writes. Composites use
``parallel()`` and ``chain()`` for fetch fan-out and rank→brief sequences.
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
    parallel(
        Step(
            "fetch_timeline_references",
            steps.fetch_timeline_references,
            reads=(ArtifactKey.ACCOUNT_BUNDLE,),
            writes=(ArtifactKey.TIMELINE_REFERENCES,),
            purpose="Fetch following-timeline reference tweets",
        ),
        Step(
            "fetch_search_references",
            steps.fetch_search_references,
            reads=(ArtifactKey.ACCOUNT_BUNDLE,),
            writes=(ArtifactKey.SEARCH_REFERENCES,),
            reads_optional=frozenset({ArtifactKey.SEARCH_REFERENCES}),
            purpose="Fetch X recent-search reference tweets (optional)",
        ),
        id="fetch_external_references",
        purpose="Acquire external reference pools in parallel",
    ),
    Step(
        "merge_external_references",
        steps.merge_external_references,
        reads=(ArtifactKey.TIMELINE_REFERENCES, ArtifactKey.SEARCH_REFERENCES),
        writes=(ArtifactKey.TIMELINE_REFERENCES,),
        reads_optional=frozenset({ArtifactKey.SEARCH_REFERENCES}),
        purpose="Merge timeline and search reference pools by tweet id",
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
)
