from __future__ import annotations

import json
import os
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


def test_manual_results_write_endpoint_locked_while_api_writes_disabled(monkeypatch) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "false")
    client = TestClient(app)
    response = client.patch("/results/manual")
    assert response.status_code == 423


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
