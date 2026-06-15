# Task 07 — Prompt Templates + Banned-Phrases Archive

## Task Overview

**Files:**
- `SocialMediaAutonomousAgents/backend/app/interval_crew/prompts/tasks/compose_timeline_post.user.md`
- `SocialMediaAutonomousAgents/backend/app/interval_crew/prompts/tasks/compose_timeline_post.system.md` (light touch)
- NEW: `SocialMediaAutonomousAgents/docs/voice-banned-phrases-archive.md`

Two jobs:
1. Align the compose prompt template with the soul vocabulary (contrast patterns instead of "banned semantics"), keeping the existing template variable names where Task 06 already wired them.
2. Preserve the ~80 historical banned phrases in a docs file (institutional memory) since they are removed from code in Task 06.

**What it affects:** the text sent to the LLM at compose time (template), and documentation only (archive).

**Dependencies:** Task 06 fills `negative_semantics_block` with `format_contrast_patterns_for_prompt(...)` output. To avoid a same-PR variable rename across code + template, we keep the template variable name `negative_semantics_block` but relabel the surrounding prose. (An optional clean rename is in Decision Defense.)

---

## Proposed Solution

### a. `compose_timeline_post.user.md`

#### BEFORE (lines 1–25)
```
Account niche: {niche}

Account personality (voice for the opinion section — follow closely; energetic, emotional, loose grammar, not AI):
{account_personality}

Post structure and formatting rules:
{account_system_prompt}

Banned semantics, phrases, characters, and sentence structures (never use in opinion or quip):
{negative_semantics_block}

Reference analysis (patterns from top external + own posts — nudge voice, not topic):
{reference_context_block}

Source tweet (id={tweet_id}, popularity_score={popularity_score}):
{source_text}

Character limits (required …):
…
Rewrite for posting. JSON only.
```

#### AFTER (lines 1–25)
```
Account niche: {niche}

Account personality (the account's character and voice — follow closely; energetic, emotional, loose grammar, not AI):
{account_personality}

Posting prompt (structure and formatting rules for this account):
{account_system_prompt}

Voice guidance — patterns to avoid and patterns to lean into:
{negative_semantics_block}

Reference analysis (patterns from top external + own posts — nudge voice, not topic):
{reference_context_block}

Source tweet (id={tweet_id}, popularity_score={popularity_score}):
{source_text}

Character limits (required …):
…
Rewrite for posting. JSON only.
```

> Only prose labels change. `{account_personality}`, `{account_system_prompt}`, `{negative_semantics_block}` remain the literal template variables filled by `prompt_loader.load_template(...)` in Task 06. `format_contrast_patterns_for_prompt` already emits "Avoid these patterns…" / "Lean into these patterns…" sub-headers, so the block reads naturally under the new "Voice guidance" label.

### b. `compose_timeline_post.system.md` (light touch)
No structural change required. Optionally update the line referencing "Voice rules" to read "Follow the account's personality and voice guidance" for consistency. The example tone block stays.

### c. NEW — `SocialMediaAutonomousAgents/docs/voice-banned-phrases-archive.md`

