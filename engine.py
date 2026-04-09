from __future__ import annotations

import os
from typing import Iterator

from ollama import Client

from model_identity import (
    CLOUD_SOURCE,
    LOCAL_SOURCE,
    normalize_model_source,
    resolve_model_host,
)


def get_cloud_client() -> Client:
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set.")
    host = resolve_model_host(CLOUD_SOURCE, cloud_host=os.getenv("OLLAMA_HOST", ""))
    return Client(host=host, headers={"Authorization": f"Bearer {api_key}"})


def get_local_client(host: str | None = None) -> Client:
    resolved_host = resolve_model_host(LOCAL_SOURCE, local_host=host)
    return Client(host=resolved_host)


def get_client_for_source(source: str, host: str | None = None) -> Client:
    normalized_source = normalize_model_source(source)
    if normalized_source == LOCAL_SOURCE:
        return get_local_client(host)
    return get_cloud_client()


def get_client() -> Client:
    # Backward-compatible alias for call sites that still use cloud-only path.
    return get_cloud_client()


def list_models(client: Client, *, source: str = CLOUD_SOURCE) -> list[str]:
    normalized_source = normalize_model_source(source)
    try:
        payload = client.list()
    except Exception:
        if normalized_source == LOCAL_SOURCE:
            return []
        raise

    models = []
    if isinstance(payload, dict):
        raw_models = payload.get("models", [])
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = getattr(payload, "models", []) or []

    for item in raw_models:
        if isinstance(item, dict):
            name = item.get("model") or item.get("name")
        else:
            name = getattr(item, "model", None) or getattr(item, "name", None)
        if name:
            models.append(str(name))
    return sorted(set(models))


def stream_chat(
    client: Client,
    model: str,
    prompt: str,
    system_prompt: str = "",
) -> Iterator[str]:
    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": prompt.strip()})

    stream = client.chat(model=model, messages=messages, stream=True)
    for chunk in stream:
        content = ""
        if isinstance(chunk, dict):
            message = chunk.get("message", {})
            if isinstance(message, dict):
                content = message.get("content", "") or ""
            if not content:
                content = chunk.get("response", "") or ""
        else:
            message = getattr(chunk, "message", None)
            if isinstance(message, dict):
                content = message.get("content", "") or ""
            elif message is not None:
                content = getattr(message, "content", "") or ""
            if not content:
                content = getattr(chunk, "response", "") or ""
        if content:
            yield content
