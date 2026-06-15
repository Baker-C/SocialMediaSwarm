"""Voice polish rules serialized for API consumption."""

from __future__ import annotations

from typing import TypedDict


class BannedPhrase(TypedDict):
    pattern: str
    replacement: str | None


class ContrastPattern(TypedDict):
    name: str
    description: str


class VoicePolishRulesResponse(TypedDict):
    banned_phrases: list[BannedPhrase]
    contrast_patterns: list[ContrastPattern]
    punctuation_rules: list[str]
    tone_rules: list[str]


def get_voice_polish_rules() -> VoicePolishRulesResponse:
    """Return all voice polish rules applied to generated posts."""
    banned_phrases: list[BannedPhrase] = [
        {"pattern": "as an ai", "replacement": None},
        {"pattern": "as a language model", "replacement": None},
        {"pattern": "i hope this helps", "replacement": None},
        {"pattern": "here's what you need to know", "replacement": None},
        {"pattern": "in this post, we'll explore", "replacement": None},
        {"pattern": "without further ado", "replacement": None},
        {"pattern": "buckle up", "replacement": None},
        {"pattern": "in conclusion", "replacement": None},
        {"pattern": "to summarize", "replacement": None},
        {"pattern": "in summary", "replacement": None},
        {"pattern": "furthermore", "replacement": None},
        {"pattern": "moreover", "replacement": None},
        {"pattern": "additionally", "replacement": None},
        {"pattern": "in addition", "replacement": None},
        {"pattern": "to be clear", "replacement": None},
        {"pattern": "put simply", "replacement": None},
        {"pattern": "simply put", "replacement": None},
        {"pattern": "that said", "replacement": None},
        {"pattern": "having said that", "replacement": None},
        {"pattern": "on the other hand", "replacement": None},
        {"pattern": "moving forward", "replacement": None},
        {"pattern": "going forward", "replacement": None},
        {"pattern": "it's worth noting that", "replacement": None},
        {"pattern": "it's important to note", "replacement": None},
        {"pattern": "it's crucial to understand", "replacement": None},
        {"pattern": "needless to say", "replacement": None},
        {"pattern": "at the end of the day", "replacement": None},
        {"pattern": "this highlights", "replacement": "this shows"},
        {"pattern": "this underscores", "replacement": "this shows"},
        {"pattern": "this speaks volumes", "replacement": None},
        {"pattern": "this is a reminder that", "replacement": None},
        {"pattern": "a sobering reminder", "replacement": None},
        {"pattern": "a wake-up call", "replacement": None},
        {"pattern": "cannot be overstated", "replacement": None},
        {"pattern": "bears mentioning", "replacement": None},
        {"pattern": "raises important questions", "replacement": None},
        {"pattern": "sparks debate", "replacement": None},
        {"pattern": "reignites debate", "replacement": None},
        {"pattern": "in today's fast-paced", "replacement": None},
        {"pattern": "as we navigate", "replacement": None},
        {"pattern": "let that sink in", "replacement": None},
        {"pattern": "read that again", "replacement": None},
        {"pattern": "the elephant in the room", "replacement": None},
        {"pattern": "let's unpack this", "replacement": None},
        {"pattern": "deep dive", "replacement": None},
        {"pattern": "dive deep", "replacement": None},
        {"pattern": "at its core", "replacement": None},
        {"pattern": "at the heart of it", "replacement": None},
        {"pattern": "paradigm shift", "replacement": "shift"},
        {"pattern": "sea change", "replacement": "shift"},
        {"pattern": "game-changer", "replacement": "big deal"},
        {"pattern": "utilize", "replacement": "use"},
        {"pattern": "utilise", "replacement": "use"},
        {"pattern": "leverage", "replacement": "use"},
        {"pattern": "delve", "replacement": "dig"},
        {"pattern": "robust", "replacement": "solid"},
        {"pattern": "holistic", "replacement": None},
        {"pattern": "comprehensive", "replacement": None},
        {"pattern": "tapestry", "replacement": "mix"},
        {"pattern": "ecosystem", "replacement": "world"},
        {"pattern": "synergy", "replacement": None},
        {"pattern": "stakeholders", "replacement": "people"},
        {"pattern": "best practices", "replacement": None},
        {"pattern": "double down", "replacement": None},
        {"pattern": "lean into", "replacement": None},
        {"pattern": "bandwidth", "replacement": "room"},
        {"pattern": "circle back", "replacement": None},
        {"pattern": "navigate the", "replacement": "handle the"},
        {"pattern": "shed light on", "replacement": "show"},
        {"pattern": "illuminate", "replacement": "show"},
        {"pattern": "embark on a journey", "replacement": None},
        {"pattern": "pivotal moment", "replacement": "big moment"},
        {"pattern": "inflection point", "replacement": "turning point"},
        {"pattern": "nuanced take", "replacement": "take"},
        {"pattern": "thoughtful take", "replacement": "take"},
        {"pattern": "complex issue with no easy answers", "replacement": None},
        {"pattern": "no easy answers", "replacement": None},
        {"pattern": "#automation", "replacement": None},
    ]

    contrast_patterns: list[ContrastPattern] = [
        {"name": "not_x_its_y", "description": "It's not X, it's Y"},
        {"name": "not_about_about", "description": "It's not about X, it's about Y"},
        {"name": "isnt_its", "description": "This isn't X, it's Y"},
        {"name": "were_not", "description": "We're not X, we're Y"},
        {"name": "theyre_not", "description": "They're not X, they're Y"},
        {"name": "real_issue", "description": "The real issue isn't ... it's ..."},
        {"name": "issue_isnt", "description": "The issue isn't X, it's Y"},
        {"name": "dont_think", "description": "Don't think of it as X, think of it as Y"},
        {"name": "thats_not", "description": "That's not X, it's Y"},
        {"name": "everyone_nobody", "description": "Everyone's focused on X, nobody's focused on Y"},
        {"name": "less_more", "description": "Less about X, more about Y"},
        {"name": "question_isnt", "description": "The question isn't X, it's Y"},
        {"name": "not_a_moment", "description": "This isn't a X moment, it's a Y moment"},
        {"name": "distraction_from", "description": "X is a distraction from Y"},
        {"name": "symptom_disease", "description": "X is a symptom, Y is the disease"},
        {"name": "headline_story", "description": "The headline is X, the story is Y"},
        {"name": "on_one_hand", "description": "On the one hand ... on the other hand"},
        {"name": "cant_understand_without", "description": "You can't understand X without understanding Y"},
        {"name": "if_youre_still", "description": "If you're still thinking about X, you're missing Y"},
        {"name": "forget_ignore", "description": "Forget about X, focus on Y"},
        {"name": "no_no_staccato", "description": "Staccato negatives: No X. No Y. No Z."},
        {"name": "not_not_staccato", "description": "Staccato negatives: Not X. Not Y. Not Z."},
    ]

    punctuation_rules = [
        "No em dashes (—) — use commas or periods instead",
        "No double hyphens (--) — use commas or periods",
        "Fix multiple spaces",
        "Remove space before punctuation",
        "Fix double punctuation (,, .. etc)",
    ]

    tone_rules = [
        "30% chance to lowercase first letter of sentences for casual tone",
    ]

    return {
        "banned_phrases": banned_phrases,
        "contrast_patterns": contrast_patterns,
        "punctuation_rules": punctuation_rules,
        "tone_rules": tone_rules,
    }
