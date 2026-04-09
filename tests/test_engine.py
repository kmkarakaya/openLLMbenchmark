from __future__ import annotations

import pytest

from engine import ChatStreamEvent, get_cloud_client, get_local_client, list_models, stream_chat, stream_chat_events


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Chunk:
    def __init__(
        self,
        content: str = "",
        response: str = "",
        *,
        done: bool = False,
        eval_count: int | None = None,
        prompt_eval_count: int | None = None,
    ) -> None:
        self.message = _Message(content) if content else None
        self.response = response
        self.done = done
        self.eval_count = eval_count
        self.prompt_eval_count = prompt_eval_count


class _ModelItem:
    def __init__(self, model: str) -> None:
        self.model = model


class _ListPayload:
    def __init__(self, models: list[_ModelItem]) -> None:
        self.models = models


class _ClientForStream:
    def chat(self, **_: object):  # type: ignore[no-untyped-def]
        return iter(
            [
                _Chunk(content="Merhaba "),
                _Chunk(content="dünya"),
                {"message": {"content": "!"}},
                {"done": True, "eval_count": 3, "prompt_eval_count": 5},
            ]
        )


class _ClientForModels:
    def list(self):  # type: ignore[no-untyped-def]
        return _ListPayload([_ModelItem("llama3"), _ModelItem("qwen3")])


class _FailingClientForModels:
    def list(self):  # type: ignore[no-untyped-def]
        raise RuntimeError("offline")


def test_stream_chat_handles_object_and_dict_chunks() -> None:
    client = _ClientForStream()
    parts = list(stream_chat(client=client, model="x", prompt="p", system_prompt="s"))  # type: ignore[arg-type]
    assert "".join(parts) == "Merhaba dünya!"


def test_stream_chat_events_preserve_final_usage_metadata() -> None:
    client = _ClientForStream()
    events = list(stream_chat_events(client=client, model="x", prompt="p", system_prompt="s"))  # type: ignore[arg-type]

    assert events[-1] == ChatStreamEvent(content="", done=True, generated_tokens=3, prompt_tokens=5)
    assert "".join(event.content for event in events) == "Merhaba dünya!"


def test_list_models_handles_object_payload() -> None:
    client = _ClientForModels()
    names = list_models(client=client)  # type: ignore[arg-type]
    assert names == ["llama3", "qwen3"]


def test_get_cloud_client_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        get_cloud_client()


def test_get_local_client_uses_default_host_without_auth(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)

    monkeypatch.setattr("engine.Client", _FakeClient)
    get_local_client()
    assert captured["host"] == "http://localhost:11434"
    assert "headers" not in captured


def test_list_models_tolerates_local_errors() -> None:
    client = _FailingClientForModels()
    assert list_models(client=client, source="local") == []  # type: ignore[arg-type]


def test_list_models_raises_for_cloud_errors() -> None:
    client = _FailingClientForModels()
    with pytest.raises(RuntimeError):
        list_models(client=client, source="cloud")  # type: ignore[arg-type]
