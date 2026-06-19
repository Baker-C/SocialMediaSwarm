# 08 — Frontend: Persona Page (chat → review → live status)

**Touches:** `frontend/src/features/account-provisioning/*` (new), `frontend/src/api/endpoints/personaChat.ts`
+ `provisioning.ts` (new), `frontend/src/hooks/usePersonaChat.ts` (new), `frontend/src/types/domain/persona.ts`
(new), `frontend/src/app/routes.tsx`, `frontend/src/navigation/navItems.ts`

A one-page, three-stage feature. The chat + stream plumbing is a **direct copy of the agent-builder
frontend** (`features/builder/AgentBuilderPage.tsx`, `hooks/useBuilderChat.ts`,
`api/endpoints/builderChat.ts`, `types/domain/builder.ts`). Copy those, rename, adjust event types.

## 1. Conventions to honor (from the codebase)
- **No `useMutation` anywhere** — call the endpoint async fn directly, then
  `queryClient.invalidateQueries(...)`. Don't introduce React Query mutations.
- **SSE is `fetch` + `ReadableStream` reader + manual `\n\n` parsing**, NOT `EventSource` (EventSource
  can't send the bearer header) — copy `builderChat.ts:36-54`.
- **Auth/base URL** via `apiFetch`/`authHeaders` (`api/client.ts`, `api/auth.ts`); stream calls add
  `Accept: text/event-stream` + `authHeaders()` manually.
- **Reuse `ui/` components:** `Button`, `Card*`, `Badge` (status pills), `Input`. There is **no
  `Textarea`** — add `ui/textarea.tsx` (small, same `cn()` + token styling) for the chat box and bio.
- Use `layout/ErrorBanner` for errors, `EmptyState` for the pre-chat state.

## 2. Types — `types/domain/persona.ts`

Mirror the backend emit helpers 1:1 (discriminated union on `type`):

```ts
export interface PersonaSpec {
  handle: string; display_name: string; bio: string;
  category: string; personality: string; posting_prompt: string;
  avatar_prompt: string; header_prompt: string;
}
export type PersonaStreamEvent =
  | { type: 'assistant_message'; text: string }
  | { type: 'persona_preview'; spec: PersonaSpec }
  | { type: 'images_generating' }
  | { type: 'images_ready'; avatar_asset_id: string; header_asset_id: string }
  | { type: 'account_written'; account_id: string }
  | { type: 'validation_errors'; errors: string[] }
  | { type: 'error'; message: string }
  | { type: 'done' };

export type ProvisioningStatusEvent =
  | { type: 'status'; status: string; current_page: string; step_log: string[]; error_message?: string }
  | { type: 'done' } | { type: 'error'; message: string };
```

## 3. Endpoints — `api/endpoints/personaChat.ts` + `provisioning.ts`

- `streamPersonaChat({ accountId, messages, proposal, approve }, onEvent, signal)` — copy
  `streamBuilderChat`; POST `/api/persona/chat` with `Accept: text/event-stream`.
- `regenerateImages(avatarPrompt, headerPrompt)` — `apiFetch` POST `/api/persona/regenerate-images`.
- `startProvisioning(accountId)` — POST `/api/provisioning/{id}/start`.
- `streamProvisioningStatus(accountId, onEvent, signal)` — GET SSE `/api/provisioning/{id}/status`.
- `sendControl(accountId, action)` — POST `/api/provisioning/{id}/control`.
- `mediaUrl(assetId)` — helper returning the media bytes route for `<img src>`.

## 4. Hook — `usePersonaChat.ts`

Copy `useBuilderChat` verbatim, then adapt the `switch (event.type)` reducer to the persona events.
State: `messages`, `running`, `error`, `proposal: PersonaSpec | null`, `images`, `written`. Methods:
`send(text)` (append user msg, stream with `approve:false`), `approve()` (re-stream same history with
`approve:true`), `editSpec(patch)` (local edit of `proposal`), `regenerate()`. Keep the `abortRef` +
`messagesRef`/`proposalRef` pattern and the unmount-abort `useEffect`.

A second small hook `useProvisioningStatus(accountId)` drives the live-status stage (start the stream
on mount-of-stage, expose `status`, `stepLog`, `awaitingCaptcha`, `continue()`, `cancel()`).

## 5. Page — `features/account-provisioning/AccountProvisioningPage.tsx`

Three stages in one page (state machine: `chat → review → provisioning`):

- **Chat stage:** two-pane (left chat transcript + `Textarea` + Send; right = live `persona_preview`
  card once a spec arrives). Modeled on `AgentBuilderPage` two-pane layout but use `ui/*` components.
- **Review stage:** editable form bound to `proposal` (handle, display_name, bio, category,
  personality, posting_prompt) + the two generated images (`<img src={mediaUrl(...)}>`) with a
  **Regenerate images** button and prompt fields. **Approve** calls `approve()` → on `account_written`
  advance to provisioning.
- **Provisioning stage:** `useProvisioningStatus`. Render a status checklist from `step_log` + a
  `Badge` for `status`. When `awaitingCaptcha`: prominent panel — *"Solve the CAPTCHA in the Chrome
  window, then click Continue"* + a **Continue** button (`continue()`), plus **Cancel**. On
  `status==="complete"`: success panel linking to the account dashboard + the existing OAuth-connect.

> The operator watches the **real Chrome window** (Option A) — the page shows status + the Continue
> control, not a screenshot/embedded browser. Keep that explicit in the UI copy.

## 6. Routing + nav
- `routes.tsx`: add under the `accounts/:accountId` children **and** a top-level "new account" entry.
  A standalone create flow (no existing account yet) fits a top-level route, e.g.
  `{ path: 'provision', element: <AccountProvisioningPage /> }`, since `account_id` is operator-chosen
  in the chat. (Account-scoped re-provisioning can also mount under `accounts/:accountId/provision`.)
- `navigation/navItems.ts`: add a "New Account" item; `Sidebar` renders it automatically.
- `app/AppLayout.tsx` `pageTitle()`: add a title branch (optional, matches convention).
- Add a "Provision New Account" button on the Fleet overview that routes to `/provision`.

## 7. Tests (`*.test.tsx`, Jest + RTL)
Copy `AgentBuilderPage.test.tsx` conventions: `jest.mock('../../api/endpoints/personaChat')`, cast to
`as jest.Mock`, `mockResolvedValue`/drive `onEvent`, render inside `QueryClientProvider` +
`BrowserRouter`, assert with `waitFor`.
- Chat: sending a message renders the assistant reply and, on `persona_preview`, shows the spec.
- Review: editing a field updates local state; Approve triggers the stream with `approve:true`.
- Provisioning: an `awaitingCaptcha` status renders the Continue button; clicking calls `sendControl`.
- Pure reducer logic (event → state) extracted and unit-tested like `flowReducer.test.ts`.

## Done when
- `/provision` runs chat → review (editable + regenerate images) → live status with the CAPTCHA
  Continue control, all against the backend with the agent stubbed.
- `npm run build` clean; Jest tests pass; only `ui/*` components used (plus the new `Textarea`).
