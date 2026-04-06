## Feature: Add Local Ollama Support Alongside Cloud (Revised)

### Problem

The app currently benchmarks models only via Ollama Cloud (`https://ollama.com`). Users with local Ollama (`http://localhost:11434`) cannot run benchmarks without a cloud API key.

Current limitations:
- `engine.get_client()` always requires `OLLAMA_API_KEY`.
- Results are deduplicated by `(question_id, model)` so cloud/local variants of the same model overwrite each other.
- UI supports model name selection, but not model source selection.
- Live panel matching is model-name-only, so cloud/local entries can collide visually.

---

### Goal

Support source-aware benchmarking per model slot.

- Each model slot (Model 1 / Model 2) has an independent `Source` selector: `Cloud` or `Local`.
- Users can run local-only benchmarks without a cloud API key.
- Users can compare the same model name across sources (`llama3:8b [cloud]` vs `llama3:8b [local]`).
- Result records store where the model ran (`model_source`) and endpoint used (`model_host`).

---

### Non-Goals

- No API/backend migration in this feature.
- No auth redesign.
- No result schema reset/migration job; backward compatibility is handled at read/merge time.

---

### Canonical Runtime Type

Use one shared typed object across app/runner/engine:

```python
from typing import Literal, TypedDict

class ModelTarget(TypedDict):
    model: str
    source: Literal["cloud", "local"]
    host: str
```

All runtime selection, run execution, pending autorun state, snapshot matching, and result lookup use `ModelTarget`.

---

### Execution Order (Important)

1. Initialize state and dataset as today.
2. Render benchmark config to build `active_targets` (source-aware).
3. Compute `needs_cloud = any(t["source"] == "cloud" for t in active_targets)`.
4. Only if `needs_cloud` and API key missing, show API key gate and stop.
5. If all selected targets are local, continue without cloud key prompt.

This prevents local-only users from being blocked.

---

### Task 1 - `engine.py` (Source-aware clients)

Replace cloud-only client construction with source-specific functions.

```python
DEFAULT_HOST = "https://ollama.com"
DEFAULT_LOCAL_HOST = "http://localhost:11434"

def get_cloud_client() -> Client: ...
def get_local_client(host: str | None = None) -> Client: ...
def get_client_for_target(target: ModelTarget) -> Client: ...
```

Rules:
- `get_cloud_client()` keeps existing behavior (requires `OLLAMA_API_KEY`, uses `OLLAMA_HOST`).
- `get_local_client()` never requires API key and uses host resolution:
  `host arg -> OLLAMA_LOCAL_HOST -> DEFAULT_LOCAL_HOST`.
- `get_client_for_target()` dispatches by `target["source"]`.

Update `list_models`:

```python
def list_models(client: Client, source: str = "cloud") -> list[str]: ...
```

Behavior:
- Keep model parsing logic unchanged.
- For `source="local"`: catch list errors and return `[]`.
- For `source="cloud"`: preserve existing error behavior.

---

### Task 2 - `runner.py` (Targets instead of model strings)

Change `LiveRunner.start` signature:

```python
def start(self, targets: list[ModelTarget], question_id: str, prompt: str, system_prompt: str) -> bool:
```

Implementation details:
- Deduplicate by `(model, source)`.
- Internal entry key: `f"{model}::{source}"`.
- `_run_worker` receives full target and calls `get_client_for_target(target)`.

Extend `ModelRunState` and snapshot entries with:
- `source`
- `host`

Snapshot entry shape:

```python
{
  "model": str,
  "source": "cloud" | "local",
  "host": str,
  "response": str,
  "running": bool,
  "completed": bool,
  "interrupted": bool,
  "error": str,
  "elapsed_ms": float,
}
```

---

### Task 3 - `storage.py` (Source-aware persistence and reports)

Update `upsert_result` key:

```python
key = (
    record["question_id"],
    record["model"],
    record.get("model_source", "cloud"),
)
```

When persisting completed entries, write:
- `model_source`
- `model_host`

Update grouping and matrix/report keys to include source fallback:
- Metrics grouping key: `(model, model_source)` where missing source is `cloud`.
- Matrix/markdown mapping key: `(question_id, model, model_source)`.

Display label convention everywhere in UI/reporting:
- `"{model} [{source}]"`

Update Excel export:
- Include `model_source`, `model_host` columns.
- Sort by `(model, model_source)` for adjacency.

---

### Task 4 - `mode_selection.py` (Return targets)

