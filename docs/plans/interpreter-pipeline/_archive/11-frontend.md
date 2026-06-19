# Doc 11 — Frontend (builder chat · spec-driven graph · full step-content viewer)

> **Status:** Ready to implement. Authored cold from a verified read of the live frontend + the sibling interpreter docs; pick up from this folder.
> **Scope:** Frontend only — one new builder page + chat, a rebuilt `flowGraph` source (rendered from the DB-loaded compiled spec, retiring the keep-in-sync hazard), and a full-fidelity run-trace viewer that renders the `PipelineRunDocument` chain and, on clicking a step, shows that step's COMPLETE `StepOutputDocument`. Plus the TS types + endpoints these need.
> **Target project:** `SocialMediaAutonomousAgents/frontend/` (CRA / React 18 + react-router 6 + @tanstack/react-query).
> **CRA reality:** no build-time codegen and no build-time mermaid plugin. Mermaid (if used) renders at **runtime**; the default graph render is plain React (the existing `PipelineFlowDiagram`) fed by spec data, with mermaid as an optional runtime view (§4.4). One account exists today — `JohnJames_News`.

---

## 0. Where this doc sits in the set

This doc is the **only** frontend slice of the Interpreter. It consumes shapes the backend siblings own; it never redefines them. The hard dependencies:

| What this doc renders | Shape owner (by doc number) | The exact fields this doc reads (pinned in §2) |
|---|---|---|
| The editable pipeline graph | **04** `PipelineSpecDocument` + `StepSpec` + `CompositeSpec` | `steps[]`, per node `kind`/`id`/`tool_id`/`reads`/`writes`/`purpose`/`children` |
| The validator errors in the builder | **05** `ValidationReport` + `ValidationError` | `ok`, `errors[].{code, step_id, artifact, detail}` |
| The run-trace chain | **08** `PipelineRunDocument.step_links[]` + `StepLink` | `step_links[].{step_id, scope, seq, status, duration_ms, doc_id}` |
| Each step's full content | **08** `StepOutputDocument` + `StepOutputArtifact` | `inputs[]`/`outputs[]`/`result_payload`, `{artifact, present, size_bytes, value}` |
| The ACT step nodes (compose/publish) | **06** `compose_until_safe` / `publish_post` (top-level dotted ids) | the leaf ids `compose_until_safe`, `publish_post` |
| The builder chat backend (SSE) | **10** `POST /api/agent-builder/chat` + `BuilderChatRequest`/`BuilderChatMessage` + the SSE event union | the SSE contract pinned in §3.3 (= doc 10 §6.3 verbatim) |

The builder SSE backend **is owned — by doc 10** (`app/api/routes/agent_builder.py`). This doc consumes doc 10's exact request body and event union; it does **not** invent a parallel contract (an earlier draft did, and that drift is corrected throughout §3.3/§6/§7 to match doc 10). The pipeline **read-routes** this doc needs — `GET /api/accounts/{id}/pipeline/spec[?status]`, `POST /api/accounts/{id}/pipeline/spec/validate`, `GET /api/pipeline/runs/{run_id}` (the trace chain), and `GET /api/pipeline/runs/{run_id}/steps/{step_id}` (full step output) — are **owned by doc 14 (`14-backend-read-routes.md`), per CC-11**. They are thin reads over methods docs 04/05/08 already ship (`PipelineSpecRepository.load_or_default`, `validate_spec` + `get_tool_catalog()`, `StepOutputRepository.get`), and doc 14 is sequenced **before** this doc (overview §4: `… → 08 → 14 → 09 → 10 → 11`). This doc mirrors doc 14's contracts read-only (§3.1 spec read + validate, §3.2 step-output read) and flags doc 14 as the owner in `cross_refs`. (`GET /api/pipeline/runs/{run_id}` already exists today as `fetchPipelineRun` in `api/endpoints/pipelineRuns.ts:18-20`; this doc reuses it for the trace header and adds only the per-step-output client.) Where a contract is uncertain the doc resolves it to the **simplest** shape that mirrors an existing route (`pipeline_runs.py`).

---

## 1. Why this change

Three concrete gaps in today's frontend (all verified on disk):

1. **The graph is a hand-maintained mirror with a documented drift hazard.** `frontend/src/lib/pipeline/flowGraph.ts:1-19` opens with a *"KEEP IN SYNC WITH THE BACKEND RUNBOOK"* banner. Every step id is hardcoded in the `PIPELINE_FLOW` constant (`flowGraph.ts:63-191`, flattened to ids at `:194-200`) and must equal `flatten_steps()` output or the node "silently stops lighting up" (its own words, lines 9-11). Doc 06 §7.1 **adds** two ACT leaves (`compose_until_safe`, `publish_post`) and **removes** the ad-hoc `compose`/`safety`/`publish`/`complete` orchestrator nodes — which today would mean another hand-edit of this file. The Interpreter makes the pipeline *data*; the graph should be rendered **from that data**, so the file stops being a parallel source of truth.

2. **The run-trace viewer reads the wrong (truncated, nested) shape.** `LatestRunPanel.tsx` renders `run.steps[]` inline (`pipelineRun.ts:18-46`) — the NATS-projected, **8000-char-truncated** nested list (doc 08 §1). Doc 08 makes `PipelineRunDocument` a header + `step_links[]` pointing at one **untruncated** `StepOutputDocument` per step. The viewer must follow the links and, on click, fetch + show a step's COMPLETE content.

3. **There is no builder UI.** The Interpreter's entire value is that an operator (or the self-rewrite loop) edits the spec by *wiring + configuring* catalog tools (settled architecture: the builder NEVER writes tool code). There is no page for that. We add an **`AgentBuilderPage`** with a chat that reuses the existing SSE client pattern (`forcePost.ts` / `usePipelineRunStream`) and `apiFetch`.

**Goal:** (a) render the graph from the loaded spec; (b) a run-trace viewer that follows `step_links` and shows full step content on click; (c) a builder chat page. All three reuse existing components/clients; none introduces a new state library or a build step.

---

## 2. Shared-type contracts this slice reads (the minimum fields)

These are added to `frontend/src/types/domain/`. They are the **read-only** projections of the backend models; only the fields this doc consumes are typed (extra backend fields are tolerated — TS structural typing ignores them).

### 2.1 `types/domain/pipelineSpec.ts` (NEW) — mirrors doc 04

