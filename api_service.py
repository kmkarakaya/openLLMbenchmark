from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import uuid

import portalocker

from config import get_feature_flags
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
from mode_selection import normalize_selected_models
from runner import get_runner
from scoring import normalize_reason_text
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
    from engine import get_client, list_models

    client = get_client()
    return list_models(client)


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
        rows = load_results(results_path)
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
        rows = load_results(results_path)
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
        rows = load_results(results_path)

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

    selected_model = model.strip()
    if not selected_model:
        return "invalid_model", None

    results_path, results_md_path = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = load_results(results_path)
        kept_rows: list[dict[str, Any]] = []
        deleted_count = 0

        for row in rows:
            row_model = str(row.get("model", "")).strip()
            if row_model != selected_model:
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
        "model": selected_model,
        "deleted_count": deleted_count,
        "remaining_count": sum(
            1
            for row in kept_rows
            if str(row.get("model", "")).strip() == selected_model
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
    results_path, results_md_path = resolve_results_paths(dataset_key, DATA_DIR, ROOT)
    with portalocker.Lock(str(LOCK_PATH), timeout=10):
        rows = load_results(results_path)
        existing = next(
            (
                row
                for row in rows
                if str(row.get("question_id", "")) == question_id and str(row.get("model", "")) == model
            ),
            None,
        )
        if existing is None:
            return "result_not_found", None
        updated = dict(existing)
        updated["dataset_key"] = dataset_key
        updated["dataset_signature"] = dataset["signature"]
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
    flags = get_feature_flags()
    if not flags.api_runs:
        return None, "disabled"
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
        return None, "conflict"
    snapshot = runner.snapshot()
    return int(snapshot.get("run_id", 0)), "started"


def stop_run(*, session_id: str) -> None:
    runner = get_runner(session_id)
    runner.request_stop()


def run_snapshot(*, session_id: str) -> dict[str, Any]:
    runner = get_runner(session_id)
    return runner.snapshot()


def get_run_status(*, run_id: int, session_id: str) -> dict[str, Any] | None:
    snapshot = run_snapshot(session_id=session_id)
    if int(snapshot.get("run_id", 0)) != run_id:
        return None
    entries = snapshot.get("entries", [])
    interrupted = any(bool(item.get("interrupted")) for item in entries)
    error = next((str(item.get("error", "")) for item in entries if str(item.get("error", "")).strip()), "")
    status_entries = [
        {
            "model": str(item.get("model", "")),
            "running": bool(item.get("running")),
            "completed": bool(item.get("completed")),
            "interrupted": bool(item.get("interrupted")),
            "error": str(item.get("error", "")),
            "event": str(item.get("event", "")),
            "elapsed_ms": float(item.get("elapsed_ms", 0.0)),
        }
        for item in entries
    ]
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
    models = sorted({str(row.get("model", "")) for row in results if str(row.get("model", "")).strip()})
    indexed = {
        (str(row.get("question_id", "")), str(row.get("model", ""))): row
        for row in results
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
        output.append(
            {
                "model": str(row.get("model", "")),
                "accuracy_percent": round(float(row.get("accuracy_percent", 0.0)), 1),
                "speed_score": round(float(row.get("latency_score", 0.0)), 1),
                "success_scored": f"{int(row.get('success_count', 0))}/{int(row.get('scored_count', 0))}",
                "median_seconds": median_seconds,
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

    models = sorted({str(row.get("model", "")).strip() for row in results if str(row.get("model", "")).strip()})
    counters: dict[str, dict[str, dict[str, int]]] = {}
    for row in results:
        model = str(row.get("model", "")).strip()
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
    if latency is None:
        return icon
    return f"{icon} {float(latency) / 1000.0:.2f}s"


def record_prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
