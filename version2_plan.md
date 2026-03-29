## Version 2 Plan (Risk-Reduced): API-First Migration with Controlled UI Replacement

### Summary

- Keep the same 2-phase strategy, but add a strict pre-phase baseline and a shadow-read/shadow-run gate before any write cutover.
- Maintain Streamlit as production path until objective parity gates are passed.
- Reduce risk by introducing feature flags, explicit rollback points, and compatibility checks on every milestone.
- Lock pre-implementation decisions for write ownership, SSE rollback SLOs, and delivery prerequisites before coding starts.
- Updated target: Phase 0 (1-2 days), Phase 1 API (4-7 days), Phase 2 UI MVP (5-8 days), parity hardening (3-6 days).

### Delivery Phases and Gates

- Phase 0: Baseline freeze and observability
- Freeze current behavior as baseline snapshots for `results.json` and `results.md` outputs on fixed fixture runs.
- Add shared log format and correlation IDs for Streamlit and API paths: `trace_id`, `run_id`, `session_id`, `dataset_key`, `question_id`, `model`, `event`, `elapsed_ms`.
- Define and lock API schema version `v1` and result-record compatibility constraints.
- Exit gate: baseline fixtures green, log fields present, schema docs approved.

- Phase 1: Thin API in shadow mode, then controlled writes
- Extract orchestration from UI into service layer (no behavior change intended).
- Start with read-only endpoints first (`/health`, `/models`, `/datasets`, `/questions`, `/results`).
- Add run endpoints in shadow mode: API can execute runs but does not publish as primary path yet.
- Introduce write enablement flag for manual decision and persistence.
- Exit gate A (shadow): for same mocked inputs, API and Streamlit outputs match record-level fields.
- Exit gate B (writes): 0 critical regressions across 3 consecutive benchmark cycles.

- Phase 2: Next.js MVP and gradual traffic shift
- Build MVP UI against API (run/stream/stop/results/manual decision).
- Keep dataset upload/delete and advanced panels in parity backlog until MVP is stable.
- Roll out with canary usage first (internal subset), then expand after stability period.
- Exit gate: MVP acceptance tests pass and rollback drills validated.

- Phase 2b: Full parity and Streamlit deprecation
- Add remaining parity features: dataset upload/delete, JSON/Excel export, metadata stats/charts, response render parity.
- Decommission Streamlit only after parity checklist and one-week stability SLA are met.

### Public API Contracts (v1, Backward-Compatible During Migration)

- `GET /health` -> `200 {"status":"ok","version":"v1"}`.
- `GET /models` -> `200 {"models":[string]}`; `503` if model provider unavailable.
- `GET /datasets` -> `200 {"datasets":[{"key","label","is_default","signature","question_count"}]}`.
- `GET /questions?dataset_key=...` -> `200 {"dataset_key","instruction","questions":[...]}`; `404` if unknown key.
- `GET /results?dataset_key=...` -> `200 {"dataset_key","results":[...],"metrics":[...],"matrix":[...]}`.
- `POST /runs` -> `201 {"run_id","status":"started"}`; `409` active-run conflict; `422` invalid request; `404` unknown dataset/question.
- `GET /runs/{run_id}/events` (SSE) -> ordered events `run_started`, `chunk`, `entry_completed`, `run_completed`, `run_interrupted`, `run_error`.
- `POST /runs/{run_id}/stop` -> `202 {"status":"stop_requested"}`.
- `PATCH /results/manual` -> updates status/score/reason/timestamp with current manual override semantics.
- Parity extension (Phase 2b only): `POST /datasets/upload`, `DELETE /datasets/{dataset_key}`.

### Locked Decisions Before Implementation

- Write ownership and data safety lock:
- While `FEATURE_API_WRITES=false` (shadow period), Streamlit is the only writer for results and manual decisions.
- When `FEATURE_API_WRITES=true`, API is the only writer. Streamlit write actions are disabled or routed through API endpoints.
- Use an inter-process file lock around persistence operations affecting `results.json`, dataset-specific result files, and markdown outputs.

- SSE rollback SLO lock:
- Disable `FEATURE_API_RUNS` if any condition holds for a rolling 15-minute window:
- SSE disconnect/error rate > 1%.
- Run completion success rate < 99%.
- P95 chunk gap > 2 seconds.

- Delivery prerequisites lock:
- Backend dependencies: `fastapi`, `uvicorn`, `httpx`, `pytest-asyncio`, `sse-starlette` (or equivalent), `portalocker`.
- Frontend dependencies: Next.js app baseline with Playwright support.
- CI gates required before feature rollout: backend unit tests, API integration/contract tests, SSE tests, frontend build, and E2E smoke tests.
- Environment contract: `OLLAMA_API_KEY`, `OLLAMA_HOST`, `API_BASE_URL`.

### Risk Controls and Rollback Strategy

- Feature flags (required):
- `FEATURE_API_READS` for read endpoints.
- `FEATURE_API_RUNS` for run lifecycle endpoints.
- `FEATURE_API_WRITES` for persistence/manual decision mutations.
- `FEATURE_NEW_UI` for Next.js visibility.

- Rollback rules:
- Any critical mismatch in scoring/persistence disables `FEATURE_API_WRITES` immediately.
- Any SSE instability beyond locked SLO thresholds disables `FEATURE_API_RUNS`; Streamlit remains primary.
- UI issues disable `FEATURE_NEW_UI` without backend rollback.

- Data safety controls:
- Continue atomic file writes exactly as current storage behavior.
- Enforce single-writer policy per phase and inter-process file locking to avoid concurrent write corruption.
- Keep `.corrupt` backup behavior and verify it in API path tests.

### Test and Acceptance Plan

- Service tests:
- Golden-master tests comparing extracted service outputs to current Streamlit-derived fixtures.
- Compatibility tests for metadata backfill, prompt-hash logic, and dataset filtering.

- API tests:
- Contract tests for status codes and payload shapes.
- SSE ordering/timing tests including stop, interruption, and error cases.
- Concurrency tests for same-session run conflict and multi-session isolation.

- End-to-end tests:
- Next.js MVP flow with Playwright: configure -> run -> stream -> stop/manual override -> verify persistence.
- Parallel-run comparison: same fixtures executed through Streamlit and API must match expected fields.

- Cutover criteria:
- 100% passing critical tests.
- 0 critical and 0 high defects in one-week internal canary.
- At least 3 full benchmark cycles with no data-compatibility regressions.

### Assumptions and Defaults

- Transport remains REST + SSE.
- Frontend remains React + Next.js.
- Deployment remains parallel services until parity completion.
- First release remains internal single-team (no auth in v1), with auth deferred to post-parity roadmap.
- API runs single-process in v1 due to in-memory run state; horizontal scale requires external run-state store in v2.1.
- The three pre-implementation locks in this plan are mandatory and are not deferred to later phases.
