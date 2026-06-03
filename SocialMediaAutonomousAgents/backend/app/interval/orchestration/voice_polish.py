"""Deterministic voice polish after safety approval, before posting."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# Keep in sync with generate_candidates.system.md "Voice rules" section.
VOICE_SOFT_FLAG_PREFIX = "voice_soft_flag"

# --- Auto-fix: remove or replace (deterministic) ---
_BANNED_PHRASES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Meta / assistant
    (re.compile(r"\bas an ai\b", re.I), ""),
    (re.compile(r"\bas a language model\b", re.I), ""),
    (re.compile(r"\bi hope this helps\b", re.I), ""),
    (re.compile(r"\bhere'?s what you need to know\b", re.I), ""),
    (re.compile(r"\bin this post,?\s+we'?ll explore\b", re.I), ""),
    (re.compile(r"\bwithout further ado\b,?\s*", re.I), ""),
    (re.compile(r"\bbuckle up\b,?\s*", re.I), ""),
    # Transitions
    (re.compile(r"\bin conclusion\b,?\s*", re.I), ""),
    (re.compile(r"\bto summarize\b,?\s*", re.I), ""),
    (re.compile(r"\bin summary\b,?\s*", re.I), ""),
    (re.compile(r"\bfurthermore\b,?\s*", re.I), ""),
    (re.compile(r"\bmoreover\b,?\s*", re.I), ""),
    (re.compile(r"\badditionally\b,?\s*", re.I), ""),
    (re.compile(r"\bin addition\b,?\s*", re.I), ""),
    (re.compile(r"\bto be clear\b,?\s*", re.I), ""),
    (re.compile(r"\bput simply\b,?\s*", re.I), ""),
    (re.compile(r"\bsimply put\b,?\s*", re.I), ""),
    (re.compile(r"\bthat said\b,?\s*", re.I), ""),
    (re.compile(r"\bhaving said that\b,?\s*", re.I), ""),
    (re.compile(r"\bon the other hand\b,?\s*", re.I), ""),
    (re.compile(r"\bmoving forward\b,?\s*", re.I), ""),
    (re.compile(r"\bgoing forward\b,?\s*", re.I), ""),
    # "Important" framing
    (re.compile(r"\bit'?s worth noting that\b\s*", re.I), ""),
    (re.compile(r"\bit is worth noting that\b\s*", re.I), ""),
    (re.compile(r"\bit'?s important to note\b,?\s*", re.I), ""),
    (re.compile(r"\bit is important to note\b,?\s*", re.I), ""),
    (re.compile(r"\bit'?s crucial to understand\b,?\s*", re.I), ""),
    (re.compile(r"\bneedless to say\b,?\s*", re.I), ""),
    (re.compile(r"\bat the end of the day\b,?\s*", re.I), ""),
    (re.compile(r"\bthis highlights\b", re.I), "this shows"),
    (re.compile(r"\bthis underscores\b", re.I), "this shows"),
    (re.compile(r"\bthis speaks volumes\b", re.I), ""),
    (re.compile(r"\bthis is a (?:stark |clear )?reminder that\b\s*", re.I), ""),
    (re.compile(r"\ba sobering reminder\b", re.I), ""),
    (re.compile(r"\ba wake-up call\b", re.I), ""),
    (re.compile(r"\bcannot be overstated\b", re.I), ""),
    (re.compile(r"\bbears mentioning\b", re.I), ""),
    (re.compile(r"\braises important questions\b", re.I), ""),
    (re.compile(r"\bsparks debate\b", re.I), ""),
    (re.compile(r"\breignites debate\b", re.I), ""),
    # Hype / engagement bait
    (re.compile(r"\bin today'?s fast[- ]paced\b[^.]*", re.I), ""),
    (re.compile(r"\bas we navigate\b[^.]*", re.I), ""),
    (re.compile(r"\blet that sink in\b\.?\s*", re.I), ""),
    (re.compile(r"\bread that again\b", re.I), ""),
    (re.compile(r"\bthe elephant in the room\b", re.I), ""),
    (re.compile(r"\blet'?s unpack (?:this|that)\b", re.I), ""),
    (re.compile(r"\bdeep dive\b", re.I), ""),
    (re.compile(r"\bdive deep\b", re.I), ""),
    (re.compile(r"\bat its core\b", re.I), ""),
    (re.compile(r"\bat the heart of it\b", re.I), ""),
    (re.compile(r"\bparadigm shift\b", re.I), "shift"),
    (re.compile(r"\bsea change\b", re.I), "shift"),
    (re.compile(r"\bgame[- ]changer\b", re.I), "big deal"),
    # Corporate / consultant
    (re.compile(r"\butilize\b", re.I), "use"),
    (re.compile(r"\butilise\b", re.I), "use"),
    (re.compile(r"\bleverage\b", re.I), "use"),
    (re.compile(r"\bdelve\b", re.I), "dig"),
    (re.compile(r"\brobust\b", re.I), "solid"),
    (re.compile(r"\bholistic\b", re.I), ""),
    (re.compile(r"\bcomprehensive\b", re.I), ""),
    (re.compile(r"\btapestry\b", re.I), "mix"),
    (re.compile(r"\becosystem\b", re.I), "world"),
    (re.compile(r"\bsynergy\b", re.I), ""),
    (re.compile(r"\bstakeholders\b", re.I), "people"),
    (re.compile(r"\bbest practices\b", re.I), ""),
    (re.compile(r"\bdouble down\b", re.I), ""),
    (re.compile(r"\blean into\b", re.I), ""),
    (re.compile(r"\bbandwidth\b", re.I), "room"),
    (re.compile(r"\bcircle back\b", re.I), ""),
    # ChatGPT-era filler
    (re.compile(r"\bnavigate the\b", re.I), "handle the"),
    (re.compile(r"\bshed light on\b", re.I), "show"),
    (re.compile(r"\billuminate\b", re.I), "show"),
    (re.compile(r"\bembark on a journey\b", re.I), ""),
    (re.compile(r"\bpivotal moment\b", re.I), "big moment"),
    (re.compile(r"\binflection point\b", re.I), "turning point"),
    (re.compile(r"\bnuanced take\b", re.I), "take"),
    (re.compile(r"\bthoughtful take\b", re.I), "take"),
    (re.compile(r"\bcomplex issue with no easy answers\b", re.I), ""),
    (re.compile(r"\bno easy answers\b", re.I), ""),
    # Legacy / automation leaks
    (re.compile(r"\b#automation\b", re.I), ""),
    (re.compile(r"\bangle\s+\d+\b", re.I), ""),
)

# --- Soft-flag only: detect AI contrast / reframe templates (do not auto-rewrite) ---
_SOFT_FLAG_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("contrast_not_x_its_y", re.compile(r"\bit'?s not [^,.]{3,50},?\s*it'?s ", re.I)),
    ("contrast_not_about", re.compile(r"\bit'?s not about [^,.]{3,50},?\s*it'?s about ", re.I)),
    ("contrast_isnt_its", re.compile(r"\bthis isn'?t [^,.]{3,50},?\s*it'?s ", re.I)),
    ("contrast_were_not", re.compile(r"\bwe'?re not [^,.]{3,50},?\s*we'?re ", re.I)),
    ("contrast_they're_not", re.compile(r"\bthey'?re not [^,.]{3,50},?\s*they'?re ", re.I)),
    ("contrast_real_issue", re.compile(r"\bthe real (?:issue|problem|story) isn'?t ", re.I)),
    ("contrast_issue_isnt", re.compile(r"\bthe (?:issue|problem|story) isn'?t [^,.]{3,40},?\s*it'?s ", re.I)),
    ("contrast_dont_think", re.compile(r"\bdon'?t think of (?:it|this) as .{3,40}think of (?:it|this) as ", re.I)),
    ("contrast_thats_not", re.compile(r"\bthat'?s not [^,.]{3,45},?\s*(?:that'?s|it'?s) ", re.I)),
    ("contrast_everyone_nobody", re.compile(r"\beveryone(?:'s| is) (?:focused on|talking about) .{3,50}nobody(?:'s| is) (?:talking about|focused on) ", re.I)),
    ("contrast_less_more", re.compile(r"\bless (?:about )?.{3,40}more (?:about )?", re.I)),
    ("contrast_question_isnt", re.compile(r"\bthe question isn'?t (?:whether )?.{3,40},?\s*it'?s ", re.I)),
    ("contrast_not_a_moment", re.compile(r"\bthis isn'?t a [^,.]{3,40} moment,?\s*it'?s a ", re.I)),
    ("contrast_distraction", re.compile(r"\b(?:is |are )?a distraction from\b", re.I)),
    ("contrast_symptom_disease", re.compile(r"\bsymptom[^.]{0,20}disease\b", re.I)),
    ("contrast_headline_story", re.compile(r"\bthe headline[^.]{0,30}the story\b", re.I)),
    ("contrast_on_one_hand", re.compile(r"\bon the one hand\b", re.I)),
    ("contrast_cant_understand_without", re.compile(r"\byou can'?t understand .+ without understanding ", re.I)),
    ("contrast_if_youre_still", re.compile(r"\bif you'?re still (?:thinking|focused) (?:about|on) .{3,40}you'?re missing ", re.I)),
    ("contrast_forget_ignore", re.compile(r"\b(?:forget|ignore) the .{3,40}(?:watch|focus on|look at) ", re.I)),
    # Staccato parallel negatives: "No law passes. No fix sticks." / "No this. No that."
    (
        "contrast_no_no_staccato",
        re.compile(
            r"\bNo\s+[^.!?]{1,80}[.!?]\s*(?:\bNo\s+[^.!?]{1,80}[.!?]\s*)+",
            re.I,
        ),
    ),
    (
        "contrast_not_not_staccato",
        re.compile(
            r"\bNot\s+[^.!?]{1,80}[.!?]\s*(?:\bNot\s+[^.!?]{1,80}[.!?]\s*)+",
            re.I,
        ),
    ),
)

# Phrase-only detectors (soft-flag if still present after auto-fix pass)
_SOFT_FLAG_PHRASE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (name, pat)
    for name, pat in (
        ("phrase_furthermore", re.compile(r"\bfurthermore\b", re.I)),
        ("phrase_moreover", re.compile(r"\bmoreover\b", re.I)),
        ("phrase_in_conclusion", re.compile(r"\bin conclusion\b", re.I)),
        ("phrase_worth_noting", re.compile(r"\bworth noting that\b", re.I)),
        ("phrase_game_changer", re.compile(r"\bgame[- ]?changer\b", re.I)),
        ("phrase_delve", re.compile(r"\bdelve\b", re.I)),
        ("phrase_utilize", re.compile(r"\butiliz(e|ing)\b", re.I)),
        ("phrase_robust", re.compile(r"\brobust\b", re.I)),
        ("phrase_paradigm", re.compile(r"\bparadigm shift\b", re.I)),
        ("phrase_fast_paced_world", re.compile(r"\bfast[- ]paced (?:world|times)\b", re.I)),
        ("phrase_let_that_sink", re.compile(r"\blet that sink in\b", re.I)),
        ("phrase_em_dash", re.compile(r"[—–]")),
        ("phrase_double_hyphen", re.compile(r"(?<=\w)\s*--\s*(?=\w)")),
    )
)

_EM_DASH = re.compile(r"\s*[—–]\s*")
_DOUBLE_HYPHEN = re.compile(r"(?<=\w)\s*--\s*(?=\w)")
_MULTI_SPACE = re.compile(r" {2,}")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")
_LEADING_PUNCT = re.compile(r"^[,;:\s]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Per-sentence chance the first letter is lowercased (casual X voice).
SENTENCE_START_LOWERCASE_PROBABILITY = 0.30


@dataclass
class VoicePolishResult:
    original: str
    polished: str
    changed: bool
    notes: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    soft_flag: bool = False


def _lowercase_first_letter(segment: str) -> str:
    chars = list(segment)
    for i, ch in enumerate(chars):
        if ch.isalpha():
            chars[i] = ch.lower()
            return "".join(chars)
    return segment


def apply_casual_sentence_starts(
    text: str,
    *,
    probability: float = SENTENCE_START_LOWERCASE_PROBABILITY,
    rng: random.Random | None = None,
) -> tuple[str, list[str]]:
    """
    With ``probability`` per sentence, lowercase the first alphabetic character
    (e.g. "Wild how. Same loop." → "wild how. Same loop.").
    """
    t = (text or "").strip()
    if not t:
        return "", []

    roll = (rng or random).random
    sentences = _SENTENCE_SPLIT.split(t)
    if len(sentences) <= 1:
        sentences = [t]

    notes: list[str] = []
    out_parts: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        if roll() < probability:
            lowered = _lowercase_first_letter(sentence)
            if lowered != sentence:
                notes.append("casual:sentence_start_lower")
                sentence = lowered
        out_parts.append(sentence)

    return " ".join(out_parts), notes


def detect_voice_violations(text: str) -> list[str]:
    """Return violation ids still present in text (used for soft-flag after auto-fix)."""
    t = (text or "").strip()
    if not t:
        return []
    found: list[str] = []
    for name, pat in _SOFT_FLAG_PATTERNS:
        if pat.search(t):
            found.append(name)
    for name, pat in _SOFT_FLAG_PHRASE_PATTERNS:
        if pat.search(t):
            found.append(name)
    return found


def polish_post(text: str) -> VoicePolishResult:
    """Apply auto-fixes, then soft-flag if generation rules were not followed."""
    original = (text or "").strip()
    if not original:
        return VoicePolishResult(original="", polished="", changed=False)

    out = original
    notes: list[str] = []

    for pattern, repl in _BANNED_PHRASES:
        new_out, n = pattern.subn(repl, out)
        if n:
            notes.append(f"fix:{pattern.pattern[:40]}")
            out = new_out

    if _EM_DASH.search(out):
        out = _EM_DASH.sub(", ", out)
        notes.append("fix:em_dash")
    if _DOUBLE_HYPHEN.search(out):
        out = _DOUBLE_HYPHEN.sub(", ", out)
        notes.append("fix:double_hyphen")

    out = _MULTI_SPACE.sub(" ", out)
    out = _SPACE_BEFORE_PUNCT.sub(r"\1", out)
    out = _LEADING_PUNCT.sub("", out)
    out = out.strip()
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\.\s*\.", ".", out)
    out = re.sub(r",\s*\.", ".", out)

    violations = detect_voice_violations(out)
    if not violations:
        casual, casual_notes = apply_casual_sentence_starts(out)
        if casual_notes:
            notes.extend(casual_notes)
            out = casual

    return VoicePolishResult(
        original=original,
        polished=out,
        changed=out != original,
        notes=notes,
        violations=violations,
        soft_flag=bool(violations),
    )
