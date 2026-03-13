# Turkish LLM Benchmark (MVP)

Real-time Streamlit app for benchmarking Ollama Cloud models on Turkish Q/A.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Environment Variables

- `OLLAMA_API_KEY` (required)
- `OLLAMA_HOST` (optional, default: `https://ollama.com`)

## Dataset

Source-of-truth dataset is:
- `benchmark.json`

Each record must include:
- `id` (immutable, format `qNNN`, e.g. `q001`)
- `question`
- `expected_answer`

Optional fields used in UI:
- `topic`
- `hardness_level`
- `why_prepared`

Dataset loading, validation, and writes are handled by:
- `data/benchmark.py`

## Runtime Outputs

- `data/results.json`: canonical run results
- `results.md`: auto-generated comparison report (accuracy + latency + matrix)

## Current Behavior

- App reads questions only from `benchmark.json` (no PDF/DOCX extraction path).
- Expected answer edits in UI are written back to `benchmark.json` by question `id`.
- Model responses stream in real time in the UI.
- Results are auto-saved after each run/decision.
- Default system prompt enforces Turkish answers.
