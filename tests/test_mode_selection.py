from mode_selection import (
    MODE_PAIR,
    MODE_SINGLE,
    derive_initial_mode,
    is_run_eligible,
    normalize_selected_models,
    resolve_active_models,
    resolve_second_model_value,
    update_pair_model_backup,
)


def test_derive_initial_mode_from_legacy_selection() -> None:
    assert derive_initial_mode(selected_models=["gemma3:4b", "qwen3:8b"], selected_model="") == MODE_PAIR
    assert derive_initial_mode(selected_models=["gemma3:4b"], selected_model="") == MODE_SINGLE
    assert derive_initial_mode(selected_models=[], selected_model="gemma3:4b") == MODE_SINGLE


def test_pair_model_backup_preserved_and_restored() -> None:
    backup = update_pair_model_backup(
        current_backup="",
        mode=MODE_PAIR,
        model_1="gemma3:4b",
        model_2="qwen3:8b",
    )
    assert backup == "qwen3:8b"

    # Simulate pair -> single transition where active models keep only model_1.
    restored = resolve_second_model_value(
        selected_models=["gemma3:4b"],
        pair_model_backup=backup,
        model_1="gemma3:4b",
    )
    assert restored == "qwen3:8b"


def test_resolve_active_models_handles_duplicate_pair_selection() -> None:
    active, duplicate = resolve_active_models(
        mode=MODE_PAIR,
        model_1="gemma3:4b",
        model_2="gemma3:4b",
    )
    assert active == ["gemma3:4b"]
    assert duplicate is True


def test_active_model_derivation_per_mode() -> None:
    single_models, _ = resolve_active_models(
        mode=MODE_SINGLE,
        model_1="gemma3:4b",
        model_2="qwen3:8b",
    )
    pair_models, _ = resolve_active_models(
        mode=MODE_PAIR,
        model_1="gemma3:4b",
        model_2="qwen3:8b",
    )
    assert single_models == ["gemma3:4b"]
    assert pair_models == ["gemma3:4b", "qwen3:8b"]


def test_run_eligibility_rules() -> None:
    assert is_run_eligible(MODE_SINGLE, ["gemma3:4b"]) is True
    assert is_run_eligible(MODE_SINGLE, []) is False
    assert is_run_eligible(MODE_PAIR, ["gemma3:4b"]) is False
    assert is_run_eligible(MODE_PAIR, ["gemma3:4b", "qwen3:8b"]) is True


def test_normalize_selected_models_deduplicates_and_limits() -> None:
    models = normalize_selected_models(" gemma3:4b ", "", "gemma3:4b", "qwen3:8b", "llama3:8b")
    assert models == ["gemma3:4b", "qwen3:8b"]