```typescript
// Mirror of backend app/models/pipeline_spec.py (doc 04). Read-only on the frontend.
export type SpecStep = {
  kind: 'step';
  id: string;
  tool_id: string;
  reads: string[];          // ArtifactKey .value strings
  writes: string[];
  reads_optional?: string[];
  config?: Record<string, unknown>;
  purpose?: string;
};

export type SpecComposite = {
  kind: 'parallel' | 'chain';
  id: string;
  children: SpecNode[];
  purpose?: string;
};

export type SpecNode = SpecStep | SpecComposite;

export type PipelineSpec = {
  account_id: string;
  steps: SpecNode[];
  status: 'champion' | 'challenger';
  parent_hash?: string | null;
  version_hash?: string | null;
  version_seq?: number;
  version_label?: string | null;
};

export const isComposite = (n: SpecNode): n is SpecComposite =>
  n.kind === 'parallel' || n.kind === 'chain';
```

> **Verified against doc 04 §3b:** `StepSpec.kind` is the literal `"step"`; `CompositeSpec.kind` is `"parallel" | "chain"`; `reads`/`writes` are `list[str]` of `ArtifactKey.value`; `PipelineSpecDocument` carries `status`/`version_*`. The discriminant `kind` lets the renderer fan out leaf vs composite with no separate flag.

### 2.2 `types/domain/validation.ts` (NEW) — mirrors doc 05 §5.2

```typescript
// Mirror of backend app/pipeline/spec/validator.py ValidationReport (doc 05 §5.2).
export type ValidationError = {
  code: string;             // stable code set (doc 05 §5.2)
  step_id?: string | null;
  artifact?: string | null;
  detail?: string;
};
export type ValidationReport = { ok: boolean; errors: ValidationError[] };
```

### 2.3 `types/domain/stepOutput.ts` (NEW) — mirrors doc 08 §4

```typescript
// Mirror of backend app/models/step_output.py (doc 08).
export type StepOutputArtifact = {
  artifact: string;         // ArtifactKey.value
  present: boolean;
  size_bytes?: number | null;
  value?: unknown;          // FULL untruncated payload; absent only when present=false
};

export type StepOutputDocument = {
  run_id: string;
  account_id: string;
  step_id: string;          // dotted flat id
  scope: string;            // runbook | orchestrator
  parent_id?: string | null;
  purpose?: string | null;
  seq: number;
  status: string;           // ok | skipped | error
  skip_reason?: string | null;
  error?: { type?: string; message?: string; traceback?: string } | null;
  started_at?: string | null;
  ended_at?: string | null;
  duration_ms?: number | null;
  inputs: StepOutputArtifact[];
  outputs: StepOutputArtifact[];
  result_payload?: Record<string, unknown>;
};

export type StepLink = {
  step_id: string;
  scope: string;
  seq: number;
  status: string;
  duration_ms?: number | null;
  doc_id: string;           // stepoutputs/{run_id}/{step_id}
};
```

> **Note vs existing `pipelineRun.ts`:** today's `StepArtifact` (`pipelineRun.ts:3-9`) has a `truncated?: boolean` flag — that is the NATS-truncated nested shape and stays for `LatestRunPanel`'s legacy read. `StepOutputArtifact` deliberately has **no `truncated` field**: doc 08 stores full payloads, so a `truncated` flag would be a lie. The two types coexist; §5 explains which viewer uses which.

### 2.4 Extend `types/domain/pipelineRun.ts` (CHANGED) — add `step_links`

Add ONE field to the existing `PipelineRun` type (doc 08 adds `step_links` to `PipelineRunDocument`, keeping `steps` for the NATS path):

```typescript
// in PipelineRun (pipelineRun.ts:33-46) — ADD:
  step_links?: StepLink[];   // doc 08: ordered links to StepOutputDocument; empty when NATS-only
```

`steps` stays untouched. When the trace ran with NATS OFF, `steps` is `[]` and `step_links` is authoritative; with NATS ON, both are present (doc 08 §9). The viewer (§5) prefers `step_links` and falls back to `steps`.

---

## 3. New endpoints — `api/endpoints/` (NEW) + the backend contracts they assume

All use the existing `apiFetch<T>(path, options?)` (`api/client.ts:38-51`), which already injects `authHeaders()`, prefixes `/api`, and throws `parseHttpError` on non-2xx. The builder SSE reuses the **exact** raw-fetch + `data: {json}\n\n` parse loop from `forcePost.ts:17-66`.

### 3.1 `api/endpoints/pipelineSpec.ts` (NEW) — read the live spec + validate

```typescript
import { apiFetch } from '../client';
import type { PipelineSpec } from '../../types/domain/pipelineSpec';
import type { ValidationReport } from '../../types/domain/validation';

export async function fetchAccountSpec(
  accountId: string,
  status: 'champion' | 'challenger' = 'champion'
): Promise<PipelineSpec> {
  return apiFetch<PipelineSpec>(
    `/accounts/${encodeURIComponent(accountId)}/pipeline/spec?status=${status}`
  );
}

export async function validateAccountSpec(accountId: string): Promise<ValidationReport> {
  return apiFetch<ValidationReport>(
    `/accounts/${encodeURIComponent(accountId)}/pipeline/spec/validate`,
    { method: 'POST' }
  );
}
```

> **Backend contract this assumes (OWNED by doc 14 per CC-11 — this is a read-only mirror):**
> `GET /accounts/{account_id}/pipeline/spec?status=champion` → `PipelineSpecRepository.load_or_default(account_id, status, kind="post")` (doc 04 §6b, the single loader per CC-5) `.model_dump()`. `load_or_default` already returns the version-stamped baseline when no doc exists (doc 04 §6b), so this never 404s — the graph always renders. `POST /accounts/{account_id}/pipeline/spec/validate` → `validate_spec(load_or_default(account_id, status, kind="post"), catalog).model_dump()`. **`catalog` is the `ToolCatalog` object from the single factory `get_tool_catalog()` (CC-1) — the same object `validate_spec(doc, catalog)` accepts everywhere (docs 03/05/09/10); the name `build_catalog()` and any raw `list[ToolCatalogDocument]` arg are removed (CC-1), so there is no cross-doc disagreement to resolve here.** Both handlers are thin wrappers around existing repo/pure functions; they mirror `pipeline_runs.py` exactly (router + `repo` module-level, `asyncio.to_thread` for the blocking load). **Owner:** doc 14 (`14-backend-read-routes.md`), sequenced before this doc per overview §4; flagged in `cross_refs`.

