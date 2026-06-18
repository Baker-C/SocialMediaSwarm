# Autopilot — X Account Provisioning

Mission: implement the plan at `docs/plans/x-account-provisioning/` end-to-end.
Branch: `feat/x-account-provisioning`. Orchestrator delegates each unit to a subagent.

## Units (build order)

| # | Unit | Plan file | Status |
|---|---|---|---|
| 1 | Data model: `AccountProvisioning` sub-doc on `AccountDocument` | 01 | done (4 passed) |
| 2 | Secrets: `AccountSecrets` model + repo + service (Fernet) | 02 | done (4 passed) |
| 3 | Image service: `PersonaImageService` (fal/Seedream) | 04 | done (2 passed) |
| 4 | Persona chat: `persona` router + types (clone agent_builder) | 03 | done (6 passed) |
| 5 | Provisioning routes + service + config + main.py wiring | 05 | done (15 passed) |
| 6 | Disposable identity: email/phone clients + agent endpoints | 07 | done (13 passed) |
| 7 | Frontend: persona page, hooks, endpoints, types, routing | 08 | done (build clean, 8 Jest passed) |
| 8 | Local provisioning agent package (BrowserPort, handlers, orchestrator) | 06 | done (37 passed) |
| 9 | Integration tests + media route + verification + completion | 09 | done (e2e 1 passed; full suite 700 passed) |

## Finishing criteria

- [x] `python -m py_compile` clean across all touched backend files.
- [x] `pytest` green for new backend tests (model 4, secrets 4, image 2, persona 6, provisioning 15, disposable 13, e2e 1). Full suite: 700 passed, 1 skipped, 1 pre-existing-unrelated failure.
- [x] `npm run build` clean (no new TS errors) in frontend; new Jest tests pass (8).
- [x] `provisioning-agent` package: `pytest` green for agent unit tests (37, fakes-based, no Playwright).
- [x] No secret field reachable from any response/view (e2e test asserts `/edit` contains no secret strings).
- [x] Routers registered in `main.py` (persona, provisioning, provisioning agent, media); config + `.env.example` updated.
- [x] `BLOCKERS.md`: 2 external gaps (providers, selectors) with route-arounds + 2 deferred-with-reason (pre-existing test, env path).

**RUN COMPLETE.** See COMPLETION.md.

## Notes
- External-reality gaps (real X selectors for unit 8; real email/phone providers for unit 6)
  are expected blockers — build structure + fake/httpx-patch tests, catalog the gap, do NOT fail on them.
- Shared files (`config.py`, `main.py`, `account.py`) — sequence to avoid concurrent edits.
