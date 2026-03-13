from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.benchmark import (
    DatasetValidationError,
    backfill_missing_ids,
    load_benchmark_payload,
    save_expected_answer,
)


def test_load_benchmark_payload_with_valid_ids(tmp_path: Path) -> None:
    dataset = [
        {
            "id": "q001",
            "question": "Soru 1?",
            "expected_answer": "A",
            "topic": "Türkçe",
        },
        {
            "id": "q002",
            "question": "Soru 2?",
            "expected_answer": "B",
            "topic": "Mantık",
        },
    ]
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    payload = load_benchmark_payload(path)
    assert len(payload["questions"]) == 2
    assert payload["questions"][0]["id"] == "q001"
    assert payload["questions"][0]["prompt"] == "Soru 1?"


def test_duplicate_id_fails_validation(tmp_path: Path) -> None:
    dataset = [
        {"id": "q001", "question": "Soru 1?", "expected_answer": "A"},
        {"id": "q001", "question": "Soru 2?", "expected_answer": "B"},
    ]
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(DatasetValidationError):
        load_benchmark_payload(path)


def test_backfill_ids(tmp_path: Path) -> None:
    dataset = [
        {"question": "Soru 1?", "expected_answer": "A"},
        {"question": "Soru 2?", "expected_answer": "B"},
        {"id": "q020", "question": "Soru 3?", "expected_answer": "C"},
    ]
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    backfill_missing_ids(path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded[0]["id"] == "q021"
    assert loaded[1]["id"] == "q022"
    assert loaded[2]["id"] == "q020"


def test_save_expected_answer_rejects_empty_value(tmp_path: Path) -> None:
    dataset = [{"id": "q001", "question": "Soru 1?", "expected_answer": "A"}]
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(DatasetValidationError):
        save_expected_answer(path, "q001", "   ")
