from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from engine import get_client, stream_chat


@dataclass
class ModelRunState:
    model: str = ""
    trace_id: str = ""
    session_id: str = ""
    dataset_key: str = ""
    question_id: str = ""
    response: str = ""
    running: bool = False
    completed: bool = False
    interrupted: bool = False
    error: str = ""
    event: str = "idle"
    started_at: float = 0.0
    ended_at: float = 0.0


@dataclass
class LiveRunState:
    run_id: int = 0
    trace_id: str = ""
    session_id: str = ""
    dataset_key: str = ""
    running: bool = False
    completed: bool = False
    question_id: str = ""
    prompt: str = ""
    entries: dict[str, ModelRunState] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)
    threads: list[threading.Thread] = field(default_factory=list)


class LiveRunner:
    def __init__(self) -> None:
        self.state = LiveRunState()

    def start(
        self,
        models: list[str],
        question_id: str,
        prompt: str,
        system_prompt: str,
        *,
        session_id: str = "",
        dataset_key: str = "",
        trace_id: str = "",
    ) -> bool:
        normalized_models: list[str] = []
        seen_models: set[str] = set()
        for model in models:
            normalized = str(model).strip()
            if not normalized or normalized in seen_models:
                continue
            normalized_models.append(normalized)
            seen_models.add(normalized)

        if not normalized_models:
            return False

        with self.state.lock:
            if self.state.running:
                return False
            self.state.run_id += 1
            self.state.running = True
            self.state.completed = False
            self.state.trace_id = trace_id
            self.state.session_id = session_id
            self.state.dataset_key = dataset_key
            self.state.question_id = question_id
            self.state.prompt = prompt
            self.state.stop_event = threading.Event()
            self.state.entries = {}
            self.state.threads = []
            started_at = time.perf_counter()
            for model in normalized_models:
                self.state.entries[model] = ModelRunState(
                    model=model,
                    trace_id=trace_id,
                    session_id=session_id,
                    dataset_key=dataset_key,
                    question_id=question_id,
                    running=True,
                    event="run_started",
                    started_at=started_at,
                )
            run_id = self.state.run_id

        for model in normalized_models:
            thread = threading.Thread(
                target=self._run_worker,
                args=(run_id, model, prompt, system_prompt),
                daemon=True,
            )
            self.state.threads.append(thread)
            thread.start()
        return True

    def request_stop(self) -> None:
        self.state.stop_event.set()

    def _run_worker(self, run_id: int, model: str, prompt: str, system_prompt: str) -> None:
        interrupted = False
        error = ""
        chunks: list[str] = []
        try:
            client = get_client()
            for chunk in stream_chat(client=client, model=model, prompt=prompt, system_prompt=system_prompt):
                if self.state.stop_event.is_set():
                    interrupted = True
                    break
                chunks.append(chunk)
                with self.state.lock:
                    if run_id != self.state.run_id:
                        return
                    entry = self.state.entries.get(model)
                    if entry is None:
                        return
                    entry.response = "".join(chunks)
                    entry.event = "chunk"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        end_time = time.perf_counter()
        with self.state.lock:
            if run_id != self.state.run_id:
                return
            entry = self.state.entries.get(model)
            if entry is None:
                return
            entry.response = "".join(chunks)
            entry.error = error
            entry.interrupted = interrupted
            entry.running = False
            entry.completed = True
            if error:
                entry.event = "run_error"
            elif interrupted:
                entry.event = "run_interrupted"
            else:
                entry.event = "entry_completed"
            entry.ended_at = end_time
            entries = list(self.state.entries.values())
            self.state.running = any(item.running for item in entries)
            self.state.completed = bool(entries) and all(item.completed for item in entries)

    def snapshot(self) -> dict[str, Any]:
        with self.state.lock:
            now = time.perf_counter()
            entries: list[dict[str, Any]] = []
            for entry in self.state.entries.values():
                elapsed_ms = 0.0
                if entry.started_at:
                    endpoint = now if entry.running else (entry.ended_at or now)
                    elapsed_ms = max(0.0, (endpoint - entry.started_at) * 1000.0)
                entries.append(
                    {
                        "model": entry.model,
                        "trace_id": entry.trace_id,
                        "session_id": entry.session_id,
                        "dataset_key": entry.dataset_key,
                        "question_id": entry.question_id,
                        "running": entry.running,
                        "completed": entry.completed,
                        "interrupted": entry.interrupted,
                        "error": entry.error,
                        "event": entry.event,
                        "response": entry.response,
                        "elapsed_ms": elapsed_ms,
                    }
                )
            return {
                "run_id": self.state.run_id,
                "trace_id": self.state.trace_id,
                "session_id": self.state.session_id,
                "dataset_key": self.state.dataset_key,
                "running": self.state.running,
                "completed": self.state.completed,
                "question_id": self.state.question_id,
                "prompt": self.state.prompt,
                "entries": entries,
            }


_RUNNERS: dict[str, LiveRunner] = {}
_RUNNERS_LOCK = threading.Lock()


def get_runner(session_id: str) -> LiveRunner:
    with _RUNNERS_LOCK:
        if session_id not in _RUNNERS:
            _RUNNERS[session_id] = LiveRunner()
        return _RUNNERS[session_id]
