from __future__ import annotations

import json
import os
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from data.benchmark import (
    DEFAULT_SYSTEM_PROMPT,
    DatasetValidationError,
    load_benchmark_payload,
)
from engine import get_client, list_models
from mode_selection import (
    MODE_PAIR,
    MODE_SINGLE,
    derive_initial_mode,
    is_run_eligible,
    normalize_selected_models as normalize_models,
    resolve_active_models,
    resolve_second_model_value,
    sanitize_mode,
    update_pair_model_backup,
)
from runner import get_runner
from scoring import evaluate_response
from storage import (
    compute_model_metrics,
    format_cell,
    load_results,
    prepare_results_excel,
    prepare_results_json,
    render_results_markdown,
    save_results,
    upsert_result,
)


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
BENCHMARK_PATH = DATA_DIR / "benchmark.json"
RESULTS_PATH = DATA_DIR / "results.json"
RESULTS_MD_PATH = ROOT / "results.md"
RESPONSE_VIEW_OPTIONS = ["Plain text", "Render (MD/HTML)"]


def init_page() -> None:
    st.set_page_config(
        page_title="Open LLM Benchmark",
        page_icon="📊",
        layout="wide",
    )
    st.markdown(
        """
        <style>
          :root {
            --bg-top: #f6f8fc;
            --bg-bottom: #e9f0f8;
            --card: #ffffff;
            --ink: #0f172a;
            --muted: #475569;
            --accent: #1f6faa;
            --accent-hover: #175a8a;
            --accent-strong: #124a73;
            --disabled-bg: #94a3b8;
            --disabled-border: #7b8ba1;
            --ok: #137a43;
            --fail: #b42318;
          }
          .stApp {
            background: radial-gradient(1400px 600px at -10% -20%, #ffe7ca 0%, transparent 60%),
                        radial-gradient(1000px 500px at 120% 120%, #d8f2ff 0%, transparent 60%),
                        linear-gradient(180deg, var(--bg-top), var(--bg-bottom));
          }
          [data-testid="stHeader"] {
            background: linear-gradient(180deg, #f7fbff 0%, #eef5fc 100%) !important;
            border-bottom: 1px solid #d9e4f0 !important;
          }
          [data-testid="stHeader"] *,
          [data-testid="stToolbar"] *,
          [data-testid="stStatusWidget"] * {
            color: var(--ink) !important;
            -webkit-text-fill-color: var(--ink) !important;
          }
          [data-testid="stDecoration"] {
            background: transparent !important;
          }
          .block-container {
            padding-top: 1.5rem;
          }
          .page-main-title {
            margin: 0.2rem 0 0.35rem 0;
            text-align: center;
            font-size: clamp(2rem, 3.8vw, 3rem);
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--ink);
          }
          .page-byline {
            margin: 0 0 0.45rem 0;
            text-align: center;
            color: var(--accent-strong);
            line-height: 1.2;
          }
          .page-byline-by {
            display: block;
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.12rem;
          }
          .page-byline-name {
            display: block;
            font-size: 1.5rem;
            font-weight: 700;
          }
          .profile-pill-wrap {
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
            gap: 0.55rem;
            margin: -0.2rem 0 1rem 0;
          }
          .profile-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.35rem 0.75rem;
            border-radius: 999px;
            border: 1px solid #c9d9ea;
            background: #ffffff;
            color: #0f3d5e !important;
            font-weight: 650;
            font-size: 0.9rem;
            text-decoration: none !important;
            box-shadow: 0 2px 8px rgba(15, 61, 94, 0.08);
          }
          .profile-pill:hover {
            border-color: #1f6faa;
            background: #f2f8ff;
            color: #124a73 !important;
            transform: translateY(-1px);
          }
          @media (max-width: 720px) {
            .profile-pill {
              font-size: 0.84rem;
              padding: 0.32rem 0.62rem;
            }
          }
          .bench-card {
            background: var(--card);
            border: 1px solid #e8ecf1;
            border-radius: 16px;
            padding: 1rem 1.25rem;
            box-shadow: 0 8px 24px rgba(23, 33, 58, 0.06);
            margin-bottom: 0.8rem;
          }
          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #fffaf2 0%, #f0f8ff 100%) !important;
            border-right: 1px solid #dce5ef;
          }
          [data-testid="stSidebar"] * {
            color: var(--ink) !important;
          }
          [data-testid="stSidebar"] .stButton > button,
          [data-testid="stSidebar"] .stButton > button[kind],
          [data-testid="stSidebar"] .stButton > button:focus,
          [data-testid="stSidebar"] .stButton > button:focus-visible {
            background: var(--accent) !important;
            color: #ffffff !important;
            border: 1px solid var(--accent-strong) !important;
            font-weight: 600 !important;
            border-radius: 12px !important;
            min-height: 44px !important;
            padding: 0.45rem 0.75rem !important;
            line-height: 1.2 !important;
            box-shadow: 0 4px 10px rgba(18, 74, 115, 0.22) !important;
            white-space: nowrap !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button {
            background: var(--accent) !important;
            color: #ffffff !important;
            border: 1px solid var(--accent-strong) !important;
            font-weight: 600 !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button *,
          [data-testid="stSidebar"] .stButton > button * {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button:hover {
            background: var(--accent-hover) !important;
            color: #ffffff !important;
            border-color: var(--accent-strong) !important;
          }
          [data-testid="stSidebar"] .stButton > button:hover {
            background: var(--accent-hover) !important;
            color: #ffffff !important;
            border-color: var(--accent-strong) !important;
            transform: translateY(-1px);
          }
          [data-testid="stSidebar"] .stButton > button:active {
            background: var(--accent-strong) !important;
            color: #ffffff !important;
            border-color: #0f3d5e !important;
          }
          [data-testid="stSidebar"] .stButton > button:focus,
          [data-testid="stSidebar"] .stButton > button:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(31, 111, 170, 0.25) !important;
          }
          [data-testid="stSidebar"] .stButton > button p,
          [data-testid="stSidebar"] .stButton > button span,
          [data-testid="stSidebar"] .stButton > button div {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
          }
          [data-testid="stSidebar"] .stButton [data-testid="stMarkdownContainer"],
          [data-testid="stSidebar"] .stButton [data-testid="stMarkdownContainer"] *,
          [data-testid="stSidebar"] .stButton [data-testid="stMarkdownContainer"] p,
          [data-testid="stSidebar"] .stButton [data-testid="stMarkdownContainer"] span {
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
          }
          [data-testid="stSidebar"] .stDownloadButton > button,
          [data-testid="stAppViewContainer"] .stDownloadButton > button {
            background: #ffffff !important;
            color: var(--accent-strong) !important;
            border: 1px solid #9cbfdc !important;
            border-radius: 10px !important;
            min-height: 40px !important;
            padding: 0.38rem 0.75rem !important;
            line-height: 1.2 !important;
            font-weight: 650 !important;
            box-shadow: 0 2px 8px rgba(18, 74, 115, 0.12) !important;
          }
          [data-testid="stSidebar"] .stDownloadButton > button *,
          [data-testid="stSidebar"] .stDownloadButton > button p,
          [data-testid="stSidebar"] .stDownloadButton > button span,
          [data-testid="stSidebar"] .stDownloadButton > button div,
          [data-testid="stSidebar"] .stDownloadButton [data-testid="stMarkdownContainer"],
          [data-testid="stSidebar"] .stDownloadButton [data-testid="stMarkdownContainer"] *,
          [data-testid="stSidebar"] .stDownloadButton [data-testid="stMarkdownContainer"] p,
          [data-testid="stSidebar"] .stDownloadButton [data-testid="stMarkdownContainer"] span {
            color: var(--accent-strong) !important;
            -webkit-text-fill-color: var(--accent-strong) !important;
          }
          [data-testid="stSidebar"] .stDownloadButton > button:hover,
          [data-testid="stAppViewContainer"] .stDownloadButton > button:hover {
            background: #eef6ff !important;
            border-color: var(--accent) !important;
            color: var(--accent-strong) !important;
            transform: translateY(-1px);
          }
          [data-testid="stSidebar"] .stDownloadButton > button:focus,
          [data-testid="stSidebar"] .stDownloadButton > button:focus-visible {
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(31, 111, 170, 0.2) !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button:disabled,
          [data-testid="stSidebar"] .stButton > button:disabled {
            background: var(--disabled-bg) !important;
            color: #ffffff !important;
            border-color: var(--disabled-border) !important;
            opacity: 1 !important;
          }
          [data-testid="stAppViewContainer"] .stDownloadButton > button:disabled,
          [data-testid="stSidebar"] .stDownloadButton > button:disabled {
            background: #e5edf5 !important;
            color: #6b7f95 !important;
            border-color: #c6d7e8 !important;
            opacity: 1 !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button[kind="primary"] {
            background: var(--accent-strong) !important;
            border-color: #0f3d5e !important;
            color: #ffffff !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button[kind="primary"]:hover {
            background: #0f3d5e !important;
            border-color: #0d324d !important;
          }
          [data-testid="stSidebar"] .stTextInput input,
          [data-testid="stSidebar"] .stNumberInput input,
          [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #ffffff !important;
            color: var(--ink) !important;
            border-color: #c8d5e3 !important;
          }
          [data-testid="stSidebar"] [data-testid="stExpander"] details > summary {
            background: var(--accent) !important;
            border: 1px solid var(--accent-strong) !important;
            border-radius: 10px !important;
            padding: 0.35rem 0.6rem !important;
          }
          [data-testid="stSidebar"] [data-testid="stExpander"] details > summary:hover,
          [data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary {
            background: var(--accent-hover) !important;
          }
          [data-testid="stSidebar"] [data-testid="stExpander"] details > summary *,
          [data-testid="stSidebar"] [data-testid="stExpander"] details > summary p,
          [data-testid="stSidebar"] [data-testid="stExpander"] details > summary span,
          [data-testid="stSidebar"] [data-testid="stExpander"] details > summary svg {
            color: #ffffff !important;
            fill: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
          }
          [data-testid="stAppViewContainer"] h1,
          [data-testid="stAppViewContainer"] h2,
          [data-testid="stAppViewContainer"] h3,
          [data-testid="stAppViewContainer"] label,
          [data-testid="stAppViewContainer"] p,
          [data-testid="stAppViewContainer"] span {
            color: var(--ink) !important;
          }
          [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"],
          [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] * {
            color: var(--ink) !important;
            -webkit-text-fill-color: var(--ink) !important;
          }
          [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] code,
          [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] code * {
            background: #0f172a !important;
            color: #e2e8f0 !important;
            -webkit-text-fill-color: #e2e8f0 !important;
            border: 1px solid #1e293b !important;
            border-radius: 6px !important;
            padding: 0.1rem 0.35rem !important;
          }
          [data-testid="stAppViewContainer"] .stTextArea textarea {
            background: #ffffff !important;
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            opacity: 1 !important;
            border: 1px solid #cfd8e3 !important;
          }
          [data-testid="stAppViewContainer"] .stTextArea textarea:disabled {
            color: #111827 !important;
            -webkit-text-fill-color: #111827 !important;
            opacity: 1 !important;
          }
          [data-testid="stAppViewContainer"] .stNumberInput input {
            background: #1e293b !important;
            color: #f8fafc !important;
            -webkit-text-fill-color: #f8fafc !important;
            border: 1px solid #0f172a !important;
          }
          [data-testid="stAppViewContainer"] .stNumberInput button {
            background: #1e293b !important;
            color: #f8fafc !important;
            border-color: #0f172a !important;
          }
          .meta-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin: 0.2rem 0 0.55rem 0;
          }
          .meta-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.3rem 0.65rem;
            border-radius: 999px;
            border: 1px solid;
            font-size: 0.88rem;
            font-weight: 700;
            line-height: 1.2;
          }
          [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] .meta-chip,
          [data-testid="stAppViewContainer"] [data-testid="stMarkdownContainer"] .meta-chip * {
            -webkit-text-fill-color: inherit !important;
          }
          .meta-id {
            background: #e0ecff;
            border-color: #bfd6ff;
            color: #1e3a8a !important;
          }
          .meta-category {
            background: #e6f8f2;
            border-color: #b8eadb;
            color: #0f766e !important;
          }
          .meta-model {
            background: #e9eefc;
            border-color: #c8d6ff;
            color: #4338ca !important;
          }
          .meta-hardness {
            background: #fff7e6;
            border-color: #ffd8a8;
            color: #9a3412 !important;
          }
          .meta-note {
            margin: 0.15rem 0 0.7rem 0;
            padding: 0.65rem 0.8rem;
            border-radius: 12px;
            border: 1px solid #bfdbfe;
            background: #eff6ff;
          }
          .meta-note-label {
            display: inline-block;
            margin-right: 0.35rem;
            font-weight: 700;
            color: #1d4ed8 !important;
          }
          .meta-note-text {
            color: #1e293b !important;
          }
          .status-wrap {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin: 0.55rem 0 0.4rem 0;
          }
          .status-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.3rem 0.65rem;
            border-radius: 999px;
            border: 1px solid;
            font-size: 0.85rem;
            font-weight: 700;
            line-height: 1.2;
          }
          .status-success {
            background: #e8f8ef;
            border-color: #b7ebce;
            color: #166534 !important;
          }
          .status-fail {
            background: #feeceb;
            border-color: #fbcac7;
            color: #9f1239 !important;
          }
          .status-review {
            background: #fff7e6;
            border-color: #ffd8a8;
            color: #9a3412 !important;
          }
          .status-neutral {
            background: #eef2ff;
            border-color: #c7d2fe;
            color: #3730a3 !important;
          }
          .status-auto-yes {
            background: #e6fffa;
            border-color: #99f6e4;
            color: #115e59 !important;
          }
          .status-auto-no {
            background: #fff7e6;
            border-color: #fed7aa;
            color: #9a3412 !important;
          }
          .status-reason {
            background: #eef2ff;
            border-color: #c7d2fe;
            color: #3730a3 !important;
            max-width: 440px;
          }
          .status-reason-label {
            font-weight: 800;
            color: #312e81 !important;
            flex-shrink: 0;
          }
          .status-reason-text {
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #3730a3 !important;
          }
          .kpi {
            font-weight: 650;
            color: var(--ink);
          }
          .muted {
            color: var(--muted);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_state() -> None:
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    if "question_index" not in st.session_state:
        st.session_state.question_index = 0
    if "selected_model" not in st.session_state:
        st.session_state.selected_model = ""
    if "selected_models" not in st.session_state:
        initial_model = str(st.session_state.selected_model or "").strip()
        st.session_state.selected_models = [initial_model] if initial_model else []
    normalized_existing = normalize_models(
        *st.session_state.selected_models,
        st.session_state.selected_model,
    )
    st.session_state.selected_models = normalized_existing
    st.session_state.selected_model = normalized_existing[0] if normalized_existing else ""
    if "benchmark_mode" not in st.session_state:
        st.session_state.benchmark_mode = derive_initial_mode(
            selected_models=normalized_existing,
            selected_model=st.session_state.selected_model,
        )
    else:
        st.session_state.benchmark_mode = sanitize_mode(st.session_state.benchmark_mode)
    if "pair_model_backup" not in st.session_state:
        st.session_state.pair_model_backup = normalized_existing[1] if len(normalized_existing) > 1 else ""
    st.session_state.pair_model_backup = str(st.session_state.pair_model_backup or "").strip()
    if "persisted_run_entry_keys" not in st.session_state:
        st.session_state.persisted_run_entry_keys = []
    if "runtime_api_key" not in st.session_state:
        st.session_state.runtime_api_key = ""
    if "model_cache" not in st.session_state:
        st.session_state.model_cache = []
    if "system_prompt" not in st.session_state:
        st.session_state.system_prompt = DEFAULT_SYSTEM_PROMPT
    if "response_view_mode_pref" not in st.session_state:
        st.session_state.response_view_mode_pref = RESPONSE_VIEW_OPTIONS[0]
    if "response_view_mode_widget" in st.session_state:
        widget_mode = str(st.session_state.response_view_mode_widget or "").strip()
        if widget_mode in RESPONSE_VIEW_OPTIONS:
            st.session_state.response_view_mode_pref = widget_mode
    if (
        "response_view_mode_widget" not in st.session_state
        or st.session_state.response_view_mode_widget not in RESPONSE_VIEW_OPTIONS
    ):
        st.session_state.response_view_mode_widget = st.session_state.response_view_mode_pref
    if "last_seen_question_id" not in st.session_state:
        st.session_state.last_seen_question_id = ""
    if "pending_autorun" not in st.session_state:
        st.session_state.pending_autorun = None


def ensure_dataset() -> dict[str, Any]:
    return load_benchmark_payload(BENCHMARK_PATH)


def refresh_models() -> list[str]:
    client = get_client()
    models = list_models(client)
    st.session_state.model_cache = models
    return models


@st.cache_data
def _cached_results_json(results: list[dict[str, Any]]) -> bytes:
    return prepare_results_json(results)


@st.cache_data
def _cached_results_excel(results: list[dict[str, Any]]) -> bytes:
    return prepare_results_excel(results)


def normalize_selected_models(*values: str) -> list[str]:
    return normalize_models(*values)


def sidebar_collapsible_section(title: str, state_key: str, default: bool = False) -> bool:
    if state_key not in st.session_state:
        st.session_state[state_key] = default
    is_open = bool(st.session_state[state_key])
    chevron = "▾" if is_open else "▸"
    if st.button(f"{chevron} {title}", key=f"{state_key}_toggle", use_container_width=True):
        is_open = not is_open
        st.session_state[state_key] = is_open
    return is_open


def pick_models(models: list[str]) -> tuple[list[str], bool]:
    options = [""] + models
    existing = normalize_selected_models(*st.session_state.selected_models, st.session_state.selected_model)
    selected_model_1 = existing[0] if existing else ""
    selected_model_2 = resolve_second_model_value(
        selected_models=existing,
        pair_model_backup=st.session_state.pair_model_backup,
        model_1=selected_model_1,
    )
    benchmark_mode = sanitize_mode(st.session_state.benchmark_mode)

    for model in normalize_selected_models(*existing, st.session_state.pair_model_backup):
        if model and model not in options:
            options.append(model)

    benchmark_config_open = sidebar_collapsible_section(
        "Benchmark Config",
        "sidebar_benchmark_config_open",
        default=False,
    )
    model_1 = selected_model_1
    model_2 = selected_model_2
    if benchmark_config_open:
        st.subheader("Usage Mode")
        mode_labels = {
            "Single model": MODE_SINGLE,
            "Comparison (2 models)": MODE_PAIR,
        }
        mode_options = list(mode_labels.keys())
        selected_mode = st.radio(
            "Usage mode",
            options=mode_options,
            index=0 if benchmark_mode == MODE_SINGLE else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        benchmark_mode = mode_labels[selected_mode]
        st.session_state.benchmark_mode = benchmark_mode
        if benchmark_mode == MODE_SINGLE:
            st.caption("Evaluates one model on its own.")
        else:
            st.caption("Tests two models side by side on the same question.")

        st.subheader("Model Selection")
        selected_1 = st.selectbox(
            "Select Ollama Cloud LLM 1",
            options=options,
            index=options.index(selected_model_1) if selected_model_1 in options else 0,
            help="Choose from the model list or enter the model name manually.",
        )
        manual_1 = st.text_input("Model 1 name (manual)", value=selected_1 or selected_model_1)
        model_1 = manual_1.strip() or selected_1.strip()
        if benchmark_mode == MODE_PAIR:
            second_options = [""] + [item for item in options[1:] if item != model_1]
            if selected_model_2 and selected_model_2 not in second_options and selected_model_2 != model_1:
                second_options.append(selected_model_2)

            selected_2 = st.selectbox(
                "Select Ollama Cloud LLM 2",
                options=second_options,
                index=second_options.index(selected_model_2) if selected_model_2 in second_options else 0,
                help="For comparison, select a second model or enter its name manually.",
            )
            manual_2 = st.text_input(
                "Model 2 name (manual)",
                value=selected_2 or (selected_model_2 if selected_model_2 != model_1 else ""),
            )
            model_2 = manual_2.strip() or selected_2.strip()

    active_models, duplicate_selection = resolve_active_models(
        mode=benchmark_mode,
        model_1=model_1,
        model_2=model_2,
    )
    st.session_state.pair_model_backup = update_pair_model_backup(
        current_backup=st.session_state.pair_model_backup,
        mode=benchmark_mode,
        model_1=model_1,
        model_2=model_2,
    )

    run_eligible = is_run_eligible(benchmark_mode, active_models)
    if benchmark_config_open and benchmark_mode == MODE_PAIR:
        if duplicate_selection:
            st.warning("Select two different models for comparison.")
        elif not model_2:
            st.info("Select or enter a second model for comparison mode.")

    st.session_state.selected_models = active_models
    st.session_state.selected_model = active_models[0] if active_models else ""
    return active_models, run_eligible


def render_question_meta(question: dict[str, Any], selected_models: list[str]) -> None:
    question_id = html_escape(str(question.get("id", "-")))
    category = html_escape(str(question.get("category", "GENERAL")))
    model = html_escape(" | ".join(selected_models) or "-")
    hardness = html_escape(str(question.get("hardness_level", "")).strip() or "-")
    why_prepared = str(question.get("why_prepared", "")).strip()

    st.markdown(
        f"""
        <div class="meta-wrap">
          <span class="meta-chip meta-id">Question: {question_id}</span>
          <span class="meta-chip meta-category">Category: {category}</span>
          <span class="meta-chip meta-model">Selected model(s): {model}</span>
          <span class="meta-chip meta-hardness">Difficulty: {hardness}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if why_prepared:
        st.markdown(
            f"""
            <div class="meta-note">
              <span class="meta-note-label">Why prepared:</span>
              <span class="meta-note-text">{html_escape(why_prepared)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_copy_button(response_text: str, key: str, disabled: bool = False) -> None:
    button_id = f"copy_btn_{abs(hash(key))}"
    status_id = f"copy_status_{abs(hash(f'{key}_status'))}"
    text_json = json.dumps(response_text or "", ensure_ascii=False).replace("</", "<\\/")
    is_disabled = disabled or not str(response_text).strip()
    disabled_attr = "disabled" if is_disabled else ""
    button_bg = "#94a3b8" if is_disabled else "#1f6faa"
    button_border = "#7b8ba1" if is_disabled else "#124a73"
    button_cursor = "not-allowed" if is_disabled else "pointer"

    components.html(
        f"""
        <div style="display:flex;align-items:center;justify-content:flex-end;gap:8px;">
          <button id="{button_id}" {disabled_attr}
            style="
              background:{button_bg};color:#ffffff;border:1px solid {button_border};
              border-radius:10px;padding:0.4rem 0.9rem;font-weight:600;cursor:{button_cursor};
            ">
            Copy
          </button>
          <span id="{status_id}" style="font-size:0.85rem;color:#475569;"></span>
        </div>
        <script>
          const button = document.getElementById("{button_id}");
          const status = document.getElementById("{status_id}");
          const textToCopy = {text_json};

          async function copyWithNavigatorClipboard(text) {{
            if (navigator && navigator.clipboard && navigator.clipboard.writeText) {{
              await navigator.clipboard.writeText(text);
              return true;
            }}
            return false;
          }}

          async function copyWithParentClipboard(text) {{
            try {{
              if (window.parent && window.parent.navigator && window.parent.navigator.clipboard) {{
                await window.parent.navigator.clipboard.writeText(text);
                return true;
              }}
            }} catch (_err) {{
              // ignore and fallback
            }}
            return false;
          }}

          function copyWithExecCommand(text) {{
            const textArea = document.createElement("textarea");
            textArea.value = text;
            textArea.setAttribute("readonly", "");
            textArea.style.position = "fixed";
            textArea.style.opacity = "0";
            textArea.style.left = "-9999px";
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            let ok = false;
            try {{
              ok = document.execCommand("copy");
            }} catch (_err) {{
              ok = false;
            }}
            document.body.removeChild(textArea);
            return ok;
          }}

          if (button) {{
            button.addEventListener("click", async () => {{
              if (!textToCopy || !textToCopy.trim()) {{
                status.textContent = "No text to copy";
                return;
              }}
              try {{
                let copied = await copyWithNavigatorClipboard(textToCopy);
                if (!copied) {{
                  copied = await copyWithParentClipboard(textToCopy);
                }}
                if (!copied) {{
                  copied = copyWithExecCommand(textToCopy);
                }}
                if (!copied) {{
                  throw new Error("copy_failed");
                }}
                status.textContent = "Copied";
                setTimeout(() => status.textContent = "", 1500);
              }} catch (_err) {{
                status.textContent = "Copy failed";
              }}
            }});
          }}
        </script>
        """,
        height=48,
    )


def is_full_html_document(response_text: str) -> bool:
    normalized = response_text.lstrip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")


def render_response_content(response_text: str, view_mode: str, key: str) -> None:
    value = str(response_text or "")
    plain_widget_key = f"{key}_plain_text"
    render_empty_widget_key = f"{key}_render_empty_text"

    if view_mode == "Plain text":
        if st.session_state.get(plain_widget_key) != value:
            st.session_state[plain_widget_key] = value
        st.text_area(
            "Response",
            height=240,
            disabled=True,
            label_visibility="collapsed",
            key=plain_widget_key,
        )
        return

    if not value.strip():
        if render_empty_widget_key not in st.session_state:
            st.session_state[render_empty_widget_key] = ""
        st.text_area(
            "Response",
            height=240,
            disabled=True,
            label_visibility="collapsed",
            key=render_empty_widget_key,
        )
        return

    if is_full_html_document(value):
        components.html(value, height=420, scrolling=True)
        return

    st.markdown(value, unsafe_allow_html=True)


def find_result(
    results: list[dict[str, Any]],
    question_id: str,
    model: str,
) -> dict[str, Any] | None:
    for item in results:
        if item.get("question_id") == question_id and item.get("model") == model:
            return item
    return None


def status_to_label(status: str) -> str:
    mapping = {
        "success": "Successful",
        "fail": "Failed",
        "manual_review": "Needs Review",
    }
    return mapping.get(status, status)


def status_chip_class(status: str) -> str:
    mapping = {
        "success": "status-success",
        "fail": "status-fail",
        "manual_review": "status-review",
    }
    return mapping.get(status, "status-neutral")


def render_result_meta(result: dict[str, Any]) -> None:
    raw_status = str(result.get("status", ""))
    status_label = html_escape(status_to_label(raw_status) or "-")
    status_class = status_chip_class(raw_status)
    auto_scored = bool(result.get("auto_scored"))
    auto_label = "Auto-scored" if auto_scored else "Manually scored"
    auto_class = "status-auto-yes" if auto_scored else "status-auto-no"
    reason = str(result.get("reason", "")).strip()
    reason_chip_html = ""
    reason_lower = reason.lower()
    show_reason = (
        bool(reason)
        and (
            "hata" in reason_lower
            or "error" in reason_lower
            or "durdur" in reason_lower
            or "stop" in reason_lower
            or "interrupt" in reason_lower
        )
    )
    if show_reason:
        reason_safe = html_escape(reason)
        reason_chip_html = (
            f'<span class="status-chip status-reason" title="{reason_safe}">'
            f'<span class="status-reason-label">Reason:</span>'
            f'<span class="status-reason-text">{reason_safe}</span>'
            "</span>"
        )

    st.markdown(
        f"""
        <div class="status-wrap">
          <span class="status-chip {status_class}">Status: {status_label}</span>
          <span class="status-chip {auto_class}">{auto_label}</span>
          {reason_chip_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def persist_result_record(
    results: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    updated = upsert_result(results, record)
    save_results(RESULTS_PATH, updated)
    render_results_markdown(questions=questions, results=updated, output_path=RESULTS_MD_PATH)
    return updated


def find_snapshot_entry(snapshot: dict[str, Any], question_id: str, model: str) -> dict[str, Any] | None:
    if snapshot.get("question_id") != question_id:
        return None
    for entry in snapshot.get("entries", []):
        if entry.get("model") == model:
            return entry
    return None


def build_verdict(entry: dict[str, Any], expected_answer: str) -> dict[str, Any]:
    response = str(entry.get("response", ""))
    if entry.get("interrupted"):
        return {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": "Stopped by user.",
        }
    if entry.get("error"):
        return {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": f"Hata: {entry['error']}",
        }
    return evaluate_response(expected_answer=expected_answer, response=response)


def handle_completed_runs(
    snapshot: dict[str, Any],
    results: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    question_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    run_id = snapshot["run_id"]
    if run_id == 0:
        return results
    if not snapshot.get("entries"):
        return results

    question = question_by_id.get(snapshot["question_id"])
    expected_answer = (question or {}).get("expected_answer", "")
    persisted_keys = set(st.session_state.persisted_run_entry_keys)

    for entry in snapshot.get("entries", []):
        if not entry.get("completed"):
            continue
        persist_key = f"{run_id}:{snapshot['question_id']}:{entry.get('model', '')}"
        if persist_key in persisted_keys:
            continue
        verdict = build_verdict(entry, expected_answer)
        record = {
            "question_id": snapshot["question_id"],
            "model": entry["model"],
            "response": str(entry.get("response", "")),
            "status": verdict["status"],
            "score": verdict["score"],
            "response_time_ms": round(float(entry.get("elapsed_ms", 0.0)), 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "interrupted": bool(entry.get("interrupted")),
            "auto_scored": bool(verdict.get("auto_scored")),
            "reason": verdict.get("reason", ""),
        }
        results = persist_result_record(results, questions, record)
        persisted_keys.add(persist_key)

    st.session_state.persisted_run_entry_keys = sorted(persisted_keys)
    return results


def render_metrics_panel(results: list[dict[str, Any]]) -> None:
    metrics = compute_model_metrics(results)
    st.subheader("Model Comparison")
    st.caption(
        "Note: Timing metrics can be affected by Ollama Cloud network/infrastructure conditions; "
        "interpret them primarily as relative comparisons between models."
    )
    if not metrics:
        st.caption("No results yet.")
        return

    frame = pd.DataFrame(
        {
            "Model Name": [row["model"] for row in metrics],
            "Performance Score": [round(row["accuracy_percent"], 1) for row in metrics],
            "Response Speed Score": [round(row["latency_score"], 1) for row in metrics],
            "Successful/Scored": [f"{row['success_count']}/{row['scored_count']}" for row in metrics],
            "Median (s)": [
                round((row["median_ms"] or 0.0) / 1000.0, 2) if row["median_ms"] else None
                for row in metrics
            ],
            "Mean (s)": [
                round((row["mean_ms"] or 0.0) / 1000.0, 2) if row["mean_ms"] else None
                for row in metrics
            ],
            "P95 (s)": [
                round((row["p95_ms"] or 0.0) / 1000.0, 2) if row["p95_ms"] else None
                for row in metrics
            ],
        }
    )
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Model Name": st.column_config.TextColumn(
                "Model Name",
                help="Evaluated Ollama model name. This column is not a higher/lower-is-better metric.",
            ),
            "Performance Score": st.column_config.NumberColumn(
                "Performance Score",
                help="(Successful answers / scored questions) x 100. Higher is better.",
                format="%.1f",
            ),
            "Successful/Scored": st.column_config.TextColumn(
                "Successful/Scored",
                help="Successful answers / total scored questions. This column is not a higher/lower-is-better metric.",
            ),
            "Median (s)": st.column_config.NumberColumn(
                "Median (s)",
                help="Median response time in seconds. Lower is better.",
                format="%.2f",
            ),
            "Mean (s)": st.column_config.NumberColumn(
                "Mean (s)",
                help="Mean response time in seconds. Lower is better.",
                format="%.2f",
            ),
            "P95 (s)": st.column_config.NumberColumn(
                "P95 (s)",
                help="95th percentile response time in seconds. Lower is better.",
                format="%.2f",
            ),
            "Response Speed Score": st.column_config.NumberColumn(
                "Response Speed Score",
                help="Speed score normalized by the fastest model median (0-100). Higher is better.",
                format="%.1f",
            ),
        },
    )


def render_matrix_panel(questions: list[dict[str, Any]], results: list[dict[str, Any]]) -> None:
    models = sorted({row.get("model", "") for row in results if row.get("model")})
    if not models:
        return

    mapping = {(r["question_id"], r["model"]): r for r in results if r.get("question_id") and r.get("model")}
    matrix_rows: list[dict[str, Any]] = []
    for q in questions:
        row: dict[str, Any] = {
            "Question ID": q["id"],
            "Category": q.get("category", "GENERAL"),
            "Difficulty": str(q.get("hardness_level", "")).strip() or "(missing)",
        }
        for model in models:
            row[model] = format_cell(mapping.get((q["id"], model)))
        matrix_rows.append(row)

    st.subheader("Question-Level Results Matrix")
    st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)


def _normalize_metadata_value(value: Any) -> str:
    normalized = str(value or "").strip()
    return normalized if normalized else "(missing)"


def build_dataset_metadata_stats(questions: list[dict[str, Any]]) -> pd.DataFrame:
    total_questions = len(questions)
    if total_questions == 0:
        return pd.DataFrame(columns=["Section", "Metric", "Count", "Share (%)"])

    topics = [_normalize_metadata_value(item.get("category", "")) for item in questions]
    hardness_levels = [_normalize_metadata_value(item.get("hardness_level", "")) for item in questions]
    why_prepared_values = [_normalize_metadata_value(item.get("why_prepared", "")) for item in questions]

    topic_counter = Counter(topics)
    hardness_counter = Counter(hardness_levels)

    non_missing_topics = sum(1 for value in topics if value != "(missing)")
    non_missing_hardness = sum(1 for value in hardness_levels if value != "(missing)")
    non_missing_why_prepared = sum(1 for value in why_prepared_values if value != "(missing)")

    rows: list[dict[str, Any]] = [
        {"Section": "Summary", "Metric": "Total questions", "Count": total_questions, "Share (%)": None},
        {"Section": "Summary", "Metric": "Unique topics", "Count": len(topic_counter), "Share (%)": None},
        {"Section": "Summary", "Metric": "Unique hardness levels", "Count": len(hardness_counter), "Share (%)": None},
        {
            "Section": "Summary",
            "Metric": "Questions with topic",
            "Count": non_missing_topics,
            "Share (%)": round(100.0 * non_missing_topics / total_questions, 1),
        },
        {
            "Section": "Summary",
            "Metric": "Questions with hardness level",
            "Count": non_missing_hardness,
            "Share (%)": round(100.0 * non_missing_hardness / total_questions, 1),
        },
        {
            "Section": "Summary",
            "Metric": "Questions with why_prepared",
            "Count": non_missing_why_prepared,
            "Share (%)": round(100.0 * non_missing_why_prepared / total_questions, 1),
        },
    ]

    for topic, count in sorted(topic_counter.items(), key=lambda x: (-x[1], x[0])):
        rows.append(
            {
                "Section": "Topic",
                "Metric": topic,
                "Count": count,
                "Share (%)": round(100.0 * count / total_questions, 1),
            }
        )

    for hardness, count in sorted(hardness_counter.items(), key=lambda x: (-x[1], x[0])):
        rows.append(
            {
                "Section": "Hardness",
                "Metric": hardness,
                "Count": count,
                "Share (%)": round(100.0 * count / total_questions, 1),
            }
        )

    return pd.DataFrame(rows, columns=["Section", "Metric", "Count", "Share (%)"])


def render_dataset_metadata_stats_panel(questions: list[dict[str, Any]]) -> None:
    st.subheader("Dataset & Metadata Statistics")
    stats_frame = build_dataset_metadata_stats(questions)
    if stats_frame.empty:
        st.caption("No dataset statistics available.")
        return

    topic_frame = (
        stats_frame[stats_frame["Section"] == "Topic"][["Metric", "Count"]]
        .rename(columns={"Metric": "Topic"})
        .copy()
    )
    hardness_frame = (
        stats_frame[stats_frame["Section"] == "Hardness"][["Metric", "Count"]]
        .rename(columns={"Metric": "Difficulty"})
        .copy()
    )

    if not topic_frame.empty:
        topic_total = float(topic_frame["Count"].sum())
        topic_frame["Share (%)"] = topic_frame["Count"].apply(lambda x: round(100.0 * float(x) / topic_total, 1))
    if not hardness_frame.empty:
        hardness_total = float(hardness_frame["Count"].sum())
        hardness_frame["Share (%)"] = hardness_frame["Count"].apply(
            lambda x: round(100.0 * float(x) / hardness_total, 1)
        )

    topic_col, difficulty_col = st.columns(2)
    with topic_col:
        st.markdown("**Topic Distribution**")
        if topic_frame.empty:
            st.caption("No topic values found.")
        else:
            st.vega_lite_chart(
                topic_frame,
                {
                    "mark": {"type": "arc", "innerRadius": 46},
                    "encoding": {
                        "theta": {"field": "Count", "type": "quantitative"},
                        "color": {"field": "Topic", "type": "nominal", "legend": {"title": "Topic"}},
                        "tooltip": [
                            {"field": "Topic", "type": "nominal"},
                            {"field": "Count", "type": "quantitative"},
                            {"field": "Share (%)", "type": "quantitative"},
                        ],
                    },
                },
                use_container_width=True,
            )

    with difficulty_col:
        st.markdown("**Difficulty Distribution**")
        if hardness_frame.empty:
            st.caption("No difficulty values found.")
        else:
            st.vega_lite_chart(
                hardness_frame,
                {
                    "mark": {"type": "arc", "innerRadius": 46},
                    "encoding": {
                        "theta": {"field": "Count", "type": "quantitative"},
                        "color": {
                            "field": "Difficulty",
                            "type": "nominal",
                            "legend": {"title": "Difficulty"},
                        },
                        "tooltip": [
                            {"field": "Difficulty", "type": "nominal"},
                            {"field": "Count", "type": "quantitative"},
                            {"field": "Share (%)", "type": "quantitative"},
                        ],
                    },
                },
                use_container_width=True,
            )


def render() -> None:
    init_page()
    init_state()

    st.markdown(
        '<div class="page-main-title">Open LLM Benchmark</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="page-byline">
          <span class="page-byline-by">By</span>
          <span class="page-byline-name">Murat Karakaya Akademi</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="profile-pill-wrap">
          <a class="profile-pill" href="https://github.com/kmkarakaya/openLLMbenchmark" target="_blank" rel="noopener noreferrer">Source Code</a>
          <a class="profile-pill" href="https://www.youtube.com/c/muratkarakayaakademi" target="_blank" rel="noopener noreferrer">YouTube</a>
          <a class="profile-pill" href="https://www.muratkarakaya.net/" target="_blank" rel="noopener noreferrer">Blog</a>
          <a class="profile-pill" href="https://github.com/kmkarakaya" target="_blank" rel="noopener noreferrer">GitHub</a>
          <a class="profile-pill" href="https://www.linkedin.com/in/muratkarakaya/" target="_blank" rel="noopener noreferrer">LinkedIn</a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    runtime_api_key = str(st.session_state.runtime_api_key or "").strip()
    if not api_key and runtime_api_key:
        os.environ["OLLAMA_API_KEY"] = runtime_api_key
        api_key = runtime_api_key

    if not api_key:
        st.warning(
            "To continue, enter `OLLAMA_API_KEY` first. "
            "The key is entered in masked mode and used only in the current session."
        )
        st.info(
            "Create an API key first for direct access to ollama.com API: "
            "https://ollama.com/settings/keys"
        )
        entered_api_key = st.text_input(
            "OLLAMA_API_KEY",
            type="password",
            placeholder="sk-...",
        )
        if st.button("Save API Key and Continue", type="primary"):
            normalized = entered_api_key.strip()
            if not normalized:
                st.error("Please enter a valid API key.")
            else:
                st.session_state.runtime_api_key = normalized
                os.environ["OLLAMA_API_KEY"] = normalized
                st.rerun()
        st.stop()

    with st.sidebar:
        st.subheader("Status:")
        api_ok = bool(os.getenv("OLLAMA_API_KEY", "").strip())
        api_status_text = "Ready" if api_ok else "Missing"
        st.markdown(
            f"🔐 API key status: <strong>{html_escape(api_status_text)}</strong>",
            unsafe_allow_html=True,
        )
        usage_mode_info = st.empty()
        selected_models_info = st.empty()
        total_questions_info = st.empty()
        tested_model_count_info = st.empty()

    try:
        payload = ensure_dataset()
    except (FileNotFoundError, DatasetValidationError) as exc:
        st.error(str(exc))
        return

    questions = payload["questions"]
    st.session_state.system_prompt = payload.get("instruction", DEFAULT_SYSTEM_PROMPT)
    question_by_id = {q["id"]: q for q in questions}

    if not questions:
        st.error("No questions found. Check data/benchmark.json content.")
        return

    if not RESULTS_PATH.exists():
        save_results(RESULTS_PATH, [])
        render_results_markdown(questions=questions, results=[], output_path=RESULTS_MD_PATH)
    results = load_results(RESULTS_PATH)

    with st.sidebar:
        if not st.session_state.model_cache and api_ok:
            try:
                refresh_models()
            except Exception:
                st.session_state.model_cache = []
        active_models, run_eligible = pick_models(st.session_state.model_cache)
        current_mode = sanitize_mode(st.session_state.benchmark_mode)
        mode_label = "Single model" if current_mode == MODE_SINGLE else "Comparison (2 models)"
        selected_models_lines = active_models if active_models else ["-"]
        selected_models_lines_html = "<br>".join(html_escape(model) for model in selected_models_lines)
        tested_model_count = len({r.get("model") for r in results if r.get("model")})
        usage_mode_info.markdown(
            f"🎯 Usage Mode: <strong>{html_escape(mode_label)}</strong>",
            unsafe_allow_html=True,
        )
        selected_models_info.markdown(
            f"🧠 Selected Model(s):<br><strong>{selected_models_lines_html}</strong>",
            unsafe_allow_html=True,
        )
        total_questions_info.markdown(
            f"🧩 Total questions: <strong>{len(questions)}</strong>",
            unsafe_allow_html=True,
        )
        tested_model_count_info.markdown(
            f"📊 Tested model count: <strong>{tested_model_count}</strong>",
            unsafe_allow_html=True,
        )
        if sidebar_collapsible_section(
            "Download Results",
            "sidebar_download_results_open",
            default=False,
        ):
            selected_download_format = st.radio(
                "Download format",
                options=["JSON", "Excel"],
                index=0,
                horizontal=True,
                label_visibility="collapsed",
                key="download_results_format",
            )
            json_bytes = _cached_results_json(results) if results else b""
            excel_bytes: bytes = b""
            excel_download_disabled = not results
            excel_dependency_hint = ""
            if results:
                try:
                    excel_bytes = _cached_results_excel(results)
                except ModuleNotFoundError as exc:
                    if exc.name == "openpyxl":
                        excel_download_disabled = True
                        excel_dependency_hint = (
                            "Excel export disabled because `openpyxl` is not available in the active Python environment."
                        )
                    else:
                        raise
            if selected_download_format == "JSON":
                st.download_button(
                    label="Download JSON",
                    data=json_bytes,
                    file_name="results.json",
                    mime="application/json",
                    use_container_width=False,
                    disabled=not results,
                )
            else:
                st.download_button(
                    label="Download Excel",
                    data=excel_bytes,
                    file_name="results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=False,
                    disabled=excel_download_disabled,
                )
            if excel_dependency_hint:
                st.caption(excel_dependency_hint)
        if sidebar_collapsible_section(
            "Quick User Manual",
            "sidebar_quick_user_manual_open",
            default=False,
        ):
            st.markdown(
                """
1. Set a valid `OLLAMA_API_KEY` to enable model access.
2. Check current run context under `Status` (`Usage Mode`, `Selected Model(s)`, `Total questions`, `Tested model count`).
3. Open `Benchmark Config` and choose `Usage Mode`: `Single model` or `Comparison (2 models)`.
4. Select model(s). In comparison mode, Model 1 and Model 2 must be set and different.
5. Click `Start Response` or `Start Responses` to run benchmark generation.
6. Read outputs in `Plain text` or `Render (MD/HTML)` view.
7. If needed, override automatic scoring with `Successful`, `Failed`, or `Needs Review`.
8. Open `Download Results`, choose `JSON` or `Excel`, and download the selected format.
9. Final outputs are saved to `data/results.json` and `results.md`.
                """
            )
            st.markdown(
                """
**Metrics note**

- Performance Score: higher is better.
- Response Speed Score: higher is better.
- Raw timing values can vary due to Ollama Cloud network/infrastructure conditions, so interpret latency mainly as a relative model-to-model comparison.
                """
            )
    idx = st.session_state.question_index
    idx = max(0, min(idx, len(questions) - 1))
    st.session_state.question_index = idx
    question = questions[idx]
    if st.session_state.last_seen_question_id != question["id"]:
        st.session_state.last_seen_question_id = question["id"]
        st.session_state.pending_autorun = None
        missing_models = []
        if run_eligible:
            missing_models = [
                model for model in active_models if not find_result(results, question["id"], model)
            ]
        if missing_models:
            st.session_state.pending_autorun = {
                "question_id": question["id"],
                "models": missing_models,
            }

    nav_a, nav_b, nav_c = st.columns([1, 2, 1])
    with nav_a:
        if st.button("◀ Previous", use_container_width=True, disabled=idx == 0):
            st.session_state.question_index = max(0, idx - 1)
            st.rerun()
    with nav_b:
        goto = st.number_input(
            "Question #",
            min_value=1,
            max_value=len(questions),
            value=idx + 1,
            step=1,
            label_visibility="collapsed",
        )
        if int(goto) - 1 != idx:
            st.session_state.question_index = int(goto) - 1
            st.rerun()
    with nav_c:
        if st.button("Next ▶", use_container_width=True, disabled=idx >= len(questions) - 1):
            st.session_state.question_index = min(len(questions) - 1, idx + 1)
            st.rerun()

    render_question_meta(question=question, selected_models=active_models)
    st.text_area(
        "Question",
        value=question["prompt"],
        height=220,
        disabled=True,
    )
    st.text_area(
        "Expected answer",
        value=question.get("expected_answer", ""),
        height=100,
        disabled=True,
    )

    runner = get_runner(st.session_state.session_id)
    snapshot = runner.snapshot()

    run_col, stop_col = st.columns(2)
    with run_col:
        start_label = "Start Responses" if st.session_state.benchmark_mode == MODE_PAIR else "Start Response"
        if st.button(
            start_label,
            type="primary",
            use_container_width=True,
            disabled=(not run_eligible) or snapshot["running"],
        ):
            st.session_state.persisted_run_entry_keys = []
            ok = runner.start(
                models=active_models,
                question_id=question["id"],
                prompt=question["prompt"],
                system_prompt=st.session_state.system_prompt,
            )
            if not ok:
                st.warning("A run is already active.")
            st.rerun()
    with stop_col:
        if st.button(
            "Stop",
            use_container_width=True,
            disabled=not snapshot["running"],
        ):
            runner.request_stop()
            st.info("Stop request sent.")
    results = handle_completed_runs(
        snapshot=snapshot,
        results=results,
        questions=questions,
        question_by_id=question_by_id,
    )
    if not run_eligible:
        st.session_state.pending_autorun = None
    pending_autorun = st.session_state.get("pending_autorun")
    if isinstance(pending_autorun, dict):
        pending_qid = str(pending_autorun.get("question_id", ""))
        pending_models = normalize_selected_models(*pending_autorun.get("models", []))
        if pending_qid != question["id"]:
            st.session_state.pending_autorun = None
        else:
            pending_models = [
                model for model in pending_models if not find_result(results, question["id"], model)
            ]
            if not pending_models:
                st.session_state.pending_autorun = None
            elif not snapshot["running"]:
                st.session_state.persisted_run_entry_keys = []
                started = runner.start(
                    models=pending_models,
                    question_id=question["id"],
                    prompt=question["prompt"],
                    system_prompt=st.session_state.system_prompt,
                )
                if started:
                    st.session_state.pending_autorun = None
                    st.rerun()

    panel_title = "Model Comparison Results" if st.session_state.benchmark_mode == MODE_PAIR else "Single Model Result"
    response_view_options = RESPONSE_VIEW_OPTIONS
    if st.session_state.response_view_mode_pref not in response_view_options:
        st.session_state.response_view_mode_pref = response_view_options[0]
    if (
        "response_view_mode_widget" not in st.session_state
        or st.session_state.response_view_mode_widget not in response_view_options
    ):
        st.session_state.response_view_mode_widget = st.session_state.response_view_mode_pref
    header_pad_left, header_col, header_pad_right = st.columns([1, 3, 1])
    with header_col:
        st.markdown(
            f'<h3 style="text-align:center; margin-bottom:0.35rem;">{panel_title}</h3>',
            unsafe_allow_html=True,
        )
        line_pad_left, line_col, line_pad_right = st.columns([1, 3, 1])
        with line_col:
            radio_pad_left, line_radio_col, radio_pad_right = st.columns([1, 2, 1])
            with line_radio_col:
                st.radio(
                    "Response view",
                    options=response_view_options,
                    key="response_view_mode_widget",
                    horizontal=True,
                    label_visibility="collapsed",
                )
    response_view_mode = st.session_state.response_view_mode_widget
    st.session_state.response_view_mode_pref = response_view_mode
    panel_models = active_models or [""]
    response_columns = st.columns(len(panel_models)) if len(panel_models) > 1 else [st.container()]
    for panel_index, model in enumerate(panel_models):
        with response_columns[panel_index]:
            active_entry = find_snapshot_entry(snapshot, question["id"], model) if model else None
            saved = find_result(results, question["id"], model) if model else None
            display_latency_s: float | None = None
            if active_entry:
                display_latency_s = float(active_entry.get("elapsed_ms", 0.0)) / 1000.0
            elif saved:
                display_latency_s = float(saved.get("response_time_ms") or 0.0) / 1000.0

            response_header = f"{model or 'No model selected'} Response"
            if display_latency_s is not None:
                response_header += f" | Response time: {display_latency_s:.2f}s"

            copy_response = ""
            copy_key = f"resp_none_{question['id']}_{panel_index}"
            copy_disabled = True
            if active_entry:
                copy_response = str(active_entry.get("response", ""))
                copy_key = f"live_{question['id']}_{model}"
                copy_disabled = bool(active_entry.get("running"))
            elif saved:
                copy_response = str(saved.get("response", ""))
                copy_key = f"saved_{question['id']}_{model}"
                copy_disabled = False

            header_col, copy_col = st.columns([6, 1])
            with header_col:
                st.subheader(response_header)
            with copy_col:
                render_copy_button(
                    response_text=copy_response,
                    key=copy_key,
                    disabled=copy_disabled,
                )

            if active_entry:
                live_response = str(active_entry.get("response", ""))
                render_response_content(
                    response_text=live_response,
                    view_mode=response_view_mode,
                    key=f"response_live_{question['id']}_{model}",
                )
                if not live_response.strip():
                    if active_entry.get("completed"):
                        st.warning("This run returned an empty response for the model. Try running again.")
                    else:
                        st.warning("Response has not arrived yet or returned empty.")
                if active_entry.get("error"):
                    st.error(str(active_entry["error"]))
                elif active_entry.get("interrupted"):
                    st.warning("Run was stopped by the user.")
                if saved and active_entry.get("completed"):
                    saved_response = str(saved.get("response", ""))
                    if saved_response == live_response:
                        render_result_meta(saved)
                elif saved and active_entry.get("running"):
                    st.caption("Live run in progress. Status chips will refresh when completion is finalized.")
            elif saved:
                saved_response = str(saved.get("response", ""))
                render_response_content(
                    response_text=saved_response,
                    view_mode=response_view_mode,
                    key=f"response_saved_{question['id']}_{model}",
                )
                if not saved_response.strip():
                    st.warning("Model response is empty in this record.")
                render_result_meta(saved)
            else:
                render_response_content(
                    response_text="",
                    view_mode=response_view_mode,
                    key=f"response_empty_{question['id']}_{panel_index}",
                )
                if model:
                    st.info("No record yet for the selected model.")
                else:
                    st.info("Please select at least one model.")

            manual_target = saved
            if active_entry and active_entry.get("completed"):
                manual_target = find_result(results, question["id"], model) if model else manual_target

            st.subheader("Manual Decision")
            c1, c2, c3 = st.columns(3)
            can_override = bool(model and manual_target)
            if c1.button(
                "Successful",
                use_container_width=True,
                disabled=not can_override,
                key=f"manual_success_{question['id']}_{model or panel_index}",
            ):
                updated = dict(manual_target)
                updated["status"] = "success"
                updated["score"] = 1
                updated["auto_scored"] = False
                updated["reason"] = "User approval"
                updated["interrupted"] = False
                updated["timestamp"] = datetime.now(timezone.utc).isoformat()
                results = persist_result_record(results, questions, updated)
                st.rerun()
            if c2.button(
                "Failed",
                use_container_width=True,
                disabled=not can_override,
                key=f"manual_fail_{question['id']}_{model or panel_index}",
            ):
                updated = dict(manual_target)
                updated["status"] = "fail"
                updated["score"] = 0
                updated["auto_scored"] = False
                updated["reason"] = "User approval"
                updated["interrupted"] = False
                updated["timestamp"] = datetime.now(timezone.utc).isoformat()
                results = persist_result_record(results, questions, updated)
                st.rerun()
            if c3.button(
                "Needs Review",
                use_container_width=True,
                disabled=not can_override,
                key=f"manual_review_{question['id']}_{model or panel_index}",
            ):
                updated = dict(manual_target)
                updated["status"] = "manual_review"
                updated["score"] = None
                updated["auto_scored"] = False
                updated["reason"] = "Marked by user for manual review"
                updated["timestamp"] = datetime.now(timezone.utc).isoformat()
                results = persist_result_record(results, questions, updated)
                st.rerun()

    render_metrics_panel(results)
    render_matrix_panel(questions, results)
    render_dataset_metadata_stats_panel(questions)

    if snapshot["running"]:
        time.sleep(0.45)
        st.rerun()


if __name__ == "__main__":
    render()

