# Task 04 — Pipeline Spec Model + Versioning

> **Status:** Ready to implement. Authored cold from a planning session; pick up from this folder.
> **Scope:** Backend only — new `app/models/pipeline_spec.py`, new `app/models/pipeline_revision.py`, new `app/services/pipeline_version_service.py`, new `app/services/pipeline_revision_repository.py`, new `app/services/pipeline_spec_repository.py`, and a one-time `scripts/seed_pipeline_spec.py`. No frontend, no runner changes (the interpreter that *executes* the spec is doc 07; the compiler/validator that lowers + checks it is doc 05; the ACT-tail tools the seed wires are doc 06).
> **DB reality:** exactly **one** account today — `JohnJames_News`. A clean seed is low-risk; we are NOT carrying deprecated baggage forward.
>
> **Sibling-doc number map (final filenames in this folder — use these, the prose below is normalized to them):** 03 = tool catalog; 05 = validator + compiler (`validate_spec`/`compile_spec`); 06 = ACT-tail tools (`compose_until_safe`/`publish_post` + the 3 ACT `ArtifactKey`s); 07 = interpreter wiring (runner becomes a spec walker); 02 = outcome ledger + attribution (`run_id`/`pipeline_hash` on `PostCreationMetrics`); 08 = full-fidelity step trace; 10 = builder API; 11 = frontend. This doc owns the spec model + versioning; everything else is referenced, not authored.

This doc owns the **canonical spec document shape** (`PipelineSpecDocument` + `StepSpec` + `CompositeSpec`). It is defined ONCE here; every sibling doc references these types by name. **This is the single source of truth for the spec node model: leaves are `StepSpec(kind="step")`, composites are `CompositeSpec(kind="parallel"|"chain")` — NOT a unified `SpecStep{kind:"leaf"|"chain"|"parallel"}`. Doc 05's §3.1 must adapt its `_step_kind`/`_step_children` helpers to THIS shape (its `kind=="leaf"` branch maps to `kind=="step"` here); the literal value is `"step"`, never `"leaf"`.** This doc also owns spec **versioning** — a verbatim mirror of the soul-versioning pattern (`voice_revision.py` + `voice_version_service.py` + `voice_revision_repository.py`).

---

## 1. Why this exists

The interpreter (doc 07) executes an account's posting pipeline by walking **compiled data** (lowered by doc 05's `compile_spec`), not hardcoded `POST_TICK_REFERENCE_STEPS`. That data is a per-account `PipelineSpecDocument` in RavenDB. For the spec to be a real source of truth it needs the same lifecycle the soul already has:

- An **editable, versioned document** on the account (here: a separate doc keyed by account, mirroring how `AccountSoul` lives on the account but `VoiceRevisionDocument` archives each version).
- A **content hash** that bumps a sequence whenever the spec's *behavior* changes, plus an **immutable revision archive** so the dashboard timeline and attribution joins can reconstruct exactly which pipeline produced a post.
- A **champion/challenger** status field so an account can run a baseline pipeline (champion) while a proposed variant (challenger) is staged, validated, and promoted.

The soul already solved this exact problem for *voice*. We copy its three-file pattern verbatim and change only the payload. The one genuinely new concept is the **champion/challenger status + parent lineage**, which voice does not have — defended in §7.

### What this doc deliberately does NOT do
- **Execute the spec.** Compiling `PipelineSpecDocument` → `tuple[Step, ...]` is doc 05 (`compile_spec`); running the compiled graph is doc 07 (the interpreter). This doc only defines the data and its versioning.
- **Add `run_id`/`pipeline_hash` to `TrackedPostDocument`.** That attribution join (the field add on `PostCreationMetrics` + the threading through `finalize_post`) is doc 02. This doc only *produces* the value doc 02 stamps as `pipeline_hash`.
- **Step-trace persistence** (`StepOutputDocument` / `PipelineRunDocument` rework). That is doc 08.

> **Settled — where `pipeline_hash` comes from (the cross-doc answer, pinned here because this doc owns the spec model).** `pipeline_hash` is **`PipelineSpecDocument.version_hash` of the spec that was loaded and walked for the run** — read at run time, NOT from an account accessor. **There is NO `account.pipeline_version_hash` and this doc deliberately does NOT add one** (the spec lives in a separate `pipelinespecs/{account_id}` document, §3b; mirroring it onto the account would create a second, drift-prone source of truth). Any sibling that says `account.pipeline_version_hash` (doc 02 §3.3/§6, earlier drafts of doc 07) is **wrong and must read the loaded spec's `version_hash` instead.** Concretely: doc 07's runner loads the spec once via `PipelineSpecRepository().load_or_default(account_id, kind="post")` (§6b, the single entry point — CC-5), captures `spec.version_hash`, threads it through `deps.live.pipeline_hash`, and hands it to `publish_post` (doc 06), which sets `creation_metrics.pipeline_hash = <that value>` (CC-3). Before any spec doc exists, `load_or_default` returns the baseline (§6b), whose `version_hash` is stamped on first `save`; for a run that used the in-memory baseline without a prior save, `pipeline_hash` is the baseline's computed hash (never `None`-by-accident — see §6b note).

---

## 2. File-by-file index

