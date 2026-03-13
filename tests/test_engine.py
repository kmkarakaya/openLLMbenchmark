from __future__ import annotations

from engine import list_models, stream_chat


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Chunk:
    def __init__(self, content: str = "", response: str = "") -> None:
        self.message = _Message(content) if content else None
        self.response = response


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
            ]
        )


class _ClientForModels:
    def list(self):  # type: ignore[no-untyped-def]
        return _ListPayload([_ModelItem("llama3"), _ModelItem("qwen3")])


def test_stream_chat_handles_object_and_dict_chunks() -> None:
    client = _ClientForStream()
    parts = list(stream_chat(client=client, model="x", prompt="p", system_prompt="s"))  # type: ignore[arg-type]
    assert "".join(parts) == "Merhaba dünya!"


def test_list_models_handles_object_payload() -> None:
    client = _ClientForModels()
    names = list_models(client=client)  # type: ignore[arg-type]
    assert names == ["llama3", "qwen3"]
