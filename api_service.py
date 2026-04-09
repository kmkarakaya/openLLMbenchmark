from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Any
import uuid

import portalocker

from data.benchmark import load_benchmark_payload
from data.dataset_config import (
    DEFAULT_DATASET_KEY,
    compute_dataset_signature,
    dataset_template_bytes,
    delete_uploaded_dataset_with_artifacts,
    discover_datasets,
    resolve_results_paths,
    save_uploaded_dataset,
)
from model_identity import (
    CLOUD_SOURCE,
    LOCAL_SOURCE,
    model_ref_from_record,
    resolve_model_host,
    split_model_ref,
    to_model_ref,
)
from mode_selection import normalize_selected_models
from runner import get_runner
from scoring import evaluate_response, normalize_reason_text
from storage import (
    compute_model_metrics,
    load_results,
    prepare_results_excel,
    prepare_results_json,
    render_results_markdown,
    save_results,
    upsert_result,
)


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BENCHMARK_PATH = DATA_DIR / "benchmark.json"
UPLOADED_DATASETS_DIR = DATA_DIR / "uploaded_datasets"
LOCK_PATH = DATA_DIR / ".persistence.lock"

TABLE_EXPORT_MODEL_LEADERBOARD = "model_leader_board"
TABLE_EXPORT_CATEGORY_PERFORMANCE = "category_level_model_performance"
TABLE_EXPORT_HARDNESS_PERFORMANCE = "hardness_level_model_performance"
TABLE_EXPORT_QUESTION_PERFORMANCE = "question_level_model_performance"
TABLE_EXPORT_RESPONSE_PERFORMANCE = "response_level_model_performance"

_PERSISTED_RUN_ENTRY_KEYS: set[str] = set()
_PERSISTED_RUN_ENTRY_KEYS_LOCK = threading.Lock()


def _normalized_result_row(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    model_ref = model_ref_from_record(normalized)
    if not model_ref:
        return normalized

    model_name, source = split_model_ref(model_ref)
    normalized["model"] = model_ref
    normalized["model_source"] = source
    normalized["model_name"] = model_name
    if not str(normalized.get("model_host", "") or "").strip():
        normalized["model_host"] = resolve_model_host(source)

    prompt_tokens = _optional_int(normalized.get("prompt_tokens"))
    generated_tokens = _optional_int(normalized.get("generated_tokens"))
    generated_tokens_estimated = normalized.get("generated_tokens_estimated")

    if generated_tokens is None:
        generated_tokens = _estimate_generated_tokens(str(normalized.get("response", "") or ""))
        normalized["generated_tokens_estimated"] = True
    elif isinstance(generated_tokens_estimated, bool):
        normalized["generated_tokens_estimated"] = generated_tokens_estimated
    else:
        normalized["generated_tokens_estimated"] = prompt_tokens is None

    normalized["generated_tokens"] = generated_tokens
    if prompt_tokens is not None:
        normalized["prompt_tokens"] = prompt_tokens
    return normalized


def _normalized_result_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalized_result_row(row) for row in rows]


def _persist_key_for_entry(snapshot: dict[str, Any], entry: dict[str, Any]) -> str:
    session_id = str(snapshot.get("session_id", "") or "").strip()
    run_id = int(snapshot.get("run_id", 0) or 0)
    question_id = str(snapshot.get("question_id", "") or "").strip()
    model_ref = model_ref_from_record({"model": entry.get("model", ""), "model_source": entry.get("source", "")})
    return f"{session_id}:{run_id}:{question_id}:{model_ref}"


def _is_entry_persisted(persist_key: str) -> bool:
    with _PERSISTED_RUN_ENTRY_KEYS_LOCK:
        return persist_key in _PERSISTED_RUN_ENTRY_KEYS


def _mark_entries_persisted(persist_keys: list[str]) -> None:
    if not persist_keys:
        return
    with _PERSISTED_RUN_ENTRY_KEYS_LOCK:
        _PERSISTED_RUN_ENTRY_KEYS.update(persist_keys)


def _verdict_for_entry(entry: dict[str, Any], expected_answer: str) -> dict[str, Any]:
    if bool(entry.get("interrupted")):
        return {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": "Stopped by user.",
        }

    error_text = str(entry.get("error", "") or "").strip()
    if error_text:
        return {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": f"Error: {error_text}",
        }

    return evaluate_response(expected_answer=expected_answer, response=str(entry.get("response", "") or ""))


