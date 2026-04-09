from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api_service import (
    apply_manual_result_override,
    delete_model_results,
    delete_dataset,
    export_results,
    export_results_table,
    get_datasets,
    get_dataset_template,
    get_health,
    get_ollama_auth_status,
    get_models,
    get_questions,
    get_results,
    get_run_status,
    run_snapshot,
    start_run,
    stop_run,
    upload_dataset,
)
from slo_monitor import get_slo_monitor


app = FastAPI(title="openLLMbenchmark API", version="v1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_API_KEY_HEADER = "X-Ollama-API-Key"


def _is_local_request(request: Request) -> bool:
    client = request.client
    host = (client.host if client else "").strip().lower()
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}


def _raise_if_runs_circuit_open() -> None:
    snapshot = get_slo_monitor().snapshot()
    if snapshot.breached:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Runs are temporarily unavailable due to SSE SLO breach. "
                "Investigate and recover before retrying."
            ),
        )


def _ollama_api_key_from_request(request: Request) -> str:
    return str(request.headers.get(OLLAMA_API_KEY_HEADER, "") or "").strip()


def _record_terminal_run_outcome(
    *,
    run_id: int,
    session_id: str,
    completed: bool,
    interrupted: bool,
    error: str,
) -> None:
    if not completed:
        return
    if interrupted:
        return
    success = not interrupted and not str(error).strip()
    run_key = f"{session_id}:{run_id}"
    get_slo_monitor().register_run_outcome(run_key, success=success)


@app.get("/health")
def health() -> dict[str, str]:
    return get_health()


@app.get("/models")
def models(request: Request) -> dict[str, list[str]]:
    try:
        return {"models": get_models(ollama_api_key=_ollama_api_key_from_request(request))}
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@app.get("/ollama/auth-status")
def ollama_auth_status() -> dict[str, bool]:
    return get_ollama_auth_status()


@app.get("/datasets")
def datasets() -> dict[str, list[dict[str, object]]]:
    return {"datasets": get_datasets()}


@app.get("/datasets/template")
def datasets_template() -> Response:
    content = get_dataset_template()
    headers = {"Content-Disposition": 'attachment; filename="benchmark_template.json"'}
    return Response(content=content, media_type="application/json", headers=headers)


@app.post("/datasets/upload", status_code=status.HTTP_201_CREATED)
async def datasets_upload(file: UploadFile = File(...)) -> dict[str, object]:
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded file is empty.")
    try:
        dataset = upload_dataset(filename=file.filename or "dataset.json", content=payload)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid dataset payload.") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dataset upload failed.") from exc
    return {"dataset": dataset}


@app.delete("/datasets/{dataset_key}")
def datasets_delete(dataset_key: str) -> dict[str, object]:
    state, summary = delete_dataset(dataset_key)
    if state == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    if state == "default_forbidden":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Default dataset cannot be deleted.")
    return {"status": "deleted", "summary": summary}


@app.get("/questions")
def questions(dataset_key: str = Query(..., min_length=1)) -> dict[str, object]:
    payload = get_questions(dataset_key)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    return payload


@app.get("/results")
def results(dataset_key: str = Query(..., min_length=1)) -> dict[str, object]:
    payload = get_results(dataset_key)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    return payload


@app.get("/results/export")
def results_export(
    dataset_key: str = Query(..., min_length=1),
    export_format: str = Query(..., alias="format", pattern="^(json|xlsx)$"),
) -> Response:
    exported = export_results(dataset_key, export_format)
    if exported is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    content, media_type, filename = exported
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@app.get("/results/table_export")
def results_table_export(
    dataset_key: str = Query(..., min_length=1),
    table: str = Query(..., min_length=1),
    export_format: str = Query(..., alias="format", pattern="^(json|xlsx)$"),
) -> Response:
    state, exported = export_results_table(dataset_key=dataset_key, table_key=table, export_format=export_format)
    if state == "dataset_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    if state == "table_not_supported":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown results table")
    if state == "format_not_supported":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported export format")
    if state != "ok" or exported is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Results table export failed")
    content, media_type, filename = exported
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=content, media_type=media_type, headers=headers)


@app.delete("/results/model")
def results_model_delete(
    dataset_key: str = Query(..., min_length=1),
    model: str = Query(..., min_length=1),
) -> dict[str, object]:
    state, summary = delete_model_results(dataset_key=dataset_key, model=model)
    if state == "dataset_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    if state == "model_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model results not found for dataset")
    if state == "invalid_model":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid model")
    if state != "deleted" or summary is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Model history delete failed")
    return {"status": "deleted", "summary": summary}


@app.post("/runs", status_code=status.HTTP_201_CREATED)
async def runs(request: Request) -> dict[str, object]:
    _raise_if_runs_circuit_open()

    body = await request.json()
    session_id = str(body.get("session_id", "")).strip() or uuid.uuid4().hex
    dataset_key = str(body.get("dataset_key", "")).strip()
    question_id = str(body.get("question_id", "")).strip()
    models = body.get("models", [])
    system_prompt = str(body.get("system_prompt", "") or "")
    if not dataset_key or not question_id or not isinstance(models, list):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid run payload")

    run_id, status_text = start_run(
        session_id=session_id,
        dataset_key=dataset_key,
        question_id=question_id,
        models=models,
        system_prompt=system_prompt,
        ollama_api_key=_ollama_api_key_from_request(request),
    )
    if status_text == "dataset_not_found" or status_text == "question_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=status_text)
    if status_text == "invalid_models":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=status_text)
    if status_text == "missing_api_key":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Enter Ollama API Key to be able to use Ollama Cloud models.",
        )
    if status_text == "conflict":
        payload: dict[str, object] = {"detail": "A run is already active for this session."}
        if run_id is not None:
            payload["run_id"] = run_id
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content=payload)
    if status_text != "started" or run_id is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=status_text)
    return {"run_id": run_id, "status": "started", "session_id": session_id}


