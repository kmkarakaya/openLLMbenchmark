from __future__ import annotations

import os
from typing import Iterator

from ollama import Client


DEFAULT_HOST = "https://ollama.com"


def get_client() -> Client:
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set.")
    host = os.getenv("OLLAMA_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    return Client(host=host, headers={"Authorization": f"Bearer {api_key}"})


def list_models(client: Client) -> list[str]:
    payload = client.list()
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
