from __future__ import annotations

from model_identity import to_model_ref


def test_to_model_ref_preserves_explicit_source_suffix() -> None:
    assert to_model_ref("glm-5:cloud", "local") == "glm-5:cloud"
    assert to_model_ref("gemma4:e4b:local", "cloud") == "gemma4:e4b:local"


def test_to_model_ref_uses_hint_when_suffix_missing() -> None:
    assert to_model_ref("gemma4:e4b", "local") == "gemma4:e4b:local"
    assert to_model_ref("qwen3.5", "cloud") == "qwen3.5:cloud"
