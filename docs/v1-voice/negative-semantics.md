# v1 — `negative_semantics` (9 items)

Account-saved value for `JohnJames_News`. These matched `default_negative_semantics()`
in `app/models/account.py` verbatim (the account used the defaults).

Fed into the compose prompt as the "Banned semantics, phrases, characters, and sentence
structures (never use in opinion or quip)" block.

1. `"It's not that, it's this"` / `"It's not X, it's Y"` false-dichotomy reframes
2. Similar contrast gimmicks: `"The real story isn't … it's …"`, `"This isn't about X, it's about Y"`
3. Em dash (—) punctuation; use commas or periods instead
4. `"Same X, same Y — two different things"` / `"same this, same that"` parallel contrast formulas
5. Obviously AI stock phrases: `"Let's be clear"`, `"Here's the thing"`, `"Make no mistake"`, `"At the end of the day"`, `"In today's world"`
6. Stiff, press-release, or essay voice — write like a person talking, not a bot
7. AP-style perfect grammar and Title Case on every name — use loose, live X caps instead
8. Rhetorical question chains or faux-Socratic setup (`"The question isn't … it's …"`)
9. Numbered lesson lists, thread voice, or `"Lesson:"` / `"Thread:"` openers

## Raw default factory (source)
```python
def default_negative_semantics() -> list[str]:
    """Phrases, structures, and stylistic tells to avoid in composed posts."""
    return [
        "\"It's not that, it's this\" / \"It's not X, it's Y\" false-dichotomy reframes",
        "Similar contrast gimmicks: \"The real story isn't … it's …\", \"This isn't about X, it's about Y\"",
        "Em dash (—) punctuation; use commas or periods instead",
        "\"Same X, same Y — two different things\" / \"same this, same that\" parallel contrast formulas",
        "Obviously AI stock phrases: \"Let's be clear\", \"Here's the thing\", \"Make no mistake\", \"At the end of the day\", \"In today's world\"",
        "Stiff, press-release, or essay voice — write like a person talking, not a bot",
        "AP-style perfect grammar and Title Case on every name — use loose, live X caps instead",
        "Rhetorical question chains or faux-Socratic setup (\"The question isn't … it's …\")",
        "Numbered lesson lists, thread voice, or \"Lesson:\" / \"Thread:\" openers",
    ]
```
