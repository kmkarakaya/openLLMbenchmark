from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from data.benchmark import (
    DEFAULT_SYSTEM_PROMPT,
    DatasetValidationError,
    load_benchmark_payload,
    save_expected_answer,
)
from engine import get_client, list_models
from runner import get_runner
from scoring import evaluate_response
from storage import (
    compute_model_metrics,
    format_cell,
    load_results,
    render_results_markdown,
    save_results,
    upsert_result,
)


ROOT = Path(__file__).resolve().parent
BENCHMARK_PATH = ROOT / "benchmark.json"
DATA_DIR = ROOT / "data"
RESULTS_PATH = DATA_DIR / "results.json"
RESULTS_MD_PATH = ROOT / "results.md"


def init_page() -> None:
    st.set_page_config(
        page_title="Türkçe LLM Karşılaştırma",
        page_icon="📊",
        layout="wide",
    )
    st.markdown(
        """
        <style>
          :root {
            --bg-top: #fff8ef;
            --bg-bottom: #eef7ff;
            --card: #ffffff;
            --ink: #1f2430;
            --muted: #5d6470;
            --accent: #0e7490;
            --accent-2: #ef7f1a;
            --ok: #137a43;
            --fail: #b42318;
          }
          .stApp {
            background: radial-gradient(1400px 600px at -10% -20%, #ffe7ca 0%, transparent 60%),
                        radial-gradient(1000px 500px at 120% 120%, #d8f2ff 0%, transparent 60%),
                        linear-gradient(180deg, var(--bg-top), var(--bg-bottom));
          }
          .block-container {
            padding-top: 1.5rem;
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
          [data-testid="stSidebar"] .stButton > button {
            background: var(--accent) !important;
            color: #ffffff !important;
            border: 1px solid #0b5f75 !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button {
            background: #0e7490 !important;
            color: #ffffff !important;
            border: 1px solid #0b5f75 !important;
            font-weight: 600 !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button:hover {
            background: #0b5f75 !important;
            color: #ffffff !important;
            border-color: #0a5266 !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button:disabled,
          [data-testid="stSidebar"] .stButton > button:disabled {
            background: #94a3b8 !important;
            color: #ffffff !important;
            border-color: #8391a6 !important;
            opacity: 1 !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button[kind="primary"] {
            background: #ef4444 !important;
            border-color: #dc2626 !important;
            color: #ffffff !important;
          }
          [data-testid="stAppViewContainer"] .stButton > button[kind="primary"]:hover {
            background: #dc2626 !important;
            border-color: #b91c1c !important;
          }
          [data-testid="stSidebar"] .stTextInput input,
          [data-testid="stSidebar"] .stNumberInput input,
          [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: #ffffff !important;
            color: var(--ink) !important;
            border-color: #c8d5e3 !important;
          }
          [data-testid="stAppViewContainer"] h1,
          [data-testid="stAppViewContainer"] h2,
          [data-testid="stAppViewContainer"] h3,
          [data-testid="stAppViewContainer"] label,
          [data-testid="stAppViewContainer"] p,
          [data-testid="stAppViewContainer"] span {
            color: var(--ink) !important;
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
    if "last_persisted_run_id" not in st.session_state:
        st.session_state.last_persisted_run_id = 0
    if "model_cache" not in st.session_state:
        st.session_state.model_cache = []
    if "system_prompt" not in st.session_state:
        st.session_state.system_prompt = DEFAULT_SYSTEM_PROMPT


def ensure_dataset() -> dict[str, Any]:
    return load_benchmark_payload(BENCHMARK_PATH)


def refresh_models() -> list[str]:
    client = get_client()
    models = list_models(client)
    st.session_state.model_cache = models
    return models


def pick_model(models: list[str]) -> str:
    options = [""] + models
    if st.session_state.selected_model and st.session_state.selected_model not in options:
        options.append(st.session_state.selected_model)

    selected = st.selectbox(
        "Ollama Cloud LLM seç",
        options=options,
        index=options.index(st.session_state.selected_model)
        if st.session_state.selected_model in options
        else 0,
        help="Model listesinden seçebilir veya alttan model adını manuel girebilirsiniz.",
    )

    manual = st.text_input("Model adı (manuel)", value=selected or st.session_state.selected_model)
    model = manual.strip() or selected.strip()
    st.session_state.selected_model = model
    return model


def find_result(
    results: list[dict[str, Any]],
    question_id: str,
    model: str,
) -> dict[str, Any] | None:
    for item in results:
        if item.get("question_id") == question_id and item.get("model") == model:
            return item
    return None


def find_latest_question_result(
    results: list[dict[str, Any]],
    question_id: str,
) -> dict[str, Any] | None:
    candidates = [item for item in results if item.get("question_id") == question_id]
    if not candidates:
        return None
    return max(candidates, key=lambda item: str(item.get("timestamp", "")))


def status_to_turkish(status: str) -> str:
    mapping = {
        "success": "Başarılı",
        "fail": "Başarısız",
        "manual_review": "İnceleme",
    }
    return mapping.get(status, status)


def persist_result_record(
    results: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    updated = upsert_result(results, record)
    save_results(RESULTS_PATH, updated)
    render_results_markdown(questions=questions, results=updated, output_path=RESULTS_MD_PATH)
    return updated


def handle_completed_run(
    snapshot: dict[str, Any],
    results: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    question_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    run_id = snapshot["run_id"]
    if run_id == 0:
        return results
    if st.session_state.last_persisted_run_id == run_id:
        return results
    if not snapshot["completed"]:
        return results

    question = question_by_id.get(snapshot["question_id"])
    expected_answer = (question or {}).get("expected_answer", "")
    response = snapshot.get("response", "")

    if snapshot.get("interrupted"):
        verdict = {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": "Kullanıcı tarafından durduruldu.",
        }
    elif snapshot.get("error"):
        verdict = {
            "status": "manual_review",
            "score": None,
            "auto_scored": False,
            "reason": f"Hata: {snapshot['error']}",
        }
    else:
        verdict = evaluate_response(expected_answer=expected_answer, response=response)

    record = {
        "question_id": snapshot["question_id"],
        "model": snapshot["model"],
        "response": response,
        "status": verdict["status"],
        "score": verdict["score"],
        "response_time_ms": round(snapshot["elapsed_ms"], 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "interrupted": bool(snapshot.get("interrupted")),
        "auto_scored": bool(verdict.get("auto_scored")),
        "reason": verdict.get("reason", ""),
    }
    st.session_state.last_persisted_run_id = run_id
    return persist_result_record(results, questions, record)


def render_metrics_panel(results: list[dict[str, Any]]) -> None:
    metrics = compute_model_metrics(results)
    st.subheader("Model Karşılaştırma")
    if not metrics:
        st.caption("Henüz sonuç yok.")
        return

    frame = pd.DataFrame(
        {
            "Model Adı": [row["model"] for row in metrics],
            "Doğruluk (%)": [round(row["accuracy_percent"], 1) for row in metrics],
            "Başarılı/Puanlanan": [f"{row['success_count']}/{row['scored_count']}" for row in metrics],
            "Medyan (sn)": [
                round((row["median_ms"] or 0.0) / 1000.0, 2) if row["median_ms"] else None
                for row in metrics
            ],
            "Ortalama (sn)": [
                round((row["mean_ms"] or 0.0) / 1000.0, 2) if row["mean_ms"] else None
                for row in metrics
            ],
            "P95 (sn)": [
                round((row["p95_ms"] or 0.0) / 1000.0, 2) if row["p95_ms"] else None
                for row in metrics
            ],
            "Gecikme Puanı": [round(row["latency_score"], 1) for row in metrics],
        }
    )
    st.dataframe(
        frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Model Adı": st.column_config.TextColumn(
                "Model Adı",
                help="Değerlendirilen Ollama model adı.",
            ),
            "Doğruluk (%)": st.column_config.NumberColumn(
                "Doğruluk (%)",
                help="(Başarılı cevap sayısı / puanlanan soru sayısı) x 100.",
                format="%.1f",
            ),
            "Başarılı/Puanlanan": st.column_config.TextColumn(
                "Başarılı/Puanlanan",
                help="Başarılı cevap sayısı / puanlanan toplam soru sayısı.",
            ),
            "Medyan (sn)": st.column_config.NumberColumn(
                "Medyan (sn)",
                help="Yanıt sürelerinin medyanı (saniye). Düşük olması daha iyidir.",
                format="%.2f",
            ),
            "Ortalama (sn)": st.column_config.NumberColumn(
                "Ortalama (sn)",
                help="Yanıt sürelerinin ortalaması (saniye).",
                format="%.2f",
            ),
            "P95 (sn)": st.column_config.NumberColumn(
                "P95 (sn)",
                help="%95 persentil yanıt süresi (saniye). Kuyruk gecikmeyi gösterir.",
                format="%.2f",
            ),
            "Gecikme Puanı": st.column_config.NumberColumn(
                "Gecikme Puanı",
                help="En hızlı modelin medyanına göre normalize edilmiş hız puanı (0-100). Büyük değer daha iyidir.",
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
            "Soru ID": q["id"],
            "Kategori": q.get("category", "GENEL"),
        }
        for model in models:
            row[model] = format_cell(mapping.get((q["id"], model)))
        matrix_rows.append(row)

    st.subheader("Soru Bazlı Sonuç Matrisi")
    st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)
    st.caption(f"Otomatik rapor: `{RESULTS_MD_PATH}`")


def render() -> None:
    init_page()
    init_state()

    st.title("Türkçe LLM Karşılaştırma")
    st.caption("Gerçek zamanlı soru-cevap, otomatik skor ve model karşılaştırma")

    with st.sidebar:
        st.header("Ayarlar")
        api_ok = bool(os.getenv("OLLAMA_API_KEY", "").strip())
        st.write(f"API anahtarı durumu: {'✅ Hazır' if api_ok else '❌ Eksik'}")
        if st.button("Soru setini yenile (benchmark.json)", use_container_width=True):
            st.rerun()

        if st.button("Model listesini yenile", use_container_width=True):
            try:
                refresh_models()
                st.success("Model listesi güncellendi.")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    try:
        payload = ensure_dataset()
    except (FileNotFoundError, DatasetValidationError) as exc:
        st.error(str(exc))
        return

    questions = payload["questions"]
    st.session_state.system_prompt = payload.get("instruction", DEFAULT_SYSTEM_PROMPT)
    question_by_id = {q["id"]: q for q in questions}

    if not questions:
        st.error("Hiç soru bulunamadı. benchmark.json içeriğini kontrol edin.")
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
        selected_model = pick_model(st.session_state.model_cache)
        st.caption(f"Toplam soru: {len(questions)}")
        st.caption(f"Test edilen model sayısı: {len({r.get('model') for r in results if r.get('model')})}")

    idx = st.session_state.question_index
    idx = max(0, min(idx, len(questions) - 1))
    st.session_state.question_index = idx
    question = questions[idx]

    nav_a, nav_b, nav_c = st.columns([1, 2, 1])
    with nav_a:
        if st.button("◀ Önceki", use_container_width=True, disabled=idx == 0):
            st.session_state.question_index = max(0, idx - 1)
            st.rerun()
    with nav_b:
        goto = st.number_input(
            "Soru no",
            min_value=1,
            max_value=len(questions),
            value=idx + 1,
            step=1,
        )
        if int(goto) - 1 != idx:
            st.session_state.question_index = int(goto) - 1
            st.rerun()
    with nav_c:
        if st.button("Sonraki ▶", use_container_width=True, disabled=idx >= len(questions) - 1):
            st.session_state.question_index = min(len(questions) - 1, idx + 1)
            st.rerun()

    st.markdown(
        f"**{question['id']}**  |  **Kategori:** {question.get('category', 'GENEL')}  "
        f"|  **Seçili model:** `{selected_model or '-'}`"
    )
    hardness = question.get("hardness_level", "").strip()
    if hardness:
        st.caption(f"Zorluk: {hardness}")
    why_prepared = question.get("why_prepared", "").strip()
    if why_prepared:
        st.caption(f"Neden hazırlandı: {why_prepared}")
    st.text_area(
        "Soru metni",
        value=question["prompt"],
        height=220,
        disabled=True,
    )
    expected_key = f"expected_{question['id']}"
    if expected_key not in st.session_state:
        st.session_state[expected_key] = question.get("expected_answer", "")
    expected_value = st.text_area(
        "Beklenen cevap (düzenlenebilir)",
        value=st.session_state[expected_key],
        height=100,
        key=f"editor_{question['id']}",
    )
    st.session_state[expected_key] = expected_value
    if st.button("Beklenen cevabı kaydet", type="secondary"):
        try:
            save_expected_answer(BENCHMARK_PATH, question["id"], expected_value.strip())
        except Exception as exc:  # noqa: BLE001
            st.error(f"Kaydedilemedi: {exc}")
        else:
            question["expected_answer"] = expected_value.strip()
            question["expected_source"] = "benchmark_json"
            question["confidence"] = 1.0 if expected_value.strip() else 0.3
            payload["questions"][idx] = question
            st.success("Beklenen cevap benchmark.json içinde güncellendi.")

    runner = get_runner(st.session_state.session_id)
    snapshot = runner.snapshot()

    run_col, stop_col, timer_col = st.columns([1, 1, 2])
    with run_col:
        if st.button(
            "Yanıtı Başlat",
            type="primary",
            use_container_width=True,
            disabled=not selected_model or snapshot["running"],
        ):
            ok = runner.start(
                model=selected_model,
                question_id=question["id"],
                prompt=question["prompt"],
                system_prompt=st.session_state.system_prompt,
            )
            if not ok:
                st.warning("Aktif bir çalışma zaten var.")
            st.rerun()
    with stop_col:
        if st.button(
            "Durdur",
            use_container_width=True,
            disabled=not snapshot["running"],
        ):
            runner.request_stop()
            st.info("Durdurma isteği gönderildi.")
    with timer_col:
        elapsed_s = snapshot["elapsed_ms"] / 1000.0
        status_label = "Çalışıyor" if snapshot["running"] else "Hazır"
        st.markdown(
            f'<div class="bench-card"><span class="kpi">{status_label}</span> '
            f'<span class="muted">| Son süre: {elapsed_s:.2f}s</span></div>',
            unsafe_allow_html=True,
        )

    results = handle_completed_run(
        snapshot=snapshot,
        results=results,
        questions=questions,
        question_by_id=question_by_id,
    )

    st.subheader("Gerçek Zamanlı Yanıt")
    active_for_current = (
        snapshot["question_id"] == question["id"]
        and snapshot["model"] == selected_model
        and (snapshot["running"] or snapshot["completed"])
    )
    saved = find_result(results, question["id"], selected_model) if selected_model else None
    latest_any_model = find_latest_question_result(results, question["id"])

    if active_for_current:
        st.caption(f"Seçili model: `{selected_model}`")
        live_response = snapshot.get("response", "")
        st.text_area(
            "Model cevabı",
            value=live_response,
            height=240,
            disabled=True,
        )
        if not str(live_response).strip():
            st.warning("Yanıt henüz gelmedi veya boş döndü.")
        st.caption(f"Yanıt süresi: {snapshot['elapsed_ms']/1000:.2f}s")
        if snapshot.get("error"):
            st.error(snapshot["error"])
        elif snapshot.get("interrupted"):
            st.warning("Çalışma kullanıcı tarafından durduruldu.")
    elif saved:
        st.caption(f"Seçili model: `{selected_model}`")
        saved_response = saved.get("response", "")
        st.text_area("Model cevabı", value=saved_response, height=240, disabled=True)
        if not str(saved_response).strip():
            st.warning("Bu kayıtta model yanıtı boş.")
        latency = (saved.get("response_time_ms") or 0.0) / 1000.0
        st.caption(
            f"Durum: {status_to_turkish(str(saved.get('status', '')))} | Yanıt süresi: {latency:.2f}s | "
            f"Otomatik skor: {'Evet' if saved.get('auto_scored') else 'Hayır'}"
        )
        if saved.get("reason"):
            st.caption(f"Açıklama: {saved['reason']}")
    elif latest_any_model:
        model_name = latest_any_model.get("model", "-")
        st.warning(
            "Seçili model için kayıt bulunamadı. Bu soru için en son kayıtlı yanıt gösteriliyor."
        )
        st.caption(f"Seçili model: `{model_name}`")
        latest_response = latest_any_model.get("response", "")
        st.text_area(
            "Model cevabı",
            value=latest_response,
            height=240,
            disabled=True,
        )
        if not str(latest_response).strip():
            st.warning("En son kayıtlı yanıt boş.")
        latency = (latest_any_model.get("response_time_ms") or 0.0) / 1000.0
        st.caption(
            f"Durum: {status_to_turkish(str(latest_any_model.get('status', '')))} | Yanıt süresi: {latency:.2f}s | "
            f"Otomatik skor: {'Evet' if latest_any_model.get('auto_scored') else 'Hayır'}"
        )
    else:
        st.info("Bu soru/model için henüz yanıt yok.")

    manual_target = saved
    if active_for_current and snapshot["completed"] and not snapshot["running"]:
        manual_target = find_result(results, question["id"], selected_model) if selected_model else manual_target

    st.subheader("Manuel Karar")
    c1, c2, c3 = st.columns(3)
    can_override = bool(selected_model and manual_target)
    if c1.button("Başarılı", use_container_width=True, disabled=not can_override):
        updated = dict(manual_target)
        updated["status"] = "success"
        updated["score"] = 1
        updated["auto_scored"] = False
        updated["reason"] = "Kullanıcı onayı"
        updated["interrupted"] = False
        updated["timestamp"] = datetime.now(timezone.utc).isoformat()
        results = persist_result_record(results, questions, updated)
        st.success("Manuel durum: Başarılı")
    if c2.button("Başarısız", use_container_width=True, disabled=not can_override):
        updated = dict(manual_target)
        updated["status"] = "fail"
        updated["score"] = 0
        updated["auto_scored"] = False
        updated["reason"] = "Kullanıcı onayı"
        updated["interrupted"] = False
        updated["timestamp"] = datetime.now(timezone.utc).isoformat()
        results = persist_result_record(results, questions, updated)
        st.warning("Manuel durum: Başarısız")
    if c3.button("İnceleme", use_container_width=True, disabled=not can_override):
        updated = dict(manual_target)
        updated["status"] = "manual_review"
        updated["score"] = None
        updated["auto_scored"] = False
        updated["reason"] = "Kullanıcı manuel inceleme işaretledi"
        updated["timestamp"] = datetime.now(timezone.utc).isoformat()
        results = persist_result_record(results, questions, updated)
        st.info("Manuel durum: İnceleme")

    render_metrics_panel(results)
    render_matrix_panel(questions, results)

    if snapshot["running"]:
        time.sleep(0.45)
        st.rerun()


if __name__ == "__main__":
    render()
