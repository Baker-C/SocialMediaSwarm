# Task 08 — Frontend (Voice tab displays the full Soul)

## Task Overview

**Files:**
- `frontend/src/types/domain/account.ts` — extend `AccountVoiceDetail`; add `ContrastPattern`/`PunctuationRule` TS types.
- `frontend/src/types/domain/pipeline.ts` — update `VoiceRevision` to soul fields.
- `frontend/src/features/voice/VoiceExperimentsPage.tsx` — render the soul; remove the global-rules section.
- **Delete** `frontend/src/hooks/queries/useVoicePolishRules.ts` (its endpoint is removed in Task 06).
- `frontend/src/hooks/queries/useAccountVoice.ts` — unchanged (already fetches `/edit`); we just consume it.
- **`frontend/src/components/UpdateAccountModal.tsx` — the actual edit UI (post-review correction; the first draft wrongly assumed a "settings form").** Must be repointed at `posting_prompt`, or the existing prompt-edit silently breaks.

**What it affects:** the Voice tab at route `/accounts/:accountId/voice` (`app/routes.tsx` → `VoiceExperimentsPage`). Read-only display. Editing remains on the Settings form.

**Important correctness note:** Today `CurrentVoiceSection` reads `account.system_prompt`/`personality`/`negative_semantics` from `useAccount` — but `useAccount` hits `GET /accounts/{id}` (the **summary** shape), which does **not** contain those fields. So the current "Current voice" panel renders "No voice configuration set." The fix: source it from `useAccountVoice` (the `/edit` payload), which Task 03 extends with the full soul.

**Dependencies:** Task 03 (the `/edit` payload now returns soul fields), Task 06 (removes `/voice-polish-rules`).

---

## Proposed Solution

### a. Types

