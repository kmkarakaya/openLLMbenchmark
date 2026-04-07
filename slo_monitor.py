from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone


WINDOW_SECONDS = 15 * 60
MAX_HISTORY = 10_000
DISCONNECT_ERROR_THRESHOLD = 0.01
RUN_SUCCESS_THRESHOLD = 0.99
P95_CHUNK_GAP_THRESHOLD_MS = 2000.0


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (pct / 100) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return ordered[low]
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


@dataclass(frozen=True)
class SloSnapshot:
    window_minutes: int
    sse_disconnect_error_rate: float
    run_completion_success_rate: float
    p95_chunk_gap_ms: float
    breached: bool
    evaluated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "window_minutes": self.window_minutes,
            "sse_disconnect_error_rate": self.sse_disconnect_error_rate,
            "run_completion_success_rate": self.run_completion_success_rate,
            "p95_chunk_gap_ms": self.p95_chunk_gap_ms,
            "breached": self.breached,
            "evaluated_at": self.evaluated_at,
        }


class SloMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connection_opened: deque[float] = deque()
        self._connection_errors: deque[float] = deque()
        self._connection_disconnects: deque[float] = deque()
        self._run_outcomes: deque[tuple[float, bool]] = deque()
        self._chunk_gaps_ms: deque[tuple[float, float]] = deque()
        self._stream_last_chunk_at: dict[str, float] = {}
        self._seen_run_keys: dict[str, float] = {}

    def reset(self) -> None:
        with self._lock:
            self._connection_opened.clear()
            self._connection_errors.clear()
            self._connection_disconnects.clear()
            self._run_outcomes.clear()
            self._chunk_gaps_ms.clear()
            self._stream_last_chunk_at.clear()
            self._seen_run_keys.clear()

    def register_stream_open(self, stream_key: str) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            self._connection_opened.append(now)
            self._stream_last_chunk_at[stream_key] = 0.0
            self._trim_history()

    def register_stream_disconnect(self, stream_key: str) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            self._connection_disconnects.append(now)
            self._stream_last_chunk_at.pop(stream_key, None)
            self._trim_history()

    def register_stream_error(self, stream_key: str) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            self._connection_errors.append(now)
            self._stream_last_chunk_at.pop(stream_key, None)
            self._trim_history()

    def register_stream_closed(self, stream_key: str) -> None:
        with self._lock:
            self._stream_last_chunk_at.pop(stream_key, None)

    def register_chunk(self, stream_key: str) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            previous = self._stream_last_chunk_at.get(stream_key, 0.0)
            if previous > 0:
                gap_ms = max(0.0, (now - previous) * 1000.0)
                self._chunk_gaps_ms.append((now, gap_ms))
            self._stream_last_chunk_at[stream_key] = now
            self._trim_history()

    def register_run_outcome(self, run_key: str, *, success: bool) -> None:
        now = time.time()
        with self._lock:
            self._prune(now)
            if run_key in self._seen_run_keys:
                return
            self._seen_run_keys[run_key] = now
            self._run_outcomes.append((now, success))
            self._trim_history()

    def snapshot(self) -> SloSnapshot:
        now = time.time()
        with self._lock:
            self._prune(now)
            opened = len(self._connection_opened)
            errored_or_disconnected = len(self._connection_errors) + len(self._connection_disconnects)
            disconnect_error_rate = (errored_or_disconnected / opened) if opened else 0.0

            outcomes = [ok for _, ok in self._run_outcomes]
            run_success_rate = (sum(1 for ok in outcomes if ok) / len(outcomes)) if outcomes else 1.0

            chunk_gaps = [gap for _, gap in self._chunk_gaps_ms]
            p95_gap_ms = _percentile(chunk_gaps, 95) if chunk_gaps else 0.0

            breached = (
                disconnect_error_rate > DISCONNECT_ERROR_THRESHOLD
                or run_success_rate < RUN_SUCCESS_THRESHOLD
                or p95_gap_ms > P95_CHUNK_GAP_THRESHOLD_MS
            )
        return SloSnapshot(
            window_minutes=WINDOW_SECONDS // 60,
            sse_disconnect_error_rate=round(disconnect_error_rate, 6),
            run_completion_success_rate=round(run_success_rate, 6),
            p95_chunk_gap_ms=round(float(p95_gap_ms), 3),
            breached=breached,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _trim_history(self) -> None:
        while len(self._connection_opened) > MAX_HISTORY:
            self._connection_opened.popleft()
        while len(self._connection_errors) > MAX_HISTORY:
            self._connection_errors.popleft()
        while len(self._connection_disconnects) > MAX_HISTORY:
            self._connection_disconnects.popleft()
        while len(self._run_outcomes) > MAX_HISTORY:
            self._run_outcomes.popleft()
        while len(self._chunk_gaps_ms) > MAX_HISTORY:
            self._chunk_gaps_ms.popleft()
        if len(self._seen_run_keys) > MAX_HISTORY:
            oldest_cutoff = time.time() - WINDOW_SECONDS
            self._seen_run_keys = {
                key: ts for key, ts in self._seen_run_keys.items() if ts >= oldest_cutoff
            }

    def _prune(self, now: float) -> None:
        cutoff = now - WINDOW_SECONDS
        while self._connection_opened and self._connection_opened[0] < cutoff:
            self._connection_opened.popleft()
        while self._connection_errors and self._connection_errors[0] < cutoff:
            self._connection_errors.popleft()
        while self._connection_disconnects and self._connection_disconnects[0] < cutoff:
            self._connection_disconnects.popleft()
        while self._run_outcomes and self._run_outcomes[0][0] < cutoff:
            self._run_outcomes.popleft()
        while self._chunk_gaps_ms and self._chunk_gaps_ms[0][0] < cutoff:
            self._chunk_gaps_ms.popleft()
        if self._seen_run_keys:
            self._seen_run_keys = {
                key: ts for key, ts in self._seen_run_keys.items() if ts >= cutoff
            }


_SLO_MONITOR = SloMonitor()


def get_slo_monitor() -> SloMonitor:
    return _SLO_MONITOR

