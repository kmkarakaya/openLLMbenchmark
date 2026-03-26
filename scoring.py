from __future__ import annotations

import math
import re
from typing import Any

from rapidfuzz import fuzz


NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("ı", "i")
    value = re.sub(r"\s+", " ", value)
    return value


def extract_first_number(value: str) -> float | None:
    match = NUMBER_RE.search(value)
    if not match:
        return None
    raw = match.group(0).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def normalize_reason_text(reason: str) -> str:
    raw = (reason or "").strip()
    if not raw:
        return raw

    lower = raw.lower()

    if lower.startswith("hata:") or lower.startswith("error:"):
        return f"Error: {raw.split(':', 1)[1].strip()}" if ":" in raw else "Error"

    if lower == "expected answer is empty." or ("beklenen" in lower and "cevap" in lower and "bo" in lower):
        return "Expected answer is empty."

    if lower == "empty model response." or (
        "model" in lower
        and ("yanıt" in lower or "yanit" in lower or "response" in lower)
        and ("bo" in lower or "empty" in lower)
    ):
        return "Empty model response."

    if "numeric comparison applied" in lower or ("say" in lower and "kar" in lower and "yap" in lower):
        return "Numeric comparison applied."

    if lower.startswith("text similarity") or lower.startswith("metin benzerli"):
        suffix = raw.split(":", 1)[1].strip() if ":" in raw else ""
        return f"Text similarity: {suffix}" if suffix else "Text similarity."

    if lower == "user approval" or ("kullan" in lower and "onay" in lower):
        return "User approval"

    if "durdur" in lower or "stopped by user" in lower:
        return "Stopped by user."

    return raw


def evaluate_response(expected_answer: str, response: str) -> dict[str, Any]:
    expected = (expected_answer or "").strip()
    model_response = (response or "").strip()
    if not expected:
        return {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": normalize_reason_text("Expected answer is empty."),
        }
    if not model_response:
        return {
            "status": "fail",
            "score": 0,
            "auto_scored": True,
            "reason": normalize_reason_text("Empty model response."),
        }

    expected_number = extract_first_number(expected)
    response_number = extract_first_number(model_response)
    if expected_number is not None and response_number is not None:
        tolerance = max(0.001, abs(expected_number) * 0.001)
        ok = math.isclose(expected_number, response_number, rel_tol=0.001, abs_tol=tolerance)
        return {
            "status": "success" if ok else "fail",
            "score": 1 if ok else 0,
            "auto_scored": True,
            "reason": normalize_reason_text("Numeric comparison applied."),
        }

    similarity = fuzz.token_set_ratio(normalize_text(expected), normalize_text(model_response))
    ok = similarity >= 82
    return {
        "status": "success" if ok else "fail",
        "score": 1 if ok else 0,
        "auto_scored": True,
        "reason": normalize_reason_text(f"Text similarity: {similarity:.1f}"),
    }
