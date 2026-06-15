# Soul Pipeline — Implementation Plan Set

Refactor the six text-shaping controllers of an account into one cohesive, per-account,
versioned **Soul** object, and make the live compose pipeline actually use it.

**Start here:** [`00-overview.md`](./00-overview.md) — context, the target Soul model, the
pipeline diagram, architecture decisions, and sequencing.

## Reading order
| # | File | What it covers |
|---|---|---|
| 0 | [00-overview.md](./00-overview.md) | Why, target model, pipeline flow, decisions, sequencing, done-criteria |
| 1 | [01-data-model.md](./01-data-model.md) | `AccountSoul`, `ContrastPattern`, `PunctuationRule`, defaults, legacy migration, accessors |
| 2 | [02-voice-revision.md](./02-voice-revision.md) | Archive full soul snapshot per version |
| 3 | [03-services-and-api.md](./03-services-and-api.md) | PATCH body, `/edit` view, create body |
| 4 | [04-repository-and-migration.md](./04-repository-and-migration.md) | normalize/serialize/upsert + one-time migration script |
| 5 | [05-versioning.md](./05-versioning.md) | Hash all soul fields; write revision |
| 6 | [06-compose-pipeline.md](./06-compose-pipeline.md) | `polish_text`, prompt injection, runner wiring, dead-code removal |
| 7 | [07-prompts-and-archive.md](./07-prompts-and-archive.md) | Prompt template prose, banned-phrases archive doc |
| 8 | [08-frontend.md](./08-frontend.md) | Types + Voice tab render of full soul + UI steps |
| 9 | [09-verification.md](./09-verification.md) | Build, migrate, API/compose/UI checks, rollback |

## Recommended implementation order
`01 → 02 → 05 → 04 → 03 → 07 → 06 → 08 → 09`

> **Read `00-overview.md §7 "Post-review corrections" first.** A review against the live code found ten gaps (missed call sites that break at runtime, a misidentified edit form, unlisted breaking tests, and a Task 02↔08 contradiction). Each fix is folded into its owning task; §7 is the index. The most load-bearing: the `negative_semantics` accessor removal must also sweep `account_snapshot_service.py` and the `runner.py` `TickInput` construction, and `UpdateAccountModal.tsx` must be repointed at `posting_prompt` or voice edits silently no-op.

## The Soul, at a glance
```
account.soul = {
  personality,         # prose: character, likes/dislikes, reactions, tone quirks  → LLM prompt
  posting_prompt,      # structural composition instructions (was system_prompt)    → LLM prompt
  contrast_patterns,   # [{ text, correlation: positive|negative }] (was neg-sem)   → LLM prompt (avoid/lean)
  punctuation_rules,   # [{ pattern: regex, replacement|null }]                      → post-gen auto-fix
  voice_version_{hash,seq,label}
}
```

## Key behavioral rules (confirmed with the user)
- Punctuation rules **auto-fix only** (never regenerate).
- Contrast patterns are **LLM guidance only** (no regex post-detection / soft-flag).
- The ~80 historical banned phrases are **archived to docs**, removed from code, NOT recreated.
- Casual sentence-lowercasing becomes **personality prose**, not a global rule.

## Target project paths
- Backend: `SocialMediaAutonomousAgents/backend/app/...`
- Frontend: `SocialMediaAutonomousAgents/frontend/src/...`
- Archive doc: `SocialMediaAutonomousAgents/docs/voice-banned-phrases-archive.md`
- DB reality: one account, `JohnJames_News`.