| # | File | Status | Role (one line) |
|---|---|---|---|
| 1 | `backend/app/models/pipeline_spec.py` | **NEW** | `PipelineSpecDocument` + `StepSpec` + `CompositeSpec` + `default_pipeline_spec()` — the canonical editable spec. |
| 2 | `backend/app/models/pipeline_revision.py` | **NEW** | `PipelineRevisionDocument` — immutable per-version archive (mirror of `voice_revision.py`). |
| 3 | `backend/app/services/pipeline_version_service.py` | **NEW** | `compute_pipeline_hash()` + `bump_pipeline_version_if_needed()` (mirror of `voice_version_service.py`). |
| 4 | `backend/app/services/pipeline_revision_repository.py` | **NEW** | `PipelineRevisionRepository` — save/list revisions (mirror of `voice_revision_repository.py`). |
| 5 | `backend/app/services/pipeline_spec_repository.py` | **NEW** | `PipelineSpecRepository` (load/`load_or_default`/save, all `kind="post"`-parameterized, mirror of `AccountRepository.save`) — `load_or_default` is the single loader siblings call (CC-5, no `load_active_spec` free fn) + the `promote_challenger()` free function (§6b/§6c). |
| 6 | `backend/scripts/seed_pipeline_spec.py` | **NEW** | One-time builder: `POST_TICK_REFERENCE_STEPS` (8 SENSE) **+ the two ACT-tail leaves** → a champion `PipelineSpecDocument`. Holds `spec_from_runbook`, re-exported as `app/services/pipeline_spec_seed.py` for `default_pipeline_spec` (§3c). |
| — | `backend/app/pipeline/runbooks/post_tick.py` | **REUSED (read-only)** | Source of the seed's SENSE leaves; not edited by THIS doc (doc 06 separately appends the two ACT `Step`s). |
| — | `backend/app/pipeline/tools/**` | **REUSED (read-only)** | `TOOL_ID` constants the seed references by string (incl. doc 06's `llm.compose_until_safe` / `data.publish_post`). |
| — | `backend/app/services/voice_version_service.py` | **REUSED (pattern)** | Copied verbatim, payload swapped. |
| — | `backend/app/services/voice_revision_repository.py` | **REUSED (pattern)** | Copied verbatim, collection + model swapped. |
| — | `backend/app/infrastructure/ravendb_http.py` | **REUSED** | `put_document` / `get_document` / `query` (no CAS — see §6). |

**Implementation order:** `1 → 2 → 3 → 4 → 5 → 6`. Models first (everything imports them), then version service (revision repo is a default dependency), then the two repositories, then the seed (needs all of them).

---

## 3. The canonical spec shape — `app/models/pipeline_spec.py` (NEW)

This is the **load-bearing definition** sibling docs import. Three Pydantic models plus a default factory.

### 3a. Design constraints that shaped the shape (verified against the engine)

1. **The catalog/validator MUST separate engine-injected deps from proposable config.** Tool `run()` signatures take live service objects as kwargs (`tick_data: TickDataService`, `post_registry`, `twitter`) *plus* tunable scalars. Verified: `tools/data/account_profile.py:20` (`tick_data`), `tools/deterministic/reference_rank.py:23` (`rows`, `top_n`, `exclude_ids`, `store_key`), `tools/data/search_fetch.py:20` (`queries`, `max_results_per_query`), `tools/llm/reference_pattern_summary.py:23` (`source`, `niche`, `features`, `store_key`). The real wiring lives in `services/steps.py` WRAPPERS, not the tools. So `StepSpec` carries **only proposable config** — never service objects, never `rows`/`queries` (those are derived at runtime by the wrapper from upstream artifacts). The injected half is invisible to the spec by construction.

2. **Composites are `parallel` / `chain` and nest.** Verified `flow.py:48,69` and the runbook `post_tick.py:47-84` (`parallel(chain(...), chain(...))`). The spec mirrors this with a recursive `CompositeSpec`.

3. **`reads`/`writes` are `ArtifactKey` enum members serialized as their `.value` strings.** Verified `artifacts.py:16` (`StrEnum`). The spec stores them as plain strings; doc 05's compiler re-validates them back to `ArtifactKey`.

   > **Settled — `StepSpec.reads`/`writes` are the canonical compile-time I/O, copied verbatim from the runbook (§7).** Doc 05's compiler builds each leaf `Step` from the **catalog tool's** declared `reads`/`writes` *where the catalog has them*, but two catalog tools (`reference_rank`, `reference_pattern_summary`) write **dynamically** via `store_key` and report `writes=None` (doc 03 §3) — the catalog cannot recover their concrete artifact. For those, the spec node's `writes` (which the seed copies from the runbook's declared `Step.writes`, §7) **is** the source of truth the compiler must use. So the rule for doc 05's `_compile_node`/validator is: **a leaf's effective `reads`/`writes` are the spec node's `reads`/`writes` when present; the catalog is consulted only for `reads_optional`.** (Per **CC-2** there is no `invariant_tool`/`TOOL_INVARIANT` catalog flag: the validator detects the required structure purely from artifacts — some step writes `SAFETY_VERDICT` and exactly one terminal step writes `PUBLISHED_POST`.) This resolves the cross-doc "spec node vs catalog" ambiguity in favor of the spec node, because the spec node is the only place that carries the *resolved* (post-`store_key`) artifact keys. The seed always populates `reads`/`writes` (§7), so this is never empty for a baseline-derived spec.

4. **The catalog is closed.** Tools are referenced by `TOOL_ID` string (`"data.account_profile"`, `"deterministic.reference_rank"`, `"llm.reference_pattern_summary"`, `"data.search_fetch"`, `"data.own_posts_fetch"`, plus the two ACT-tail tools `"llm.compose_until_safe"` / `"data.publish_post"` from doc 06). The builder only WIRES + CONFIGURES existing tools; it never writes tool code. So `StepSpec.tool_id` is a string the doc-05 compiler resolves against the catalog (doc 03 owns the catalog; the only factory is `get_tool_catalog()` returning a `ToolCatalog` object — CC-1; this doc only stores the string).

### 3b. The models

```python
"""Canonical editable pipeline spec. One per account; compiled by doc 05 and executed by the interpreter (doc 07).

A spec is DATA describing which catalog tools run, in what order/shape, with what
PROPOSABLE config. It NEVER carries engine-injected service objects (tick_data, repo,
post_registry, twitter) — those are wired by the interpreter at run time exactly as
services/steps.py wires them today. See 04 §3a.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ── A single leaf step: one catalog tool + its proposable config ──
class StepSpec(BaseModel):
    """A leaf step. `tool_id` resolves to a catalog tool (doc 03 catalog).
    The discriminant `kind` is the literal "step" (NOT "leaf") — this is the
    canonical value the validator/compiler (doc 05) and frontend (doc 11) switch on.
    `config` holds ONLY proposable scalars the catalog marks config_origin=="literal"
    (today just top_n and max_results_per_query; the coarse ACT tools expose none).
    It NEVER carries `store_key`/`source`: those are COMPILE-TIME WIRING
    (config_origin=="wired" — the compiler/wrapper computes them, never proposed in the
    spec; see §7) — so doc 05's R2 (config_unknown_key) rejects them as keys here and
    does NOT reject the baseline for omitting them."""
    kind: Literal["step"] = "step"
    id: str                                   # step id, e.g. "rank_external_references"
    tool_id: str                              # catalog id, e.g. "deterministic.reference_rank"
    reads: list[str] = Field(default_factory=list)    # ArtifactKey .value strings
    writes: list[str] = Field(default_factory=list)   # ArtifactKey .value strings
    reads_optional: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)        # proposable, LLM/builder-tunable
    purpose: str = ""


# ── A composite: parallel or chain over children (recursive) ──
class CompositeSpec(BaseModel):
    """parallel | chain over children. Mirrors flow.parallel()/flow.chain().
    children may be StepSpec or nested CompositeSpec (matches the runbook's
    parallel(chain(...), chain(...))). reads/writes are DERIVED at compile time
    by the compiler (doc 05) exactly as flow.py unions them, so they are NOT
    stored here — storing them would risk drift from the children."""
    kind: Literal["parallel", "chain"]
    id: str
    children: list["StepSpec | CompositeSpec"] = Field(default_factory=list)
    purpose: str = ""


# ── The whole spec document for one account ──
class PipelineSpecDocument(BaseModel):
    """The per-account posting pipeline as data. Document id:
    pipelinespecs/{account_id}. The CHAMPION is the live spec; a CHALLENGER is a
    staged variant awaiting promotion (see 04 §7)."""
    account_id: str
    # Ordered top-level steps; each entry is a leaf or a composite. This is the
    # exact analogue of POST_TICK_REFERENCE_STEPS: tuple[Step, ...].
    steps: list[StepSpec | CompositeSpec] = Field(default_factory=list)

    # ── champion/challenger ──
    status: Literal["champion", "challenger"] = "champion"
    parent_hash: str | None = None            # version_hash this spec was forked from

    # ── version stamp (bumps when `steps` changes; see pipeline_version_service) ──
    version_hash: str | None = None
    version_seq: int = 1
    version_label: str | None = "v1"

    @staticmethod
    def document_id(account_id: str, status: str = "champion", kind: str = "post") -> str:
        # One live doc per (account, kind, status). A challenger lives alongside the
        # champion until promoted; promotion overwrites the champion doc. `kind`
        # ("post" default; "reply" is doc 12's separate family — CC-12) namespaces
        # the id so the two spec families never collide.
        prefix = "pipelinespecs" if kind == "post" else f"pipelinespecs-{kind}"
        suffix = "" if status == "champion" else f"-{status}"
        return f"{prefix}/{account_id}{suffix}"


CompositeSpec.model_rebuild()  # resolve the forward ref in children
```

