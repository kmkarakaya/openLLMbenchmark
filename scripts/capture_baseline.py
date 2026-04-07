from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fixtures import capture_baseline_fixtures

DATA_DIR = ROOT / "data"


def main() -> None:
    results_path = DATA_DIR / "results.json"
    markdown_path = ROOT / "results.md"
    json_target, md_target = capture_baseline_fixtures(results_path, markdown_path)
    print(f"Baseline JSON: {json_target}")
    print(f"Baseline MD: {md_target}")


if __name__ == "__main__":
    main()
