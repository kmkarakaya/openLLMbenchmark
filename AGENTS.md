# Project Guidelines

## Architecture

- Active product path is FastAPI backend plus Next.js frontend. Do not add new Streamlit runtime work unless the user explicitly asks for legacy recovery or archaeology.
- Backend contracts in `api.py` and `api_service.py` are the source of truth for runs, datasets, results, exports, and SSE lifecycle behavior.
- Local and cloud Ollama models are first-class. Preserve source-aware model refs such as `model:cloud` and `model:local` plus `model_source` and `model_host` across backend logic, persistence, exports, and UI.

## Conventions

- When changing run or results metadata, update the full path together: persistence and normalization in `api_service.py`/`storage.py`, API payloads, frontend types in `frontend/lib/types.ts`, the relevant Run and Results UI, and focused regression tests.
- Prefer backward-compatible normalization for saved artifacts instead of one-off migrations. Older rows in `data/results.json` and dataset-scoped result files must remain readable, with inferred defaults or estimated values marked explicitly.
- User-visible reporting should stay aligned across the Run page, Results tables, exports, and markdown reports when the data is shown in more than one place.
- For results-page changes, validate the actual `get_results()` payload when possible. Leaderboard and matrix values are backend-shaped, so helper-only checks are not enough.
- Keep newly added result rows visible and understandable in the UI. Avoid table behaviors that hide recent model runs behind stale ordering.

## Code Style

- Keep fixes minimal but end-to-end. Do not stop at a partial wiring change if the feature crosses backend, API, and frontend boundaries.
- Reuse shared formatting and aggregation layers when they already exist, especially `storage.py`, `api_service.py`, and `frontend/lib/view-models.ts`, instead of duplicating display logic in individual pages.
- Preserve existing JSON artifact compatibility and avoid rewriting repository data files unless the task explicitly requires it.

## Build And Test

- See `README.md` for the standard local run, validation, and deployment commands.
- Preferred local stack command: `./run_local_stack.bat`
- Preferred backend validation: focused `pytest` for touched areas, then `pytest -q` when the change is broad.
- Preferred frontend validation for UI and type changes: `npm --prefix frontend run typecheck`
- For run/results/reporting changes, finish with targeted backend tests plus frontend typecheck at minimum.
