from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ID_PATTERN = re.compile(r"^q\d{3,}$")
DEFAULT_SYSTEM_PROMPT = "Sen Türkçe konuşan bir botsun. Tüm yanıtlarını yalnızca Türkçe ver."


class DatasetValidationError(ValueError):
    pass


def _load_raw_dataset(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _extract_records(raw_payload: Any) -> list[dict[str, Any]]:
    if isinstance(raw_payload, list):
        return raw_payload
    if isinstance(raw_payload, dict) and isinstance(raw_payload.get("questions"), list):
        return raw_payload["questions"]
    raise DatasetValidationError(
        "benchmark.json must be either a list of questions or an object with a 'questions' list."
    )


def _require_text_field(record: dict[str, Any], field_name: str, index: int) -> str:
    if field_name not in record:
        raise DatasetValidationError(f"Record #{index} is missing required field '{field_name}'.")
    value = str(record.get(field_name, "")).strip()
    if not value:
        raise DatasetValidationError(f"Record #{index} has empty '{field_name}'.")
    return value


def validate_question_records(records: list[dict[str, Any]]) -> None:
    seen_ids: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise DatasetValidationError(f"Record #{index} must be an object.")

        question_id = _require_text_field(record, "id", index)
        if not ID_PATTERN.match(question_id):
            raise DatasetValidationError(
                f"Record #{index} has invalid id '{question_id}'. Expected format like q001."
            )
        if question_id in seen_ids:
            raise DatasetValidationError(f"Duplicate question id found: {question_id}")
        seen_ids.add(question_id)

        _require_text_field(record, "question", index)
        _require_text_field(record, "expected_answer", index)


def load_benchmark_payload(dataset_path: Path) -> dict[str, Any]:
    raw_payload = _load_raw_dataset(dataset_path)
    records = _extract_records(raw_payload)
    validate_question_records(records)

    questions: list[dict[str, Any]] = []
    for record in records:
        questions.append(
            {
                "id": str(record["id"]).strip(),
                "prompt": str(record["question"]).strip(),
                "expected_answer": str(record["expected_answer"]).strip(),
                "category": str(record.get("topic", "GENEL")).strip() or "GENEL",
                "expected_source": "benchmark_json",
                "confidence": 1.0,
                "hardness_level": str(record.get("hardness_level", "")).strip(),
                "why_prepared": str(record.get("why_prepared", "")).strip(),
            }
        )

    return {"instruction": DEFAULT_SYSTEM_PROMPT, "questions": questions}


def save_expected_answer(dataset_path: Path, question_id: str, expected_answer: str) -> None:
    normalized_answer = expected_answer.strip()
    if not normalized_answer:
        raise DatasetValidationError("expected_answer cannot be empty.")

    raw_payload = _load_raw_dataset(dataset_path)
    records = _extract_records(raw_payload)
    validate_question_records(records)

    found = False
    for record in records:
        if str(record.get("id", "")).strip() == question_id:
            record["expected_answer"] = normalized_answer
            found = True
            break

    if not found:
        raise KeyError(f"Question id not found: {question_id}")

    with dataset_path.open("w", encoding="utf-8") as file:
        json.dump(raw_payload, file, ensure_ascii=False, indent=2)


def backfill_missing_ids(dataset_path: Path) -> None:
    raw_payload = _load_raw_dataset(dataset_path)
    records = _extract_records(raw_payload)

    existing_numbers: set[int] = set()
    for record in records:
        raw_id = str(record.get("id", "")).strip()
        if ID_PATTERN.match(raw_id):
            existing_numbers.add(int(raw_id[1:]))

    next_number = 1 if not existing_numbers else (max(existing_numbers) + 1)
    changed = False

    for index, record in enumerate(records, start=1):
        raw_id = str(record.get("id", "")).strip()
        if raw_id:
            continue

        candidate_number = index if not existing_numbers else next_number
        while candidate_number in existing_numbers:
            candidate_number += 1

        record["id"] = f"q{candidate_number:03d}"
        existing_numbers.add(candidate_number)
        next_number = candidate_number + 1
        changed = True

    validate_question_records(records)

    if changed:
        with dataset_path.open("w", encoding="utf-8") as file:
            json.dump(raw_payload, file, ensure_ascii=False, indent=2)
