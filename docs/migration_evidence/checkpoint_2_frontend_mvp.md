# Checkpoint 2 - Frontend MVP Integrated with API

## Implemented

- Added `frontend/` Next.js + TypeScript + Tailwind project.
- Implemented core UI flows:
  - Configure benchmark (dataset/mode/models/system prompt)
  - Run controls (start/stop) with SSE + reconnect-safe polling
  - Results rendering (metrics/matrix/raw payload)
  - Dataset management (template/upload/delete)
  - Export links (JSON/XLSX)
- Added typed API client for FastAPI endpoints.

## Verification

- Frontend typecheck and build scripts configured.
- Playwright smoke test validates route stubs and core page visibility.

