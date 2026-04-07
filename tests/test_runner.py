import time

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
    monkeypatch.setattr("runner.get_client", lambda: object())
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

    entries = {entry["model"]: entry for entry in snapshot["entries"]}  # type: ignore[index]
    assert entries["gemma3:4b"]["response"] == "Merhaba"
    assert entries["qwen3:8b"]["response"] == "Dünya"
    assert entries["gemma3:4b"]["elapsed_ms"] >= 0
    assert entries["qwen3:8b"]["elapsed_ms"] >= 0
    assert snapshot["trace_id"] == "trace-123"
    assert snapshot["session_id"] == "session-a"
    assert snapshot["dataset_key"] == "default_tr"
    assert entries["gemma3:4b"]["trace_id"] == "trace-123"
    assert entries["gemma3:4b"]["session_id"] == "session-a"
    assert entries["gemma3:4b"]["dataset_key"] == "default_tr"
    assert entries["gemma3:4b"]["question_id"] == "q001"
    assert entries["gemma3:4b"]["event"] in {"entry_completed", "run_error", "run_interrupted"}


def test_runner_stop_interrupts_all_models(monkeypatch) -> None:
    monkeypatch.setattr("runner.get_client", lambda: object())

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

    snapshot = wait_until_completed(live_runner)
    entries = snapshot["entries"]  # type: ignore[index]
    assert snapshot["completed"] is True
    assert snapshot["running"] is False
    assert all(entry["interrupted"] for entry in entries)