def _estimate_generated_tokens(response_text: str) -> int:
    trimmed = response_text.strip()
    if not trimmed:
        return 0
    chars = len(trimmed)
    words = len([part for part in trimmed.split() if part])
    return max(words, round(chars / 4))


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _persist_completed_run_entries(snapshot: dict[str, Any]) -> None:
    run_id = int(snapshot.get("run_id", 0) or 0)
    if run_id <= 0:
        return

    dataset_key = str(snapshot.get("dataset_key", "") or "").strip()
    question_id = str(snapshot.get("question_id", "") or "").strip()
    session_id = str(snapshot.get("session_id", "") or "").strip()
    if not dataset_key or not question_id or not session_id:
        return

    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return
    question = next((q for q in dataset["questions"] if str(q.get("id", "") or "") == question_id), None)
    if question is None:
        return

    prompt = str(question.get("prompt", "") or "")
    expected_answer = str(question.get("expected_answer", "") or "")
    prompt_hash = record_prompt_hash(prompt) if prompt else ""
    results_path, results_md_path = resolve_results_paths(dataset_key, DATA_DIR, ROOT)

    persisted_keys: list[str] = []
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = load_results(results_path)
        changed = False

        for entry_raw in snapshot.get("entries", []):
            if not isinstance(entry_raw, dict):
                continue
            if not bool(entry_raw.get("completed")):
                continue

            entry = dict(entry_raw)
            model_ref = model_ref_from_record({"model": entry.get("model", ""), "model_source": entry.get("source", "")})
            if not model_ref:
                continue

            persist_key = _persist_key_for_entry(snapshot, entry)
            if _is_entry_persisted(persist_key):
                continue

            model_name, source = split_model_ref(model_ref)
            host = str(entry.get("host", "") or "").strip() or resolve_model_host(source)
            verdict = _verdict_for_entry(entry, expected_answer)
            response_text = str(entry.get("response", "") or "")
            exact_generated_tokens = _optional_int(entry.get("generated_tokens"))
            exact_prompt_tokens = _optional_int(entry.get("prompt_tokens"))

            record = {
                "dataset_key": dataset_key,
                "dataset_signature": dataset["signature"],
                "question_prompt_hash": prompt_hash,
                "question_id": question_id,
                "model": model_ref,
                "model_name": model_name,
                "model_source": source,
                "model_host": host,
                "response": response_text,
                "status": verdict["status"],
                "score": verdict["score"],
                "response_time_ms": round(float(entry.get("elapsed_ms", 0.0) or 0.0), 2),
                "generated_tokens": exact_generated_tokens if exact_generated_tokens is not None else _estimate_generated_tokens(response_text),
                "generated_tokens_estimated": exact_generated_tokens is None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "interrupted": bool(entry.get("interrupted")),
                "auto_scored": bool(verdict.get("auto_scored")),
                "reason": normalize_reason_text(str(verdict.get("reason", "") or "")),
                "run_id": run_id,
                "session_id": session_id,
            }
            if exact_prompt_tokens is not None:
                record["prompt_tokens"] = exact_prompt_tokens
            rows = upsert_result(rows, record)
            persisted_keys.append(persist_key)
            changed = True

        if changed:
            save_results(results_path, rows)
            render_results_markdown(dataset["questions"], rows, results_md_path)

    _mark_entries_persisted(persisted_keys)


def _dataset_option_map() -> dict[str, dict[str, Any]]:
    options = discover_datasets(BENCHMARK_PATH, UPLOADED_DATASETS_DIR)
    option_map: dict[str, dict[str, Any]] = {}
    for option in options:
        path = Path(option["path"])
        payload = load_benchmark_payload(path)
        option_map[option["key"]] = {
            "key": option["key"],
            "label": option["label"],
            "is_default": bool(option["is_default"]),
            "path": path,
            "signature": compute_dataset_signature(path),
            "instruction": payload.get("instruction", ""),
            "questions": payload.get("questions", []),
        }
    return option_map


def get_health() -> dict[str, str]:
    return {"status": "ok", "version": "v1"}


