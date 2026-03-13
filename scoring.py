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


def evaluate_response(expected_answer: str, response: str) -> dict[str, Any]:
    expected = (expected_answer or "").strip()
    model_response = (response or "").strip()
    if not expected:
        return {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": "Beklenen cevap boş.",
        }
    if not model_response:
        return {
            "status": "fail",
            "score": 0,
            "auto_scored": True,
            "reason": "Boş model yanıtı.",
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
            "reason": "Sayısal karşılaştırma yapıldı.",
        }

    similarity = fuzz.token_set_ratio(normalize_text(expected), normalize_text(model_response))
    ok = similarity >= 82
    return {
        "status": "success" if ok else "fail",
        "score": 1 if ok else 0,
        "auto_scored": True,
        "reason": f"Metin benzerliği: {similarity:.1f}",
    }
