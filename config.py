from __future__ import annotations

import os
from dataclasses import dataclass


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FeatureFlags:
    api_reads: bool
    api_runs: bool
    api_writes: bool
    new_ui: bool


def get_feature_flags() -> FeatureFlags:
    return FeatureFlags(
        api_reads=_env_flag("FEATURE_API_READS", True),
        api_runs=_env_flag("FEATURE_API_RUNS", False),
        api_writes=_env_flag("FEATURE_API_WRITES", False),
        new_ui=_env_flag("FEATURE_NEW_UI", False),
    )
