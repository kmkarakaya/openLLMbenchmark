import time

from engine import ChatStreamEvent
from model_identity import to_model_ref
from runner import LiveRunner


def wait_until_completed(live_runner: LiveRunner, timeout: float = 2.0) -> dict[str, object]:
    deadline = time.time() + timeout
    snapshot: dict[str, object] = {}
    while time.time() < deadline:
        snapshot = live_runner.snapshot()
        if snapshot.get("completed"):
            return snapshot
        time.sleep(0.01)
    return live_runner.snapshot()


def test_runner_collects_two_model_responses(monkeypatch) -> None:
    monkeypatch.setattr("runner.get_client_for_source", lambda source, host=None, api_key=None: object())
    response_parts = {
        "gemma3:4b": ["Mer", "haba"],
        "qwen3:8b": ["Dün", "ya"],
    }

    def fake_stream_chat_events(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, prompt, system_prompt
        for part in response_parts[model]:
            time.sleep(0.01)
            yield ChatStreamEvent(content=part)
        yield ChatStreamEvent(done=True, generated_tokens=len("".join(response_parts[model])), prompt_tokens=4)

    monkeypatch.setattr("runner.stream_chat_events", fake_stream_chat_events)

    live_runner = LiveRunner()
    started = live_runner.start(
        models=["gemma3:4b", "qwen3:8b"],
        question_id="q001",
        prompt="Merhaba?",
        system_prompt="Türkçe cevap ver.",
        session_id="session-a",
        dataset_key="default_tr",
        trace_id="trace-123",
    )

    assert started is True
    snapshot = wait_until_completed(live_runner)
    assert snapshot["running"] is False
    assert snapshot["completed"] is True

    model_1_ref = to_model_ref("gemma3:4b", "cloud")
    model_2_ref = to_model_ref("qwen3:8b", "cloud")
    entries = {entry["model"]: entry for entry in snapshot["entries"]}  # type: ignore[index]
    assert entries[model_1_ref]["response"] == "Merhaba"
    assert entries[model_2_ref]["response"] == "Dünya"
    assert entries[model_1_ref]["elapsed_ms"] >= 0
    assert entries[model_2_ref]["elapsed_ms"] >= 0
    assert snapshot["trace_id"] == "trace-123"
    assert snapshot["session_id"] == "session-a"
    assert snapshot["dataset_key"] == "default_tr"
    assert entries[model_1_ref]["trace_id"] == "trace-123"
    assert entries[model_1_ref]["session_id"] == "session-a"
    assert entries[model_1_ref]["dataset_key"] == "default_tr"
    assert entries[model_1_ref]["question_id"] == "q001"
    assert entries[model_1_ref]["source"] == "cloud"
    assert entries[model_1_ref]["generated_tokens"] == len("Merhaba")
    assert entries[model_1_ref]["prompt_tokens"] == 4
    assert entries[model_1_ref]["event"] in {"entry_completed", "run_error", "run_interrupted"}


def test_runner_stop_interrupts_all_models(monkeypatch) -> None:
    monkeypatch.setattr("runner.get_client_for_source", lambda source, host=None, api_key=None: object())

    def slow_stream_chat_events(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, model, prompt, system_prompt
        for _ in range(20):
            time.sleep(0.01)
            yield ChatStreamEvent(content="x")

    monkeypatch.setattr("runner.stream_chat_events", slow_stream_chat_events)

    live_runner = LiveRunner()
    started = live_runner.start(
        models=["gemma3:4b", "qwen3:8b"],
        question_id="q002",
        prompt="Dur?",
        system_prompt="Türkçe cevap ver.",
        session_id="session-b",
        dataset_key="default_tr",
        trace_id="trace-456",
    )

    assert started is True
    time.sleep(0.03)
    live_runner.request_stop()

    immediate_snapshot = live_runner.snapshot()
    assert immediate_snapshot["running"] is False
    assert immediate_snapshot["completed"] is True

    snapshot = wait_until_completed(live_runner)
    entries = snapshot["entries"]  # type: ignore[index]
    assert snapshot["completed"] is True
    assert snapshot["running"] is False
    assert all(entry["interrupted"] for entry in entries)


def test_runner_distinguishes_same_model_across_sources(monkeypatch) -> None:
    monkeypatch.setattr("runner.get_client_for_source", lambda source, host=None, api_key=None: object())

    def fake_stream_chat_events(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, prompt, system_prompt
        yield ChatStreamEvent(content=f"{model}-ok")
        yield ChatStreamEvent(done=True, generated_tokens=1, prompt_tokens=2)

    monkeypatch.setattr("runner.stream_chat_events", fake_stream_chat_events)

    live_runner = LiveRunner()
    started = live_runner.start(
        models=["gemma3:4b:cloud", "gemma3:4b:local"],
        question_id="q001",
        prompt="Ayni model?",
        system_prompt="",
        session_id="session-c",
        dataset_key="default_tr",
        trace_id="trace-789",
    )

    assert started is True
    snapshot = wait_until_completed(live_runner)
    entries = {entry["model"]: entry for entry in snapshot["entries"]}  # type: ignore[index]
    assert "gemma3:4b:cloud" in entries
    assert "gemma3:4b:local" in entries
    assert entries["gemma3:4b:cloud"]["source"] == "cloud"
    assert entries["gemma3:4b:local"]["source"] == "local"
    assert entries["gemma3:4b:cloud"]["generated_tokens"] == 1


def test_runner_passes_request_scoped_api_key_to_cloud_client(monkeypatch) -> None:
    captured: list[tuple[str, str | None, str | None]] = []

    def fake_get_client_for_source(source, host=None, api_key=None):  # type: ignore[no-untyped-def]
        captured.append((source, host, api_key))
        return object()

    def fake_stream_chat_events(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, model, prompt, system_prompt
        yield ChatStreamEvent(done=True, generated_tokens=1, prompt_tokens=1)

    monkeypatch.setattr("runner.get_client_for_source", fake_get_client_for_source)
    monkeypatch.setattr("runner.stream_chat_events", fake_stream_chat_events)

    live_runner = LiveRunner()
    started = live_runner.start(
        models=["gemma3:4b:cloud"],
        question_id="q001",
        prompt="Prompt?",
        system_prompt="",
        session_id="session-d",
        dataset_key="default_tr",
        trace_id="trace-abc",
        ollama_api_key="session-key",
    )

    assert started is True
    wait_until_completed(live_runner)
    assert captured == [("cloud", "https://ollama.com", "session-key")]
