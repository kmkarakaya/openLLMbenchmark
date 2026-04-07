# Implement Version 2 Risk-Reduced Migration Plan With Cloud Coding Agent

## Objective

Implement the risk-reduced Version 2 migration plan in `version2_plan.md` using a cloud coding agent.

## Source of Truth

- Plan file: `version2_plan.md`
- Repository: `kmkarakaya/openLLMbenchmark`

## What to Implement

1. Phase 0: Baseline freeze + observability
- Create baseline fixtures for `results.json` and `results.md` behavior on fixed test inputs.
- Add shared correlation/log fields (`trace_id`, `run_id`, `session_id`, `dataset_key`, `question_id`, `model`, `event`, `elapsed_ms`).
- Lock API schema/version compatibility (`v1`).

2. Phase 1: Thin API (shadow mode first, writes later)
- Extract orchestration logic from UI to service layer without behavior changes.
- Implement API contracts defined in plan (`/health`, `/models`, `/datasets`, `/questions`, `/results`, `/runs`, `/runs/{id}/events`, `/runs/{id}/stop`, `/results/manual`).
- Keep read endpoints enabled first.
- Enable run endpoints in shadow mode.
- Enable write endpoints only after parity gates pass.

3. Phase 2: Next.js MVP UI + gradual rollout
- Build MVP against API: model/dataset selection, run/stop, streaming responses, manual decisions, metrics/matrix.
- Canary internal rollout, then expansion after stability criteria.

4. Phase 2b: Full parity + Streamlit deprecation gate
- Add dataset upload/delete, JSON/Excel export, metadata stats/charts, response render parity.
- Decommission Streamlit only after all parity and stability checks pass.

## Required Endpoint Scope (Full Parity Target)

Implement these endpoints as explicit deliverables (not implied work):

- `GET /health`
- `GET /models`
- `GET /datasets`
- `GET /datasets/template` (download benchmark JSON template)
- `POST /datasets/upload` (multipart file upload, validation, save)
- `DELETE /datasets/{dataset_key}` (uploaded datasets only)
- `GET /questions?dataset_key=...`
- `GET /results?dataset_key=...`
- `GET /results/export?dataset_key=...&format=json|xlsx`
- `PATCH /results/manual`
- `POST /runs`
- `GET /runs/{run_id}/events` (SSE)
- `GET /runs/{run_id}/status` (reconnect/snapshot state)
- `POST /runs/{run_id}/stop`

Notes:
- Endpoint behavior must preserve existing storage/scoring semantics.
- Export endpoint must match current JSON/Excel output compatibility.
- `GET /runs/{run_id}/status` is required for robust UI refresh/reconnect behavior.

## Mandatory Pre-Implementation Locks (Do Not Skip)

1. Single-writer policy
- While `FEATURE_API_WRITES=false`: Streamlit is sole writer.
- When `FEATURE_API_WRITES=true`: API is sole writer; Streamlit writes disabled/routed.
- Use inter-process file locks for persistence paths.

2. SSE rollback thresholds (15-minute rolling window)
- Disable `FEATURE_API_RUNS` if any:
- SSE disconnect/error rate > 1%
- Run completion success rate < 99%
- P95 chunk gap > 2s

3. Delivery prerequisites
- Add backend/frontend dependencies, CI gates, and environment contract exactly as defined in the plan.

## Feature Flags

- `FEATURE_API_READS`
- `FEATURE_API_RUNS`
- `FEATURE_API_WRITES`
- `FEATURE_NEW_UI`

## Acceptance Criteria

- Golden-master parity tests pass between existing Streamlit behavior and service/API output.
- API contract/integration/SSE tests pass.
- Next.js MVP E2E flow passes.
- 0 critical and 0 high defects during one-week internal canary.
- At least 3 benchmark cycles with no data compatibility regression.

## Constraints

- Preserve existing storage/scoring semantics.
- No breaking changes to result artifacts unless explicitly approved.
- Keep migration backward-compatible until cutover gates are met.

## Deliverables

- PR(s) implementing phases with clear checkpoints.
- Test evidence for each gate.
- Rollback runbook tied to feature flags.

---

Please execute phase-by-phase and stop at each gate with evidence before enabling the next flag.