@app.get("/runs/{run_id}/events")
async def run_events(
    request: Request,
    run_id: int,
    session_id: str = Query(..., min_length=1),
) -> EventSourceResponse:
    _raise_if_runs_circuit_open()
    monitor = get_slo_monitor()
    stream_key = f"{session_id}:{run_id}:{uuid.uuid4().hex}"
    monitor.register_stream_open(stream_key)

    async def _event_generator() -> AsyncIterator[dict[str, str]]:
        emitted_started = False
        emitted_completed_for: set[str] = set()
        try:
            while True:
                snapshot = run_snapshot(session_id=session_id)
                if int(snapshot.get("run_id", 0)) != run_id:
                    monitor.register_stream_error(stream_key)
                    yield {"event": "run_error", "data": json.dumps({"reason": "run_not_found"})}
                    break

                running = bool(snapshot.get("running"))
                completed = bool(snapshot.get("completed"))
                if await request.is_disconnected():
                    if running and not completed:
                        monitor.register_stream_disconnect(stream_key)
                    else:
                        monitor.register_stream_closed(stream_key)
                    break

                if not emitted_started:
                    emitted_started = True
                    yield {"event": "run_started", "data": json.dumps({"run_id": run_id})}

                entries = snapshot.get("entries", [])
                for entry in entries:
                    model = str(entry.get("model", ""))
                    source = str(entry.get("source", ""))
                    host = str(entry.get("host", ""))
                    response = str(entry.get("response", ""))
                    monitor.register_chunk(stream_key)
                    yield {
                        "event": "chunk",
                        "data": json.dumps(
                            {
                                "run_id": run_id,
                                "model": model,
                                "source": source,
                                "host": host,
                                "response": response,
                            }
                        ),
                    }
                    if bool(entry.get("completed")) and model not in emitted_completed_for:
                        emitted_completed_for.add(model)
                        event_name = "run_interrupted" if bool(entry.get("interrupted")) else "entry_completed"
                        payload = {
                            "run_id": run_id,
                            "model": model,
                            "source": source,
                            "host": host,
                            "interrupted": bool(entry.get("interrupted")),
                            "error": str(entry.get("error", "")),
                            "elapsed_ms": float(entry.get("elapsed_ms", 0.0) or 0.0),
                        }
                        yield {"event": event_name, "data": json.dumps(payload)}

                interrupted = any(bool(item.get("interrupted")) for item in entries)
                error = next((str(item.get("error", "")) for item in entries if str(item.get("error", "")).strip()), "")
                if completed and not running:
                    _record_terminal_run_outcome(
                        run_id=run_id,
                        session_id=session_id,
                        completed=completed,
                        interrupted=interrupted,
                        error=error,
                    )
                    yield {"event": "run_completed", "data": json.dumps({"run_id": run_id})}
                    monitor.register_stream_closed(stream_key)
                    break

                await asyncio.sleep(0.2)
        except Exception:
            monitor.register_stream_error(stream_key)
            raise

    return EventSourceResponse(_event_generator())


@app.get("/runs/{run_id}/status")
def run_status(run_id: int, session_id: str = Query(..., min_length=1)) -> dict[str, object]:
    payload = get_run_status(run_id=run_id, session_id=session_id)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    _record_terminal_run_outcome(
        run_id=run_id,
        session_id=session_id,
        completed=bool(payload.get("completed")),
        interrupted=bool(payload.get("interrupted")),
        error=str(payload.get("error", "")),
    )
    return payload


@app.post("/runs/{run_id}/stop", status_code=status.HTTP_202_ACCEPTED)
def run_stop(run_id: int, session_id: str = Query(..., min_length=1)) -> dict[str, str]:
    del run_id
    stop_run(session_id=session_id)
    return {"status": "stop_requested"}


@app.get("/ops/slo")
def ops_slo(request: Request) -> dict[str, object]:
    if not _is_local_request(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local/internal endpoint only.")
    return get_slo_monitor().snapshot().as_dict()


@app.post("/ops/slo/reset")
def ops_slo_reset(request: Request) -> dict[str, object]:
    if not _is_local_request(request):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Local/internal endpoint only.")
    monitor = get_slo_monitor()
    monitor.reset()
    return {"status": "reset", "slo": monitor.snapshot().as_dict()}


@app.patch("/results/manual")
async def results_manual(request: Request):
    body = await request.json()
    dataset_key = str(body.get("dataset_key", "")).strip()
    question_id = str(body.get("question_id", "")).strip()
    model = str(body.get("model", "")).strip()
    override_status = str(body.get("status", "")).strip()
    reason = str(body.get("reason", ""))
    if not dataset_key or not question_id or not model or not override_status:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid manual override payload")
    state, payload = apply_manual_result_override(
        dataset_key=dataset_key,
        question_id=question_id,
        model=model,
        status=override_status,
        reason=reason,
    )
    if state == "dataset_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown dataset")
    if state == "result_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result record not found")
    if state == "invalid_status":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid status; expected success, fail, or manual_review.",
        )
    if state != "updated" or payload is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Manual override failed")
    return {"status": "updated", "result": payload}
