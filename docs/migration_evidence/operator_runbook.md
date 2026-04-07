# Operator Runbook - API First Cutover

## Flag Matrix

| Mode | FEATURE_API_READS | FEATURE_API_RUNS | FEATURE_API_WRITES | FEATURE_NEW_UI | Intended behavior |
|---|---:|---:|---:|---:|---|
| Streamlit primary | `1` | `0` | `0` | `0` | API read-only support, Streamlit runs and writes remain active path. |
| API shadow run | `1` | `1` | `0` | `0` | API run lifecycle enabled, Streamlit still primary writer. |
| API single-writer | `1` | `1` | `1` | `0` | API is sole writer; Streamlit becomes read/observe-only. |
| New UI canary | `1` | `1` | `1` | `1` | Next.js UI exposed for internal canary users. |
| Full internal cutover | `1` | `1` | `1` | `1` | API + Next.js primary internal path, Streamlit kept for rollback. |

## Rollback Actions

1. SSE instability or circuit breach:
- Set `FEATURE_API_RUNS=0`.
- Keep `FEATURE_API_READS=1`, `FEATURE_API_WRITES=1` only if persistence is stable; otherwise set writes to `0`.
- Verify `/ops/slo` returns healthy trend before re-enabling runs.

2. Persistence or scoring mismatch:
- Set `FEATURE_API_WRITES=0` immediately.
- Keep Streamlit as sole writer and preserve API reads.
- Reconcile `results.json`, dataset scoped artifacts, and markdown output before retry.

3. Frontend instability only:
- Set `FEATURE_NEW_UI=0`.
- Keep API flags as-is if backend is healthy.
- Continue operations from Streamlit while frontend fixes are applied.

## Canary Checklist

1. Pre-canary
- `pytest -q` passes.
- Frontend `npm run typecheck`, `npm run build`, `npm run test:e2e` pass.
- `/ops/slo` healthy (not breached) before opening canary.

2. During one-week canary
- Monitor `/ops/slo` at regular intervals.
- Track start/stop success for each run.
- Validate dataset upload/delete and export behavior daily.
- Validate manual override updates persist and appear in results.

3. Exit criteria
- 0 critical and 0 high defects.
- 3 benchmark cycles with artifact compatibility preserved.
- Rollback drill executed and recorded for `FEATURE_API_RUNS` and `FEATURE_NEW_UI`.
