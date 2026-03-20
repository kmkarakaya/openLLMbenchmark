from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.benchmark import DatasetValidationError
from data.dataset_config import (
    DEFAULT_DATASET_KEY,
    dataset_artifact_paths,
    dataset_template_bytes,
    delete_uploaded_dataset_with_artifacts,
    discover_datasets,
    resolve_results_paths,
    save_uploaded_dataset,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_dataset_template_contains_expected_fields() -> None:
    template = json.loads(dataset_template_bytes().decode("utf-8"))
    assert isinstance(template, list)
    assert len(template) == 1
    row = template[0]
    assert set(row.keys()) == {
        "id",
        "question",
        "expected_answer",
        "topic",
        "hardness_level",
        "why_prepared",
    }


def test_discover_datasets_returns_default_and_uploaded_valid_only(tmp_path: Path) -> None:
    default_path = tmp_path / "benchmark.json"
    upload_dir = tmp_path / "uploaded_datasets"
    upload_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        default_path,
        [{"id": "q001", "question": "Soru?", "expected_answer": "A"}],
    )
    _write_json(
        upload_dir / "custom-valid.json",
        [{"id": "q010", "question": "Custom?", "expected_answer": "B"}],
    )
    _write_json(
        upload_dir / "custom-invalid.json",
        [{"id": "invalid", "question": "Broken?", "expected_answer": "C"}],
    )

    options = discover_datasets(default_path, upload_dir)
    keys = [item["key"] for item in options]
    labels = [item["label"] for item in options]

    assert keys[0] == DEFAULT_DATASET_KEY
    assert labels[0] == "Default benchmark set (TR)"
    assert any(label.startswith("Uploaded: custom-valid") for label in labels)
    assert not any(label.startswith("Uploaded: custom-invalid") for label in labels)


def test_save_uploaded_dataset_accepts_valid_json(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploaded"
    payload = [{"id": "q101", "question": "Valid?", "expected_answer": "Yes"}]
    target = save_uploaded_dataset(
        upload_dir,
        "my_dataset.json",
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    assert target.exists()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded[0]["id"] == "q101"


def test_save_uploaded_dataset_rejects_invalid_json(tmp_path: Path) -> None:
    upload_dir = tmp_path / "uploaded"
    payload = [{"id": "bad-id", "question": "Invalid?", "expected_answer": "No"}]
    with pytest.raises(DatasetValidationError):
        save_uploaded_dataset(
            upload_dir,
            "invalid.json",
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
    assert list(upload_dir.glob("*.json")) == []


def test_resolve_results_paths_default_and_uploaded(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    default_results, default_md = resolve_results_paths(DEFAULT_DATASET_KEY, data_dir, root_dir)
    assert default_results == data_dir / "results.json"
    assert default_md == root_dir / "results.md"

    uploaded_results, uploaded_md = resolve_results_paths("uploaded_demo", data_dir, root_dir)
    assert uploaded_results == data_dir / "results_by_dataset" / "uploaded-demo.json"
    assert uploaded_md == data_dir / "results_by_dataset" / "uploaded-demo.md"
    assert uploaded_results.parent.exists()


def test_dataset_artifact_paths_include_dataset_results_and_sidecars(tmp_path: Path) -> None:
    dataset_key = "uploaded_demo"
    dataset_file = tmp_path / "data" / "uploaded_datasets" / "demo.json"
    expected_results, expected_md = resolve_results_paths(dataset_key, tmp_path / "data", tmp_path)
    paths = dataset_artifact_paths(
        dataset_key=dataset_key,
        dataset_path=dataset_file,
        data_dir=tmp_path / "data",
        root_dir=tmp_path,
    )
    assert dataset_file in paths
    assert expected_results in paths
    assert expected_md in paths
    assert expected_results.with_suffix(".json.tmp") in paths
    assert expected_results.with_suffix(".json.corrupt") in paths
    assert expected_md.with_suffix(".md.tmp") in paths
    assert expected_md.with_suffix(".md.corrupt") in paths


def test_delete_uploaded_dataset_with_artifacts_removes_all_targets(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    uploaded_dir = data_dir / "uploaded_datasets"
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = uploaded_dir / "demo-abc123.json"
    dataset_file.write_text('[{"id":"q001","question":"Q?","expected_answer":"A"}]', encoding="utf-8")

    option = {
        "key": "uploaded_demo-abc123",
        "label": "Uploaded: demo-abc123",
        "path": dataset_file,
        "is_default": False,
    }

    results_path, md_path = resolve_results_paths(option["key"], data_dir, root_dir)
    for artifact in [
        results_path,
        results_path.with_suffix(".json.tmp"),
        results_path.with_suffix(".json.corrupt"),
        md_path,
        md_path.with_suffix(".md.tmp"),
        md_path.with_suffix(".md.corrupt"),
    ]:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("x", encoding="utf-8")

    summary = delete_uploaded_dataset_with_artifacts(option, data_dir, root_dir)
    assert summary["target_count"] == 7
    assert summary["deleted_count"] == 7
    assert summary["missing_count"] == 0
    assert not dataset_file.exists()
    assert not results_path.exists()
    assert not md_path.exists()


def test_delete_uploaded_dataset_with_artifacts_is_idempotent(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    uploaded_dir = data_dir / "uploaded_datasets"
    uploaded_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = uploaded_dir / "demo-abc123.json"
    dataset_file.write_text('[{"id":"q001","question":"Q?","expected_answer":"A"}]', encoding="utf-8")

    option = {
        "key": "uploaded_demo-abc123",
        "label": "Uploaded: demo-abc123",
        "path": dataset_file,
        "is_default": False,
    }
    first = delete_uploaded_dataset_with_artifacts(option, data_dir, root_dir)
    second = delete_uploaded_dataset_with_artifacts(option, data_dir, root_dir)
    assert first["deleted_count"] >= 1
    assert second["deleted_count"] == 0
    assert second["missing_count"] == second["target_count"]


def test_delete_uploaded_dataset_with_artifacts_blocks_default(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    root_dir = tmp_path
    option = {
        "key": DEFAULT_DATASET_KEY,
        "label": "Default benchmark set (TR)",
        "path": data_dir / "benchmark.json",
        "is_default": True,
    }
    with pytest.raises(ValueError):
        delete_uploaded_dataset_with_artifacts(option, data_dir, root_dir)
