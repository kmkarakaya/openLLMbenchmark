from __future__ import annotations

import os
from typing import Mapping

CLOUD_SOURCE = "cloud"
LOCAL_SOURCE = "local"
SUPPORTED_SOURCES = {CLOUD_SOURCE, LOCAL_SOURCE}

DEFAULT_CLOUD_HOST = "https://ollama.com"
DEFAULT_LOCAL_HOST = "http://localhost:11434"


def normalize_model_source(source: str | None, *, default: str = CLOUD_SOURCE) -> str:
    candidate = str(source or "").strip().lower()
    if candidate in SUPPORTED_SOURCES:
        return candidate
    return default


def split_model_ref(value: str, default_source: str = CLOUD_SOURCE) -> tuple[str, str]:
    raw = str(value or "").strip()
    fallback_source = normalize_model_source(default_source)
    if not raw:
        return "", fallback_source

    lowered = raw.lower()
    for source in (CLOUD_SOURCE, LOCAL_SOURCE):
        suffix = f":{source}"
        if lowered.endswith(suffix):
            model_name = raw[: -len(suffix)].strip()
            if model_name:
                return model_name, source
    return raw, fallback_source


def _explicit_model_source(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    lowered = raw.lower()
    for source in (CLOUD_SOURCE, LOCAL_SOURCE):
        suffix = f":{source}"
        if lowered.endswith(suffix) and raw[: -len(suffix)].strip():
            return source
    return None


def to_model_ref(model: str, source: str | None = None) -> str:
    source_hint = normalize_model_source(source)
    base_model, detected_source = split_model_ref(model, default_source=source_hint)
    if not base_model:
        return ""
    explicit_source = _explicit_model_source(model)
    if explicit_source is not None:
        final_source = explicit_source
    else:
        final_source = normalize_model_source(source, default=detected_source)
    return f"{base_model}:{final_source}"


def resolve_model_host(source: str, *, cloud_host: str | None = None, local_host: str | None = None) -> str:
    normalized_source = normalize_model_source(source)
    if normalized_source == LOCAL_SOURCE:
        resolved_local = str(local_host or os.getenv("OLLAMA_LOCAL_HOST", "")).strip()
        return resolved_local or DEFAULT_LOCAL_HOST
    resolved_cloud = str(cloud_host or os.getenv("OLLAMA_HOST", "")).strip()
    return resolved_cloud or DEFAULT_CLOUD_HOST


def model_ref_from_record(record: Mapping[str, object], default_source: str = CLOUD_SOURCE) -> str:
    model = str(record.get("model", "") or "").strip()
    explicit_source = str(record.get("model_source", "") or "").strip().lower()
    if explicit_source in SUPPORTED_SOURCES:
        return to_model_ref(model, explicit_source)

    lowered = model.lower()
    if lowered.endswith(f":{CLOUD_SOURCE}") or lowered.endswith(f":{LOCAL_SOURCE}"):
        return to_model_ref(model)

    return to_model_ref(model, default_source)
