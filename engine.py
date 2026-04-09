from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterator

from ollama import Client

from model_identity import (
    CLOUD_SOURCE,
    LOCAL_SOURCE,
    normalize_model_source,
    resolve_model_host,
)


@dataclass(frozen=True)
class ChatStreamEvent:
    content: str = ""
    done: bool = False
    generated_tokens: int | None = None
    prompt_tokens: int | None = None


def _chunk_value(chunk: Any, key: str) -> Any:
    if isinstance(chunk, dict):
        return chunk.get(key)
    return getattr(chunk, key, None)


def _chunk_content(chunk: Any) -> str:
    content = ""
    message = _chunk_value(chunk, "message")
    if isinstance(message, dict):
        content = str(message.get("content", "") or "")
    elif message is not None:
        content = str(getattr(message, "content", "") or "")
    if not content:
        content = str(_chunk_value(chunk, "response") or "")
    return content


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


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


def stream_chat_events(
    client: Client,
    model: str,
    prompt: str,
    system_prompt: str = "",
) -> Iterator[ChatStreamEvent]:
    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": prompt.strip()})

    stream = client.chat(model=model, messages=messages, stream=True)
    for chunk in stream:
        content = _chunk_content(chunk)
        done = bool(_chunk_value(chunk, "done"))
        generated_tokens = _optional_int(_chunk_value(chunk, "eval_count"))
        prompt_tokens = _optional_int(_chunk_value(chunk, "prompt_eval_count"))
        if content or done or generated_tokens is not None or prompt_tokens is not None:
            yield ChatStreamEvent(
                content=content,
                done=done,
                generated_tokens=generated_tokens,
                prompt_tokens=prompt_tokens,
            )


def stream_chat(
    client: Client,
    model: str,
    prompt: str,
    system_prompt: str = "",
) -> Iterator[str]:
    for event in stream_chat_events(client=client, model=model, prompt=prompt, system_prompt=system_prompt):
        if event.content:
            yield event.content