def get_models() -> list[str]:
    from engine import get_cloud_client, get_local_client, list_models

    model_refs: set[str] = set()
    cloud_error: Exception | None = None

    try:
        cloud_client = get_cloud_client()
        for model in list_models(cloud_client, source=CLOUD_SOURCE):
            model_ref = to_model_ref(model, CLOUD_SOURCE)
            if model_ref:
                model_refs.add(model_ref)
    except Exception as exc:  # noqa: BLE001
        cloud_error = exc

    try:
        local_client = get_local_client()
        for model in list_models(local_client, source=LOCAL_SOURCE):
            model_ref = to_model_ref(model, LOCAL_SOURCE)
            if model_ref:
                model_refs.add(model_ref)
    except Exception:
        # Local model discovery is best-effort and should not block cloud usage.
        pass

    if model_refs:
        return sorted(model_refs)
    if cloud_error is not None:
        raise RuntimeError(str(cloud_error))
    raise RuntimeError("No models discovered from Ollama cloud/local providers.")


def get_datasets() -> list[dict[str, Any]]:
    datasets = []
    for item in _dataset_option_map().values():
        datasets.append(
            {
                "key": item["key"],
                "label": item["label"],
                "is_default": item["is_default"],
                "signature": item["signature"],
                "question_count": len(item["questions"]),
            }
        )
    datasets.sort(key=lambda row: (not row["is_default"], row["label"].lower()))
    return datasets


def get_questions(dataset_key: str) -> dict[str, Any] | None:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return None
    return {
        "dataset_key": dataset_key,
        "instruction": dataset["instruction"],
        "questions": dataset["questions"],
    }


def get_results(dataset_key: str) -> dict[str, Any] | None:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return None
    results_path, _ = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = _normalized_result_rows(load_results(results_path))
    matrix = _build_matrix(dataset["questions"], rows)
    return {
        "dataset_key": dataset_key,
        "results": rows,
        "metrics": compute_model_metrics(rows),
        "matrix": matrix,
    }


def get_dataset_template() -> bytes:
    return dataset_template_bytes()


def upload_dataset(*, filename: str, content: bytes) -> dict[str, Any]:
    path = save_uploaded_dataset(UPLOADED_DATASETS_DIR, filename, content)
    options = discover_datasets(BENCHMARK_PATH, UPLOADED_DATASETS_DIR)
    option = next((item for item in options if Path(item["path"]) == path), None)
    if option is None:
        raise RuntimeError("Uploaded dataset could not be resolved.")
    payload = load_benchmark_payload(path)
    return {
        "key": option["key"],
        "label": option["label"],
        "is_default": bool(option["is_default"]),
        "signature": compute_dataset_signature(path),
        "question_count": len(payload.get("questions", [])),
    }


def delete_dataset(dataset_key: str) -> tuple[str, dict[str, Any] | None]:
    options = _dataset_option_map()
    target = options.get(dataset_key)
    if target is None:
        return "not_found", None
    if target["is_default"] or dataset_key == DEFAULT_DATASET_KEY:
        return "default_forbidden", None
    summary = delete_uploaded_dataset_with_artifacts(target, DATA_DIR, ROOT)
    return "deleted", {
        "dataset_key": dataset_key,
        "target_count": summary["target_count"],
        "deleted_count": summary["deleted_count"],
        "missing_count": summary["missing_count"],
    }


def export_results(dataset_key: str, export_format: str) -> tuple[bytes, str, str] | None:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return None
    results_path, _ = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = _normalized_result_rows(load_results(results_path))
    stem = "results" if dataset_key == DEFAULT_DATASET_KEY else f"results_{dataset_key}"
    if export_format == "json":
        return prepare_results_json(rows), "application/json", f"{stem}.json"
    if export_format == "xlsx":
        return (
            prepare_results_excel(rows),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{stem}.xlsx",
        )
    raise ValueError("Unsupported export format.")


