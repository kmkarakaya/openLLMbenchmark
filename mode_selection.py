from __future__ import annotations

MODE_SINGLE = "single"
MODE_PAIR = "pair"


def normalize_selected_models(*values: str) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        model = str(value).strip()
        if not model or model in seen:
            continue
        normalized.append(model)
        seen.add(model)
    return normalized[:2]


def sanitize_mode(mode: str) -> str:
    return MODE_PAIR if str(mode).strip() == MODE_PAIR else MODE_SINGLE


def derive_initial_mode(*, selected_models: list[str], selected_model: str) -> str:
    normalized = normalize_selected_models(*selected_models, selected_model)
    return MODE_PAIR if len(normalized) >= 2 else MODE_SINGLE


def resolve_second_model_value(
    *,
    selected_models: list[str],
    pair_model_backup: str,
    model_1: str,
) -> str:
    candidate = ""
    if len(selected_models) > 1:
        candidate = str(selected_models[1]).strip()
    elif pair_model_backup:
        candidate = str(pair_model_backup).strip()

    if candidate and candidate == str(model_1).strip():
        return ""
    return candidate


def resolve_active_models(*, mode: str, model_1: str, model_2: str) -> tuple[list[str], bool]:
    first = str(model_1).strip()
    second = str(model_2).strip()
    duplicate_selection = bool(first and second and first == second)
    if sanitize_mode(mode) == MODE_SINGLE:
        return normalize_selected_models(first), duplicate_selection
    return normalize_selected_models(first, second), duplicate_selection


def is_run_eligible(mode: str, active_models: list[str]) -> bool:
    normalized = normalize_selected_models(*active_models)
    if sanitize_mode(mode) == MODE_PAIR:
        return len(normalized) == 2
    return len(normalized) >= 1


def update_pair_model_backup(
    *,
    current_backup: str,
    mode: str,
    model_1: str,
    model_2: str,
) -> str:
    backup = str(current_backup or "").strip()
    if sanitize_mode(mode) != MODE_PAIR:
        return backup

    first = str(model_1).strip()
    second = str(model_2).strip()
    if second and second != first:
        return second
    return backup