### 3.2 `api/endpoints/stepOutputs.ts` (NEW) — one step's full content

```typescript
import { apiFetch } from '../client';
import type { StepOutputDocument } from '../../types/domain/stepOutput';

export async function fetchStepOutput(
  runId: string,
  stepId: string
): Promise<StepOutputDocument> {
  return apiFetch<StepOutputDocument>(
    `/pipeline/runs/${encodeURIComponent(runId)}/steps/${encodeURIComponent(stepId)}`
  );
}
```

> **Backend contract this assumes (OWNED by doc 14 per CC-11):** `GET /pipeline/runs/{run_id}/steps/{step_id}` → `StepOutputRepository.get(run_id, step_id)` (doc 08 §5, already implemented there) `.model_dump()`, 404 if `None`. This is a one-line handler over a method doc 08 already ships. **The dotted `step_id` contains no slash** (e.g. `summarize_for_compose.analyze_external_references.rank_external_references`) so a single path segment is safe; `encodeURIComponent` handles the dots defensively. The doc-08 doc id is `stepoutputs/{run_id}/{step_id}` and `get()` rebuilds it, so the route never exposes the slash-bearing raw doc id. **Owner:** doc 14 (the same read-route slice as §3.1) — flagged in `cross_refs`.

### 3.3 `api/endpoints/builderChat.ts` (NEW) — the builder SSE client (consumes doc 10's contract verbatim)

The builder backend **is owned by doc 10** (`POST /api/agent-builder/chat`). This client is a near-verbatim copy of `streamForcePost` (`forcePost.ts:17-66`) — same `apiPrefix`, same `Accept: text/event-stream`, same `authHeaders()`, same `data: {json}\n\n` split loop — pointed at doc 10's route, posting doc 10's `BuilderChatRequest` body, and parsing doc 10's `BuilderStreamEvent` union (§6.3 of doc 10). **There is no contract negotiation here: every URL/body/event below is copied from doc 10, not invented by this doc.**

```typescript
import { apiPrefix, parseHttpError } from '../client';
import { authHeaders } from '../auth';
import type { BuilderChatRequest, BuilderStreamEvent } from '../../types/domain/builder';

function parseSse(line: string): BuilderStreamEvent | null {
  const payload = line.startsWith('data: ') ? line.slice(6) : line;
  if (!payload.trim()) return null;
  try {
    return JSON.parse(payload) as BuilderStreamEvent;
  } catch {
    return null;
  }
}

// `req` is doc 10's BuilderChatRequest: { account_id, mode, messages[], approve }.
// The full message history is posted every turn (doc 10's server is stateless; the
// client echoes prior proposed_spec/validation_errors back in `messages` — doc 10 §6.1).
export async function streamBuilderChat(
  apiBase: string,
  req: BuilderChatRequest,
  onEvent: (event: BuilderStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const prefix = apiPrefix(apiBase);
  const res = await fetch(`${prefix}/agent-builder/chat`, {   // doc 10 §4: POST /api/agent-builder/chat
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok) throw new Error(await parseHttpError(res));
  if (!res.body) throw new Error('No response body from builder stream');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  // identical chunk/line loop to forcePost.ts:40-65
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const chunk of parts)
      for (const line of chunk.split('\n')) {
        const ev = parseSse(line);
        if (ev) onEvent(ev);
      }
  }
  if (buffer.trim())
    for (const line of buffer.split('\n')) {
      const ev = parseSse(line);
      if (ev) onEvent(ev);
    }
}
```

The request body + event union (`types/domain/builder.ts`, NEW) — **mirror of doc 10 §6.1 + §6.3**:

```typescript
// Mirror of backend app/api/routes/agent_builder_types.py (doc 10 §6). Read-only on the frontend.
import type { PipelineSpec } from './pipelineSpec';
import type { ValidationError } from './validation';

export type BuilderChatMessage = {
  role: 'user' | 'assistant';
  text: string;
  // When an assistant turn proposed a spec, the client echoes the streamed
  // spec_preview.spec + validation_errors back here so the next turn / approve can
  // reference the exact prior proposal without a server session (doc 10 §6.1).
  proposed_spec?: PipelineSpec | null;
  validation_errors?: ValidationError[] | null;
};

export type BuilderChatRequest = {
  account_id: string;
  mode: 'create' | 'edit';            // doc 10: "create" provisions; "edit" stages a challenger
  messages: BuilderChatMessage[];
  approve?: boolean;                  // true => write the last proposed_spec (re-validated first)
};

// doc 10 §6.3 — every frame has a `type` discriminant. NOTE: the assistant text is
// delivered WHOLE in one `assistant_message` per turn (doc 10 does NOT token-stream;
// it emits the parsed BuilderDraft.reply after the single Claude call). The right
// pane renders on `spec_preview`; errors surface on `validation_errors`.
export type BuilderStreamEvent =
  | { type: 'assistant_message'; text: string }
  | { type: 'validation_errors'; errors: ValidationError[] }
  | { type: 'spec_preview'; mermaid: string; spec: PipelineSpec;
      catalog_hash: string; soul_edit?: Record<string, unknown> | null }
  | { type: 'spec_written'; spec_doc_id: string; status: 'champion' | 'challenger';
      version_label: string; soul_bumped: boolean; account_id: string }
  | { type: 'error'; message: string }
  | { type: 'done' };
```

> **Backend contract (OWNED by doc 10 — this is a mirror, not a new spec):**
> `POST /api/agent-builder/chat` with `Accept: text/event-stream` and a `BuilderChatRequest` body, returning `StreamingResponse(media_type="text/event-stream")` that yields `data: {json}\n\n` frames of the union above (doc 10 §7.1 route, §6.3 events). Doc 10's worker holds the catalog + soul schema + seed-spec example in context, has `ClaudeClient` draft a `BuilderDraft{reply, spec?, soul_edit?}`, runs the pure `validate_spec` (doc 05), emits `validation_errors` on failure or `spec_preview` (with `artifact_graph_mermaid` output) on success, and — only on `approve: true` — writes a champion (create) or challenger (edit) via `PipelineSpecRepository.save` and emits `spec_written`. **If doc 10 ever changes an event field, the single adapter point on this side is `types/domain/builder.ts` + `parseSse`.** The non-SSE buffered fallback doc 10 §6.4 ships (`{"events": [...]}`) is not used by this client (the page always sends `Accept: text/event-stream`).

