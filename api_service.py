from __future__ import annotations

import hashlib
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
from storage import compute_model_metrics, load_results, prepare_results_excel, prepare_results_json


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BENCHMARK_PATH = DATA_DIR / "benchmark.json"
UPLOADED_DATASETS_DIR = DATA_DIR / "uploaded_datasets"
LOCK_PATH = DATA_DIR / ".persistence.lock"


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