### 3c. `default_pipeline_spec()` — the baseline

The default is **not** hand-authored prose; it is exactly what the seed (§7) produces: the 8 SENSE leaves from `POST_TICK_REFERENCE_STEPS` **plus the two ACT-tail leaves** (`compose_until_safe`, `publish_post`) so it is a complete, validator-passing graph (§7). To avoid two sources of truth, `default_pipeline_spec(account_id)` calls the same `spec_from_runbook()` helper the seed uses (defined in §7), so the model file has a thin wrapper:

```python
def default_pipeline_spec(account_id: str) -> "PipelineSpecDocument":
    """Baseline champion spec = the current hardcoded runbook + the ACT tail, as data.
    Delegates to the seed builder so there is ONE canonical baseline (04 §7).
    Flattens to the 10 dotted ids the frontend baseline fixture (doc 11 §4.3) locks."""
    from app.services.pipeline_spec_seed import spec_from_runbook  # avoid import cycle
    return spec_from_runbook(account_id)
```

> **Decision Defense — why `steps: list[StepSpec | CompositeSpec]` and not a flat list of leaves?**
> Flattening at storage time (`flatten_steps`) is lossy — `flow.py:103` keeps tree structure only in dotted ids and `FlatStep.parent_id`. The runbook's `parallel(chain(...), chain(...))` cannot be reconstructed from a flat list (the dotted-id reconstruction is one-way, per the verified gotcha). Storing the nested shape means doc 05's compiler builds the *same* `Step` tree `post_tick.py` declares today, so `flatten_steps` yields the *identical* dotted ids the frontend `flowGraph.ts` already matches. Storing flat leaves would break that contract.