---

## 4. The graph: render from the loaded spec, retire the keep-in-sync hazard

### 4.1 File-by-file

| Kind | File | Role (one line) |
|---|---|---|
| **CHANGED** | `frontend/src/lib/pipeline/flowGraph.ts` | Stop hardcoding the section/node tree. Keep the `FlowNodeDef`/`FlowRow`/`FlowSection` **types** and `EXTERNAL_LABELS`; replace the constant `PIPELINE_FLOW` with `flowFromSpec(spec): FlowSection[]` that derives the same shape from a `PipelineSpec`. |
| **NEW** | `frontend/src/lib/pipeline/specToFlow.ts` | Pure `flowFromSpec(spec: PipelineSpec): FlowSection[]` + `flowStepIds(spec): string[]` (the dotted-id list, replacing `PIPELINE_FLOW_STEP_IDS`). |
| **CHANGED (small)** | `frontend/src/features/pipeline/PipelineFlowDiagram.tsx` | Today it **imports `PIPELINE_FLOW` directly** (`PipelineFlowDiagram.tsx:14`) and maps over it at `:95`. Change: add `sections?: FlowSection[]` to `PipelineFlowDiagramProps` (`:20-24`), default it to the imported `PIPELINE_FLOW`, and replace the `PIPELINE_FLOW.map(...)` at `:95` with `(sections ?? PIPELINE_FLOW).map(...)`. ~4 lines; all existing call sites that pass no `sections` are byte-identical. The node/branch render bodies (`NodeCard`/`Row`/`statusOf`) are untouched — they already consume `FlowSection`/`FlowRow`/`FlowNodeDef` as data. |
| **CHANGED** | `frontend/src/lib/pipeline/flowReducer.ts` | `initialFlowState`/`applyFlowProgress` take the dotted-id set from `flowStepIds(spec)` instead of the static `PIPELINE_FLOW_STEP_IDS`. |
| **CHANGED** | `frontend/src/features/pipeline/PipelineRunPanel.tsx` | Load the spec (`useAccountSpec`), derive sections + step-id set, seed the reducer from them. |

### 4.2 `flowFromSpec` — the derivation (the elegant replacement)

The current `PIPELINE_FLOW` is three sections: `orchestrator-pre` (start/load/lock), `runbook` (the SENSE leaves + the `summarize_for_compose` parallel), `orchestrator-post` (compose/safety/publish/complete). Post-doc-06 the spec **is** the whole graph (SENSE + ACT), and the orchestrator-pre locks stay imperative outside the spec (doc 07 §2.2). So:

