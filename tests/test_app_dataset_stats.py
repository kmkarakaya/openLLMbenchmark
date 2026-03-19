import pandas as pd

from app import build_dataset_metadata_stats


def _lookup(frame: pd.DataFrame, section: str, metric: str) -> pd.Series:
    row = frame[(frame["Section"] == section) & (frame["Metric"] == metric)]
    assert len(row) == 1
    return row.iloc[0]


def test_build_dataset_metadata_stats_dynamic_counts() -> None:
    questions = [
        {"id": "q001", "category": "Finance", "hardness_level": "Easy", "why_prepared": "numeric reasoning"},
        {"id": "q002", "category": "Finance", "hardness_level": "", "why_prepared": ""},
        {"id": "q003", "category": "Coding", "hardness_level": "Hard", "why_prepared": "coding skills"},
        {"id": "q004", "category": "", "hardness_level": "Hard", "why_prepared": None},
    ]

    frame = build_dataset_metadata_stats(questions)

    assert _lookup(frame, "Summary", "Total questions")["Count"] == 4
    assert _lookup(frame, "Summary", "Unique topics")["Count"] == 3
    assert _lookup(frame, "Summary", "Unique hardness levels")["Count"] == 3
    assert _lookup(frame, "Summary", "Questions with topic")["Count"] == 3
    assert _lookup(frame, "Summary", "Questions with hardness level")["Count"] == 3
    assert _lookup(frame, "Summary", "Questions with why_prepared")["Count"] == 2

    assert _lookup(frame, "Topic", "Finance")["Count"] == 2
    assert _lookup(frame, "Topic", "Coding")["Count"] == 1
    assert _lookup(frame, "Topic", "(missing)")["Count"] == 1

    assert _lookup(frame, "Hardness", "Hard")["Count"] == 2
    assert _lookup(frame, "Hardness", "Easy")["Count"] == 1
    assert _lookup(frame, "Hardness", "(missing)")["Count"] == 1


def test_build_dataset_metadata_stats_handles_empty_input() -> None:
    frame = build_dataset_metadata_stats([])
    assert list(frame.columns) == ["Section", "Metric", "Count", "Share (%)"]
    assert frame.empty


def test_build_dataset_metadata_stats_strips_but_preserves_case() -> None:
    questions = [
        {"id": "q001", "category": "  Finance  ", "hardness_level": " Easy ", "why_prepared": "x"},
        {"id": "q002", "category": "finance", "hardness_level": "Easy", "why_prepared": "y"},
    ]

    frame = build_dataset_metadata_stats(questions)

    assert _lookup(frame, "Topic", "Finance")["Count"] == 1
    assert _lookup(frame, "Topic", "finance")["Count"] == 1
    assert _lookup(frame, "Hardness", "Easy")["Count"] == 2
