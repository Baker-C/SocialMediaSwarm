# Task 3: typed-context

## Section 1 – Task Overview

### Goal

Extend `app/pipeline/types/context.py` with **`get_artifact`**, **`require_artifact`**, and **`set_artifact`** that route all pipeline writes through Pydantic validation (locked decision: validate on every `set_artifact`).

### Gathered context

`TickRunContext` is a thin dataclass wrapping `data: dict[str, Any]` with untyped `get` / `set`:

```11:23:SocialMediaAutonomousAgents/backend/app/pipeline/types/context.py
@dataclass
class TickRunContext:
    account_id: str
    slot: str
    mode: TickMode = "scheduled"
    niche: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
```

Every tool today writes via raw `ctx.set`:

```25:25:SocialMediaAutonomousAgents/backend/app/pipeline/tools/data/account_profile.py
    ctx.set("account_bundle", bundle)
```

```32:32:SocialMediaAutonomousAgents/backend/app/pipeline/tools/data/timeline_fetch.py
    ctx.set("timeline_references", payload)
```

`reference_phase.py` and compose read `ctx.get("timeline_analysis")` etc. as plain dicts—compatible if `data` stores JSON-serializable dicts after validation.

### Location in project

| Path | Role |
|------|------|
| `app/pipeline/types/context.py` | Add typed accessors |
| `app/pipeline/types/artifacts.py` | Supplies `ARTIFACTS`, `ArtifactKey` (task 1) |
| All pipeline tools + steps | Migrate to `set_artifact` (tasks 4–5) |

### What it affects

- **Write path**: pipeline code must use `set_artifact`; invalid payloads raise `ValueError` with Pydantic detail.
- **Read path**: `get_artifact` returns validated `BaseModel`; `get` remains for interval bridge code during migration.
- **Storage**: validated values stored as `model_dump(mode="json")` dicts so existing consumers expecting dicts keep working.

### Related changes / dependencies

- **Depends on task 1** (`ARTIFACTS` registry).
- **Blocks task 4** (tool migration) and **task 5** (steps using `require_artifact`).
- **Does not** validate on read if external code mutates `ctx.data` directly—convention + review enforce pipeline-only writes.

---

## Section 2 – Proposed Solution

### a. Describe proposed solution

1. Import `ARTIFACTS`, `ArtifactKey` from `artifacts.py`.
2. Add `get_artifact(key) -> BaseModel | None` — load from `data[key.value]`, validate/coerce via model.
3. Add `require_artifact(key) -> BaseModel` — raises `KeyError` if missing.
4. Add `set_artifact(key, value)` — **`model_validate` on every call**, store JSON dict.
5. Add `has_artifact(key) -> bool` — convenience for skip guards.
6. Deprecate `set` in docstring; keep method for backward compat / tests that pre-seed context.

### b. Before Panel

```1:23:SocialMediaAutonomousAgents/backend/app/pipeline/types/context.py
"""Mutable run context passed through the post runbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TickMode = Literal["scheduled", "force"]


@dataclass
class TickRunContext:
    account_id: str
    slot: str
    mode: TickMode = "scheduled"
    niche: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
```

### c. After Panel

```python
"""Mutable run context passed through the post runbook."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.pipeline.types.artifacts import ARTIFACTS, ArtifactKey

TickMode = Literal["scheduled", "force"]


@dataclass
class TickRunContext:
    account_id: str
    slot: str
    mode: TickMode = "scheduled"
    niche: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Low-level write; prefer set_artifact in pipeline code (bypasses validation)."""
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Untyped read — kept for interval bridge and legacy tests during migration."""
        return self.data.get(key, default)

    def get_artifact(self, key: ArtifactKey) -> BaseModel | None:
        """Return validated artifact model or None if key absent."""
        raw = self.data.get(key.value)
        if raw is None:
            return None
        model = ARTIFACTS[key].model
        if isinstance(raw, model):
            return raw
        return model.model_validate(raw)

    def require_artifact(self, key: ArtifactKey) -> BaseModel:
        """Fail fast when a step's declared read is missing."""
        artifact = self.get_artifact(key)
        if artifact is None:
            raise KeyError(f"Required artifact missing: {key.value}")
        return artifact

    def set_artifact(self, key: ArtifactKey, value: BaseModel | dict[str, Any]) -> None:
        """Validate and store an artifact — ALL pipeline writes must use this (locked decision)."""
        model = ARTIFACTS[key].model
        try:
            validated = model.model_validate(value)
        except ValidationError as exc:
            raise ValueError(f"Invalid artifact {key.value}: {exc}") from exc
        # JSON mode keeps ctx.data JSON-serializable for logging/compose consumers
        self.data[key.value] = validated.model_dump(mode="json")

    def has_artifact(self, key: ArtifactKey) -> bool:
        return key.value in self.data and self.data[key.value] is not None
```

### d. Written explanation connecting changes to broader picture

Typed accessors make the artifact registry **enforced at runtime** rather than advisory. Storing dumps preserves the existing contract that `reference_phase.py` and compose see dicts in `ctx.data`, while pipeline producers get immediate feedback on shape errors. Keeping raw `get`/`set` avoids breaking interval-layer code that has not migrated yet; grep/review targets pipeline package for `set_artifact`-only writes.

---

## Section 3 – Decision Defense

### Chosen path: strict validation on every `set_artifact`

| Alternative | Why not chosen |
|-------------|----------------|
| **Validate only at runbook boundaries** | User locked “validate on every set”; boundary-boundary checks miss tool-level bugs. |
| **Store live Pydantic models in `data`** | Breaks code expecting dicts; JSON dump is safer for logging/serialization. |
| **Remove `set` entirely** | Breaks unit tests and gradual migration; docstring deprecation is enough. |
| **Typed `get` replacing all `get`** | Large blast radius outside pipeline; phased migration. |

### `ValueError` on validation failure

Clear producer-site errors (`Invalid artifact timeline_references: ...`) beat silent corruption. Engine treats uncaught exceptions as step failures (existing `_runbook_engine` behavior).

### No read-time re-validation on every `get`

`get_artifact` validates/coerces on read for typed step code. Plain `get` remains zero-cost for hot paths in interval layer.

### Frontend

**N/A** — backend context typing only.
