from __future__ import annotations

import time
import uuid
from dataclasses import dataclass


SCHEMA_VERSION = "v1"


@dataclass(frozen=True)
class LogContext:
    trace_id: str
    run_id: int | None
    session_id: str
    dataset_key: str
    question_id: str
    model: str
    event: str
    elapsed_ms: float


def build_log_context(
    *,
    session_id: str,
    dataset_key: str,
    question_id: str,
    model: str,
    event: str,
    started_at: float | None = None,
    run_id: int | None = None,
    trace_id: str | None = None,
) -> LogContext:
    if started_at is None:
        elapsed_ms = 0.0
    else:
        elapsed_ms = max(0.0, (time.perf_counter() - started_at) * 1000.0)
    return LogContext(
        trace_id=(trace_id or uuid.uuid4().hex),
        run_id=run_id,
        session_id=session_id,
        dataset_key=dataset_key,
        question_id=question_id,
        model=model,
        event=event,
        elapsed_ms=round(elapsed_ms, 2),
    )
