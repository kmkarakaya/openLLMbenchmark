from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api
from api import app
import api_service
from data.dataset_config import resolve_results_paths
from fixtures import load_baseline_fixtures
from slo_monitor import get_slo_monitor


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def reset_slo_monitor_state() -> None:
    monitor = get_slo_monitor()
    monitor.reset()
    yield
    monitor.reset()


def test_health_returns_v1_schema_lock() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "v1"}


def test_read_endpoints_are_available() -> None:
    client = TestClient(app)
    assert client.get("/models").status_code in {200, 503}
    assert client.get("/ollama/auth-status").status_code == 200
    assert client.get("/datasets").status_code == 200
    assert client.get("/questions", params={"dataset_key": "default_tr"}).status_code == 200
    assert client.get("/results", params={"dataset_key": "default_tr"}).status_code == 200


def test_ollama_auth_status_reports_env_key_presence(monkeypatch) -> None:
    client = TestClient(app)
    monkeypatch.setenv("OLLAMA_API_KEY", "env-key")

    response = client.get("/ollama/auth-status")

    assert response.status_code == 200
    assert response.json() == {"server_api_key_configured": True}


def test_models_endpoint_passes_request_scoped_api_key_header(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_get_models(*, ollama_api_key: str = "") -> list[str]:
        captured["api_key"] = ollama_api_key
        return ["gemma3:4b:cloud"]

    monkeypatch.setattr("api.get_models", fake_get_models)
    client = TestClient(app)

    response = client.get("/models", headers={"X-Ollama-API-Key": "session-key"})

    assert response.status_code == 200
    assert response.json() == {"models": ["gemma3:4b:cloud"]}
    assert captured["api_key"] == "session-key"


def test_runs_endpoint_passes_request_scoped_api_key_header(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def fake_start_run(**kwargs):  # type: ignore[no-untyped-def]
        captured["api_key"] = kwargs["ollama_api_key"]
        return 23, "started"

    monkeypatch.setattr("api.start_run", fake_start_run)
    client = TestClient(app)

    response = client.post(
        "/runs",
        headers={"X-Ollama-API-Key": "session-key"},
        json={
            "session_id": "s1",
            "dataset_key": "default_tr",
            "question_id": "q001",
            "models": ["gemma3:4b:cloud"],
            "system_prompt": "x",
        },
    )

    assert response.status_code == 201
    assert response.json()["run_id"] == 23
    assert captured["api_key"] == "session-key"


def test_results_endpoint_uses_baseline_compatible_payload_shape(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get("/results", params={"dataset_key": "default_tr"})
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_key"] == "default_tr"
    assert isinstance(body["results"], list)
    assert isinstance(body["metrics"], list)
    assert isinstance(body["matrix"], list)


def test_datasets_template_returns_downloadable_json(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get("/datasets/template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert "benchmark_template.json" in response.headers.get("content-disposition", "")
    payload = response.json()
    assert isinstance(payload, list)
    assert payload and set(payload[0].keys()) == {
        "id",
        "question",
        "expected_answer",
        "topic",
        "hardness_level",
        "why_prepared",
    }


def test_runs_endpoint_returns_conflict_when_runner_active(monkeypatch) -> None:
    monkeypatch.setattr("api.start_run", lambda **_: (17, "conflict"))
    client = TestClient(app)
    response = client.post(
        "/runs",
        json={
            "session_id": "s1",
            "dataset_key": "default_tr",
            "question_id": "q001",
            "models": ["gemma3:4b"],
            "system_prompt": "x",
        },
    )
    assert response.status_code == 409
    payload = response.json()
    assert payload["detail"] == "A run is already active for this session."
    assert payload["run_id"] == 17


def test_datasets_upload_accepts_valid_dataset(monkeypatch, tmp_path: Path) -> None:
    default_path = tmp_path / "benchmark.json"
    default_path.write_text(
        json.dumps([{"id": "q001", "question": "Default?", "expected_answer": "A"}], ensure_ascii=False),
        encoding="utf-8",
    )
    upload_dir = tmp_path / "uploaded_datasets"
    upload_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(api_service, "BENCHMARK_PATH", default_path)
    monkeypatch.setattr(api_service, "UPLOADED_DATASETS_DIR", upload_dir)

    client = TestClient(app)
    response = client.post(
        "/datasets/upload",
        files={
            "file": (
                "myset.json",
                '[{"id":"q101","question":"Yeni soru?","expected_answer":"Yanıt"}]'.encode("utf-8"),
                "application/json",
            )
        },
    )
    assert response.status_code == 201
    body = response.json()["dataset"]
    assert str(body["key"]).startswith("uploaded_")
    assert body["question_count"] == 1
    assert any(upload_dir.glob("*.json"))


def test_datasets_delete_blocks_default_dataset(monkeypatch) -> None:
    client = TestClient(app)
    response = client.delete("/datasets/default_tr")
    assert response.status_code == 400


def test_datasets_delete_removes_uploaded_dataset(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps([{"id": "q001", "question": "Default?", "expected_answer": "A"}], ensure_ascii=False),
        encoding="utf-8",
    )
    uploaded_dir = data_dir / "uploaded_datasets"
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    uploaded_path = uploaded_dir / "demo.json"
    uploaded_path.write_text(
        json.dumps([{"id": "q101", "question": "Q?", "expected_answer": "A"}], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(api_service, "BENCHMARK_PATH", benchmark_path)
    monkeypatch.setattr(api_service, "UPLOADED_DATASETS_DIR", uploaded_dir)

    dataset_key = "uploaded_demo"
    results_dir = data_dir / "results_by_dataset"
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "uploaded-demo.json").write_text("[]", encoding="utf-8")
    (results_dir / "uploaded-demo.md").write_text("# x", encoding="utf-8")

    client = TestClient(app)
    response = client.delete(f"/datasets/{dataset_key}")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert not uploaded_path.exists()


def test_start_run_passes_correlation_fields_to_runner(monkeypatch) -> None:
    dataset = {
        "default_tr": {
            "key": "default_tr",
            "label": "Default",
            "is_default": True,
            "path": ROOT / "data" / "benchmark.json",
            "signature": "sig",
            "instruction": "sys",
            "questions": [{"id": "q001", "prompt": "Prompt"}],
        }
    }
    monkeypatch.setattr(api_service, "_dataset_option_map", lambda: dataset)

    captured: dict[str, object] = {}

    class _Runner:
        def start(self, **kwargs):  # type: ignore[no-untyped-def]
            captured.update(kwargs)
            return True

        def snapshot(self):  # type: ignore[no-untyped-def]
            return {"run_id": 7}

    monkeypatch.setattr(api_service, "get_runner", lambda session_id: _Runner())
    run_id, state = api_service.start_run(
        session_id="sess-1",
        dataset_key="default_tr",
        question_id="q001",
        models=["gemma3:4b"],
        system_prompt="system",
    )
    assert run_id == 7
    assert state == "started"
    assert captured["session_id"] == "sess-1"
    assert captured["dataset_key"] == "default_tr"
    assert captured["question_id"] == "q001"
    assert isinstance(captured.get("trace_id"), str) and captured["trace_id"]


def test_run_status_returns_snapshot_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.get_run_status",
        lambda run_id, session_id: {
            "run_id": run_id,
            "session_id": session_id,
            "dataset_key": "default_tr",
            "question_id": "q001",
            "running": False,
            "completed": True,
            "interrupted": False,
            "error": "",
            "entries": [
                {
                    "model": "gemma3:4b",
                    "running": False,
                    "completed": True,
                    "interrupted": False,
                    "error": "",
                    "event": "entry_completed",
                    "elapsed_ms": 123.0,
                }
            ],
        },
    )
    client = TestClient(app)
    response = client.get("/runs/5/status", params={"session_id": "sess-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == 5
    assert body["completed"] is True
    assert body["entries"][0]["model"] == "gemma3:4b"


def test_run_status_enforces_session_isolation(monkeypatch) -> None:
    monkeypatch.setattr(
        "api.get_run_status",
        lambda run_id, session_id: (
            {
                "run_id": run_id,
                "session_id": session_id,
                "dataset_key": "default_tr",
                "question_id": "q001",
                "running": False,
                "completed": True,
                "interrupted": False,
                "error": "",
                "entries": [],
            }
            if session_id == "sess-1"
            else None
        ),
    )
    client = TestClient(app)
    forbidden = client.get("/runs/7/status", params={"session_id": "sess-2"})
    allowed = client.get("/runs/7/status", params={"session_id": "sess-1"})
    assert forbidden.status_code == 404
    assert allowed.status_code == 200


def test_run_events_emit_ordered_lifecycle(monkeypatch) -> None:
    first_snapshot = {
        "run_id": 9,
        "running": True,
        "completed": False,
        "entries": [
            {
                "model": "gemma3:4b",
                "response": "Mer",
                "completed": False,
                "running": True,
                "interrupted": False,
                "error": "",
            }
        ],
    }
    final_snapshot = {
        "run_id": 9,
        "running": False,
        "completed": True,
        "entries": [
            {
                "model": "gemma3:4b",
                "response": "Merhaba",
                "completed": True,
                "running": False,
                "interrupted": False,
                "error": "",
            }
        ],
    }
    snapshots = [first_snapshot, final_snapshot]

    def fake_snapshot(*, session_id: str):  # type: ignore[no-untyped-def]
        del session_id
        if snapshots:
            return snapshots.pop(0)
        return final_snapshot

    monkeypatch.setattr("api.run_snapshot", fake_snapshot)
    client = TestClient(app)

    events: list[str] = []
    with client.stream("GET", "/runs/9/events", params={"session_id": "sess-1"}) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8", errors="ignore")
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if events and events[-1] == "run_completed":
                break

    assert "run_started" in events
    assert "chunk" in events
    assert "entry_completed" in events
    assert "run_completed" in events
    assert events.index("run_started") < events.index("entry_completed") < events.index("run_completed")


def test_results_export_supports_json_and_xlsx(monkeypatch) -> None:
    client = TestClient(app)
    json_response = client.get("/results/export", params={"dataset_key": "default_tr", "format": "json"})
    xlsx_response = client.get("/results/export", params={"dataset_key": "default_tr", "format": "xlsx"})
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert "results.json" in json_response.headers.get("content-disposition", "")
    assert xlsx_response.status_code == 200
    assert "spreadsheetml" in xlsx_response.headers["content-type"]
    assert "results.xlsx" in xlsx_response.headers.get("content-disposition", "")


def test_results_table_export_supports_json_and_xlsx(monkeypatch) -> None:
    client = TestClient(app)
    json_response = client.get(
        "/results/table_export",
        params={
            "dataset_key": "default_tr",
            "table": "model_leader_board",
            "format": "json",
        },
    )
    xlsx_response = client.get(
        "/results/table_export",
        params={
            "dataset_key": "default_tr",
            "table": "model_leader_board",
            "format": "xlsx",
        },
    )
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert "results_model_leader_board.json" in json_response.headers.get("content-disposition", "")
    assert xlsx_response.status_code == 200
    assert "spreadsheetml" in xlsx_response.headers["content-type"]
    assert "results_model_leader_board.xlsx" in xlsx_response.headers.get("content-disposition", "")


def test_results_table_export_returns_404_for_unknown_dataset(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get(
        "/results/table_export",
        params={
            "dataset_key": "unknown",
            "table": "model_leader_board",
            "format": "json",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown dataset"


def test_results_table_export_rejects_unknown_table(monkeypatch) -> None:
    client = TestClient(app)
    response = client.get(
        "/results/table_export",
        params={
            "dataset_key": "default_tr",
            "table": "not_a_table",
            "format": "json",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown results table"


def test_results_model_delete_returns_404_for_unknown_dataset(monkeypatch) -> None:
    monkeypatch.setattr(api_service, "_dataset_option_map", lambda: {})
    client = TestClient(app)
    response = client.delete("/results/model", params={"dataset_key": "unknown", "model": "gemma3:4b"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown dataset"


def test_results_model_delete_returns_404_when_model_not_found(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir = data_dir / "results_by_dataset"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "uploaded-demo.json"
    results_path.write_text(
        json.dumps(
            [
                {
                    "dataset_key": "uploaded_demo",
                    "dataset_signature": "sig-123",
                    "question_id": "q001",
                    "model": "qwen3:8b",
                    "status": "success",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(
        api_service,
        "_dataset_option_map",
        lambda: {
            "uploaded_demo": {
                "key": "uploaded_demo",
                "label": "Uploaded",
                "is_default": False,
                "path": tmp_path / "uploaded-demo-dataset.json",
                "signature": "sig-123",
                "instruction": "",
                "questions": [{"id": "q001", "prompt": "Prompt text"}],
            }
        },
    )
    client = TestClient(app)
    response = client.delete("/results/model", params={"dataset_key": "uploaded_demo", "model": "gemma3:4b"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Model results not found for dataset"


def test_results_model_delete_removes_only_target_model_rows(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir = data_dir / "results_by_dataset"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "uploaded-demo.json"
    results_path.write_text(
        json.dumps(
            [
                {
                    "dataset_key": "uploaded_demo",
                    "dataset_signature": "sig-123",
                    "question_id": "q001",
                    "model": "gemma3:4b",
                    "status": "success",
                    "response_time_ms": 1200,
                },
                {
                    "dataset_key": "uploaded_demo",
                    "dataset_signature": "sig-123",
                    "question_id": "q002",
                    "model": "gemma3:4b",
                    "status": "fail",
                    "response_time_ms": 1400,
                },
                {
                    "dataset_key": "uploaded_demo",
                    "dataset_signature": "sig-123",
                    "question_id": "q001",
                    "model": "qwen3:8b",
                    "status": "success",
                    "response_time_ms": 900,
                },
                {
                    "dataset_key": "another_dataset",
                    "dataset_signature": "sig-other",
                    "question_id": "q001",
                    "model": "gemma3:4b",
                    "status": "success",
                    "response_time_ms": 500,
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(
        api_service,
        "_dataset_option_map",
        lambda: {
            "uploaded_demo": {
                "key": "uploaded_demo",
                "label": "Uploaded",
                "is_default": False,
                "path": tmp_path / "uploaded-demo-dataset.json",
                "signature": "sig-123",
                "instruction": "",
                "questions": [
                    {"id": "q001", "prompt": "Prompt text 1"},
                    {"id": "q002", "prompt": "Prompt text 2"},
                ],
            }
        },
    )
    client = TestClient(app)
    response = client.delete("/results/model", params={"dataset_key": "uploaded_demo", "model": "gemma3:4b"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "deleted"
    assert body["summary"]["dataset_key"] == "uploaded_demo"
    assert body["summary"]["model"] == "gemma3:4b"
    assert body["summary"]["deleted_count"] == 2
    assert body["summary"]["remaining_count"] == 0

    persisted = json.loads(results_path.read_text(encoding="utf-8"))
    assert len(persisted) == 2
    assert all(
        not (
            item.get("dataset_key") == "uploaded_demo"
            and item.get("dataset_signature") == "sig-123"
            and item.get("model") == "gemma3:4b"
        )
        for item in persisted
    )
    assert any(item.get("model") == "qwen3:8b" for item in persisted)
    assert any(item.get("dataset_key") == "another_dataset" for item in persisted)
    assert (results_dir / "uploaded-demo.md").exists()


def test_manual_results_write_updates_dataset_scoped_record(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir = data_dir / "results_by_dataset"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "uploaded-demo.json"
    results_path.write_text(
        json.dumps(
            [
                {
                    "question_id": "q001",
                    "model": "gemma3:4b",
                    "status": "fail",
                    "score": 0,
                    "auto_scored": True,
                    "reason": "Text similarity: 10",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(
        api_service,
        "_dataset_option_map",
        lambda: {
            "uploaded_demo": {
                "key": "uploaded_demo",
                "label": "Uploaded",
                "is_default": False,
                "path": tmp_path / "uploaded-demo.json",
                "signature": "sig-123",
                "instruction": "",
                "questions": [{"id": "q001", "prompt": "Prompt text"}],
            }
        },
    )
    client = TestClient(app)
    response = client.patch(
        "/results/manual",
        json={
            "dataset_key": "uploaded_demo",
            "question_id": "q001",
            "model": "gemma3:4b",
            "status": "success",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "updated"
    assert body["result"]["status"] == "success"
    assert body["result"]["score"] == 1
    assert body["result"]["auto_scored"] is False
    assert body["result"]["evaluation"] == "Successful"
    assert body["result"]["evaluation_method"] == "Manual"
    assert body["result"]["reason"] == "User approval"
    persisted = json.loads(results_path.read_text(encoding="utf-8"))
    assert persisted[0]["status"] == "success"
    assert persisted[0]["evaluation"] == "Successful"
    assert persisted[0]["evaluation_method"] == "Manual"
    assert persisted[0]["dataset_key"] == "uploaded_demo"
    assert persisted[0]["dataset_signature"] == "sig-123"
    assert persisted[0]["question_prompt_hash"] == hashlib.sha256("Prompt text".encode("utf-8")).hexdigest()[:16]
    assert (results_dir / "uploaded-demo.md").exists()


def test_manual_results_write_rejects_invalid_status(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    data_dir.mkdir(parents=True, exist_ok=True)
    results_dir = data_dir / "results_by_dataset"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "uploaded-demo.json"
    results_path.write_text(
        json.dumps(
            [
                {
                    "question_id": "q001",
                    "model": "gemma3:4b",
                    "status": "fail",
                    "score": 0,
                    "auto_scored": True,
                    "reason": "Text similarity: 10",
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(
        api_service,
        "_dataset_option_map",
        lambda: {
            "uploaded_demo": {
                "key": "uploaded_demo",
                "label": "Uploaded",
                "is_default": False,
                "path": tmp_path / "uploaded-demo.json",
                "signature": "sig-123",
                "instruction": "",
                "questions": [{"id": "q001", "prompt": "Prompt text"}],
            }
        },
    )
    client = TestClient(app)
    response = client.patch(
        "/results/manual",
        json={
            "dataset_key": "uploaded_demo",
            "question_id": "q001",
            "model": "gemma3:4b",
            "status": "unknown",
        },
    )
    assert response.status_code == 422


def test_ops_slo_returns_schema_for_local_requests() -> None:
    client = TestClient(app)
    response = client.get("/ops/slo")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "window_minutes",
        "sse_disconnect_error_rate",
        "run_completion_success_rate",
        "p95_chunk_gap_ms",
        "breached",
        "evaluated_at",
    }


def test_ops_slo_reset_clears_breached_state_for_local_requests() -> None:
    monitor = get_slo_monitor()
    monitor.register_stream_open("stream-a")
    monitor.register_stream_error("stream-a")

    client = TestClient(app)
    response = client.post("/ops/slo/reset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "reset"
    assert payload["slo"]["breached"] is False


def test_ops_slo_rejects_non_local_requests(monkeypatch) -> None:
    monkeypatch.setattr(api, "_is_local_request", lambda request: False)
    client = TestClient(app)
    response = client.get("/ops/slo")
    assert response.status_code == 403


def test_ops_slo_reset_rejects_non_local_requests(monkeypatch) -> None:
    monkeypatch.setattr(api, "_is_local_request", lambda request: False)
    client = TestClient(app)
    response = client.post("/ops/slo/reset")
    assert response.status_code == 403


def test_runs_endpoint_returns_503_when_slo_breached(monkeypatch) -> None:
    monitor = get_slo_monitor()
    monitor.register_stream_open("stream-a")
    monitor.register_stream_error("stream-a")
    client = TestClient(app)
    response = client.post(
        "/runs",
        json={
            "session_id": "s1",
            "dataset_key": "default_tr",
            "question_id": "q001",
            "models": ["gemma3:4b"],
            "system_prompt": "x",
        },
    )
    assert response.status_code == 503
    assert "SSE SLO breach" in response.json()["detail"]


def test_run_events_endpoint_returns_503_when_slo_breached(monkeypatch) -> None:
    monitor = get_slo_monitor()
    monitor.register_stream_open("stream-a")
    monitor.register_stream_error("stream-a")
    client = TestClient(app)
    response = client.get("/runs/1/events", params={"session_id": "s1"})
    assert response.status_code == 503


def test_interrupted_run_does_not_reduce_run_success_rate() -> None:
    monitor = get_slo_monitor()
    api._record_terminal_run_outcome(
        run_id=101,
        session_id="s1",
        completed=True,
        interrupted=True,
        error="",
    )

    snapshot = monitor.snapshot()
    assert snapshot.run_completion_success_rate == 1.0
    assert snapshot.breached is False


def test_runs_endpoint_not_blocked_by_plain_stream_disconnect(monkeypatch) -> None:
    monitor = get_slo_monitor()
    monitor.register_stream_open("stream-a")
    monitor.register_stream_disconnect("stream-a")
    monkeypatch.setattr("api.start_run", lambda **_: (23, "started"))

    client = TestClient(app)
    response = client.post(
        "/runs",
        json={
            "session_id": "s1",
            "dataset_key": "default_tr",
            "question_id": "q001",
            "models": ["gemma3:4b"],
            "system_prompt": "x",
        },
    )

    assert response.status_code == 201
    assert response.json()["run_id"] == 23


def test_phase0_baseline_fixtures_exist_and_are_loadable() -> None:
    baseline_results, baseline_markdown = load_baseline_fixtures()
    assert isinstance(baseline_results, list)
    assert isinstance(baseline_markdown, str)
    baseline_md_path = ROOT / "data" / "baselines" / "results.md"
    if baseline_md_path.exists():
        assert "# Open LLM Benchmark Results" in baseline_markdown
    else:
        assert baseline_markdown == ""


def test_baseline_fixture_json_matches_repo_results_json_shape() -> None:
    baseline_results, _ = load_baseline_fixtures()
    results_path = ROOT / "data" / "results.json"
    if not results_path.exists():
        assert baseline_results == []
        return
    repo_results = json.loads(results_path.read_text(encoding="utf-8"))
    assert isinstance(repo_results, list)
    if baseline_results and repo_results:
        baseline_keys = set(baseline_results[0].keys())
        repo_keys = set(repo_results[0].keys())
        assert baseline_keys == repo_keys


def test_get_models_preserves_explicit_cloud_suffix_from_local_provider(monkeypatch) -> None:
    cloud_client = object()
    local_client = object()

    monkeypatch.setattr("engine.get_cloud_client", lambda api_key=None: cloud_client)
    monkeypatch.setattr("engine.get_local_client", lambda: local_client)

    def fake_list_models(client, source="cloud"):  # type: ignore[no-untyped-def]
        if client is cloud_client:
            return ["gemma3:4b"]
        if client is local_client:
            return ["glm-5:cloud", "qwen3.5:cloud"]
        return []

    monkeypatch.setattr("engine.list_models", fake_list_models)
    models = api_service.get_models()

    assert "gemma3:4b:cloud" in models
    assert "glm-5:cloud" in models
    assert "qwen3.5:cloud" in models
    assert "glm-5:local" not in models
    assert "qwen3.5:local" not in models


def test_run_status_persists_completed_entries_with_model_source(monkeypatch, tmp_path: Path) -> None:

    data_dir = tmp_path / "data"
    root_dir = tmp_path
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "results_by_dataset").mkdir(parents=True, exist_ok=True)

    dataset_key = "uploaded_demo"
    dataset_signature = "sig-123"
    question_id = "q001"

    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(
        api_service,
        "_dataset_option_map",
        lambda: {
            dataset_key: {
                "key": dataset_key,
                "label": "Uploaded",
                "is_default": False,
                "path": tmp_path / "uploaded-demo.json",
                "signature": dataset_signature,
                "instruction": "",
                "questions": [{"id": question_id, "prompt": "2+2 nedir?", "expected_answer": "4"}],
            }
        },
    )

    snapshot = {
        "run_id": 77,
        "trace_id": "trace-1",
        "session_id": "sess-1",
        "dataset_key": dataset_key,
        "question_id": question_id,
        "running": False,
        "completed": True,
        "entries": [
            {
                "model": "gemma3:4b:local",
                "source": "local",
                "host": "http://localhost:11434",
                "response": "4",
                "running": False,
                "completed": True,
                "interrupted": False,
                "error": "",
                "event": "entry_completed",
                "elapsed_ms": 320.0,
                "generated_tokens": 7,
                "prompt_tokens": 4,
            }
        ],
    }

    class _Runner:
        def snapshot(self):  # type: ignore[no-untyped-def]
            return snapshot

    monkeypatch.setattr(api_service, "get_runner", lambda session_id: _Runner())

    payload = api_service.get_run_status(run_id=77, session_id="sess-1")
    assert payload is not None
    assert payload["entries"][0]["model"] == "gemma3:4b:local"
    assert payload["entries"][0]["source"] == "local"
    assert payload["entries"][0]["generated_tokens"] == 7
    assert payload["entries"][0]["prompt_tokens"] == 4

    results_path, _ = resolve_results_paths(dataset_key, data_dir, root_dir)
    persisted = json.loads(results_path.read_text(encoding="utf-8"))
    assert len(persisted) == 1
    assert persisted[0]["model"] == "gemma3:4b:local"
    assert persisted[0]["model_source"] == "local"
    assert persisted[0]["model_host"] == "http://localhost:11434"
    assert persisted[0]["status"] == "success"
    assert persisted[0]["evaluation"] == "Successful"
    assert persisted[0]["evaluation_method"] == "Automatic"
    assert persisted[0]["generated_tokens"] == 7
    assert persisted[0]["generated_tokens_estimated"] is False
    assert persisted[0]["prompt_tokens"] == 4


def test_get_results_backfills_estimated_generated_tokens_for_legacy_rows(monkeypatch, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "results_by_dataset").mkdir(parents=True, exist_ok=True)

    dataset_key = "uploaded_demo"
    dataset_signature = "sig-123"
    question_id = "q001"

    monkeypatch.setattr(api_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(api_service, "ROOT", root_dir)
    monkeypatch.setattr(
        api_service,
        "_dataset_option_map",
        lambda: {
            dataset_key: {
                "key": dataset_key,
                "label": "Uploaded",
                "is_default": False,
                "path": tmp_path / "uploaded-demo.json",
                "signature": dataset_signature,
                "instruction": "",
                "questions": [{"id": question_id, "prompt": "2+2 nedir?", "expected_answer": "4"}],
            }
        },
    )

    results_path, _ = resolve_results_paths(dataset_key, data_dir, root_dir)
    legacy_row = {
        "dataset_key": dataset_key,
        "dataset_signature": dataset_signature,
        "question_id": question_id,
        "question_prompt_hash": "abc123",
        "model": "gemma3:4b:local",
        "response": "Dort",
        "status": "manual_review",
        "score": None,
        "response_time_ms": 111.0,
        "timestamp": "2026-04-09T00:00:00+00:00",
        "interrupted": False,
        "auto_scored": False,
        "reason": "legacy",
    }
    results_path.write_text(json.dumps([legacy_row], ensure_ascii=False, indent=2), encoding="utf-8")

    payload = api_service.get_results(dataset_key)

    assert payload is not None
    normalized_row = payload["results"][0]
    assert normalized_row["evaluation"] == "Needs Review"
    assert normalized_row["evaluation_method"] == "Manual"
    assert normalized_row["generated_tokens"] == api_service._estimate_generated_tokens("Dort")
    assert normalized_row["generated_tokens_estimated"] is True