def export_results_table(
    dataset_key: str,
    table_key: str,
    export_format: str,
) -> tuple[str, tuple[bytes, str, str] | None]:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return "dataset_not_found", None

    results_path, _ = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = _normalized_result_rows(load_results(results_path))

    if table_key == TABLE_EXPORT_MODEL_LEADERBOARD:
        table_rows = _table_rows_model_leader_board(rows)
    elif table_key == TABLE_EXPORT_CATEGORY_PERFORMANCE:
        table_rows = _table_rows_group_performance(dataset["questions"], rows, group_key="category", fallback_value="GENEL")
    elif table_key == TABLE_EXPORT_HARDNESS_PERFORMANCE:
        table_rows = _table_rows_group_performance(dataset["questions"], rows, group_key="hardness_level", fallback_value="(missing)")
    elif table_key == TABLE_EXPORT_QUESTION_PERFORMANCE:
        table_rows = _table_rows_question_performance(dataset["questions"], rows)
    elif table_key == TABLE_EXPORT_RESPONSE_PERFORMANCE:
        table_rows = rows
    else:
        return "table_not_supported", None

    stem = "results" if dataset_key == DEFAULT_DATASET_KEY else f"results_{dataset_key}"
    filename_stem = f"{stem}_{table_key}"
    if export_format == "json":
        return "ok", (prepare_results_json(table_rows), "application/json", f"{filename_stem}.json")
    if export_format == "xlsx":
        return (
            "ok",
            (
                prepare_results_excel(table_rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                f"{filename_stem}.xlsx",
            ),
        )
    return "format_not_supported", None


def _is_row_in_dataset_scope(row: dict[str, Any], *, dataset_key: str, dataset_signature: str) -> bool:
    row_dataset_key = str(row.get("dataset_key", "") or "").strip()
    if dataset_key == DEFAULT_DATASET_KEY:
        return row_dataset_key in {"", DEFAULT_DATASET_KEY}
    if row_dataset_key != dataset_key:
        return False
    return str(row.get("dataset_signature", "") or "").strip() == dataset_signature


def delete_model_results(*, dataset_key: str, model: str) -> tuple[str, dict[str, Any] | None]:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return "dataset_not_found", None

    selected_model_input = model.strip()
    selected_model_ref = to_model_ref(selected_model_input)
    if not selected_model_ref:
        return "invalid_model", None

    results_path, results_md_path = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = load_results(results_path)
        kept_rows: list[dict[str, Any]] = []
        deleted_count = 0

        for row in rows:
            row_model_ref = model_ref_from_record(row)
            if row_model_ref != selected_model_ref:
                kept_rows.append(row)
                continue
            if _is_row_in_dataset_scope(row, dataset_key=dataset_key, dataset_signature=str(dataset["signature"])):
                deleted_count += 1
                continue
            kept_rows.append(row)

        if deleted_count == 0:
            return "model_not_found", None

        save_results(results_path, kept_rows)
        render_results_markdown(dataset["questions"], kept_rows, results_md_path)

    return "deleted", {
        "dataset_key": dataset_key,
        "model": selected_model_input,
        "deleted_count": deleted_count,
        "remaining_count": sum(
            1
            for row in kept_rows
            if model_ref_from_record(row) == selected_model_ref
            and _is_row_in_dataset_scope(
                row,
                dataset_key=dataset_key,
                dataset_signature=str(dataset["signature"]),
            )
        ),
    }


def apply_manual_result_override(
    *,
    dataset_key: str,
    question_id: str,
    model: str,
    status: str,
    reason: str,
) -> tuple[str, dict[str, Any] | None]:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return "dataset_not_found", None
    override_defaults = {
        "success": {"score": 1, "reason": "User approval"},
        "fail": {"score": 0, "reason": "User approval"},
        "manual_review": {"score": None, "reason": "Marked by user for manual review"},
    }
    selected = override_defaults.get(status)
    if selected is None:
        return "invalid_status", None
    selected_model_ref = to_model_ref(model)
    if not selected_model_ref:
        return "result_not_found", None
    selected_model_name, selected_source = split_model_ref(selected_model_ref)

    results_path, results_md_path = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = load_results(results_path)
        existing = next(
            (
                row
                for row in rows
                if str(row.get("question_id", "")) == question_id and model_ref_from_record(row) == selected_model_ref
            ),
            None,
        )
        if existing is None:
            return "result_not_found", None
        updated = dict(existing)
        updated["dataset_key"] = dataset_key
        updated["dataset_signature"] = dataset["signature"]
        updated["model"] = selected_model_ref
        updated["model_name"] = selected_model_name
        updated["model_source"] = selected_source
        if not str(updated.get("model_host", "") or "").strip():
            updated["model_host"] = resolve_model_host(selected_source)
        updated["status"] = status
        updated["score"] = selected["score"]
        updated["auto_scored"] = False
        updated["interrupted"] = False
        updated["reason"] = normalize_reason_text(reason.strip() or selected["reason"])
        updated["timestamp"] = datetime.now(timezone.utc).isoformat()
        if not str(updated.get("question_prompt_hash", "")).strip():
            prompt = next(
                (
                    str(question.get("prompt", ""))
                    for question in dataset["questions"]
                    if str(question.get("id", "")) == question_id
                ),
                "",
            )
            if prompt:
                updated["question_prompt_hash"] = record_prompt_hash(prompt)
        merged = upsert_result(rows, updated)
        save_results(results_path, merged)
        render_results_markdown(dataset["questions"], merged, results_md_path)
    return "updated", updated


def start_run(*, session_id: str, dataset_key: str, question_id: str, models: list[str], system_prompt: str) -> tuple[int | None, str]:
    dataset = _dataset_option_map().get(dataset_key)
    if dataset is None:
        return None, "dataset_not_found"
    question = next((q for q in dataset["questions"] if str(q.get("id", "")) == question_id), None)
    if question is None:
        return None, "question_not_found"
    normalized_models = normalize_selected_models(*models)
    if not normalized_models:
        return None, "invalid_models"
    runner = get_runner(session_id)
    started = runner.start(
        models=normalized_models,
        question_id=question_id,
        prompt=str(question.get("prompt", "")),
        system_prompt=system_prompt,
        session_id=session_id,
        dataset_key=dataset_key,
        trace_id=uuid.uuid4().hex,
    )
    if not started:
        snapshot = runner.snapshot()
        conflict_run_id = int(snapshot.get("run_id", 0)) or None
        return conflict_run_id, "conflict"
    snapshot = runner.snapshot()
    return int(snapshot.get("run_id", 0)), "started"


def stop_run(*, session_id: str) -> None:
    runner = get_runner(session_id)
    runner.request_stop()


def run_snapshot(*, session_id: str) -> dict[str, Any]:
    runner = get_runner(session_id)
    snapshot = runner.snapshot()
    _persist_completed_run_entries(snapshot)
    return snapshot


def get_run_status(*, run_id: int, session_id: str) -> dict[str, Any] | None:
    snapshot = run_snapshot(session_id=session_id)
    if int(snapshot.get("run_id", 0)) != run_id:
        return None
    entries = snapshot.get("entries", [])
    interrupted = any(bool(item.get("interrupted")) for item in entries)
    error = next((str(item.get("error", "")) for item in entries if str(item.get("error", "")).strip()), "")
    status_entries: list[dict[str, Any]] = []
    for item in entries:
        model_ref = model_ref_from_record({"model": item.get("model", ""), "model_source": item.get("source", "")})
        _, source = split_model_ref(model_ref, str(item.get("source", "") or CLOUD_SOURCE))
        host = str(item.get("host", "") or "").strip() or resolve_model_host(source)
        status_entry = {
            "model": model_ref,
            "source": source,
            "host": host,
            "running": bool(item.get("running")),
            "completed": bool(item.get("completed")),
            "interrupted": bool(item.get("interrupted")),
            "error": str(item.get("error", "")),
            "event": str(item.get("event", "")),
            "elapsed_ms": float(item.get("elapsed_ms", 0.0)),
        }
        generated_tokens = _optional_int(item.get("generated_tokens"))
        prompt_tokens = _optional_int(item.get("prompt_tokens"))
        if generated_tokens is not None:
            status_entry["generated_tokens"] = generated_tokens
        if prompt_tokens is not None:
            status_entry["prompt_tokens"] = prompt_tokens
        status_entries.append(status_entry)
    return {
        "run_id": run_id,
        "session_id": str(snapshot.get("session_id", "")),
        "dataset_key": str(snapshot.get("dataset_key", "")),
        "question_id": str(snapshot.get("question_id", "")),
        "running": bool(snapshot.get("running")),
        "completed": bool(snapshot.get("completed")),
        "interrupted": interrupted,
        "error": error,
        "entries": status_entries,
    }


def _build_matrix(questions: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    models = sorted({model_ref_from_record(row) for row in results if model_ref_from_record(row)})
    indexed = {
        (str(row.get("question_id", "")), model_ref_from_record(row)): row
        for row in results
        if model_ref_from_record(row)
    }
    matrix: list[dict[str, Any]] = []
    for question in questions:
        question_id = str(question.get("id", ""))
        row = {"question_id": question_id, "category": question.get("category", "GENEL"), "cells": {}}
        for model in models:
            row["cells"][model] = _format_matrix_cell(indexed.get((question_id, model)))
        matrix.append(row)
    return matrix


def _table_rows_model_leader_board(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = compute_model_metrics(results)
    output: list[dict[str, Any]] = []
    for row in metrics:
        median_ms = row.get("median_ms")
        median_seconds = round(float(median_ms) / 1000.0, 2) if median_ms is not None else None
        avg_generated_tokens = row.get("avg_generated_tokens")
        output.append(
            {
                "model": str(row.get("model", "")),
                "accuracy_percent": round(float(row.get("accuracy_percent", 0.0)), 1),
                "speed_score": round(float(row.get("latency_score", 0.0)), 1),
                "success_scored": f"{int(row.get('success_count', 0))}/{int(row.get('scored_count', 0))}",
                "median_seconds": median_seconds,
                "avg_generated_tokens": round(float(avg_generated_tokens), 1) if avg_generated_tokens is not None else None,
            }
        )
    return output


def _table_rows_group_performance(
    questions: list[dict[str, Any]],
    results: list[dict[str, Any]],
    *,
    group_key: str,
    fallback_value: str,
) -> list[dict[str, Any]]:
    question_to_group: dict[str, str] = {}
    group_counts: dict[str, int] = {}
    for question in questions:
        question_id = str(question.get("id", "")).strip()
        group_value = str(question.get(group_key, "")).strip() or fallback_value
        if question_id:
            question_to_group[question_id] = group_value
        group_counts[group_value] = group_counts.get(group_value, 0) + 1

    models = sorted({model_ref_from_record(row) for row in results if model_ref_from_record(row)})
    counters: dict[str, dict[str, dict[str, int]]] = {}
    for row in results:
        model = model_ref_from_record(row)
        question_id = str(row.get("question_id", "")).strip()
        status = str(row.get("status", "")).strip()
        if not model or not question_id:
            continue
        group_value = question_to_group.get(question_id, fallback_value)
        group_bucket = counters.setdefault(group_value, {})
        model_bucket = group_bucket.setdefault(model, {"success": 0, "scored": 0})
        if status in {"success", "fail"}:
            model_bucket["scored"] += 1
            if status == "success":
                model_bucket["success"] += 1

    output: list[dict[str, Any]] = []
    for group_value in sorted(group_counts.keys()):
        row: dict[str, Any] = {
            group_key: group_value,
            "questions": int(group_counts.get(group_value, 0)),
        }
        for model in models:
            model_counter = counters.get(group_value, {}).get(model, {"success": 0, "scored": 0})
            scored = int(model_counter.get("scored", 0))
            if scored == 0:
                row[model] = None
            else:
                row[model] = round((100.0 * int(model_counter.get("success", 0))) / scored, 1)
        output.append(row)
    return output


def _table_rows_question_performance(questions: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matrix = _build_matrix(questions, results)
    output: list[dict[str, Any]] = []
    for row in matrix:
        item: dict[str, Any] = {
            "question_id": str(row.get("question_id", "")),
            "category": str(row.get("category", "")),
        }
        cells = row.get("cells", {})
        if isinstance(cells, dict):
            for model, value in cells.items():
                item[str(model)] = value
        output.append(item)
    return output


def _format_matrix_cell(record: dict[str, Any] | None) -> str:
    if not record:
        return "-"
    status = str(record.get("status", "manual_review"))
    icon = {"success": "✅", "fail": "❌", "manual_review": "🟡"}.get(status, "🟡")
    latency = record.get("response_time_ms")
    generated_tokens = _optional_int(record.get("generated_tokens"))
    token_suffix = ""
    if generated_tokens is not None:
        token_suffix = f" | {generated_tokens} tok"
        if record.get("generated_tokens_estimated") is True:
            token_suffix += " (est.)"
    if latency is None:
        return f"{icon}{token_suffix}" if token_suffix else icon
    return f"{icon} {float(latency) / 1000.0:.2f}s{token_suffix}"


def record_prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
