import time

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
    monkeypatch.setattr("runner.get_client_for_source", lambda source, host=None: object())
    response_parts = {
        "gemma3:4b": ["Mer", "haba"],
        "qwen3:8b": ["Dün", "ya"],
    }

    def fake_stream_chat(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, prompt, system_prompt
        for part in response_parts[model]:
            time.sleep(0.01)
            yield part

    monkeypatch.setattr("runner.stream_chat", fake_stream_chat)

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
    assert entries[model_1_ref]["event"] in {"entry_completed", "run_error", "run_interrupted"}


def test_runner_stop_interrupts_all_models(monkeypatch) -> None:
    monkeypatch.setattr("runner.get_client_for_source", lambda source, host=None: object())

    def slow_stream_chat(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, model, prompt, system_prompt
        for _ in range(20):
            time.sleep(0.01)
            yield "x"

    monkeypatch.setattr("runner.stream_chat", slow_stream_chat)

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
    monkeypatch.setattr("runner.get_client_for_source", lambda source, host=None: object())

    def fake_stream_chat(*, client, model, prompt, system_prompt):  # type: ignore[no-untyped-def]
        del client, prompt, system_prompt
        yield f"{model}-ok"

    monkeypatch.setattr("runner.stream_chat", fake_stream_chat)

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
