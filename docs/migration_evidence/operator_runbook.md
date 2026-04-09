# Operator Runbook - API + Next.js

## Runtime Model

- One product path: FastAPI backend + Next.js frontend.
- Streamlit is removed from active runtime.
- Rollback is git-based (revert + redeploy).

## Local Operations

1. Start stack:
- `run_local_stack.bat`
2. Verify:
- UI: `http://localhost:3001`
- API docs: `http://localhost:8000/docs`
3. Stop by closing spawned terminals.

## HF Docker Operations

- Public URL serves UI.
- Backend is proxied under `/api/*`.
- Health checks:
  - `/api/health`
  - `/api/docs`

## Incident Actions

1. SSE degradation:
- Check `/api/ops/slo` metrics.
- Restart container if transient issue.
- Roll back commit if persistent.

2. Persistence mismatch:
- Validate `data/results.json` or dataset-scoped artifact files.
- Roll back to previous stable commit if regression confirmed.

3. Frontend regression:
- Roll back commit; backend contracts remain stable.