**`types/domain/account.ts` — AFTER**
```typescript
export type ContrastPattern = {
  text: string;
  correlation: 'positive' | 'negative';
};

export type PunctuationRule = {
  pattern: string;
  replacement: string | null;
};

// /edit payload — now the single source of truth for the Voice tab.
export type AccountVoiceDetail = {
  account_id: string;
  // soul
  posting_prompt: string;                 // was system_prompt
  personality?: string;
  contrast_patterns?: ContrastPattern[];  // was negative_semantics
  punctuation_rules?: PunctuationRule[];  // NEW
  // version stamp (now returned by account_edit_view, Task 03)
  voice_version_label?: string | null;
  voice_version_seq?: number | null;
  voice_version_hash?: string | null;
};
```
> **`AccountEditPayload.system_prompt` MUST be renamed to `posting_prompt` (corrected — not optional).** This type backs `UpdateAccountModal.tsx`, the real edit form. Task 03 renamed the `/edit` response and the PATCH body, and `AccountUpdateBody` uses `extra="ignore"` — so if the modal keeps sending `system_prompt`, the edit is **silently discarded** (no error, looks saved, isn't), and the field loads blank because `/edit` no longer returns `system_prompt`. Rename the type field and the modal binding together (see §c.2). The first draft listed this as "optional / flagged in Decision Defense"; it is a hard requirement.

**`types/domain/pipeline.ts` — AFTER**
```typescript
export type VoiceRevision = {
  account_id: string;
  seq: number;
  label: string;
  version_hash: string;
  changed_at: string;
  // soul snapshot (Task 02)
  personality?: string;
  posting_prompt?: string;
  contrast_patterns?: { text: string; correlation: 'positive' | 'negative' }[];
  punctuation_rules?: { pattern: string; replacement: string | null }[];
  // legacy (older revisions) — kept optional for graceful display
  system_prompt?: string;
  negative_semantics?: string[];
};
```

### b. `VoiceExperimentsPage.tsx`

#### BEFORE — relevant pieces (current on-disk)
- `import { useVoicePolishRules } from '../../hooks/queries/useVoicePolishRules';`
- `VoicePromptSource` keyed on `system_prompt | personality | negative_semantics`
- `VoicePromptDetail` renders System prompt / Personality / Negative semantics
- `CurrentVoiceSection({ account, revision })` reads `account.system_prompt/personality/negative_semantics` (from `useAccount` — wrong source)
- `VoicePolishRulesSection()` fetches global rules via `useVoicePolishRules`
- Page renders `<CurrentVoiceSection account={accountQuery.data} …/>` then `<VoicePolishRulesSection />`

#### AFTER — targeted changes (with inline rationale)

```tsx
// 1) Imports: drop useVoicePolishRules; add useAccountVoice + soul types.
import { useAccountVoice } from '../../hooks/queries/useAccountVoice';
import type { AccountVoiceDetail, ContrastPattern, PunctuationRule } from '../../types';
import type { VoiceRevision } from '../../types';
// (remove the useVoicePolishRules import entirely)

// 2) A soul source can be either the live /edit payload or an archived revision.
type SoulSource = {
  personality?: string;
  posting_prompt?: string;
  contrast_patterns?: ContrastPattern[];
  punctuation_rules?: PunctuationRule[];
  // legacy fallbacks for old revisions:
  system_prompt?: string;
  negative_semantics?: string[];
};

function hasStoredSoul(s: SoulSource | null | undefined): boolean {
  if (!s) return false;
  return Boolean(
    s.personality?.trim() ||
    s.posting_prompt?.trim() || s.system_prompt?.trim() ||
    (s.contrast_patterns && s.contrast_patterns.length) ||
    (s.punctuation_rules && s.punctuation_rules.length) ||
    (s.negative_semantics && s.negative_semantics.length)
  );
}

// 3) Reusable soul renderer (replaces VoicePromptDetail). Handles legacy fallbacks
//    so old revisions still display.
function SoulDetail({ soul }: { soul: SoulSource }) {
  const posting = soul.posting_prompt?.trim() || soul.system_prompt?.trim() || '';
  const contrast: ContrastPattern[] =
    soul.contrast_patterns ??
    (soul.negative_semantics ?? []).map((t) => ({ text: t, correlation: 'negative' as const }));
  const punctuation = soul.punctuation_rules ?? [];

  return (
    <>
      {soul.personality?.trim() && (
        <div className="voice-expand__block">
          <span className="voice-expand__label">Personality</span>
          <p className="voice-expand__text" style={{ whiteSpace: 'pre-wrap' }}>{soul.personality}</p>
        </div>
      )}
      <div className="voice-expand__block">
        <span className="voice-expand__label">Posting prompt</span>
        <p className="voice-expand__text" style={{ whiteSpace: 'pre-wrap' }}>{posting || '—'}</p>
      </div>
      {contrast.length > 0 && (
        <div className="voice-expand__block">
          <span className="voice-expand__label">Contrast patterns</span>
          <ul className="voice-expand__list">
            {contrast.map((p) => (
              <li key={p.text}>
                <span className={p.correlation === 'negative' ? 'text-red-400' : 'text-green-400'}>
                  [{p.correlation}]
                </span>{' '}
                {p.text}
              </li>
            ))}
          </ul>
        </div>
      )}
      {punctuation.length > 0 && (
        <div className="voice-expand__block">
          <span className="voice-expand__label">Punctuation rules</span>
          <ul className="voice-expand__list">
            {punctuation.map((r) => (
              <li key={r.pattern} className="font-mono text-xs">
                {r.pattern}{r.replacement != null ? ` → ${r.replacement}` : ' → (remove)'}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

// 4) Current Soul section — now fed by the /edit payload (useAccountVoice), not the summary.
function CurrentSoulSection({
  voice,
  isLoading,
}: {
  voice: AccountVoiceDetail | undefined;
  isLoading: boolean;
}) {
  return (
    <section className="hq-panel" aria-label="Current soul">
      <div className="hq-panel__header">
        <h3 className="hq-panel__title">Current soul</h3>
        <div className="flex gap-2">
          <span className="text-xs px-2 py-1 bg-orange-900/30 text-orange-400 rounded">
            {voice?.voice_version_label || 'v1'}
          </span>
          {voice?.voice_version_seq != null && (
            <span className="text-xs px-2 py-1 bg-gray-800 text-gray-400 rounded">seq #{voice.voice_version_seq}</span>
          )}
          {voice?.voice_version_hash && (
            <span className="text-xs px-2 py-1 bg-gray-800 text-gray-400 rounded font-mono cursor-help"
                  title={voice.voice_version_hash}>
              {voice.voice_version_hash.slice(0, 12)}…
            </span>
          )}
        </div>
      </div>

      {isLoading ? (
        <p className="App-loading">Loading soul…</p>
      ) : hasStoredSoul(voice) ? (
        <div className="space-y-6"><SoulDetail soul={voice as SoulSource} /></div>
      ) : (
        <p className="page-hint">No soul configuration set.</p>
      )}
    </section>
  );
}

// 5) In VoiceExperimentsPage():
//    - add: const voiceQuery = useAccountVoice(accountId);
//    - replace <CurrentVoiceSection .../> with:
//        <CurrentSoulSection voice={voiceQuery.data} isLoading={voiceQuery.isLoading} />
//    - DELETE the <VoicePolishRulesSection /> usage and the function itself.
//    - revision timeline + comparison expansion: swap VoicePromptDetail → SoulDetail,
//      hasStoredVoiceText → hasStoredSoul (revisions are a SoulSource too).
```

### c. Delete `useVoicePolishRules.ts`
Remove the file and any remaining import. Its backend endpoint no longer exists (Task 06).

### c.2 `UpdateAccountModal.tsx` — repoint the edit form at the soul (post-review correction)

This is the form reached from the account **Settings** page (`AccountSettingsPage` renders an `AccountCard` whose Update button calls `openUpdateModal`). It is the only working PATCH surface for voice. Today it loads `data.system_prompt` and PATCHes `{ system_prompt }` — both broken by Task 03's rename.

```tsx
// load (in the /edit fetch handler): read posting_prompt, fall back to legacy system_prompt
setSystemPrompt(data.posting_prompt ?? data.system_prompt ?? '');   // rename the state var to postingPrompt if you prefer

// NEW (cheap win): personality is a flat string in the payload — give it a textarea
setPersonality(data.personality ?? '');

// submit body
const body = {
  niche,
  twitter_handle: twitterHandle,
  status,
  posting_prompt: systemPrompt,   // was: system_prompt: systemPrompt
  personality,                    // NEW
  followers,
  posts_total: postsTotal,
};
```

**Scope decision (matches `00-overview.md §3` "deferred"):**
- **In scope now:** `posting_prompt` rename (prevents the silent-break) + a `personality` textarea (one field, high value, trivial).
- **Deferred:** `contrast_patterns` and `punctuation_rules` editors need array/regex UI (add/remove rows, correlation toggle, regex tester). That bespoke editor stays future work. Until then those two fields are editable only via `PATCH /accounts/{id}` (curl), which is exactly what Task 09(d) exercises — so end-to-end coverage does not depend on the missing UI.

### d. Written explanation
The Voice tab becomes an honest mirror of the per-account soul. `CurrentSoulSection` now pulls from `/edit` (`useAccountVoice`) — fixing the latent bug where it read soul fields off the summary endpoint that never contained them. `SoulDetail` is a single renderer reused by the current panel, the revision timeline, and the comparison-table expansion, and it degrades gracefully for legacy revisions (mapping `negative_semantics → [negative] contrast`, `system_prompt → posting_prompt`).

> **This fallback only works because of the Task 02 correction.** The backend `VoiceRevisionDocument` must (a) keep `system_prompt`/`negative_semantics` as read-only passthrough fields and (b) default the new lists to **empty**, not to the default factories. Otherwise Pydantic's `extra="ignore"` strips the legacy keys before they reach the client (fallback never fires) and old rows render the *current* default contrast set (fabricated history). Keep the optional `system_prompt?`/`negative_semantics?` on the `VoiceRevision` TS type so these legacy rows type-check. Removing `VoicePolishRulesSection`/`useVoicePolishRules` deletes the now-defunct global-rules surface.

---

## Decision Defense

**Why source the current panel from `useAccountVoice` (`/edit`) instead of `useAccount` (summary)?**
The soul lives in the `/edit` payload (Task 03). The summary endpoint intentionally stays lightweight (counts, labels) for list views. Using the correct endpoint fixes the existing "No voice configuration set" bug and avoids bloating the summary.

**Why one `SoulDetail` component for three call sites?**
DRY + consistency: current soul, timeline entry, and comparison-row expansion should look identical and evolve together. A single component with legacy fallbacks means old and new revisions render through the same path.

**Why color-code contrast correlation (red/green) but render punctuation monospace?**
Correlation is the one piece of contrast metadata that changes meaning (avoid vs lean) — color makes it scannable. Punctuation rules are regex; monospace signals "this is a pattern, not prose" and aids quick scanning of `pattern → replacement`.

**Why keep editing on the Settings form rather than adding inline edit here?**
Scope. The PATCH contract (Task 03) already supports full soul edits via the Settings form. A bespoke soul editor (regex tester, drag-reorder, add/remove patterns) is valuable but separable future work.

---

## UI interaction — how to access and evaluate (previous vs new)

**Role/permissions:** This dashboard has no per-user RBAC; any operator with access to the dashboard (default `http://localhost:3000`) can view all tabs. No elevated role required.

**Reach the Voice tab (new behavior):**
1. Open `http://localhost:3000`. The **Fleet Overview** loads (list of account cards).
2. Click the account card titled **`JohnJames_News`** (top-left card; only one exists).
3. In the account's left/top tab strip, click **`Voice`** (between `Posts` and `References`/`Settings` depending on layout).
4. Route is now `/accounts/JohnJames_News/voice`.

**Evaluate the NEW components, top to bottom:**
- Top-right of the page: the **`Current: v1`** badge (a link to Settings). Click target is the pill in the page toolbar, right-aligned.
- First panel **"Current soul"** (top of page, full width): shows version chips (label/seq/hash) on the panel header's right; body shows **Personality** (prose), **Posting prompt** (prose), **Contrast patterns** (each line prefixed with a red `[negative]` or green `[positive]` tag), **Punctuation rules** (monospace `pattern → replacement`).
- The previously-present **"Voice polish rules (auto-applied)"** panel is **gone** (it sat directly beneath Current voice).
- **"Revision timeline"** panel (below): each `#seq · label · date` row has a **"Voice prompt"** disclosure (`<summary>`); click it to expand the same `SoulDetail` view for that archived version.
- **"Performance by voice version"** table (below): click any row's expander (leftmost cell chevron) to expand `SoulDetail` for that version alongside its ER/impressions.
- **Correlation scatter** at the bottom (unchanged).

**Compare to PREVIOUS behavior:** before this change, "Current voice" showed **"No voice configuration set"** (wrong data source) and a global **"Voice polish rules"** panel listed ~78 phrases fetched from `/voice-polish-rules`. After: "Current soul" is populated from the account's `/edit` payload, and the global rules panel is removed.

**Verification clicks after an edit (ties to Task 03) — corrected for the real edit surface:**
1. Click the top-right **`Current: v1`** badge → **Settings** page → click **Update** to open `UpdateAccountModal`.
2. Edit **Posting prompt** or **Personality** in the modal; Save. (Contrast/punctuation have no UI yet — edit those with the `PATCH /accounts/{id}` call from Task 09(d).)
3. Return to **Voice** tab → the version chip reads **`v2`**, and a new **`#2`** row appears at the top of the Revision timeline whose **"Voice prompt"** disclosure shows the edited soul.

> If you skip the modal fix in §c.2, step 2 *appears* to succeed but the posting prompt is silently dropped server-side and the version does not bump — the regression this correction exists to prevent.
