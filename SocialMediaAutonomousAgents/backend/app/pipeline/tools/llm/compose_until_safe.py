"""Coarse compose tool: owns the ranked-refs build + the ref-fallback × regeneration
loop and the guardian feedback that runner.py:304-365 runs imperatively today. Writes
COMPOSED_POST when a body passes the guardian, and always writes SAFETY_VERDICT."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.interval.compose_timeline_post import compose_formatted_post
from app.interval.reference_context import format_reference_context_for_compose
from app.agents.safety_guardian import is_niche_mismatch_reject
from app.interval.tweet_topic_preanalysis import GatheredTweet, preanalysis_from_winner
from app.services.tick_data_service import TickDataService
from app.social.tweet_enrichment import filter_rows_with_urls
from app.pipeline.services.deps import PostRunDeps
from app.pipeline.types.artifacts import ArtifactKey
from app.pipeline.types.context import TickRunContext
from app.pipeline.types.tool import StepResult

logger = logging.getLogger(__name__)

TOOL_ID = "llm.compose_until_safe"
TOOL_KIND = "llm"
TOOL_PURPOSE = "Compose a post, regenerating with guardian feedback and falling back across references until one passes safety"
TOOL_READS = (ArtifactKey.TIMELINE_ANALYSIS, ArtifactKey.OWN_POSTS_ANALYSIS, ArtifactKey.TIMELINE_RANKED, ArtifactKey.TIMELINE_REFERENCES)
TOOL_READS_OPTIONAL = (ArtifactKey.OWN_POSTS,)
TOOL_WRITES = (ArtifactKey.COMPOSED_POST, ArtifactKey.SAFETY_VERDICT)


def _ranked_refs(ctx: TickRunContext, copied_exclude: frozenset[str]) -> list[GatheredTweet]:
    """Verbatim port of reference_phase.ranked_refs_from_runbook (reference_phase.py:49-67):
    read TIMELINE_RANKED.ranked rows, drop copied refs, cap to max_reference_fallback_attempts."""
    ranked_payload = ctx.data.get("timeline_ranked") or {}
    ranked_raw = ranked_payload.get("ranked") if isinstance(ranked_payload, dict) else []
    out: list[GatheredTweet] = []
    for row in ranked_raw or []:
        if not isinstance(row, dict):
            continue
        gt = GatheredTweet.model_validate(row)
        if gt.tweet_id in copied_exclude:
            continue
        out.append(gt)
    max_attempts = max(0, int(settings.max_reference_fallback_attempts))
    if max_attempts > 0:
        out = out[:max_attempts]
    return out


def _reference_inputs(ctx: TickRunContext) -> tuple[str, dict, list[dict]]:
    """Derive the compose-context block + reference pool from the SENSE artifacts that
    the runner used to carry on ActLive. Mirrors reference_phase.py:88,103 and
    runner.py:244-247 — now sourced from ctx, not deps.live (CC-7).

      reference_context_block  ← format_reference_context_for_compose(TIMELINE_ANALYSIS,
                                  OWN_POSTS_ANALYSIS)  (the two brief artifacts)
      refs_payload             ← TIMELINE_REFERENCES artifact (for pulled_tweet_stats)
      reference_pool           ← filter_rows_with_urls(merge_reference_pool(refs_payload))
    """
    timeline_analysis = ctx.data.get("timeline_analysis") or {}
    own_posts_analysis = ctx.data.get("own_posts_analysis") or {}
    block = format_reference_context_for_compose(timeline_analysis, own_posts_analysis)
    refs_payload = ctx.data.get("timeline_references") or {}
    if not isinstance(refs_payload, dict):
        refs_payload = {}
    reference_pool = filter_rows_with_urls(TickDataService.merge_reference_pool(refs_payload))
    return block, refs_payload, reference_pool


def _fivegrams(text: str) -> set[str]:
    """Return the set of whitespace-token 5-grams for overlap scoring."""
    tokens = text.lower().split()
    if len(tokens) < 5:
        return {" ".join(tokens)}
    return {" ".join(tokens[i:i + 5]) for i in range(len(tokens) - 4)}


def _similar_recent_post(body: str, own_posts_raw: list) -> str | None:
    """Return the text of the first recent post (last 5) that overlaps >60% of 5-grams
    with *body*, or None if no match.  Handles both raw strings and dicts with a 'text' key."""
    body_grams = _fivegrams(body)
    if not body_grams:
        return None
    recent = own_posts_raw[-5:] if len(own_posts_raw) > 5 else own_posts_raw
    for item in recent:
        post_text = item if isinstance(item, str) else (item.get("text") if isinstance(item, dict) else None)
        if not post_text:
            continue
        post_grams = _fivegrams(post_text)
        if not post_grams:
            continue
        overlap = len(body_grams & post_grams) / len(body_grams)
        if overlap > 0.60:
            return post_text
    return None


def run(ctx: TickRunContext, deps: PostRunDeps) -> StepResult:
    live = deps.live
    guardian = live.guardian
    account = live.account
    ranked_refs = _ranked_refs(ctx, live.copied_exclude)
    reference_context_block, refs_payload, reference_pool = _reference_inputs(ctx)
    max_rounds = max(1, int(live.max_regeneration_rounds))
    own_posts_raw: list = ctx.data.get("own_posts") or []
    if not isinstance(own_posts_raw, list):
        own_posts_raw = []

    last_reject: str | None = None
    selected_body: str | None = None
    selected_round: int | None = None
    selected_ref_idx: int | None = None
    winner = None
    topic_pre = None
    references_tried = 0

    for ref_idx, candidate in enumerate(ranked_refs):
        winner = candidate
        topic_pre = preanalysis_from_winner(winner)
        references_tried += 1
        candidate_reject: str | None = None
        for reg_round in range(max_rounds):
            body = compose_formatted_post(
                winner,
                account.category,
                account_posting_prompt=(account.posting_prompt or "").strip(),
                account_personality=(account.personality or "").strip(),
                contrast_patterns=list(account.contrast_patterns or []),
                punctuation_rules=list(account.punctuation_rules or []),
                reference_context_block=reference_context_block,
                regeneration_round=reg_round,
                safety_reject_reason=candidate_reject if reg_round > 0 else None,
            )
            if own_posts_raw:
                similar_post = _similar_recent_post(body, own_posts_raw)
                if similar_post is not None:
                    candidate_reject = (
                        f"too_similar_to_recent_post: Your draft was too similar to a recent post:"
                        f" '{similar_post[:100]}'. Write about a completely different angle or topic."
                    )
                    continue
            approved, reject = guardian.evaluate(body, niche=account.category)
            if approved:
                selected_body = body
                selected_round = reg_round
                selected_ref_idx = ref_idx
                break
            candidate_reject = reject or "safety_rejected"
            if is_niche_mismatch_reject(candidate_reject):
                last_reject = candidate_reject
                break
        if selected_body is not None:
            break
        last_reject = candidate_reject or last_reject

    # Cost reporting: NOTHING to do here. Per CC-9, the engine's cost meter (07 §4) tallies
    # LLM spend automatically — every compose_formatted_post + guardian.evaluate call (incl.
    # each regeneration round) funnels through ClaudeClient, which accumulates token cost per
    # run; 07's cost wrapper drains it after each leaf. This tool reports no cost itself and
    # sets no `_step_cost_usd` key (that earlier-draft seam is dropped — 07 §4.1).

    if selected_body is None or winner is None or topic_pre is None:
        ctx.set_artifact(
            ArtifactKey.SAFETY_VERDICT,
            {"approved": False, "last_reject": last_reject or "all_compose_attempts_failed",
             "references_tried": references_tried, "regeneration_round": 0},
        )
        # No COMPOSED_POST written → publish_post skips. Mirror today's "rejected" outcome.
        return StepResult(ok=True, skipped=True, skip_reason=last_reject or "all_compose_attempts_failed")

    source_id = topic_pre.selected_tweet_ids[0] if topic_pre.selected_tweet_ids else None
    pull_stats = refs_payload.get("pulled_tweet_stats") or {}
    source_metrics = _source_metrics_at_pick(winner)

    ctx.set_artifact(
        ArtifactKey.COMPOSED_POST,
        {
            "body": selected_body,
            "reference_index": selected_ref_idx or 0,
            "references_tried": references_tried,
            "regeneration_round": selected_round or 0,
            "source_reference_tweet_id": source_id,
            "chosen_embed_url": topic_pre.chosen_embed_url,
            "source_reference_metrics_at_pick": source_metrics,
            "tweets_pulled": len(reference_pool),
            "tweets_pulled_new": int(pull_stats.get("new_count") or 0),
            "tweets_pulled_duplicates": int(pull_stats.get("duplicate_count") or 0),
        },
    )
    ctx.set_artifact(
        ArtifactKey.SAFETY_VERDICT,
        {"approved": True, "last_reject": last_reject, "references_tried": references_tried,
         "regeneration_round": selected_round or 0},
    )
    return StepResult(ok=True, payload={"body": selected_body, "references_tried": references_tried})


def _source_metrics_at_pick(winner) -> dict | None:
    from app.metrics.derived import extract_entities, extract_text_features
    if winner is None:
        return None
    return {
        "tweet_id": winner.tweet_id,
        "popularity_score": winner.popularity_score,
        "author_followers_count": winner.metrics.get("author_followers_count"),
        "quote_count": winner.metrics.get("quote_count"),
        "impression_count": winner.metrics.get("impression_count"),
        "text_features": extract_text_features(winner.text),
        "entity_tags": extract_entities(winner.metrics),
    }
