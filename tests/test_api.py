from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from api import app
import api_service
from fixtures import load_baseline_fixtures


ROOT = Path(__file__).resolve().parents[1]


def test_health_returns_v1_schema_lock() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "v1"}


def test_read_endpoints_return_404_when_feature_api_reads_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_READS", "false")
    client = TestClient(app)
    assert client.get("/models").status_code == 404
    assert client.get("/datasets").status_code == 404
    assert client.get("/questions", params={"dataset_key": "default_tr"}).status_code == 404
    assert client.get("/results", params={"dataset_key": "default_tr"}).status_code == 404


def test_results_endpoint_uses_baseline_compatible_payload_shape(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_READS", "true")
    client = TestClient(app)
    response = client.get("/results", params={"dataset_key": "default_tr"})
    assert response.status_code == 200
    body = response.json()
    assert body["dataset_key"] == "default_tr"
    assert isinstance(body["results"], list)
    assert isinstance(body["metrics"], list)
    assert isinstance(body["matrix"], list)


def test_datasets_template_returns_downloadable_json(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_READS", "true")
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


def test_runs_endpoint_gated_by_feature_flag(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_RUNS", "false")
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
    assert response.status_code == 404


def test_datasets_upload_requires_api_writes(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "false")
    client = TestClient(app)
    response = client.post(
        "/datasets/upload",
        files={"file": ("demo.json", b'[{"id":"q001","question":"Soru?","expected_answer":"A"}]', "application/json")},
    )
    assert response.status_code == 423


def test_datasets_upload_accepts_valid_dataset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
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
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
    client = TestClient(app)
    response = client.delete("/datasets/default_tr")
    assert response.status_code == 400


def test_datasets_delete_removes_uploaded_dataset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
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
    monkeypatch.setenv("FEATURE_API_RUNS", "true")
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
    monkeypatch.setenv("FEATURE_API_RUNS", "true")
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


def test_results_export_supports_json_and_xlsx(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_READS", "true")
    client = TestClient(app)
    json_response = client.get("/results/export", params={"dataset_key": "default_tr", "format": "json"})
    xlsx_response = client.get("/results/export", params={"dataset_key": "default_tr", "format": "xlsx"})
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert "results.json" in json_response.headers.get("content-disposition", "")
    assert xlsx_response.status_code == 200
    assert "spreadsheetml" in xlsx_response.headers["content-type"]
    assert "results.xlsx" in xlsx_response.headers.get("content-disposition", "")


def test_manual_results_write_endpoint_locked_while_api_writes_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "false")
    client = TestClient(app)
    response = client.patch("/results/manual")
    assert response.status_code == 423


def test_manual_results_write_updates_dataset_scoped_record(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
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
    assert body["result"]["reason"] == "User approval"
    persisted = json.loads(results_path.read_text(encoding="utf-8"))
    assert persisted[0]["status"] == "success"
    assert persisted[0]["dataset_key"] == "uploaded_demo"
    assert persisted[0]["dataset_signature"] == "sig-123"
    assert persisted[0]["question_prompt_hash"] == hashlib.sha256("Prompt text".encode("utf-8")).hexdigest()[:16]
    assert (results_dir / "uploaded-demo.md").exists()


def test_manual_results_write_rejects_invalid_status(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
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