- **One labelled section, `runbook`, derived from `spec.steps`.** Walk the nested `SpecNode[]`. A `SpecStep` → a `{type:'step', node}` row with `id = <dotted id>` (built exactly like `flatten_steps`: a composite contributes its `id` as a prefix to descendants — see §4.3). A `SpecComposite` with `kind:'parallel'` → a `{type:'parallel', ...}` row whose branches are its `chain` children. A `chain` at top level → its children become sequential `step` rows (matching how `flatten_steps` flattens a top-level chain). The `summarize_for_compose` parallel and the two new ACT leaves (`compose_until_safe`, `publish_post`) fall out automatically.
- **A fixed `orchestrator-pre` section for the imperative locks** (`start`/`load_account`/`post_lock`) is **retained as a small constant** (`OPS_PRE_SECTION`) because those stages are NOT in the spec (doc 07 §2.2 keeps locks imperative) and they still emit progress events. This is the one honest piece of hand-maintenance left, and it is *stable* (locks don't change with the spec).
- **External call-out (`claude`/`x_api`/`ravendb`)** is derived from `tool_id` prefix: `data.search_fetch`/`data.account_profile` → `x_api`; `data.own_posts_fetch` → `ravendb`; `llm.*` → `claude`; `deterministic.*` → none. A small `EXTERNAL_BY_TOOL_PREFIX` map (verified against the catalog inventory in doc 03 §3: `data.*` sources are `x_api`/`x_search`/`ravendb`, `llm.*` call Claude). `compose_until_safe` is `llm.*` → `claude`; `publish_post` is `data.*` writing to X → `x_api`.
- **`label`/`subtext`** come from the node: `label` = a humanized `id` (replace `_`→space, title-case) or `purpose` if short; `subtext` = `purpose` truncated. No magic — purely presentational.

```typescript
// specToFlow.ts (sketch — pure, no React)
import type { FlowSection, FlowNodeDef, FlowExternal } from './flowGraph';
import { type PipelineSpec, type SpecNode, isComposite } from '../../types/domain/pipelineSpec';

// Tool ids verified: doc 03 §3 (the 6 SENSE tools) + doc 06 §5 (the 2 ACT tools).
// Longest-prefix-first so 'data.publish_post' is matched before any shorter 'data.' rule.
const EXTERNAL_BY_TOOL_PREFIX: Array<[string, FlowExternal]> = [
  ['data.search_fetch', 'x_api'],       // doc 03: search_fetch.TOOL_SOURCE = x_search/x_api
  ['data.account_profile', 'x_api'],    // doc 03: account_profile reads the X profile
  ['data.own_posts_fetch', 'ravendb'],  // doc 03: own posts come from RavenDB, not X
  ['data.publish_post', 'x_api'],       // doc 06 §5.2: publish_post.TOOL_SOURCE = "x_api"
  ['llm.', 'claude'],                   // doc 06 §5.1: compose_until_safe is llm.* → claude
];
// `_internal.collect_external` (doc 04 §7 sentinel) and `deterministic.*` rankers have
// no external call-out (in-process) — externalFor returns undefined for them.
function externalFor(toolId: string): FlowExternal | undefined {
  const hit = EXTERNAL_BY_TOOL_PREFIX.find(([p]) => toolId.startsWith(p));
  return hit?.[1];
}

function dottedId(node: SpecNode, prefix: string): string {
  return prefix ? `${prefix}.${node.id}` : node.id;
}

function leafNode(step: Extract<SpecNode, { kind: 'step' }>, prefix: string): FlowNodeDef {
  return {
    id: dottedId(step, prefix),         // matches flatten_steps + emitted progress step_id
    label: humanize(step.id),
    subtext: step.purpose?.slice(0, 48),
    external: externalFor(step.tool_id),
  };
}
// flowFromSpec(spec) walks spec.steps building FlowSection rows; flowStepIds(spec)
// returns the dotted-id list (the reducer's known-id set). Both reuse dottedId.
```

> **Decision Defense — render the graph from spec data, not a hand-maintained constant.**
> The brief asks to "retire the keep-in-sync hazard." The current file's own banner (`flowGraph.ts:1-19`) is an admission that a hand-mirror drifts; doc 06 §7.1 would force the next hand-edit. The Interpreter's premise is that the pipeline *is* data, and `flatten_steps`' dotted-id scheme is **deterministic from the nested ids** (doc 05 §6.1 makes the compiler reproduce it). So the frontend can reproduce the *same* dotted ids from the *same* nested spec, purely. This deletes the drift class entirely: change the spec → graph + reducer follow, no file edit. The only retained constant is the 3 imperative lock stages (doc 07 §2.2), which are genuinely not in the spec and are stable.

> **Decision Defense — keep `PipelineFlowDiagram` as the default renderer; mermaid is an optional runtime view.**
> `PipelineFlowDiagram.tsx` already renders `FlowSection[]` with live per-node status, parallel-branch layout, and external call-outs — and it costs zero new deps. CRA forbids a build-time mermaid plugin; mermaid would have to render at runtime (dynamic `import('mermaid')` + `mermaid.render`). For the *interactive, status-lit* graph the React renderer is strictly better (mermaid SVG can't show per-node live status without re-rendering the whole diagram each tick). So the default stays React. §4.4 keeps a **runtime** mermaid toggle for a static "export/share" view only, behind a lazy import so it never enters the main bundle.

### 4.3 The dotted-id contract (the graded property)

`flowStepIds(spec)` MUST produce the **exact strings** `flatten_steps(compile_spec(spec))` produces on the backend, because those are the `step_id`s the SSE progress events carry (`pipelineProgress.ts:9-16`) and the reducer matches (`flowReducer.ts:14`). The rule is identical to doc 05 §6.1: a composite contributes its `id` as a dotted prefix; leaves are `prefix.leafId`; top-level leaves are bare. Concretely, the baseline spec must yield the same 8 SENSE ids the current file hardcodes in its `runbook` section (`flowGraph.ts:84-164`) plus the two ACT leaves:

> **The 10-leaf baseline is OWNED by doc 04 — settled, no handoff ambiguity.** Doc 04 §7 (its "Settled — the baseline MUST be a full SENSE+ACT graph (10 leaves)" note) makes `default_pipeline_spec(account_id)`/`spec_from_runbook` append `compose_until_safe` (`tool_id` `llm.compose_until_safe`) and `publish_post` (`tool_id` `data.publish_post`) to the 8 SENSE leaves, so the seed already validates under doc 05's R6/R7. **Doc 04's `default_pipeline_spec` therefore yields 10 dotted ids, exactly the list below — the `baselineSpec` fixture in §8 mirrors it 1:1.** Doc 06 owns only the *tools/artifacts*; doc 04 owns *wiring them into the seed*. This frontend lock test and doc 04 §8 / doc 13 §1's `test_pipeline_runbook` 10-leaf expectation all grade against the same baseline.

```
load_account_bundle
fetch_search_references
collect_external_references
fetch_own_post_history
summarize_for_compose.analyze_external_references.rank_external_references
summarize_for_compose.analyze_external_references.brief_external_references
summarize_for_compose.analyze_own_posts.rank_own_posts
summarize_for_compose.analyze_own_posts.brief_own_posts
compose_until_safe
publish_post
```

A unit test (§8) asserts `flowStepIds(baselineSpec)` equals this list — the frontend mirror of doc 05's backend lock test. This is the regression the `flowGraph.ts:9-11` comment asks for, now enforced by a test instead of a prose warning.

### 4.4 Optional runtime mermaid view (lazy, no build step)

A `MermaidGraph.tsx` (NEW, optional) renders a static diagram for sharing: `const mermaid = (await import('mermaid')).default; mermaid.initialize({startOnLoad:false}); const { svg } = await mermaid.render(id, defFromSpec(spec));`. `defFromSpec` emits `flowchart TD` text from `spec.steps` (reads→writes edges, exactly like the backend `artifact_graph_mermaid` at `flow.py:127-138`). It is **dynamically imported** so mermaid stays out of the main CRA bundle, and it shows **no live status** (static). This satisfies "runtime mermaid (CRA, no build-time)" without making it the default. `mermaid` is added to `package.json` dependencies; if the team prefers zero new deps, this whole component is droppable (the React diagram is the product).

---

## 5. The run-trace viewer: render the `step_links` chain, show full step content on click

### 5.1 File-by-file

| Kind | File | Role (one line) |
|---|---|---|
| **NEW** | `frontend/src/features/pipeline/RunTraceViewer.tsx` | Renders a `PipelineRun`'s ordered chain from `step_links` (fallback `steps`); each row is a button that, on click, fetches and shows the full `StepOutputDocument`. |
| **NEW** | `frontend/src/features/pipeline/StepContentPanel.tsx` | Full-content panel for one `StepOutputDocument`: status/timing/error + every input/output artifact's **complete** `value` (untruncated) + `result_payload`. |
| **NEW** | `frontend/src/hooks/queries/useStepOutput.ts` | `useStepOutput(runId, stepId, enabled)` → `fetchStepOutput`, lazy (only fetches when a row is expanded). |
| **REUSED (read for shape)** | `frontend/src/features/posts/LatestRunPanel.tsx` | The `ArtifactList`/`fmt*` helpers are the template for `StepContentPanel`; copy the presentation, drop the `truncated` tag, render `value` whole. |
| **CHANGED (wire-in)** | `frontend/src/features/pipeline/PipelineOpsPage.tsx` | Add a `RunTraceViewer` panel under the live-flow panel, fed by the account's latest run. **Unwrap required:** `useLatestPipelineRun(accountId)` returns `UseQueryResult<PipelineRunsResponse>` where `PipelineRunsResponse = { count: number; runs: PipelineRun[] }` (`api/endpoints/pipelineRuns.ts:4-7`), **not** a bare `PipelineRun`. Read the run as `const run = query.data?.runs?.[0];` (matching how `usePipelineRuns.ts:12` already does `query.state.data?.runs?.[0]`) and pass `run` to `<RunTraceViewer run={run} />`; render nothing/an empty state when `run` is undefined. |

### 5.2 `RunTraceViewer` — the chain

`RunTraceViewer` takes a single resolved `run: PipelineRun` prop (the caller does the `data.runs[0]` unwrap above — the viewer never sees the `PipelineRunsResponse` envelope).

```tsx
// Source of truth for the chain: step_links (doc 08, full+durable); fall back to
// the NATS-projected nested steps only when step_links is empty/absent.
function chainRows(run: PipelineRun): { stepId: string; scope: string; seq: number;
                                        status: string; durationMs?: number | null }[] {
  if (run.step_links && run.step_links.length) {
    return [...run.step_links]
      .sort((a, b) => a.seq - b.seq)
      .map((l) => ({ stepId: l.step_id, scope: l.scope, seq: l.seq,
                     status: l.status, durationMs: l.duration_ms }));
  }
  // legacy fallback: nested steps carry no seq; preserve array order.
  return run.steps.map((s, i) => ({ stepId: s.step_id, scope: s.scope, seq: i + 1,
                                    status: s.status, durationMs: s.duration_ms }));
}
```

Each row: status badge (reuse `statusColor`/`badge` from `LatestRunPanel.tsx:9-77`), the dotted `step_id`, `scope` tag, duration. Clicking toggles a `StepContentPanel` that lazily fetches `fetchStepOutput(run.run_id, stepId)` via `useStepOutput`. Only ONE step's full content is fetched at a time (click-to-expand), so the viewer never pulls every untruncated payload at once — the whole reason doc 08 split into per-step docs.

### 5.3 `StepContentPanel` — FULL fidelity, no truncation

This is the explicit user requirement: the COMPLETE input + output artifact, untruncated. The panel renders, for one `StepOutputDocument`:

- header: `status` badge, `scope`, `started_at → ended_at`, `duration_ms`, `purpose`;
- `error` block (type/message/traceback) when `status === 'error'`;
- `skip_reason` when `status === 'skipped'`;
- **Inputs** and **Outputs**: each `StepOutputArtifact` renders `artifact` name, `present`, `size_bytes`, and — when `present` — its **entire** `value` via `<pre>{JSON.stringify(value, null, 2)}</pre>`. **No char cap, no `truncated` tag** (the field doesn't exist on `StepOutputArtifact` by design, §2.3).
- `result_payload` as a final `<pre>` block.

```tsx
function ArtifactBlock({ art }: { art: StepOutputArtifact }) {
  return (
    <div className="step-content__artifact">
      <div className="step-content__art-head">
        <code>{art.artifact}</code>
        {!art.present ? <span className="tag">absent</span> : null}
        {art.size_bytes != null ? <span className="tag">{fmtBytes(art.size_bytes)}</span> : null}
      </div>
      {art.present ? (
        // FULL value, untruncated. The whole point of doc 08's separate-doc-per-step.
        <pre className="step-content__pre">{formatValue(art.value)}</pre>
      ) : null}
    </div>
  );
}
```

`formatValue`/`fmtBytes`/`fmtDuration`/`fmtTime`/`statusColor`/`badge` are copied from `LatestRunPanel.tsx:18-110` (same presentation language). The ONE behavioral difference from `LatestRunPanel`: the `<pre>` has **no `maxHeight`/truncation** on the value beyond a scroll container — full content is the spec.

> **Decision Defense — click-to-expand + per-step fetch instead of one fat run fetch.**
> Doc 08 deliberately splits each step's untruncated I/O into its own `StepOutputDocument` so the run header stays tiny. Mirroring that on the client — fetch a step's full doc only when its row is expanded — keeps the trace viewer's initial load cheap (it loads only the header's `step_links`, which carry id/scope/seq/status/duration, no payloads) and pulls a megabyte-class artifact only on demand. Fetching the whole run's worth of full payloads up front would re-inline exactly what doc 08 split apart.

> **Decision Defense — keep `LatestRunPanel` as-is; add a new viewer rather than rewrite it.**
> `LatestRunPanel` reads the NATS-projected nested `steps[]` and works today for accounts where NATS is on. It is surgical to leave it: it still renders a quick (truncated) summary from `steps`. The new `RunTraceViewer` is the full-fidelity surface keyed on `step_links`. When `step_links` is populated (the doc-08 path, NATS on or off), the viewer is authoritative; `LatestRunPanel` becomes the lightweight glance. Rewriting `LatestRunPanel` to fetch per-step docs would couple the "latest post" glance to N extra requests for no gain. (A later cleanup can retire `LatestRunPanel` once `RunTraceViewer` is proven; flagged, not done here — CLAUDE.md surgical.)

### 5.4 Step-id matching stays intact

The chain rows key on the **dotted `step_id`** from `step_links` — the same strings the graph (§4.3) and the live SSE progress (`pipelineProgress.ts`) use. So a node clicked in the live diagram and a row clicked in the trace viewer resolve to the same `StepOutputDocument` via `fetchStepOutput(runId, stepId)`. The doc-08 doc id `stepoutputs/{run_id}/{step_id}` closes the loop: graph node id == progress step_id == step_link.step_id == path param == doc id suffix. This is the "keep step-id matching intact" constraint, enforced by the §8 test that `flowStepIds(baselineSpec)` equals the backend's flatten output.

---

## 6. The builder page — `AgentBuilderPage.tsx` (NEW)

### 6.1 File-by-file

| Kind | File | Role (one line) |
|---|---|---|
| **NEW** | `frontend/src/features/builder/AgentBuilderPage.tsx` | Two-pane page: left = chat (SSE), right = the spec graph (`PipelineFlowDiagram` fed by the current/proposed spec) + validation report. |
| **NEW** | `frontend/src/hooks/useBuilderChat.ts` | Mirrors `usePipelineRunStream.ts` structure: holds `messages`, `running`, `error`, `proposal`; `send(text)` and `approve()` call `streamBuilderChat`, consuming doc 10's `assistant_message`/`validation_errors`/`spec_preview`/`spec_written`/`error`/`done` events. |
| **NEW** | `frontend/src/hooks/queries/useAccountSpec.ts` | `useAccountSpec(accountId)` → `fetchAccountSpec`; used by the graph and the builder. |
| **CHANGED** | `frontend/src/app/routes.tsx` | Add child route `{ path: 'builder', element: <AgentBuilderPage /> }` under `accounts/:accountId`. |
| **CHANGED** | `frontend/src/navigation/navItems.ts` | Add `{ segment: 'builder', label: 'Builder' }` to the `ACCOUNT_SUB_NAV` array (`navItems.ts:9-16`) — the sidebar sub-nav renders every entry automatically, no `Sidebar.tsx` edit required. |
| **CHANGED (small)** | `frontend/src/features/account/AccountLayout.tsx` | Add `'builder'` to the `AccountSection` union (`AccountLayout.tsx:24-31`), a `pathname.endsWith('/builder') → 'builder'` branch in `resolveAccountSection` (`:44-46` mirrors the `'pipeline'` branch), and a `case 'builder':` in `sectionHeader` (`:78-82` mirrors the `'pipeline'` case) with title "Agent Builder". ~6 lines total. |

### 6.2 `useBuilderChat` — reuse the SSE hook shape (driving doc 10's event union)

Structurally a clone of `usePipelineRunStream.ts:21-122`: `AbortController` in a ref, `running`/`error` state, a `finalize` guard, cleanup on unmount. Because doc 10's server is **stateless** (it re-reads the whole message history each turn — doc 10 §5.3/§6.1), the hook **owns the `messages` array and posts it every call** as the `BuilderChatRequest.messages`. Differences from the force-post hook:

- It keeps `messages: BuilderChatMessage[]` (the same shape it posts back — user turns are plain text; an assistant turn that proposed a spec carries `proposed_spec`/`validation_errors` so the next turn/approve can reference it without a server session, doc 10 §6.1).
- `send(text)` pushes a `{role:'user', text}` turn, then calls `streamBuilderChat(apiBase, { account_id, mode, messages, approve:false }, onEvent)`.
- The `onEvent` switch maps doc 10's union: `assistant_message` → append a `{role:'assistant', text}` turn; `validation_errors` → store `{errors}` and stamp them onto the in-flight assistant turn's `validation_errors`; `spec_preview` → store `proposal = {spec, mermaid, catalog_hash, soul_edit}` and stamp `proposed_spec` onto the assistant turn; `spec_written` → store the written result + clear `proposal`; `error` → set `error`; `done` → finalize the turn (clear `running`).
- `approve()` re-calls `streamBuilderChat` with the SAME `messages` and `approve:true` (no new user turn); doc 10's approve path re-validates and writes `messages[-1].proposed_spec`.

```typescript
import type { BuilderChatMessage } from '../types/domain/builder';
import type { PipelineSpec } from '../types/domain/pipelineSpec';
type BuilderProposal = { spec: PipelineSpec; mermaid: string; catalog_hash: string;
                         soul_edit?: Record<string, unknown> | null };
type BuilderWritten = { spec_doc_id: string; status: 'champion' | 'challenger';
                        version_label: string; soul_bumped: boolean };
// useBuilderChat({ apiBase, accountId, mode })
//   -> { messages, running, error, proposal, written, send, approve }
//   proposal: BuilderProposal | null   (from the latest spec_preview)
//   written:  BuilderWritten  | null   (from spec_written, after approve)
// `mode` is 'create' | 'edit' (default 'edit'); it is passed straight into BuilderChatRequest.
```

### 6.3 Page layout

- **Left pane (chat):** message list (`messages: BuilderChatMessage[]`), a textarea + Send button (both disabled while `running`). Reuses existing panel/button classes (`hq-panel`, `force-post-section__btn` — used in `PipelineRunPanel.tsx:49`).
- **Right pane (graph + validation):** `PipelineFlowDiagram` fed `sections={flowFromSpec(proposal?.spec ?? currentSpec)}` with `nodeState` all-`pending` (this is a *shape* preview, not a live run — every node renders neutral). Below it, the validation surface, driven by doc 10's events:
  - a `spec_preview` event (doc 10 emits it **only when `validate_spec` passed**) → a green "Valid — ready to write" line + an **"Approve & write"** button enabled. (Doc 10 only previews valid specs, so a visible preview already implies validity.)
  - a `validation_errors` event → the error list rendered from `errors[]` (`code` + `detail`, highlighting the node whose dotted id == `step_id`), and the write button stays disabled until the next passing turn.
- The **"Approve & write"** button calls the hook's `approve()` — which re-POSTs `/agent-builder/chat` with `approve:true` (doc 10 §7.3). **There is no separate stage/promote endpoint:** doc 10's approve path itself re-validates and writes the spec (champion for `mode:'create'`, challenger for `mode:'edit'`), emitting `spec_written`. The page shows the `spec_written` result (`status`, `version_label`, `soul_bumped`) on success.

> **Decision Defense — builder proposes; operator approves; doc 10 writes a challenger, not a live swap.**
> Settled architecture: "default to manual-promote with auto-rollback on hard regression" (doc 04 §6c). The builder UI never silently activates a spec — it shows the proposed graph + validation, and the explicit "Approve & write" click stages a **challenger** (doc 10 §7.3 writes `status:'challenger'` for `mode:'edit'`; promotion to champion is a separate later operator action via `promote_challenger`, doc 04 §6c — out of scope for this page). Doc 10 re-validates server-side on approve before the single `put_document`, so the non-bypassable invariants (cost ceiling, guardian) and the validator gate (doc 05) are strictly upstream of any write. The UI cannot bypass them: the only write path is doc 10's endpoint, which re-validates.

---

## 7. What this doc does NOT own (honest boundaries)

- **The builder backend — OWNED by doc 10**, not this doc and not "unowned". Doc 10 ships the Claude loop, the `POST /api/agent-builder/chat` SSE route, and the approve-writes-a-challenger path (doc 10 §7). This doc consumes doc 10's request body + event union (§3.3, §6) **verbatim**; it does not re-specify them. If doc 10 changes an event field, the single adapter point on this side is `types/domain/builder.ts` + `parseSse` in `builderChat.ts`. **There is no separate stage/promote endpoint for the builder UI** — approval rides the same `/agent-builder/chat` route with `approve:true`.
- **The pipeline read routes — OWNED by doc 14 (`14-backend-read-routes.md`), per CC-11** (`GET /api/accounts/{id}/pipeline/spec[?status]`, `POST /api/accounts/{id}/pipeline/spec/validate`, `GET /api/pipeline/runs/{run_id}`, `GET /api/pipeline/runs/{run_id}/steps/{step_id}`). They are thin reads over methods docs 04/05/08 already ship (`PipelineSpecRepository.load_or_default` + `validate_spec` + `get_tool_catalog()`; `StepOutputRepository.get`), and doc 14 is **already in the plan and sequenced before this doc** (overview §4: `… → 08 → 14 → 09 → 10 → 11`). Contract mirrored read-only in §3.1/§3.2; this doc does not register them. (`GET /api/pipeline/runs/{run_id}` already exists today — `fetchPipelineRun`, `api/endpoints/pipelineRuns.ts:18-20` — so only the spec/validate and per-step-output routes are new doc-14 work.) Until doc 14 lands, the graph still renders from the spec route and the trace viewer degrades gracefully (§9); the §9 trace/builder DoD can only be fully verified once doc 14's routes exist.
- **Backend spec/trace models.** Owned by docs 04 (spec), 05 (validator), 06 (ACT artifacts), 08 (step output), 10 (builder request/event types). This doc only mirrors their JSON.

---

## 8. Tests (frontend)

| File (NEW) | Asserts |
|---|---|
| `frontend/src/lib/pipeline/specToFlow.test.ts` | `flowStepIds(baselineSpec)` equals the exact 10-id list in §4.3 (the dotted-id lock — frontend mirror of doc 05 §8). `flowFromSpec(baselineSpec)` yields one `parallel` row (`summarize_for_compose`) with two branches and the two top-level ACT leaves. |
| `frontend/src/features/pipeline/RunTraceViewer.test.tsx` | Given a `PipelineRun` with `step_links`, renders rows in `seq` order; given one with empty `step_links` and non-empty `steps`, falls back to nested order. Clicking a row fetches `fetchStepOutput` once (mocked) and shows the full `value`. |
| `frontend/src/features/builder/AgentBuilderPage.test.tsx` | A mocked `streamBuilderChat` emitting doc 10's `assistant_message` → `spec_preview` → `done` renders the assistant text + the proposed graph and enables "Approve & write"; a run emitting `assistant_message` → `validation_errors` → `done` renders the error list and leaves the button disabled; clicking "Approve & write" re-invokes the mock with `approve:true` and an `spec_written` event shows the written status/label. |

`baselineSpec` is a small fixture mirroring doc 04 `default_pipeline_spec` — the **10-leaf** SENSE+ACT tree (8 SENSE `StepSpec`/`CompositeSpec` nodes + the top-level `compose_until_safe` and `publish_post` leaves doc 04 §7 appends). The §4.3 list is the single graded property tying the frontend to the backend's `flatten_steps`; the fixture must match doc 04's seed 1:1 so the lock test grades the real baseline, not a frontend-only invention.

---

## 9. Definition of Done (per slice)

**Types slice (§2)**
- `npm run build` clean with the four new/changed type files; `PipelineRun.step_links?` added, `steps` untouched.

**Graph slice (§4)**
- `flowFromSpec`/`flowStepIds` are pure (no React import); the §8 dotted-id lock test passes (10 ids, ACT leaves included).
- `PipelineFlowDiagram` takes `sections` as a prop; the live `PipelineRunPanel` renders nodes that light up from SSE progress exactly as before (the dotted ids are identical), now derived from the spec — verified by force-posting `JohnJames_News` and watching every node transition.
- Editing the spec (or doc 06 adding ACT leaves) requires **no edit** to `flowGraph.ts` node lists; the only retained constant is the 3 `orchestrator-pre` lock stages.

**Trace slice (§5)**
- `RunTraceViewer` renders the latest run's chain from `step_links` (fallback `steps`); clicking a step lazily fetches its `StepOutputDocument` and shows COMPLETE inputs/outputs/`result_payload` with **no truncation marker**. The caller unwraps `useLatestPipelineRun(...).data?.runs?.[0]` before passing `run` (§5.1/§5.2).
- With NATS OFF (doc 08 §10 acceptance), the viewer still shows the full chain (because `step_links` is durable) — manual check: stop NATS, force-post, open the trace, confirm a `timeline_references` artifact > 8000 chars renders whole.
- **Sequencing-aware expectation (not a bug):** verified between doc 08 and doc 06/07 (doc 13 sequences 08 *before* 06/07), `step_links` carries **only the 8 SENSE steps** — compose/safety/publish are still imperative orchestrator code in that window (doc 08 §8) and are legitimately absent. The viewer renders an 8-row chain then; after 06/07 land it becomes 10 rows automatically (the ACT leaves flow through the same trace hook). Do **not** flag the missing ACT rows during the 08-only window.
- Step-id matching intact: the node id clicked in the diagram and the row clicked in the viewer resolve to the same `StepOutputDocument`.

**Builder slice (§6)**
- `AgentBuilderPage` reachable at `/accounts/:accountId/builder` (route + sub-nav `navItems.ts` entry + layout section/title added); the chat streams via `streamBuilderChat` against doc 10's `POST /api/agent-builder/chat` (reusing the force-post SSE parse loop), posting the full `BuilderChatRequest` history each turn.
- A `spec_preview` event renders the proposed graph + a "Valid — ready to write" line and enables "Approve & write"; a `validation_errors` event renders the error list and disables the button; clicking "Approve & write" re-POSTs with `approve:true` and a `spec_written` event shows the persisted `status`/`version_label`.
- The builder never activates a spec directly — approve writes a **challenger** (doc 10 §7.3, manual-promote invariant), and there is no separate stage/promote call. The only new dep introduced is optional `mermaid` (lazy-imported) — droppable.

**Global**
- `npm run build` clean (no new TS errors); existing `PipelineRunPanel`/`LatestRunPanel`/force-post flows unchanged in behavior.
- No build-time codegen, no build-time mermaid; any mermaid use is a runtime dynamic import (§4.4).
- Cross-slice dependencies are explicit: the builder SSE is **doc 10's** route (§3.3), and the pipeline read routes (§3.1/§3.2) are **doc 14's** slice (CC-11), sequenced before this doc (§7). The frontend degrades gracefully — the graph never 404s (`load_or_default` always returns a baseline), the trace viewer shows an empty/error state if the step-output route is absent, and the builder page shows an error toast if `/api/agent-builder/chat` is not yet registered.
