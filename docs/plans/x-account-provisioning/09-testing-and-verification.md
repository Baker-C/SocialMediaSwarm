# 09 — Testing, Spike & Verification

## 1. The spike (do this BEFORE writing the agent — `06`)

The agent's page-state machine must be built against X's *real* DOM, not a guess. Manually walk one
account through end-to-end, capturing reality:

1. Real Chrome, a fresh profile. Go to X signup.
2. Use an **owned-domain** email (`07`) and walk to email verification — confirm the address is
   accepted and the code arrives in your mailbox read path.
3. When/if a phone wall appears, buy **one** SIM-based number (`07`) and confirm X accepts it and the
   SMS arrives. (If email-only succeeds, note that phone is conditional.)
4. Observe the **FunCaptcha**: when it triggers, what the challenge is, that solving it in the window
   lets the flow continue.
5. Continue into the **developer console**: app creation, developer agreement, **pay-per-use billing**
   (does it demand a card immediately?), and the **API key/secret/bearer** capture screen.
6. For each page, record: a stable **selector** for the key field(s)/button, and a **detection signal**
   (selector or visible text) unique to that page. These populate `selectors.py` + `SIGNALS`.

**Output of the spike:** a filled `selectors.py`, the confirmed page sequence, which steps are
conditional, and go/no-go on the email + phone providers. Only then implement `06`.

> The spike answers the questions that decide the agent's shape. Treat a failed spike step (e.g. email
> domain blocked, phone rejected) as a provider change, not a code bug.

## 2. Per-layer automated tests (all sync; `unittest.mock` + `monkeypatch`; inject fakes)

| Layer | File | What |
|---|---|---|
| Model (`01`) | `test_account_provisioning_model.py` | defaults, legacy passthrough, round-trip, invalid status |
| Secrets (`02`) | `test_account_secrets_service.py` | encrypt/decrypt round-trip, partial upsert, missing-key error |
| Persona (`03`) | `test_persona_routes.py` | chat turn (fake Claude), approve (fake images/repo), dup-id |
| Images (`04`) | `test_persona_image_service.py` | two ids, sizes per call, FAL-disabled error (fake fal) |
| Routes (`05`) | `test_provisioning_routes.py`, `test_provisioning_service.py` | start/status/control/job/result, two auth domains, card on/off |
| Disposable (`07`) | `test_disposable_clients.py` | code parsing, polling, error mapping (`httpx.Client` patch) |
| Agent (`06`) | `provisioning-agent/tests/*` | page detector, each handler, orchestrator incl. CAPTCHA pause |
| Frontend (`08`) | `*.test.tsx` | chat render, review edit/approve, captcha-continue; reducer unit test |

**Mocking rules (from the codebase):** RavenDB never connected — inject a fake repo/client; HTTP
mocked by patching `httpx.Client` *as imported in the module under test* with real `httpx.Response`
fixtures; Claude/fal injected as fakes at the call site; routes via `TestClient` with auth
auto-bypassed by `tests/conftest.py:12`. No respx/responses, no async runner.

## 3. Backend-only end-to-end (no X, no agent)

With the agent **stubbed**, drive the full backend happy path with `TestClient` + injected fakes:
1. `POST /api/persona/chat` (approve) → account written, `AccountProvisioning(status="draft")`,
   two media assets.
2. `POST /api/provisioning/{id}/start` → status `in_progress`.
3. Simulate the agent: `GET …/job` (agent token) → `POST …/status` (awaiting_captcha) →
   `POST …/control {continue}` (frontend) → `GET …/control` returns then clears → `POST …/result`.
4. Assert `AccountSecrets` round-trips decrypted server-side; `provisioning.status == "complete"`;
   **no secret appears** in `GET /api/accounts/{id}/edit` or any public view (explicit assertion).

## 4. Agent dry-run (against the spike flow or a staging double)

`python -m agent.run` with a test `ACCOUNT_ID`: detects pages, fills/clicks, pauses on FunCaptcha,
resumes on Continue, uploads images, captures keys, posts result. Run sparingly (X rate limits);
prefer the fake-browser orchestrator test for routine CI.

## 5. Build / health gates
- `python -m py_compile` clean across touched backend files; `pytest` green.
- `npm run build` clean (no new TS errors); Jest green.
- `docker compose up -d --build` healthy (backend unaffected by the agent — Playwright is not a
  backend dep; confirm `requirements.txt` for the hosted backend is unchanged).
- `provisioning-agent` installs independently: `pip install -r requirements.txt && playwright install chromium`.

## 6. Global definition of done
Mirrors `00 §8`. Headline criteria:
- Chat → review (editable + regenerate) → approve writes account + provisioning draft + images.
- Backend brokers provisioning: start, SSE status, control; agent fetches job, pushes status, polls
  control, posts result; secrets stored encrypted, never exposed.
- Agent logic fully unit-tested behind `BrowserPort`; selectors centralized; spike captured.
- Card-from-`.env` used only on a real billing page; absent → free-tier path skips it.

## 7. Sequencing recap
`01 → 02 → 04 → 03 → 05 → 07 → 08 → 06 → 09`. The backend (01–05, 07–08) is fully testable without
beating X. The agent (06) is gated behind the spike (§1). Verification (§3–§5) runs continuously, not
just at the end.
