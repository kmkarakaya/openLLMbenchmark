from __future__ import annotations

from pathlib import Path

import app


def test_persist_result_record_skips_write_when_api_writes_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
    save_calls: list[tuple[Path, list[dict[str, object]]]] = []

    def _save_results(path: Path, results: list[dict[str, object]]) -> None:
        save_calls.append((path, results))

    monkeypatch.setattr(app, "save_results", _save_results)

    current_results = [{"question_id": "q001", "model": "gemma3:4b", "status": "success"}]
    output = app.persist_result_record(
        results=current_results,
        questions=[{"id": "q001", "prompt": "Soru"}],
        record={"question_id": "q001", "model": "gemma3:4b", "status": "fail"},
        dataset_key="default_tr",
        dataset_signature="sig",
        results_path=tmp_path / "results.json",
        results_md_path=tmp_path / "results.md",
    )

    assert output == current_results
    assert save_calls == []


def test_sanitize_dataset_results_skips_write_when_api_writes_enabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FEATURE_API_WRITES", "true")
    save_calls: list[tuple[Path, list[dict[str, object]]]] = []

    def _save_results(path: Path, results: list[dict[str, object]]) -> None:
        save_calls.append((path, results))

    monkeypatch.setattr(app, "save_results", _save_results)

    raw_results = [{"question_id": "q001", "model": "m1"}, {"question_id": "q002", "model": "m1"}]
    filtered_results = [{"question_id": "q001", "model": "m1"}]

    output = app.sanitize_dataset_results(
        raw_results=raw_results,
        filtered_results=filtered_results,
        dataset_key="uploaded_demo",
        questions=[{"id": "q001", "prompt": "Soru"}],
        results_path=tmp_path / "uploaded-demo.json",
        results_md_path=tmp_path / "uploaded-demo.md",
    )

    assert output == filtered_results
    assert save_calls == []

