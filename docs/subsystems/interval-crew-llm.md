# Interval crew and LLM

Scope: prompt loading, Claude integration, and the **alternate** generate→rank content pipeline. The **live posting path** uses timeline compose prompts instead — see [compose-and-safety](compose-and-safety.md). Parent: [../PROJECT.md](../PROJECT.md).

## Key paths

| Path | Role |
|------|------|
| `SocialMediaAutonomousAgents/backend/app/interval_crew/prompt_loader.py` | Load `.md` templates from `prompts/` |
| `SocialMediaAutonomousAgents/backend/app/interval_crew/llm_pipeline.py` | `generate_candidates`, `rank_candidates` |
| `SocialMediaAutonomousAgents/backend/app/interval_crew/runner.py` | `run_content_pipeline` |
| `SocialMediaAutonomousAgents/backend/app/interval_crew/crew.py` | Optional CrewAI sequential crew |
| `SocialMediaAutonomousAgents/backend/app/infrastructure/claude_client.py` | Anthropic API wrapper |
| `SocialMediaAutonomousAgents/backend/app/agents/content_creator.py` | Thin facade over `llm_pipeline` |
| `SocialMediaAutonomousAgents/backend/app/interval_crew/prompts/` | Live prompt files (do not duplicate here) |
| `SocialMediaAutonomousAgents/backend/app/interval_crew/tools/` | Tick data helpers used by orchestration |
| `SocialMediaAutonomousAgents/backend/app/pipeline/tools/llm/` | Live-path LLM tools (compose, reference pattern summary) |

## Configuration

| Setting | Effect |
|---------|--------|
| `ANTHROPIC_API_KEY` | Enables Claude calls |
| `CLAUDE_MODEL` | Default `claude-sonnet-4-6` |

When Claude is disabled, `llm_pipeline` uses deterministic fallback candidate text.

## Prompt inventory

| File | Used by |
|------|---------|
| `tasks/compose_timeline_post.system.md` | **Live path** — [compose-and-safety](compose-and-safety.md) |
| `tasks/compose_timeline_post.user.md` | **Live path** |
| `tasks/reference_pattern_summary.system.md` | **Pipeline** — `tools.llm.reference_pattern_summary` |
| `tasks/reference_pattern_summary.user.md` | **Pipeline** — timeline + own-post subagents |
| `tasks/niche_fit_check.system.md` | `SafetyGuardian` niche check |
| `tasks/niche_fit_check.user.md` | `SafetyGuardian` niche check |
| `tasks/generate_candidates.system.md` | Alternate generate/rank path |
| `tasks/generate_candidates.user.md` | Alternate path |
| `tasks/rank_candidates.system.md` | Alternate path |
| `tasks/rank_candidates.user.md` | Alternate path |
| `agents/content_creator.role.md` | CrewAI / role metadata |
| `agents/content_ranker.role.md` | CrewAI / role metadata |
| `tasks/analyze_tick.system.md` | Reserved; not wired in live tick |

## Alternate pipeline: generate → rank

`run_content_pipeline(tick_input, prompt_bundle)`:

1. `generate_candidates` — JSON `{posts: [...]}` up to `max_candidates`
2. `rank_candidates` — reorders by LLM ranking

`kickoff_content_pipeline(..., use_crew=True)` can run CrewAI agents when installed; on failure falls back to `llm_pipeline`.

**Not called** by `interval/runner.py` today. The orchestrator still constructs `ContentCreator` for tests and future use, but the production tick uses `compose_formatted_post` for timeline references.

## Claude client

`get_claude_client()` exposes `enabled`, `messages_json_dict(system, user, max_tokens)` for structured JSON responses used across compose, safety, and generate/rank.

## Pipeline LLM tools

LLM calls for the posting pipeline should live under `app/pipeline/tools/llm/`, not inline in data or deterministic modules. Each tool declares `PROMPT_STEM` and loads matching files from `prompts/tasks/`.

Import surface: `from app.pipeline import tools` → `tools.llm.<name>`.

See [pipeline-runbook](pipeline-runbook.md).

## Related docs

- Tools catalog and runbook: [pipeline-runbook](pipeline-runbook.md)
- Live compose: [compose-and-safety](compose-and-safety.md)
- Orchestration: [interval-orchestration](interval-orchestration.md)
- X data for prompts: [reference-ingestion](reference-ingestion.md)
