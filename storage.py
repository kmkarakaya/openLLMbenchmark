from __future__ import annotations

import json
import math
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_ICON = {
    "success": "✅",
    "fail": "❌",
    "manual_review": "🟡",
}


def load_questions(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_questions(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def load_results(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []

    if not raw.strip():
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Keep the broken file for debugging and continue with empty results.
        try:
            backup_path = path.with_suffix(path.suffix + ".corrupt")
            path.replace(backup_path)
        except OSError:
            pass
        return []

    if not isinstance(parsed, list):
        return []
    return parsed


def save_results(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


def upsert_result(results: list[dict[str, Any]], record: dict[str, Any]) -> list[dict[str, Any]]:
    output = list(results)
    key = (record["question_id"], record["model"])
    replaced = False
    for idx, item in enumerate(output):
        if (item.get("question_id"), item.get("model")) == key:
            output[idx] = record
            replaced = True
            break
    if not replaced:
        output.append(record)
    return output


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    rank = (pct / 100) * (len(data) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return data[low]
    weight = rank - low
    return data[low] * (1 - weight) + data[high] * weight


def compute_model_metrics(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, list[dict[str, Any]]] = {}
    for record in results:
        model = record.get("model", "").strip()
        if not model:
            continue
        by_model.setdefault(model, []).append(record)

    rows: list[dict[str, Any]] = []
    for model, items in by_model.items():
        scored = [x for x in items if x.get("status") in {"success", "fail"}]
        success = sum(1 for x in scored if x.get("status") == "success")
        total = len(scored)
        accuracy = (100 * success / total) if total else 0.0

        latencies = [
            float(x["response_time_ms"])
            for x in items
            if x.get("response_time_ms") is not None and not x.get("interrupted", False)
        ]
        median_ms = statistics.median(latencies) if latencies else None
        mean_ms = statistics.mean(latencies) if latencies else None
        p95_ms = percentile(latencies, 95) if latencies else None

        rows.append(
            {
                "model": model,
                "accuracy_percent": accuracy,
                "success_count": success,
                "scored_count": total,
                "median_ms": median_ms,
                "mean_ms": mean_ms,
                "p95_ms": p95_ms,
                "latency_score": 0.0,
            }
        )

    medians = [row["median_ms"] for row in rows if row["median_ms"] is not None]
    best_median = min(medians) if medians else None
    for row in rows:
        if best_median is not None and row["median_ms"]:
            row["latency_score"] = min(100.0, 100.0 * best_median / row["median_ms"])
        else:
            row["latency_score"] = 0.0

    rows.sort(
        key=lambda x: (
            -x["accuracy_percent"],
            x["median_ms"] if x["median_ms"] is not None else float("inf"),
            x["model"].lower(),
        )
    )
    return rows


def format_cell(record: dict[str, Any] | None) -> str:
    if not record:
        return "-"
    icon = STATUS_ICON.get(record.get("status", "manual_review"), "🟡")
    latency_ms = record.get("response_time_ms")
    if latency_ms is None:
        return icon
    seconds = float(latency_ms) / 1000.0
    return f"{icon} {seconds:.2f}s"


def render_results_markdown(
    questions: list[dict[str, Any]],
    results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    models = sorted({r.get("model", "") for r in results if r.get("model")})
    record_by_key = {
        (r.get("question_id"), r.get("model")): r
        for r in results
        if r.get("question_id") and r.get("model")
    }
    metrics = compute_model_metrics(results)

    lines: list[str] = []
    lines.append("# Open LLM Benchmark Results")
    timestamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines.append(f"_Güncellendi: {timestamp}_")
    lines.append("")

    if metrics:
        lines.append("## Model Karşılaştırma")
        lines.append(
            "| Model | Accuracy % | Success/Scored | Median | Mean | P95 | Latency Score |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for row in metrics:
            median = f"{row['median_ms']/1000:.2f}s" if row["median_ms"] else "-"
            mean = f"{row['mean_ms']/1000:.2f}s" if row["mean_ms"] else "-"
            p95 = f"{row['p95_ms']/1000:.2f}s" if row["p95_ms"] else "-"
            lines.append(
                f"| {row['model']} | {row['accuracy_percent']:.1f} | "
                f"{row['success_count']}/{row['scored_count']} | {median} | {mean} | {p95} | "
                f"{row['latency_score']:.1f} |"
            )
        lines.append("")

    if models:
        lines.append("## Soru Bazlı Sonuç Matrisi")
        header = "| Soru ID | Kategori | " + " | ".join(models) + " |"
        separator = "|---|---|" + "---|" * len(models)
        lines.append(header)
        lines.append(separator)
        for question in questions:
            row = [
                question["id"],
                question.get("category", "GENEL"),
            ]
            for model in models:
                record = record_by_key.get((question["id"], model))
                row.append(format_cell(record))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