Keep existing string helpers (`normalize_selected_models`, `resolve_second_model_value`, `update_pair_model_backup`) as-is.

Update:

```python
def resolve_active_models(...)-> tuple[list[ModelTarget], bool]: ...
def is_run_eligible(mode: str, active_targets: list[ModelTarget]) -> bool: ...
```

Duplicate logic:
- Duplicate is true only if `(model_1, source_1) == (model_2, source_2)`.
- Same model name with different source is allowed.

---

### Task 5 - `app.py` (UI, UX, wiring)

#### 5.1 Session state

Add:
- `model_1_source` default `"cloud"`
- `model_2_source` default `"cloud"`

Update `model_cache` shape to:
- `{"cloud": [], "local": []}`

Backward compatibility:
- If old session has list-shaped `model_cache`, reinitialize to new dict format.

#### 5.2 Model loading helper

Add `_load_models(source)` returning `(models, warning_or_none)` with source-aware cache.

UX rules:
- Local list error -> warning: local endpoint unreachable.
- Local list empty with no exception -> info: endpoint reachable but no local models found.
- Cloud list behavior unchanged (errors handled by existing flow).

#### 5.3 Sidebar model selection UX

For each slot:
- Source selector (`Cloud` / `Local`) plus model selector.
- Keep manual model text input, but move under an `Advanced` expander (do not remove).
  Reason: preserves current flexibility for tag not in list.

Selection result returned from `pick_models`:
- `active_targets` instead of `active_models`.

#### 5.4 API key gate placement

Move API key gate after `active_targets` are known.
- If no cloud target selected: skip gate.
- If cloud selected and key missing: show existing masked input flow and stop.

#### 5.5 Source-aware result lookup and panel matching

Update:
- `find_result(results, question_id, model, source="cloud")`
- `find_snapshot_entry(snapshot, question_id, model, source="cloud")`

Both must treat missing `model_source` as `cloud` for old records.

All call sites must pass source from active target.

#### 5.6 Autorun state migration

Replace pending autorun payload from model-name list to target list:

```python
{"question_id": "...", "targets": list[ModelTarget]}
```

Filtering of missing runs must compare `(question_id, model, source)`.

#### 5.7 Status/meta/panel labels

Replace bare model labels with source-aware labels:
- Status panel
- Question meta chips
- Response panel headers
- Metrics and matrix

Format: `model [source]`.

#### 5.8 Manual decision mapping

Manual override actions must update the exact `(question_id, model, source)` record only.

---

### Task 6 - Tests

Update and extend (do not remove existing passing tests):

`tests/test_engine.py`
- `get_cloud_client` requires `OLLAMA_API_KEY`
- `get_local_client` uses no auth header
- `get_local_client` host resolution with `OLLAMA_LOCAL_HOST`
- `list_models(source="local")` returns `[]` on list exception

`tests/test_runner.py`
- `start(targets=...)` works
- snapshot includes `source` and `host`
- same model name with cloud+local yields two distinct entries

`tests/test_storage.py`
- `upsert_result` does not overwrite cloud with local variant
- metrics separate `model [cloud]` and `model [local]`
- old rows without `model_source` default to `cloud`

`tests/test_mode_selection.py`
- returns `ModelTarget` with correct source/host
- duplicate true for same model+same source
- duplicate false for same model+different source
- pair eligibility requires exactly 2 targets

`tests` updates in `app` behavior via focused integration/unit helpers:
- `find_result` and `find_snapshot_entry` source-aware lookup
- pending autorun stores `targets` and resolves missing by source-aware key

---

### Backward Compatibility

Existing result rows without `model_source` and `model_host` remain valid.

Compatibility rules:
- Any read path uses `row.get("model_source", "cloud")`.
- `find_result(..., source="cloud")` matches legacy rows lacking source.
- Existing model cache list in session state is auto-upgraded to dict cache.

---

### Definition of Done

- [ ] `pytest tests/` passes.
- [ ] Local-only run works with no `OLLAMA_API_KEY`.
- [ ] Cloud-only run behavior remains unchanged.
- [ ] Cloud-vs-local pair run persists two distinct records for same model name.
- [ ] Manual override updates the correct `(question_id, model, source)` record.
- [ ] Live response panel and saved result lookup are source-aware (no cloud/local collision).
- [ ] Metrics/matrix/report show source-aware labels (`model [cloud]`, `model [local]`).
- [ ] Sidebar UX provides clear source selection and clear local connectivity/no-model feedback.
