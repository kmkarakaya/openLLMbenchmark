# Checkpoint 3 - Single-URL Deployment Readiness

## Completed

- Docker runtime now serves a single public URL with:
  - Next.js on `/`
  - FastAPI proxied at `/api/*`
- Nginx reverse proxy configured for API routing and SSE-friendly timeouts.

## Validation Targets

- Local: API + UI start with `run_local_stack.bat`.
- HF-like: `/`, `/api/health`, `/api/docs`, run streaming, exports.

## Notes

- Streamlit rollback flags are no longer part of runtime policy.
- Rollback is commit-based.
