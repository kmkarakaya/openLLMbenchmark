from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import TypedDict

import portalocker

from data.benchmark import load_benchmark_payload


DEFAULT_DATASET_KEY = "default_tr"
_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class DatasetOption(TypedDict):
    key: str
    label: str
    path: Path
    is_default: bool


class DatasetDeleteSummary(TypedDict):
    target_count: int
    deleted_count: int
    missing_count: int


def slugify(value: str) -> str:
    normalized = _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")
    return normalized or "dataset"


def dataset_template_bytes() -> bytes:
    payload = [
        {
            "id": "q001",
            "question": "",
            "expected_answer": "",
            "topic": "",
            "hardness_level": "",
            "why_prepared": "",
        }
    ]
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_uploaded_filename(original_name: str, content: bytes) -> str:
    stem = slugify(Path(original_name).stem or "dataset")
    digest = hashlib.sha256(content).hexdigest()[:12]
    return f"{stem}-{digest}.json"


def save_uploaded_dataset(upload_dir: Path, original_name: str, content: bytes) -> Path:
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / build_uploaded_filename(original_name, content)
    lock_path = upload_dir / ".datasets.lock"
    wrote_file = False
    with portalocker.Lock(str(lock_path), timeout=10):
        if not destination.exists():
            destination.write_bytes(content)
            wrote_file = True

        try:
            load_benchmark_payload(destination)
        except Exception:
            if wrote_file and destination.exists():
                destination.unlink(missing_ok=True)
            raise

    return destination


def discover_datasets(default_dataset_path: Path, upload_dir: Path) -> list[DatasetOption]:
    options: list[DatasetOption] = [
        {
            "key": DEFAULT_DATASET_KEY,
            "label": "Default benchmark set (TR)",
            "path": default_dataset_path,
            "is_default": True,
        }
    ]
    used_keys = {DEFAULT_DATASET_KEY}
    if not upload_dir.exists():
        return options

    for dataset_path in sorted(upload_dir.glob("*.json"), key=lambda item: item.name.lower()):
        try:
            load_benchmark_payload(dataset_path)
        except Exception:
            continue

        base_key = f"uploaded_{slugify(dataset_path.stem)}"
        unique_key = base_key
        suffix = 2
        while unique_key in used_keys:
            unique_key = f"{base_key}_{suffix}"
            suffix += 1
        used_keys.add(unique_key)
        options.append(
            {
                "key": unique_key,
                "label": f"Uploaded: {dataset_path.stem}",
                "path": dataset_path,
                "is_default": False,
            }
        )
    return options


def resolve_results_paths(dataset_key: str, data_dir: Path, root_dir: Path) -> tuple[Path, Path]:
    if dataset_key == DEFAULT_DATASET_KEY:
        return data_dir / "results.json", root_dir / "results.md"

    results_dir = data_dir / "results_by_dataset"
    results_dir.mkdir(parents=True, exist_ok=True)
    safe_key = slugify(dataset_key)
    return results_dir / f"{safe_key}.json", results_dir / f"{safe_key}.md"


def compute_dataset_signature(dataset_path: Path) -> str:
    digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    return digest[:16]


def dataset_artifact_paths(dataset_key: str, dataset_path: Path, data_dir: Path, root_dir: Path) -> list[Path]:
    targets: list[Path] = [dataset_path]
    if dataset_key != DEFAULT_DATASET_KEY:
        results_path, results_md_path = resolve_results_paths(dataset_key, data_dir, root_dir)
        targets.extend(
            [
                results_path,
                results_path.with_suffix(results_path.suffix + ".tmp"),
                results_path.with_suffix(results_path.suffix + ".corrupt"),
                results_md_path,
                results_md_path.with_suffix(results_md_path.suffix + ".tmp"),
                results_md_path.with_suffix(results_md_path.suffix + ".corrupt"),
            ]
        )

    unique_targets: list[Path] = []
    seen: set[Path] = set()
    for target in targets:
        if target in seen:
            continue
        seen.add(target)
        unique_targets.append(target)
    return unique_targets


def delete_uploaded_dataset_with_artifacts(
    dataset_option: DatasetOption,
    data_dir: Path,
    root_dir: Path,
) -> DatasetDeleteSummary:
    if dataset_option.get("is_default") or dataset_option.get("key") == DEFAULT_DATASET_KEY:
        raise ValueError("Default dataset cannot be deleted.")

    target_paths = dataset_artifact_paths(
        dataset_key=dataset_option["key"],
        dataset_path=dataset_option["path"],
        data_dir=data_dir,
        root_dir=root_dir,
    )

    deleted_count = 0
    missing_count = 0
    lock_path = data_dir / ".datasets.lock"
    with portalocker.Lock(str(lock_path), timeout=10):
        for target in target_paths:
            if target.exists():
                target.unlink(missing_ok=True)
                deleted_count += 1
            else:
                missing_count += 1

    return {
        "target_count": len(target_paths),
        "deleted_count": deleted_count,
        "missing_count": missing_count,
    }
