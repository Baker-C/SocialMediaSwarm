# v1 Voice — Archived Record (`JohnJames_News`)

Faithful snapshot of the account voice **as it existed at the start of the Soul-pipeline work**,
i.e. voice version **v1** (`voice_version_seq = 1`, created **2026-06-09**). This is the
"previous" voice, before the per-account Soul refactor migrated/restructured it.

## Provenance
- **Account-stored fields** (`system_prompt`, `personality`, `negative_semantics`): captured from
  the live `JohnJames_News` account during the audit/planning session and cross-checked against
  RavenDB. The `negative_semantics` were the code defaults verbatim; `system_prompt` and
  `personality` were custom.
- **Global polish machinery** (banned phrases, soft-flag patterns, tone rule): transcribed
  verbatim from `backend/app/interval/orchestration/voice_polish.py` as read at the start of the
  session (the pre-refactor module).
- Version label/seq from the account's voice versioning (`voice_version_*`).

## Contents
| File | What it holds |
|---|---|
| [system-prompt.md](./system-prompt.md) | Account-saved `system_prompt` (custom) + the code default for context |
| [personality.md](./personality.md) | Account-saved `personality` |
| [negative-semantics.md](./negative-semantics.md) | The 9 `negative_semantics` entries |
| [polish-rules.md](./polish-rules.md) | Full verbatim `voice_polish.py`: ~80 banned phrases, 22 soft-flag contrast patterns, 13 soft-flag phrase patterns, cleanup regexes, tone rule |

## v1 voice model shape (for reference)
```python
class AccountVoice(BaseModel):
    system_prompt: str = ""
    personality: str = ""
    negative_semantics: list[str] = Field(default_factory=default_negative_semantics)
    voice_version_hash: str | None = None
    voice_version_seq: int = 1
    voice_version_label: str | None = "v1"
```
The full text-shaping behavior at v1 = these three stored fields (fed into the compose prompt)
**plus** the global `voice_polish.py` post-generation machinery in [polish-rules.md](./polish-rules.md).
