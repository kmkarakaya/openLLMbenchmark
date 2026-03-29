from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import portalocker

from config import get_feature_flags
from data.benchmark import load_benchmark_payload
from data.dataset_config import (
    DEFAULT_DATASET_KEY,
    compute_dataset_signature,
    discover_datasets,
    resolve_results_paths,
)
from mode_selection import normalize_selected_models
from runner import get_runner
from storage import compute_model_metrics, load_results


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

