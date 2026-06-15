# Bugfix Brief — Pre-existing test failures (surfaced during Soul pipeline work)

> **Status:** Ready to implement. Authored after the Soul pipeline refactor.
> **Scope:** Backend test suite only (`SocialMediaAutonomousAgents/backend/tests/`).
> **TL;DR:** 7 failing tests, in 3 clusters. **All are pre-existing and unrelated to the Soul refactor** — confirmed by stashing the soul changes and re-running: the identical 7 fail on the untouched tree. **All 3 are test-side staleness** (the production code paths are correct and intentional); none are product bugs. Fixes are low-risk and touch tests only (plus one optional doc-comment).

---

## 1. Context

While verifying the Soul pipeline (`docs/plans/soul-pipeline/`), the full suite ran **317 passed, 7 failed, 1 skipped**. To rule the failures in/out as regressions, the soul changes were `git stash`-ed and the suite re-run on the clean tree — the **same 7** failed. So they predate this work.

The failing tests:

| # | Test | Cluster |
|---|------|---------|
| 1 | `tests/test_orchestrator.py::test_interval_posts_once_per_slot` | A — AccountBundle stub |
| 2 | `tests/test_orchestrator.py::test_pipeline_posts_composed_body_after_safety` | A — AccountBundle stub |
| 3 | `tests/test_orchestrator.py::test_force_mode_bypasses_slot_guard` | A — AccountBundle stub |
| 4 | `tests/unit/test_oauth_routes.py::test_oauth_callback_access_denied_user_friendly` | B — OAuth redirect |
| 5 | `tests/unit/test_oauth_routes.py::test_oauth_callback_missing_code_or_state` | B — OAuth redirect |
| 6 | `tests/unit/test_oauth_routes.py::test_oauth_callback_exchange_invalid_grant` | B — OAuth redirect |
| 7 | `tests/unit/test_x_client_media_expansions.py::test_search_recent_tweets_requests_media_expansions` | C — expansions list |

---

## 2. Cluster A — Orchestrator `AccountBundle` validation (3 tests)

**Symptom**
```
ValidationError: 1 validation error for AccountBundle
account_id
  Field required [type=missing, input_value={'profile': {}}, input_type=dict]
```
Raised from `app/pipeline/tools/data/account_profile.py` → `ctx.set_artifact(ArtifactKey.ACCOUNT_BUNDLE, bundle)`, which validates the bundle against the `AccountBundle` model.

**Root cause (test staleness, not a product bug)**
- `AccountBundle` (`app/pipeline/types/artifacts.py:45`) requires `account_id: str` (and `profile: dict | None`).
- The **real** `TickDataService.compile_account_bundle` (`app/services/tick_data_service.py:36`) returns `{"account_id": account_id, "profile": ..., ...}` — i.e. it includes `account_id`. Production is correct.
- The orchestrator tests stub it with a value that **omits** `account_id`:
  ```python
  # tests/test_orchestrator.py  (lines ~96, 131, 177)
  mock_td.compile_account_bundle.return_value = {"profile": {}}
  ```
  When the pipeline later hardened artifact writes with model validation, these stubs fell out of sync.

**Proposed fix (test-only)**
Update the three stubs to satisfy the model contract:
```python
tick_data.compile_account_bundle.return_value = {"account_id": "a1", "profile": {}}
```
Use the same `account_id` each test already provisions for its account (`"a1"` per the in-test repo fixture). No production change.

---

## 3. Cluster B — OAuth callback now redirects instead of returning JSON errors (3 tests)

**Symptom**
- `test_oauth_callback_missing_code_or_state` expects `400`, gets **`404`**.
- The other two similarly expect `400 + JSON detail`.

**Root cause (test staleness, not a product bug)**
`app/api/routes/oauth.py:63` `oauth_callback` was reworked to redirect the browser back to the frontend on every outcome when a frontend redirect base is configured:
```python
redirect = _frontend_redirect(oauth_error=message)
if redirect is not None:
    return redirect              # 3xx redirect to the SPA
raise HTTPException(status_code=400, detail=message)   # fallback only when no redirect base
```
In the test environment a redirect base **is** configured, so the route returns a `3xx`. `TestClient` follows redirects by default; the redirect target (the SPA route) isn't part of the FastAPI app, so the followed request lands on **404**. The tests predate the redirect behavior and assert the old `400 + JSON` contract.

**Proposed fix (test-only) — pick one, recommend (a)**
- **(a) Exercise the API-error fallback path.** Force `_frontend_redirect` to return `None` so the route raises the `HTTPException` the tests assert:
  ```python
  monkeypatch.setattr(oauth_routes, "_frontend_redirect", lambda **kw: None)
  ```
  Add this to each test (the `invalid_grant` test already uses `monkeypatch`). Keeps the tests' intent — verifying the user-friendly 400 messages — intact.
- **(b) Assert the redirect contract instead.** Construct the client with `follow_redirects=False`, assert `response.status_code in (302, 307)` and that the `Location` query string carries the error message. Higher-fidelity to real behavior but a larger rewrite.

Recommendation: **(a)** — smallest change, preserves the original assertions, and the 400-fallback path is real (it fires when no frontend base is set, e.g. headless/cron).

---

## 4. Cluster C — X client search expansions gained `author_id` (1 test)

**Symptom**
```
assert call_kw["expansions"] == ["attachments.media_keys"]
E  Left contains one more item: 'author_id'
E  ['attachments.media_keys', 'author_id'] == ['attachments.media_keys']
```

**Root cause (test staleness, not a product bug)**
`app/social/implementations/x_client.py:393` intentionally requests author info on the reference-search path:
```python
"expansions": [*_REFERENCE_EXPANSIONS, "author_id"],
```
`_REFERENCE_EXPANSIONS` is `["attachments.media_keys"]`. The test still asserts the pre-`author_id` exact list.

**Proposed fix (test-only)**
Assert membership rather than exact equality (robust to future expansion additions), or update the exact list:
```python
assert "attachments.media_keys" in call_kw["expansions"]
assert "author_id" in call_kw["expansions"]
```
First confirm `author_id` is intended (it is — it backs author attribution on reference tweets); if so, the test simply needs to catch up.

---

## 5. Risk & sequencing

- **Risk: low.** All three fixes are confined to `tests/`. No production code changes (Cluster C optionally gets a one-line confirming comment). No schema, API, or behavior changes.
- **Independent** — can be done in any order, or in parallel.
- **Verification:**
  ```bash
  cd SocialMediaAutonomousAgents/backend
  python -m pytest tests/test_orchestrator.py tests/unit/test_oauth_routes.py \
    tests/unit/test_x_client_media_expansions.py -q
  # expect: all green
  python -m pytest -q   # expect: full suite green (324 passed)
  ```
- **Definition of done:** the 7 listed tests pass; full suite green; no production files modified (except an optional comment in `x_client.py` / test docstrings).

---

## 6. Notes
- These are **not** Soul-pipeline regressions; they were failing before and after. They're called out here only because the Soul work surfaced them during full-suite runs.
- If any of these tests are considered obsolete (e.g. the OAuth redirect behavior fully replaced the JSON-error contract in all environments), the alternative to fixing is deleting/rewriting them to assert the redirect contract — but the 400 fallback path still exists in code, so keeping coverage of it (Cluster B option **a**) is worthwhile.