```markdown
# Voice Banned-Phrases Archive (historical)

> **Status:** Archived reference. NOT used by code as of the Soul pipeline change.
> Previously hardcoded in `app/interval/orchestration/voice_polish.py` as `_BANNED_PHRASES`
> (auto-fix) and `_SOFT_FLAG_PATTERNS` / `_SOFT_FLAG_PHRASE_PATTERNS` (soft-flag).

## Why these were removed
The Soul pipeline shifts voice control from **post-generation regex** to
**generation-time guidance** (account `personality` + `contrast_patterns`) plus a small
deterministic **punctuation** auto-fix. The ~80 phrase substitutions below were brittle,
global, and not even wired into the live composer. They are preserved here for reference
and in case a specific phrase needs to be reintroduced as account `contrast_patterns`
(negative correlation) or as a punctuation rule.

## Auto-fix phrases (pattern → replacement; blank = delete)
### Meta / assistant
- as an ai → (delete)
- as a language model → (delete)
- i hope this helps → (delete)
- here's what you need to know → (delete)
- in this post, we'll explore → (delete)
- without further ado → (delete)
- buckle up → (delete)
### Transitions
- in conclusion, to summarize, in summary, furthermore, moreover, additionally,
  in addition, to be clear, put simply, simply put, that said, having said that,
  on the other hand, moving forward, going forward → (delete)
### "Important" framing
- it's worth noting that, it is worth noting that, it's important to note,
  it is important to note, it's crucial to understand, needless to say,
  at the end of the day → (delete)
- this highlights → this shows
- this underscores → this shows
- this speaks volumes, this is a (stark|clear) reminder that, a sobering reminder,
  a wake-up call, cannot be overstated, bears mentioning, raises important questions,
  sparks debate, reignites debate → (delete)
### Hype / engagement bait
- in today's fast-paced …, as we navigate …, let that sink in, read that again,
  the elephant in the room, let's unpack this/that, deep dive, dive deep,
  at its core, at the heart of it → (delete)
- paradigm shift → shift
- sea change → shift
- game-changer → big deal
### Corporate / consultant
- utilize → use; utilise → use; leverage → use; delve → dig; robust → solid;
  tapestry → mix; ecosystem → world; stakeholders → people; bandwidth → room
- holistic, comprehensive, synergy, best practices, double down, lean into,
  circle back → (delete)
### ChatGPT-era filler
- navigate the → handle the; shed light on → show; illuminate → show;
  pivotal moment → big moment; inflection point → turning point;
  nuanced take → take; thoughtful take → take
- embark on a journey, complex issue with no easy answers, no easy answers → (delete)
### Legacy / automation leaks
- #automation → (delete); "angle <number>" → (delete)

## Soft-flag contrast structures (detected, triggered regeneration)
These map directly onto default `contrast_patterns` (correlation = negative):
"It's not X, it's Y"; "It's not about X, it's about Y"; "This isn't X, it's Y";
"We're not X, we're Y"; "They're not X, they're Y"; "The real issue/problem/story isn't …";
"The issue isn't X, it's Y"; "Don't think of it as X, think of it as Y"; "That's not X, it's Y";
"Everyone's focused on X, nobody's …"; "Less about X, more about Y"; "The question isn't X, it's Y";
"This isn't a X moment, it's a Y moment"; "X is a distraction from Y"; "symptom … disease";
"the headline … the story"; "On the one hand …"; "You can't understand X without understanding Y";
"If you're still thinking about X, you're missing Y"; "Forget the X, watch/focus on Y";
staccato "No X. No Y."; staccato "Not X. Not Y."

## Tone behavior (now personality prose)
- Casual sentence-start lowercasing (~30% per sentence) — formerly
  `SENTENCE_START_LOWERCASE_PROBABILITY`. Now expressed in an account's `personality`
  if desired (e.g. "lowercases the start of a sentence now and then for a casual feel").
```

### d. Written explanation
The template edit keeps the machinery intact (same variables) but makes the prompt read in the soul's language and—critically—presents contrast guidance as *both* avoid and lean lists rather than a one-directional "banned" list. That matches `format_contrast_patterns_for_prompt` from Task 01.

The archive doc is pure documentation. It captures the exact substitutions and contrast structures so nothing is lost, and explicitly maps the soft-flag structures to the default `contrast_patterns` (which is exactly where they now live), making the migration legible to a future reader.

---

## Decision Defense

**Why not rename the `{negative_semantics_block}` template variable to `{voice_guidance_block}` now?**
It would require editing the template and the `prompt_loader.load_template(...)` kwargs in the same change, increasing surface area and merge risk for zero behavioral gain. The variable is an internal name; the user-visible prose is what we relabel. The rename is a trivial, isolated follow-up: change the key in `compose_timeline_post.py` and the `{...}` token in the template together.

**Why archive in `SocialMediaAutonomousAgents/docs/` and not delete outright?**
These phrases encode hard-won taste about what "AI slop" looks like. If a future persona needs to hard-block a phrase, this is the menu. Deleting would throw away that curation; keeping it in code would reintroduce the global-rule anti-pattern.

**Why keep the system prompt essentially unchanged?**
It defines the JSON contract and the three-part structure, which are independent of the soul refactor. Minimizing edits there reduces the chance of breaking the parser (`_parse_compose_json`).

**No frontend in this task.**
