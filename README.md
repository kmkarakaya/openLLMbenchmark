---
title: openLLMbenchmark
emoji: 🤖
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Open LLM Benchmark (Web App)

A Streamlit web app to benchmark open LLMs on Ollama Cloud using any question/answer dataset.

The repository includes a Turkish sample dataset by default, but the app is language-agnostic and domain-agnostic.
You can replace the dataset to benchmark other languages or other skills (for example coding, finance, reasoning, legal, healthcare, etc.).

## Live App

https://openllmbenchmark.streamlit.app/

## Source Code

https://github.com/kmkarakaya/openLLMbenchmark

## Social Links

- YouTube: https://www.youtube.com/c/muratkarakayaakademi
- Blog: https://www.muratkarakaya.net/
- GitHub: https://github.com/kmkarakaya
- LinkedIn: https://www.linkedin.com/in/muratkarakaya/

## What This App Does

- Runs benchmarks for one model or two models side by side.
- Streams responses in real time.
- Applies automatic scoring against `expected_answer`.
- Allows manual override (`Successful`, `Failed`, `Needs Review`).
- Tracks response-time metrics (median, mean, P95) and a normalized speed score.
- Saves all benchmark outputs to JSON and a markdown report.

## Supported Benchmark Scenarios

You can use this app for any Q/A benchmark dataset, for example:

- Turkish language ability
- English language ability
- Coding/problem-solving
- Financial literacy
- Domain-specific knowledge checks

## Dataset Model

Source-of-truth dataset:

- `data/benchmark.json`

Required fields per question:

- `id` (immutable, format `qNNN`, for example `q001`)
- `question`
- `expected_answer`

Optional metadata fields:

- `topic`
- `hardness_level`
- `why_prepared`

Example record:

```json
{
  "id": "q001",
  "question": "Sort these words alphabetically: ...",
  "expected_answer": "...",
  "topic": "language",
  "hardness_level": "easy",
  "why_prepared": "tests lexical ordering"
}
```

## Important Defaults

- The bundled dataset is Turkish and intended as a sample baseline.
- The default system prompt is language-agnostic and asks the model to answer in the same language as the question.
- If you replace `data/benchmark.json`, the app benchmarks your new dataset without code changes.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## API + Frontend MVP (Local/Internal)

Backend API:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Frontend UI:

```bash
cd frontend
npm install
set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Open `http://localhost:3000`.

## Local Automation Helper (Windows)

Use `devops_helper.bat` from the repo root:

```bat
.\devops_helper.bat github "your commit message"
.\devops_helper.bat hf
.\devops_helper.bat all "your commit message"
```

- `github`: stages all changes, commits, pushes to `origin/current-branch`
- `hf`: creates a clean temp snapshot and deploys to Hugging Face Space
- `all`: runs `github` then `hf`

## Deploy on Hugging Face Spaces (Docker)

This repository is ready to run as a Docker Space with the included `Dockerfile`.

1. Create a new Space on Hugging Face and select `Docker` as SDK.
2. Push this repository to that Space.
3. In Space `Settings -> Variables and secrets`, add:
- `OLLAMA_API_KEY` (required)
- `OLLAMA_HOST` (optional, default: `https://ollama.com`)
4. Trigger a rebuild (or push a new commit). The app will start on port `7860` automatically.

Notes:
- The container runs `streamlit run app.py --server.address=0.0.0.0 --server.port=7860`.
- If `OLLAMA_API_KEY` is not configured as a Space secret, the app asks it in the UI at runtime.

## Environment Variables

- `OLLAMA_API_KEY` (required)
- `OLLAMA_HOST` (optional, default: `https://ollama.com`)
- `API_BASE_URL` (for upcoming v1 API/Next.js integration)
- `FEATURE_API_READS` (default: `true`)
- `FEATURE_API_RUNS` (default: `false`)
- `FEATURE_API_WRITES` (default: `false`)
- `FEATURE_NEW_UI` (default: `false`)
- `NEXT_PUBLIC_API_BASE_URL` (frontend runtime API base URL, default `http://localhost:8000`)

