# Compose and safety

Scope: turning a ranked timeline reference into a post and validating it before publish. Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/interval/compose_timeline_post.py` | `compose_formatted_post`, length budget |
| `SocialMediaAutonomousAgents/backend/app/agents/safety_guardian.py` | `SafetyGuardian.evaluate` |
| `SocialMediaAutonomousAgents/backend/app/interval/tweet_topic_preanalysis.py` | `GatheredTweet`, `preanalysis_from_winner` |
| `SocialMediaAutonomousAgents/backend/app/interval/orchestration/voice_polish.py` | Voice heuristics (alternate rank path) |
| `SocialMediaAutonomousAgents/backend/app/interval/orchestration/safety_filter.py` | Ranked-candidate selection (not live tick) |
| `SocialMediaAutonomousAgents/backend/app/pipeline/tools/llm/compose_timeline_post.py` | Pipeline wrapper around `compose_formatted_post` |
| `SocialMediaAutonomousAgents/backend/app/pipeline/tools/llm/reference_pattern_summary.py` | Pattern analysis across top reference posts |

## Live compose path

For each ranked reference, `run_account_pipeline` calls:

1. `compose_formatted_post(winner, niche, account_system_prompt, account_personality, negative_semantics, ...)`
2. `ctx.guardian.evaluate(body, niche=...)`

Up to `MAX_REGENERATION_ROUNDS` regeneration attempts per reference. If reject reason is `niche_mismatch:*`, tries the **next** reference tweet.

### Output shape

```
{opinion}

{quip}

{source_media_or_permalink_url}
```

Total length ≤ 280 characters. Link length is reserved first via `compute_post_length_budget`; the LLM receives separate opinion/quip char caps.

### Prompts

Loaded from `interval_crew/prompts/tasks/compose_timeline_post.*.md`. Account fields injected:

- `system_prompt`, `personality`, `negative_semantics`
- Source tweet text, id, popularity score
- Regeneration hints on safety or length retries

Without Claude, deterministic `_fallback_compose` + shrink-to-budget is used.

### Reference context (pipeline, incoming)

The [pipeline runbook](pipeline-runbook.md) produces structured briefs before compose:

- **Timeline analysis** — top external posts, `selected_winner_id`, `pattern_summary`, `voice_signals`
- **Own-posts analysis** — top own posts, style/success patterns (skipped when history is thin)

These briefs are injected via `reference_context_block` in `compose_timeline_post.user.md` (alongside the single winner text). **Timeline/search winner = topic/link**; **own-post brief = voice/structure**.

## Safety guardian

`SafetyGuardian.evaluate(content, niche)` checks:

| Check | Reject reason |
|-------|---------------|
| Length &lt; 10 or &gt; 300 | `too_short` / `too_long` |
| JSON / prompt leak markers | `prompt_json_leak` |
| Legacy automation markers | various |
| Niche fit (Claude + `niche_fit_check` prompts) | `niche_mismatch:{reason}` |

If Claude is disabled, niche fit check is **skipped** (passes unless other rules fail).

## Voice polish (alternate path only)

`voice_polish.py` / `voice_select.py` / `safety_filter.select_from_ranked` support polishing ranked **generated** candidates. The timeline pipeline in `interval/runner.py` does **not** invoke these modules today.

## Related docs

- Pipeline runbook + subagents: [pipeline-runbook](pipeline-runbook.md)
- Prompt files overview: [interval-crew-llm](interval-crew-llm.md)
- Reference selection: [reference-ingestion](reference-ingestion.md)
- Post after approval: [interval-orchestration](interval-orchestration.md)
