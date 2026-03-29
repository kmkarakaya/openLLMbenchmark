from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BASELINE_DIR = DATA_DIR / "baselines"


def _normalise_markdown(text: str) -> str:
    lines = []
    for line in text.splitlines():
        if line.startswith("_Güncellendi: "):
            lines.append("_Güncellendi: <normalized>_")
        else:
            lines.append(line)
    return "\n".join(lines)


def capture_baseline_fixtures(results_path: Path, markdown_path: Path) -> tuple[Path, Path]:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    json_target = BASELINE_DIR / "results.json"
    md_target = BASELINE_DIR / "results.md"

    payload: list[dict[str, Any]] = []
    if results_path.exists():
        payload = json.loads(results_path.read_text(encoding="utf-8"))
    json_target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else ""
    md_target.write_text(_normalise_markdown(markdown), encoding="utf-8")
    return json_target, md_target


def load_baseline_fixtures() -> tuple[list[dict[str, Any]], str]:
    json_target = BASELINE_DIR / "results.json"
    md_target = BASELINE_DIR / "results.md"
    payload: list[dict[str, Any]] = []
    if json_target.exists():
        payload = json.loads(json_target.read_text(encoding="utf-8"))
    markdown = md_target.read_text(encoding="utf-8") if md_target.exists() else ""
    return payload, markdown