If `OLLAMA_API_KEY` is missing at startup, the app asks for it via masked input in the UI.

## Internal Ops Endpoint

- `GET /ops/slo` returns rolling-window SSE SLO metrics and breach state.
- This endpoint is local/internal only.

## Version 2 Baseline Fixtures

- Baseline snapshots are stored in `data/baselines/results.json` and `data/baselines/results.md`.
- In baseline markdown, `_Güncellendi:` timestamp is normalized to `<normalized>` so fixture comparisons remain deterministic.

## Runtime Outputs

- Default dataset outputs:
- `data/results.json`: canonical run results
- `results.md`: auto-generated comparison report (scores + latency + question matrix)
- Uploaded dataset outputs:
- `data/results_by_dataset/<dataset_key>.json`: dataset-specific run results
- `data/results_by_dataset/<dataset_key>.md`: dataset-specific markdown report
- Uploaded dataset files:
- `data/uploaded_datasets/*.json`: validated user-uploaded datasets

## Current UI Behavior

- Sidebar groups: `Status`, `Dataset Config`, `Benchmark Config`, `Download Results`, `Quick User Manual`.
- `Status` shows dynamic run context: API key status, usage mode, selected model(s), selected dataset, total questions, tested model count.
- `Dataset Config` lets users download an empty template, upload JSON datasets, select active dataset, and delete uploaded datasets with a two-step confirmation (`Delete Uploaded Dataset` -> `Delete Permanently`).
- Default dataset cannot be deleted.
- Deleting an uploaded dataset removes only dataset-specific artifacts (`data/uploaded_datasets/<file>.json` and matching `data/results_by_dataset/<dataset_key>.json|.md` + sidecars).
- Usage modes: `Single model` and `Comparison (2 models)`.
- `Benchmark Config` contains both usage mode and model selection controls.
- Question metadata pills include: dataset, selected model(s), question id, category, difficulty.
- Response view modes: `Plain text` and `Render (MD/HTML)`.
- In comparison mode, both models must be set and different.
- Model 2 value is preserved when switching modes.
- `Download Results` lets you choose format (`JSON` / `Excel`) and download the selected format (`results.json` for default dataset, `results_<dataset_key>.*` for uploaded datasets).
- Scoring `reason` values in exported results are standardized in English (for example: `Numeric comparison applied.`, `Text similarity: ...`).
- `Copy` is disabled while generation is active or when response text is empty.
- `Stop` marks interrupted runs as `manual_review`.

## Metrics Notes

- `Performance Score` is based on successful answers over scored answers.
- `Response Speed Score` is normalized from median response time.
- Ollama Cloud network/infrastructure conditions can affect timing values.
- Treat latency values mainly as relative model-to-model comparisons.

## Example Snapshot (From Current Bundled Dataset)

The following values are only a snapshot from the current repository dataset and are not product limits:

| Model        | Accuracy % | Success/Scored | Median (s) | Mean (s) | P95 (s) | Latency Score |
| ------------ | ---------: | -------------: | ---------: | -------: | ------: | ------------: |
| qwen3.5:397b |      100.0 |          23/23 |      13.18 |    15.01 |   37.47 |          24.1 |
| gemma3:27b   |       82.6 |          19/23 |       6.02 |     6.50 |   10.77 |          52.8 |
| gemma3:12b   |       69.6 |          16/23 |       3.18 |     4.46 |    6.60 |         100.0 |
| gemma3:4b    |       34.8 |           8/23 |       3.43 |     4.14 |    9.38 |          92.8 |

## Contributing

To update or add benchmark questions, edit `data/benchmark.json` and open a pull request.

Rules:

- Keep JSON structure valid.
- Keep existing IDs unchanged.
- Add new IDs in `qNNN` format.
- Fill required fields for each question.