> **Decision Defense — why derive `reads`/`writes` for composites at compile time, but store them for leaves?**
> For leaves they are authored fact (the tool's declared I/O) and the validator checks them against the catalog. For composites `flow.parallel`/`flow.chain` *compute* them by union (`flow.py:50-62, 71-81`); storing a composite's reads/writes would be a denormalized copy that can silently disagree with its children. Compile-time derivation is the single source of truth and is free.

---

## 4. The immutable revision archive — `app/models/pipeline_revision.py` (NEW)

Verbatim mirror of `voice_revision.py` (read in full: `app/models/voice_revision.py:15-44`). Same id scheme, same "immutable archive → list fields default empty, never default-factory" discipline. Only the payload differs: instead of soul fields it snapshots `steps` + the champion/challenger lineage.

```python
"""Pipeline spec revision history. One immutable document per spec version.

Mirrors VoiceRevisionDocument: each revision captures the COMPLETE spec at a
version bump so the dashboard timeline and the attribution join (doc 02 stamps
TrackedPost.creation_metrics.pipeline_hash = this version_hash) can reconstruct
the exact pipeline that produced a post.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.pipeline_spec import CompositeSpec, StepSpec


class PipelineRevisionDocument(BaseModel):
    account_id: str
    seq: int
    label: str
    version_hash: str
    changed_at: str

    # ── Full spec snapshot (canonical going forward) ──
    # List defaults EMPTY (not a default factory): a revision is an immutable
    # archive, so filling a missing `steps` with today's baseline would FABRICATE
    # history. Mirrors voice_revision.py's empty-default discipline.
    steps: list[StepSpec | CompositeSpec] = Field(default_factory=list)
    status: str = "champion"          # status this revision was in when archived
    parent_hash: str | None = None    # lineage: what it was forked from

    @staticmethod
    def document_id(account_id: str, seq: int) -> str:
        return f"pipelinerevisions/{account_id}-v{seq}"
```

> **Decision Defense — why archive a full spec snapshot, not a diff?**
> Same reasoning as `voice_revision.py` (read `02-voice-revision.md` Decision Defense): the timeline reads revisions individually and a future "restore this version" / "diff champion vs vN" action wants one self-contained read. A diff chain is fragile if any link is missing. Specs are small (the baseline is 10 leaves), so full snapshots are cheap.

---

## 5. Versioning service — `app/services/pipeline_version_service.py` (NEW)

Verbatim mirror of `voice_version_service.py` (read in full: lines 14-104). The seq/label bump logic is copied **unchanged**; only the hash inputs and the revision payload swap. This is the "reuse the seq+hash+immutable-archive pattern VERBATIM" requirement.

### 5a. `compute_pipeline_hash` — what is hashed

The hash covers **only spec behavior** — the `steps` tree. It does NOT cover `status`, `parent_hash`, `version_*`, or `account_id` (those are bookkeeping, not behavior — mirrors the voice rule that niches/followers don't bump the version, `voice_version_service.py` comment at line 18). Two specs with identical `steps` but different status share a hash, which is exactly right: a challenger that is byte-identical to the champion is not a new behavior.

```python
"""Version and stamp pipeline spec revisions. Verbatim mirror of
voice_version_service.py — only the hash inputs and revision payload differ."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models.pipeline_spec import PipelineSpecDocument
from app.models.pipeline_revision import PipelineRevisionDocument
from app.services.pipeline_revision_repository import PipelineRevisionRepository


def compute_pipeline_hash(spec: PipelineSpecDocument) -> str:
    """SHA256 over the steps tree only. Canonical JSON (sorted keys) → stable digest.
    ORDER-SENSITIVE on `steps` and `children` by design: reordering steps is a real,
    auditable behavior change (mirrors voice_version_service._normalize_patterns)."""
    payload = [s.model_dump(mode="json") for s in spec.steps]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def bump_pipeline_version_if_needed(
    spec: PipelineSpecDocument,
    *,
    previous_hash: str | None,
    manual_label: str | None = None,
    revision_repo: PipelineRevisionRepository | None = None,
) -> PipelineSpecDocument:
    current_hash = compute_pipeline_hash(spec)
    prev = (previous_hash or "").strip() or (spec.version_hash or "").strip()
    manual = (manual_label or "").strip()
    changed = False

    if not prev:
        seq = max(1, int(spec.version_seq or 1))
        spec.version_seq = seq
        spec.version_hash = current_hash
        spec.version_label = manual or (spec.version_label or "").strip() or f"v{seq}"
        changed = True
    elif prev == current_hash and not manual:
        return spec
    else:
        if prev != current_hash:
            seq = max(1, int(spec.version_seq or 1)) + 1
            spec.version_seq = seq
            spec.version_label = f"v{seq}"
            spec.version_hash = current_hash
            changed = True
        if manual:
            spec.version_label = manual
            changed = True

    if not changed:
        return spec

    seq = max(1, int(spec.version_seq or 1))
    repo = revision_repo or PipelineRevisionRepository()
    repo.save(
        PipelineRevisionDocument(
            account_id=spec.account_id,
            seq=seq,
            label=spec.version_label or f"v{seq}",
            version_hash=spec.version_hash or current_hash,
            changed_at=datetime.now(timezone.utc).isoformat(),
            steps=list(spec.steps),
            status=spec.status,
            parent_hash=spec.parent_hash,
        )
    )
    return spec
```

The bump logic block (`if not prev: … else: …`) is a **line-for-line copy** of `voice_version_service.py:66-104` with `account.voice_version_*` → `spec.version_*`. Verified against that file in this session.

> **Decision Defense — hash the `steps` tree, not the whole document.**
> Mirrors `compute_voice_hash`, which hashes soul *content* only and explicitly excludes the version stamp and niches (`voice_version_service.py:18` comment). A version is a behavior digest. If we folded `status`/`parent_hash` into the hash, promoting a challenger (a status flip, §7) would spuriously bump the version even though the executed steps are unchanged.

---

## 6. Repositories — `pipeline_revision_repository.py` + `pipeline_spec_repository.py` (NEW)

### 6a. `PipelineRevisionRepository` — verbatim mirror of `voice_revision_repository.py`

Read in full: `app/services/voice_revision_repository.py:20-56`. Copy it; change the collection constant, the model, and the id prefix. The RQL fallback (collection query → `startsWith(id(), ...)`) is copied unchanged — it is the project's defensive pattern for collections that may not have an index yet.

```python
PIPELINE_REVISION_COLLECTION = "PipelineRevisions"

class PipelineRevisionRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def save(self, revision: PipelineRevisionDocument) -> str:
        doc_id = PipelineRevisionDocument.document_id(revision.account_id, revision.seq)
        self.client.put_document(
            doc_id, revision.model_dump(exclude_none=True), collection=PIPELINE_REVISION_COLLECTION
        )
        return doc_id

    def list_for_account(self, account_id: str) -> list[PipelineRevisionDocument]:
        # identical structure to VoiceRevisionRepository.list_for_account:
        #   primary: from PipelineRevisions where account_id == "{aid}" order by seq asc
        #   fallback: from @all where startsWith(id(), "pipelinerevisions/{aid}-") order by seq asc
        ...
```

`put_document(doc_id, document, *, collection)` verified at `ravendb_http.py:103`. `model_dump(exclude_none=True)` matches `voice_revision_repository.py:30` (drops the empty legacy passthrough fields — here it drops `parent_hash`/`version_hash` when `None`).

### 6b. `PipelineSpecRepository` — load/save the live spec

Mirrors `AccountRepository.save` (`account_repository.py:115-121`), which calls `bump_voice_version_if_needed` on every write before `put_document`. We do the same: `save()` calls `bump_pipeline_version_if_needed` so any edit to `steps` auto-versions and archives a revision.

```python
PIPELINE_SPEC_COLLECTION = "PipelineSpecs"

class PipelineSpecRepository:
    def __init__(self, client: RavenDBHttpClient | None = None) -> None:
        self._client = client

    @property
    def client(self) -> RavenDBHttpClient:
        return self._client or get_ravendb_client()

    def load(
        self, account_id: str, status: str = "champion", kind: str = "post"
    ) -> PipelineSpecDocument | None:
        doc_id = PipelineSpecDocument.document_id(account_id, status, kind)
        raw = self.client.get_document(doc_id)
        if raw is None:
            return None
        stripped = {k: v for k, v in raw.items() if not str(k).startswith("@")}
        return PipelineSpecDocument.model_validate(stripped)

    def load_or_default(
        self, account_id: str, status: str = "champion", kind: str = "post"
    ) -> PipelineSpecDocument:
        """The interpreter (doc 07) calls this — the single entry point per CC-5:
        the live `status` spec for this `kind`, or the baseline if no spec doc exists
        yet (graceful default — mirrors how account load folds in a default soul).
        This is the ONE place that decides 'no spec → baseline'. `kind` defaults to
        "post"; "reply" (doc 12) is a separate family (CC-12). The returned baseline is
        version-STAMPED in memory (see note) so its `version_hash` is never None even
        when no spec was ever saved."""
        from app.models.pipeline_spec import default_pipeline_spec
        loaded = self.load(account_id, status, kind)
        if loaded is not None:
            return loaded
        baseline = default_pipeline_spec(account_id)
        # Stamp the in-memory baseline so callers that read .version_hash (attribution,
        # doc 02/07) get the baseline's real hash, not None. This does NOT write to Raven
        # and does NOT archive a revision (revision_repo is a no-op sink): it is a pure
        # in-memory hash so the unsaved baseline still attributes correctly.
        baseline.version_hash = compute_pipeline_hash(baseline)
        return baseline

    def save(self, spec: PipelineSpecDocument, kind: str = "post") -> None:
        # `kind` ("post" default; "reply" is doc 12's family — CC-12) selects the doc-id
        # namespace. The spec model itself carries no `kind` field; the family is a
        # repository-level concern, exactly as `status` namespaces the champion/challenger.
        spec = bump_pipeline_version_if_needed(spec, previous_hash=spec.version_hash)
        doc_id = PipelineSpecDocument.document_id(spec.account_id, spec.status, kind)
        self.client.put_document(
            doc_id, spec.model_dump(exclude_none=True), collection=PIPELINE_SPEC_COLLECTION
        )
```

> **Note — the in-memory baseline stamp uses `compute_pipeline_hash`** (import it at the top of `pipeline_spec_repository.py` alongside `bump_pipeline_version_if_needed`: `from app.services.pipeline_version_service import compute_pipeline_hash, bump_pipeline_version_if_needed`). It is the same digest a first `save` would persist, so a run on the unsaved baseline and a run on the seeded baseline attribute to the **identical** `pipeline_hash` — the seed (`v1`) and the live default are the same behavior, so they share a hash by design (§5a). This closes the cross-doc gap where doc 07's `load_or_default(...) or SEED_SPEC` could otherwise hand attribution a `version_hash=None` (and per CC-5 the `or SEED_SPEC` arm is removed entirely).

### 6b-bis. The canonical loader is the repository method — NO `load_active_spec` free function (CC-5)

**Per CC-5, the single entry point siblings call is the repository method `PipelineSpecRepository().load_or_default(account_id, kind="post")`** (§6b), returning the **champion** spec or the seeded baseline. There is **no `load_active_spec` free function** and the interpreter reads only `status="champion"`. Earlier drafts of docs 07/09 named a module-level `load_active_spec(...)` wrapper; that name is **removed everywhere** — those call sites use `PipelineSpecRepository().load_or_default(account_id, kind="post")` directly (doc 09 passes `status=ctx.spec_status` to read the challenger slot). One import path, one signature, no free-function indirection to keep in sync.

> **Settled — there is NO module-level `SEED_SPEC` constant (CC-5).** Doc 07 §0/§2.4's `SEED_SPEC` is a misnomer: the baseline is **per-account** and needs `account_id`, so it cannot be a constant. `load_or_default(account_id, kind="post")` already returns the baseline when no doc exists, so doc 07's `... or SEED_SPEC` fallback is dead and must be removed. The baseline factory is `default_pipeline_spec(account_id)` (§3c), never a constant.

### 6c. Champion/challenger promotion — the partial-write window

**Verified hard constraint:** RavenDB has NO multi-doc transactions and the HTTP client has NO CAS/If-Match (`ravendb_http.py:103-110` — unconditional PUT; `delete_document` takes a change vector but `put_document` does not). Promotion is therefore **sequential puts**, and we must document and bound the partial-write window.

Promotion (a free function in `pipeline_spec_repository.py`):

```python
def promote_challenger(
    account_id: str, repo: PipelineSpecRepository | None = None, kind: str = "post"
) -> PipelineSpecDocument:
    """Promote the challenger to champion. Champion/challenger status is per
    (account_id, kind) (CC-12), so `kind` ("post" default) selects the family.
    NO CAS available, so this is a validate-then-activate sequence of plain puts.
    Ordering is chosen so a crash mid-promotion leaves the OLD champion intact
    (fail-safe), never a half-built one."""
    repo = repo or PipelineSpecRepository()
    challenger = repo.load(account_id, "challenger", kind)
    if challenger is None:
        raise ValueError(f"no challenger to promote for {account_id}")

    # 1. VALIDATE first (doc 05's validate_spec must pass) — never activate an
    #    unexecutable spec. If this raises/returns errors, nothing was written.
    from app.pipeline.spec import validate_spec, compile_spec  # doc 05 (re-exported from spec/__init__.py)
    from app.pipeline.spec.catalog import get_tool_catalog      # doc 03 (the ToolCatalog object — CC-1)
    report = validate_spec(challenger, get_tool_catalog())      # ValidationReport (doc 05 §5.2)
    if not report.ok:
        raise ValueError(f"challenger invalid: {[e.code for e in report.errors]}")
    compile_spec(challenger)  # final lowering check (raises on a catalog/shape defect validate missed)

    # 2. ACTIVATE: write champion (status flips to "champion", parent_hash set to
    #    the OUTGOING champion's hash for lineage). save() versions + archives it.
    outgoing = repo.load(account_id, "champion", kind)
    challenger.status = "champion"
    challenger.parent_hash = outgoing.version_hash if outgoing else None
    challenger.version_hash = None  # force a fresh bump/revision for the promotion
    repo.save(challenger, kind)    # PUT #1: champion doc is now the new spec

    # 3. CLEAN UP the challenger doc (best-effort). If this delete fails, the only
    #    residue is a stale challenger doc identical to the new champion — harmless;
    #    it never executes (the interpreter reads status="champion" only).
    repo.client.delete_document(PipelineSpecDocument.document_id(account_id, "challenger", kind))
    return challenger
```

**Partial-write window, stated honestly:** between PUT #1 (new champion) and the challenger delete, both docs exist and describe the same steps. The interpreter (doc 07, via `load_or_default`) reads only the champion doc, so execution is never ambiguous. A crash after validate but before PUT #1 leaves the old champion live — the fail-safe outcome. There is exactly one mutating write to the champion (PUT #1); it is not split, so the champion is never half-written.

> **Settled — the `catalog` argument and the `ToolCatalog` wrapper (cross-doc seam, pinned — CC-1).** `validate_spec(doc, catalog)` (doc 05) takes a catalog **object** (a `ToolCatalog`) exposing `.get(tool_id) -> ToolCatalogDocument | None`, `tool_id in catalog`, iteration, and `run_for(tool_id)`. **The only factory is `get_tool_catalog()` in `app/pipeline/spec/catalog.py`** (CC-1); the raw `build_tool_catalog() -> list[ToolCatalogDocument]` builder still exists in doc 03 but is wrapped by `ToolCatalog`, and the name `build_catalog()` does NOT exist anywhere. Per-tool fields doc 05 reads are `reads`/`writes`/`reads_optional`/`config_schema` — **there is no `invariant_tool` field (CC-2)**; the validator detects the required structure purely from artifacts (`SAFETY_VERDICT` written somewhere, exactly one terminal `PUBLISHED_POST` writer). `reads`/`writes` for the dynamic-`store_key` tools come from the **spec node** at validate time per §3a-3, not the catalog. This doc imports `get_tool_catalog` from `app.pipeline.spec.catalog`; doc 10's `_load_catalog()` returns the same object. One catalog type, constructed once, consumed by promotion (here), the builder (doc 10), and the runner (doc 07).

**Default policy: manual promote, auto-rollback on hard regression.** Promotion is operator-triggered (a button/endpoint owned by doc 10's builder API; the self-rewrite loop that *proposes* challengers is doc 09). The only automatic action is *rollback*: if the reward/ledger (doc 01's `avg_post_reward` + doc 02's `OutcomeLedger`) show a hard regression after a promotion, re-promote the previous champion by hash from the revision archive (`PipelineRevisionRepository.list_for_account` → pick the row whose `version_hash == new champion's parent_hash` → rebuild a `PipelineSpecDocument` from its `steps` → `repo.save`). No CAS is needed because rollback is itself just another sequential put.

> **Decision Defense — separate challenger DOC (id suffix) vs a `challenger` field on the champion doc.**
> A suffixed doc id (`pipelinespecs/{account_id}-challenger`) means champion and challenger version **independently** — each gets its own revision lineage and the version service treats them as two specs. Embedding the challenger inside the champion doc would make `compute_pipeline_hash` (which hashes `steps`) entangle the two, and a single `put_document` would have to rewrite both, widening the failure blast radius. Separate docs also make "the interpreter reads only `status=champion`" a trivial, single-doc read with zero filtering. This is the simpler, more elegant option and it keeps the no-CAS reality contained to the one promotion sequence.

---

## 7. The one-time SEED — `scripts/seed_pipeline_spec.py` (NEW)

Export the live `POST_TICK_REFERENCE_STEPS` (verified `post_tick.py:20-85`) into a champion `PipelineSpecDocument`, **then append the two ACT-tail leaves** (`compose_until_safe` + `publish_post`) so the seeded baseline is a **complete, validator-passing** pipeline. The export walks the `Step` tree and emits `StepSpec`/`CompositeSpec`.

> **Settled — the baseline MUST be a full SENSE+ACT graph (10 leaves), not SENSE-only (8 leaves) (CC-6).** doc 05's validator requires (purely from artifacts, no `invariant_tool` flag — CC-2) that some step writes `SAFETY_VERDICT` and exactly one **terminal** step writes `PUBLISHED_POST`. A SENSE-only seed FAILS both, which would break `promote_challenger` (§6c validates before activate), doc 10's few-shot example (`default_pipeline_spec` must be a *valid* worked example), and any `validate_spec` run between seeding and the runner rewrite. **This doc therefore owns appending the two ACT leaves to the seed** — it is NOT deferred to doc 06. Doc 06 owns the *tools and artifacts* (`compose_until_safe`/`publish_post` modules, the 3 `ArtifactKey`s, the `compose_step`/`publish_step` wrappers); this seed only *wires* them by `tool_id` string + declared reads/writes, exactly as it wires the SENSE tools. The frontend baseline fixture (doc 11 §4.3/§8, the 10-id lock) and doc 13 §1's `test_pipeline_runbook` expectation both assume this 10-leaf baseline; this resolves the cross-doc "who appends the ACT leaves" gap in favor of doc 04.
>
> **Sequencing consequence (for doc 13):** because the seed now references `tool_id` `llm.compose_until_safe`/`data.publish_post` and the `COMPOSED_POST`/`SAFETY_VERDICT`/`PUBLISHED_POST` artifact `.value` strings, **running the seed (or `default_pipeline_spec`) requires doc 06's artifact-key additions to exist** for `validate_spec`/`compile_spec` to pass — the *string* seed is doc-04 code, but a *validate/compile of it* is gated on doc 06. The seed-builder module itself (`spec_from_runbook`) imports nothing from doc 06 (it hard-codes the two `tool_id`/reads/writes string sets, §7), so doc 04 still `py_compile`s and unit-tests its model/versioning slices independently; only the end-to-end "seed → validate → compile" check (doc 04 §8 Slice 6, doc 13 B2) waits for doc 06. doc 13's order (06 before the runner rewrite) already satisfies this; the seed script is run after 06 lands.

**What maps to what (verified against the runbook + tool constants):**

| Runbook `Step` field | Spec field | Source of truth |
|---|---|---|
| `Step.id` | `StepSpec.id` | `post_tick.py` literal ids |
| (wrapper → tool) | `StepSpec.tool_id` | a fixed `STEP_TOOL_MAP` (below) — wrappers call exactly one catalog tool |
| `Step.reads` (enum) | `StepSpec.reads` (`.value` strings) | `post_tick.py` |
| `Step.writes` (enum) | `StepSpec.writes` (`.value` strings) | `post_tick.py` |
| `Step.purpose` | `StepSpec.purpose` | `post_tick.py` |
| hardcoded wrapper config (PROPOSABLE only) | `StepSpec.config` | `services/steps.py` (below) — `store_key`/`source` EXCLUDED (they are wired, not config) |
| `parallel()`/`chain()` | `CompositeSpec(kind=...)` | `flow.py` `composite_kind` ∈ {`parallel`,`chain`} |

The wrapper→tool map and the per-step proposable config are hand-built once from `services/steps.py` (verified this session — line numbers below are the real ones in the live file).

> **Settled — where `store_key`/`source` come from at run time, now that they are NOT in the spec config.** They are `config_origin == "wired"` (doc 03 §4.4): the wrapper computes them, the spec never carries them. There are TWO `top_n` ranker sites (`steps.py:138` external, `steps.py:214` own-posts) and TWO `store_key`/`source` pairs; the seam that lets a `literal` config key (`top_n`) reach the tool while `store_key`/`source` stay wrapper-pinned is **doc 03/05's wrapper rewrite, not doc 04's** — this doc only authors the *data*. The contract doc 04 fixes for the downstream wrapper rewrite is: each SENSE wrapper gains a `config: dict | None = None` kwarg (doc 05 §6.2 option A) and reads its **literal** knobs from it (`top_n = (config or {}).get("top_n", MIN_TOP_N)` at BOTH ranker sites; `max_results_per_query` at search), while continuing to pass `store_key=ArtifactKey.<…>.value` and `source="timeline"|"own_posts"` as the wrapper's own hard-coded wiring (never from `config`). So a baseline spec whose rank steps carry `config={"top_n": 10}` reproduces today's behavior exactly, and the spec is free of any `wired` key the validator would reject. doc 09's deterministic `top_n` proposer tunes whichever ranker step it targets by `step.id` (`rank_external_references` vs `rank_own_posts`) — the two sites are addressable because they are distinct spec leaves.

```python
# scripts/seed_pipeline_spec.py (and re-exported as app/services/pipeline_spec_seed.py
# so default_pipeline_spec() can reuse spec_from_runbook — see 04 §3c)

# Each runbook leaf wrapper calls exactly ONE catalog tool (or the internal primitive).
# Verified in app/pipeline/services/steps.py (line numbers are the real ones in the live file).
# 10 entries (CC-6): the 8 SENSE leaves PLUS the two ACT-tail leaves, so that once doc 06
# appends compose_until_safe/publish_post INTO POST_TICK_REFERENCE_STEPS, the runbook walk
# in spec_from_runbook (which looks up STEP_TOOL_MAP[step.id]) resolves them instead of
# raising KeyError. Pre-06, ACT_TAIL_SPECS (below) supplies the same two leaves by literal.
STEP_TOOL_MAP = {
    "load_account_bundle":         "data.account_profile",         # steps.py:38
    "fetch_search_references":     "data.search_fetch",            # steps.py:81
    "collect_external_references": "_internal.collect_external",   # steps.py:90 — internal primitive (see Decision Defense)
    "fetch_own_post_history":      "data.own_posts_fetch",         # steps.py:120
    "rank_external_references":    "deterministic.reference_rank", # steps.py:135
    "brief_external_references":   "llm.reference_pattern_summary",# steps.py:160
    "rank_own_posts":              "deterministic.reference_rank", # steps.py:211
    "brief_own_posts":             "llm.reference_pattern_summary",# steps.py:249
    # ── ACT tail (CC-6): the two leaves doc 06 appends to the runbook ──
    "compose_until_safe":          "llm.compose_until_safe",       # doc 06 §7.1 Step
    "publish_post":                "data.publish_post",            # doc 06 §7.1 Step (terminal — writes PUBLISHED_POST)
}

# PROPOSABLE config ONLY — keys whose catalog config_origin == "literal" (doc 03 §4.4).
# store_key / source are config_origin == "wired" (engine-computed, NOT spec config), so
# they are DELIBERATELY ABSENT here: doc 05 R2 (config_unknown_key) rejects any non-literal
# key in StepSpec.config, and the wrapper still computes store_key/source itself (see note).
# Values copied from the hardcoded constants in services/steps.py.
STEP_CONFIG = {
    "fetch_search_references":   {"max_results_per_query": 50},   # SEARCH_RESULTS_PER_NICHE, steps.py:35,86
    "rank_external_references":  {"top_n": 10},                   # MIN_TOP_N, steps.py:32,138
    "rank_own_posts":            {"top_n": 10},                   # MIN_TOP_N, steps.py:32,214
    # brief_external_references / brief_own_posts carry NO proposable config:
    #   their only signature-config (source, store_key) are both "wired", not "literal".
}

# The two ACT-tail leaves the runbook does NOT yet contain. doc 06 appends the same Steps
# to POST_TICK_REFERENCE_STEPS; the seed wires them by string so the baseline is COMPLETE
# and validator-passing even before that runbook edit lands. reads/writes are the ACT
# ArtifactKey .value strings doc 06 §3 defines; they match doc 06 §7.1's Step declarations.
# The canonical publish artifact key is PUBLISHED_POST (doc 06 §3.1; doc 05 R6 checks
# PUBLISHED_POST) — NOT "publish_result".
ACT_TAIL_SPECS: list["StepSpec"] = [
    StepSpec(
        id="compose_until_safe",
        tool_id="llm.compose_until_safe",
        reads=["timeline_analysis", "own_posts_analysis", "timeline_ranked"],  # CC-7: 3-read tuple — compose reads TIMELINE_RANKED to build ranked_refs internally; MUST match doc 06 TOOL_READS / doc 07 §2.3
        writes=["composed_post", "safety_verdict"],          # ArtifactKey.COMPOSED_POST / SAFETY_VERDICT
        config={},                                            # coarse ACT tool exposes NO proposable config (doc 06 §5.1)
        purpose="Compose with guardian feedback + reference fallback until safe",
    ),
    StepSpec(
        id="publish_post",
        tool_id="data.publish_post",
        reads=["composed_post", "safety_verdict"],            # ArtifactKey.COMPOSED_POST / SAFETY_VERDICT
        writes=["published_post"],                            # ArtifactKey.PUBLISHED_POST (terminal — R6)
        config={},
        purpose="Publish to X (idempotent) and finalize state",
    ),
]


def spec_from_runbook(account_id: str) -> PipelineSpecDocument:
    """Walk POST_TICK_REFERENCE_STEPS → nested StepSpec/CompositeSpec, then append the two
    ACT-tail leaves so the baseline is a COMPLETE SENSE+ACT graph (10 flattened leaves).
    The single canonical baseline (also backs default_pipeline_spec, 04 §3c)."""
    from app.pipeline.runbooks.post_tick import POST_TICK_REFERENCE_STEPS
    sense = [_node_to_spec(s) for s in POST_TICK_REFERENCE_STEPS]
    # Once doc 06 appends compose_until_safe/publish_post INTO POST_TICK_REFERENCE_STEPS, the
    # walk already yields them (and STEP_TOOL_MAP gains the two tool ids). The guard below
    # prevents a double-add in that post-06 world; pre-06 it appends the literals so the seed
    # is complete on its own.
    have = {s.id for s in sense}
    tail = [s for s in ACT_TAIL_SPECS if s.id not in have]
    spec = PipelineSpecDocument(
        account_id=account_id, steps=sense + tail, status="champion"
    )
    return spec  # version stamp is applied by repo.save → bump_pipeline_version_if_needed


def _node_to_spec(step: "Step") -> "StepSpec | CompositeSpec":
    if step.is_composite:  # flow.py:32 (is_composite); composite_kind ∈ {"parallel","chain"}
        return CompositeSpec(
            kind=step.composite_kind,                # "parallel" | "chain"
            id=step.id,
            children=[_node_to_spec(c) for c in step.children],
            purpose=step.purpose,
        )
    return StepSpec(
        id=step.id,
        tool_id=STEP_TOOL_MAP[step.id],
        reads=[k.value for k in step.reads],
        writes=[k.value for k in step.writes],
        reads_optional=[k.value for k in step.reads_optional],
        config=STEP_CONFIG.get(step.id, {}),
        purpose=step.purpose,
    )
```

The script's `main()`: `spec = spec_from_runbook("JohnJames_News"); PipelineSpecRepository().save(spec)`. The first `save` runs `bump_pipeline_version_if_needed` with `previous_hash=None` → stamps `v1`, writes `pipelinerevisions/JohnJames_News-v1`. Idempotent: re-running computes the same hash and (with no manual label) returns early without a spurious bump (verified against the `elif prev == current_hash and not manual: return` branch).

> **Decision Defense — `collect_external_references` is an INTERNAL PRIMITIVE (`_internal.collect_external`), resolved here, NOT deferred.**
> Verified `steps.py:90-114`: this wrapper does pure dict promotion (`SEARCH_REFERENCES` → `TIMELINE_REFERENCES`); it calls no `tools/**` `run()`, so it is not a catalog tool. **Decision (the simpler option): keep it a hard-coded interpreter primitive registered in a tiny `INTERNAL_PRIMITIVES` table that the compiler AND validator both consult — do NOT write a fake catalog tool module for it.** Promoting it to a real catalog tool would mean a new `tools/` module + `inspect.signature` introspection (doc 03) for a function with no tunable config and no live-service deps — pure ceremony for a 4-line dict promotion. Instead:
> - **`app/pipeline/spec/internal_primitives.py` (NEW, owned by doc 05)** holds `INTERNAL_PRIMITIVES: dict[str, _Primitive]` with one entry: `"_internal.collect_external"` → `{run: steps.collect_external_references, reads: (SEARCH_REFERENCES,), writes: (TIMELINE_REFERENCES,)}` (no `invariant_tool` key — that flag does not exist, CC-2; the validator's structure check is artifact-based, and this primitive writes neither `SAFETY_VERDICT` nor `PUBLISHED_POST`).
> - **Validator R1 (`unknown_tool`):** a `tool_id` resolves if it is in the catalog **or** in `INTERNAL_PRIMITIVES`. So `_internal.collect_external` passes R1. Its `config` must be `{}` (R2: an internal primitive declares no config schema → any key is `config_unknown_key`).
> - **Compiler `_compile_node`:** for an `_internal.*` leaf, bind `run` from `INTERNAL_PRIMITIVES` instead of the catalog; `reads`/`writes` come from the spec node (per §3a-3), so the dotted-id round-trip is unaffected.
> - **It is NOT proposable by the builder:** doc 10's prompt renders only catalog tools, so an LLM never sees `_internal.*`; it appears only in the seed/baseline, preserved in order with its real reads/writes.
>
> This keeps the seed faithful, makes the baseline validate + compile, and confines the special case to one registry both pure functions read. **This RESOLVES the prior "defer to doc 06": doc 06 does not touch `collect_external`; doc 05 owns `INTERNAL_PRIMITIVES`, and this doc's seed simply references the id string.**

---

## 8. Definition of Done (per slice)

**Slice 1 — `pipeline_spec.py`**
- `from app.models.pipeline_spec import PipelineSpecDocument, StepSpec, CompositeSpec, default_pipeline_spec` imports clean.
- `CompositeSpec(kind="parallel", id="x", children=[StepSpec(id="a", tool_id="t"), CompositeSpec(kind="chain", id="c", children=[])])` validates (nested composite round-trips).
- `PipelineSpecDocument.document_id("acct")` → `"pipelinespecs/acct"`; `document_id("acct","challenger")` → `"pipelinespecs/acct-challenger"`; `document_id("acct","champion","reply")` → `"pipelinespecs-reply/acct"` (the `kind` family namespace — CC-12).

**Slice 2 — `pipeline_revision.py`**
- `PipelineRevisionDocument(account_id="a", seq=1, label="v1", version_hash="h", changed_at="t")` validates with empty `steps`.
- `document_id("a", 1)` → `"pipelinerevisions/a-v1"`.

**Slice 3 — `pipeline_version_service.py`**
- `compute_pipeline_hash(spec)` is stable across calls and **changes** when any `steps` entry changes; **unchanged** when only `status`/`parent_hash`/`version_label` change.
- `bump_pipeline_version_if_needed(spec, previous_hash=None)` sets `version_seq=1`, stamps a hash, and saves one revision (assert via an injected fake `revision_repo`).
- A second call with `previous_hash=spec.version_hash` and no `steps` change returns early (no new revision).

**Slice 4 — `pipeline_revision_repository.py`**
- `save(rev)` PUTs to collection `PipelineRevisions` at id `pipelinerevisions/{aid}-v{seq}` (verify against a fake `RavenDBHttpClient`).
- `list_for_account` orders by `seq asc` and survives the index-missing fallback path.

**Slice 5 — `pipeline_spec_repository.py`**
- `save(spec)` bumps version then PUTs to collection `PipelineSpecs`.
- `load_or_default("JohnJames_News")` (and `load_or_default("JohnJames_News", kind="post")`, the default) returns the baseline when no doc exists, and the returned baseline carries a non-`None` `version_hash` (the in-memory stamp, §6b note). This is the single loader entry point — there is NO `load_active_spec` free function (CC-5).
- `promote_challenger` runs `validate_spec(challenger, get_tool_catalog())` (doc 05/03, CC-1) then `compile_spec` (doc 05) before activating, writes the new champion with `parent_hash` = outgoing champion's hash, deletes the challenger doc; a simulated delete failure leaves a harmless duplicate and does not raise; an invalid challenger raises before any write.

**Slice 6 — `seed_pipeline_spec.py`**
- Running it produces a champion `PipelineSpecDocument` whose `steps` tree, when compiled by doc 05 and flattened, yields the **identical 10 dotted leaf ids** = the 8 SENSE ids `flatten_steps(POST_TICK_REFERENCE_STEPS)` produces today (`load_account_bundle`, `fetch_search_references`, `collect_external_references`, `fetch_own_post_history`, `summarize_for_compose.analyze_external_references.rank_external_references`, `…brief_external_references`, `summarize_for_compose.analyze_own_posts.rank_own_posts`, `…brief_own_posts`) **plus** the two ACT leaves (`compose_until_safe`, `publish_post`).
- The seeded baseline **passes `validate_spec`** (doc 05): exactly one terminal `published_post` writer (R6) and at least one `safety_verdict` writer (R7) are present — both detected purely from artifacts, no `invariant_tool` flag (CC-2); no `StepSpec.config` carries a non-`literal` key (R2). (This DoD line is gated on doc 06's artifact keys + the two ACT tools existing; run it after doc 06 lands — see §7 sequencing note.)
- `v1` revision archived; re-running is idempotent (no spurious `v2`).

**Global**
- `python -m py_compile` clean on all six new files.
- No edits to `post_tick.py`, `flow.py`, or any `tools/**` file (this doc is purely additive). (doc 06 separately appends the two ACT `Step`s to `post_tick.py`; that edit is doc 06's, not this doc's — the seed wires the same two leaves by string so it stands alone pre-06.)
