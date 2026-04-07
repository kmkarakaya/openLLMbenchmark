# Checkpoint 3 - Parity and Cutover Evidence

## Parity Status

- API parity endpoints are available for run lifecycle, dataset operations, exports, and manual decision update.
- Streamlit is retained side-by-side, with write-path restrictions enabled under `FEATURE_API_WRITES`.

## Operator Runbook Matrix

- `FEATURE_API_READS=true`: read endpoints enabled.
- `FEATURE_API_RUNS=true`: run endpoints enabled unless SLO breach circuit is active.
- `FEATURE_API_WRITES=true`: API is sole writer; Streamlit mutation controls are disabled.
- `FEATURE_NEW_UI=true`: operators are guided to the new frontend entry path.
- Detailed runbook is documented in `docs/migration_evidence/operator_runbook.md`.

## Cutover Checks (to execute during rollout)

- One-week internal canary with 0 critical / 0 high defects.
- Three benchmark cycles with no result artifact compatibility regression.
- Rollback drill validated for:
  - setting `FEATURE_API_RUNS=0` on SLO breach
  - disabling `FEATURE_NEW_UI` on frontend instability
