from pathlib import Path

from storage import load_results, render_results_markdown, save_results


def test_markdown_generation(tmp_path: Path) -> None:
    questions = [
        {"id": "q001", "category": "TURKCE", "prompt": "Soru 1", "expected_answer": ""},
        {"id": "q002", "category": "FINANS", "prompt": "Soru 2", "expected_answer": "2.95"},
    ]
    results = [
        {
            "question_id": "q001",
            "model": "llama3",
            "response": "yanit",
            "status": "manual_review",
            "score": None,
            "response_time_ms": 910.0,
            "timestamp": "2026-01-01T00:00:00+00:00",
            "interrupted": False,
        },
        {
            "question_id": "q002",
            "model": "llama3",
            "response": "2.95",
            "status": "success",
            "score": 1,
            "response_time_ms": 1400.0,
            "timestamp": "2026-01-01T00:01:00+00:00",
            "interrupted": False,
        },
    ]

    output = tmp_path / "results.md"
    render_results_markdown(questions, results, output)
    text = output.read_text(encoding="utf-8")
    assert "Model" in text
    assert "Soru ID" in text
    assert "llama3" in text


def test_load_results_handles_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text("", encoding="utf-8")
    loaded = load_results(path)
    assert loaded == []


def test_load_results_handles_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    path.write_text("{broken json", encoding="utf-8")
    loaded = load_results(path)
    assert loaded == []
    assert (tmp_path / "results.json.corrupt").exists()


def test_save_results_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    payload = [{"question_id": "q001", "model": "x"}]
    save_results(path, payload)
    loaded = load_results(path)
    assert loaded == payload


def test_save_results_creates_file_lock_sidecar(tmp_path: Path) -> None:
    path = tmp_path / "results.json"
    save_results(path, [{"question_id": "q001", "model": "x"}])
    assert (tmp_path / "results.json.lock").exists()
