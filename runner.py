from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from engine import get_client, stream_chat


@dataclass
class LiveRunState:
    run_id: int = 0
    running: bool = False
    completed: bool = False
    interrupted: bool = False
    error: str = ""
    model: str = ""
    question_id: str = ""
    prompt: str = ""
    response: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None


class LiveRunner:
    def __init__(self) -> None:
        self.state = LiveRunState()

    def start(self, model: str, question_id: str, prompt: str, system_prompt: str) -> bool:
        with self.state.lock:
            if self.state.running:
                return False
            self.state.run_id += 1
            self.state.running = True
            self.state.completed = False
            self.state.interrupted = False
            self.state.error = ""
            self.state.model = model
            self.state.question_id = question_id
            self.state.prompt = prompt
            self.state.response = ""
            self.state.started_at = time.perf_counter()
            self.state.ended_at = 0.0
            self.state.stop_event = threading.Event()
            run_id = self.state.run_id

        thread = threading.Thread(
            target=self._run_worker,
            args=(run_id, model, prompt, system_prompt),
            daemon=True,
        )
        self.state.thread = thread
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
                    if run_id == self.state.run_id:
                        self.state.response = "".join(chunks)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        end_time = time.perf_counter()
        with self.state.lock:
            if run_id != self.state.run_id:
                return
            self.state.response = "".join(chunks)
            self.state.error = error
            self.state.interrupted = interrupted
            self.state.running = False
            self.state.completed = True
            self.state.ended_at = end_time

    def snapshot(self) -> dict[str, Any]:
        with self.state.lock:
            now = time.perf_counter()
            elapsed_ms = 0.0
            if self.state.started_at:
                endpoint = now if self.state.running else (self.state.ended_at or now)
                elapsed_ms = max(0.0, (endpoint - self.state.started_at) * 1000.0)
            return {
                "run_id": self.state.run_id,
                "running": self.state.running,
                "completed": self.state.completed,
                "interrupted": self.state.interrupted,
                "error": self.state.error,
                "model": self.state.model,
                "question_id": self.state.question_id,
                "prompt": self.state.prompt,
                "response": self.state.response,
                "elapsed_ms": elapsed_ms,
            }


_RUNNERS: dict[str, LiveRunner] = {}
_RUNNERS_LOCK = threading.Lock()


def get_runner(session_id: str) -> LiveRunner:
    with _RUNNERS_LOCK:
        if session_id not in _RUNNERS:
            _RUNNERS[session_id] = LiveRunner()
        return _RUNNERS[session_id]
