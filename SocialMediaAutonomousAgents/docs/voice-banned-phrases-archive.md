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
