## Streamlit Shutdown Plan (Decision-Complete Replacement)

### Summary

- Execute a **hard cutover**: Streamlit is removed from `main`; product runtime becomes **FastAPI + Next.js only**.
- Keep **all current backend endpoint contracts unchanged**.
- Remove migration/runtime feature flags (`FEATURE_API_READS`, `FEATURE_API_RUNS`, `FEATURE_API_WRITES`, `FEATURE_NEW_UI`).
- Support both targets:

1. **Local dev** (`uvicorn` + `next dev`)
2. **HF Spaces single URL** (public UI + proxied API in one container).

### Locked Decisions

- HF deployment model: **single public URL** with internal reverse proxy.
- Proxy tech: **Nginx**.
- API path behavior: frontend uses `/api/*`; proxy strips `/api` and forwards to backend root routes.
- Cleanup scope: **full removal** from runtime, CI relevance, dependencies, docs (no legacy folder).

### Implementation Changes

- **Phase 1: Remove Streamlit runtime and coupling**
- Delete Streamlit execution path from product runtime and container startup.
- Remove Streamlit-specific dependencies from Python requirements.
- Remove Streamlit-only tests and any test imports that require `app.py`.
- If any useful pure helper logic from Streamlit is still needed by tests/features, move it to backend/service modules before deleting Streamlit files.
- **Phase 2: Keep API stable, remove migration toggles**
- Keep existing routes/response shapes exactly as they are now.
- Remove feature-flag gating branches and defaults from backend/config.
- Keep persistence behavior unchanged (file locking, atomic writes, `.corrupt` recovery, dataset-scoped artifacts).
- **Phase 3: Frontend + API wiring standardization**
- Frontend API base defaults to `/api` (single-URL deployment default).
- Allow local override via env (`NEXT_PUBLIC_API_BASE_URL`) for direct local API calls.
- Preserve current UI behavior and flows already implemented (configure/run/results/datasets, exports, model-history delete, run status/stream/manual decisions).
- **Phase 4: HF Docker single-URL architecture**
- Container runs three internal processes:

1. FastAPI on `127.0.0.1:8000`
2. Next.js production server on `127.0.0.1:3001`
3. Nginx on public `7860`

- Nginx routing:

1. `/api/*` -> FastAPI with prefix stripped
2. all other paths -> Next.js

- Ensure proxy headers and timeouts are set for SSE (`/api/runs/{id}/events`) so streaming is stable.
- Docker startup no longer uses Streamlit.
- **Phase 5: CI/docs/scripts cleanup**
- Update README to API+Next.js only (remove Streamlit live link and Streamlit quick-start sections).
- Keep local launcher (`run_local_stack.bat`) as primary dev command.
- CI remains backend + frontend pipelines, but remove Streamlit-oriented assumptions from docs/tests.

### Public Interfaces / Config

- **Backend API routes:** unchanged.
- **Public deployment URL:** one URL on HF; API reachable under `/api/*`.
- **Active env contract after cutover:**

1. `OLLAMA_API_KEY` (required)
2. `OLLAMA_HOST` (optional)
3. `OLLAMA_LOCAL_HOST` (optional)
4. `NEXT_PUBLIC_API_BASE_URL` (optional; local override)

- Migration feature flags are removed from runtime contract.

### Test Plan (must pass)

- **Backend**

1. Full `pytest -q` pass.
2. SSE lifecycle and status behavior still passing.
3. Exports (`json/xlsx`), dataset upload/delete, manual decision, model-history delete, table export verified.

- **Frontend**

1. `npm run typecheck`
2. `npm run build`
3. Playwright E2E updated to run against live backend (not only mocked routes) for core flow:
   configure -> run -> stream -> stop/manual -> results -> exports -> dataset actions.

- **Deployment smoke**

1. Local stack one-command smoke (`run_local_stack.bat`).
2. HF-like container smoke:
   `/` loads UI, `/api/health` works, `/api/docs` works, run streaming works, exports download.

### Acceptance Criteria

- No Streamlit runtime path remains.
- No Streamlit dependency remains in active runtime requirements.
- No migration feature-flag branches remain in active backend/frontend code.
- All tests/checks above pass.
- Repo can run both locally and on HF single URL without manual patching.

### Assumptions

- No existing external users require backward compatibility with Streamlit UX.
- Rollback strategy is git revert/redeploy (not flag-based rollback).
