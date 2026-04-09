from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from engine import get_client_for_source, stream_chat_events
from model_identity import resolve_model_host, split_model_ref, to_model_ref


@dataclass
class ModelRunState:
    model: str = ""
    model_name: str = ""
    source: str = "cloud"
    host: str = ""
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
    generated_tokens: int | None = None
    prompt_tokens: int | None = None


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
        ollama_api_key: str = "",
    ) -> bool:
        normalized_targets: list[dict[str, str]] = []
        seen_refs: set[str] = set()
        for raw_model in models:
            model_name, source = split_model_ref(str(raw_model).strip())
            if not model_name:
                continue
            model_ref = to_model_ref(model_name, source)
            if not model_ref or model_ref in seen_refs:
                continue
            seen_refs.add(model_ref)
            normalized_targets.append(
                {
                    "model": model_name,
                    "source": source,
                    "host": resolve_model_host(source),
                    "ref": model_ref,
                }
            )

        if not normalized_targets:
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
            for target in normalized_targets:
                model_ref = target["ref"]
                self.state.entries[model_ref] = ModelRunState(
                    model=model_ref,
                    model_name=target["model"],
                    source=target["source"],
                    host=target["host"],
                    trace_id=trace_id,
                    session_id=session_id,
                    dataset_key=dataset_key,
                    question_id=question_id,
                    running=True,
                    event="run_started",
                    started_at=started_at,
                )
            run_id = self.state.run_id

        for target in normalized_targets:
            thread = threading.Thread(
                target=self._run_worker,
                args=(run_id, target, prompt, system_prompt, ollama_api_key),
                daemon=True,
            )
            self.state.threads.append(thread)
            thread.start()
        return True

    def request_stop(self) -> None:
        with self.state.lock:
            self.state.stop_event.set()
            if not self.state.entries:
                self.state.running = False
                self.state.completed = False
                return

            end_time = time.perf_counter()
            for entry in self.state.entries.values():
                if entry.running and not entry.completed:
                    entry.running = False
                    entry.completed = True
                    entry.interrupted = True
                    entry.event = "run_interrupted"
                    entry.ended_at = end_time

            entries = list(self.state.entries.values())
            self.state.running = any(item.running for item in entries)
            self.state.completed = bool(entries) and all(item.completed for item in entries)

    def _run_worker(self, run_id: int, target: dict[str, str], prompt: str, system_prompt: str, ollama_api_key: str = "") -> None:
        model_ref = target["ref"]
        model_name = target["model"]
        source = target["source"]
        host = target["host"]
        interrupted = False
        error = ""
        chunks: list[str] = []
        try:
            client = get_client_for_source(source=source, host=host, api_key=ollama_api_key)
            for event in stream_chat_events(client=client, model=model_name, prompt=prompt, system_prompt=system_prompt):
                if self.state.stop_event.is_set():
                    interrupted = True
                    break
                if event.content:
                    chunks.append(event.content)
                with self.state.lock:
                    if run_id != self.state.run_id:
                        return
                    entry = self.state.entries.get(model_ref)
                    if entry is None:
                        return
                    entry.response = "".join(chunks)
                    if event.generated_tokens is not None:
                        entry.generated_tokens = event.generated_tokens
                    if event.prompt_tokens is not None:
                        entry.prompt_tokens = event.prompt_tokens
                    if event.content:
                        entry.event = "chunk"
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        end_time = time.perf_counter()
        with self.state.lock:
            if run_id != self.state.run_id:
                return
            entry = self.state.entries.get(model_ref)
            if entry is None:
                return
            entry.response = "".join(chunks)
            entry.error = error
            previously_interrupted = entry.interrupted
            entry.interrupted = interrupted or previously_interrupted
            entry.running = False
            entry.completed = True
            if error:
                entry.event = "run_error"
            elif entry.interrupted:
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
                        "model_name": entry.model_name,
                        "source": entry.source,
                        "host": entry.host,
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
                        "generated_tokens": entry.generated_tokens,
                        "prompt_tokens": entry.prompt_tokens,
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
