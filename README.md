---
title: openLLMbenchmark
emoji: 📊
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
# openLLMbenchmark

API-first benchmark platform for open LLM evaluation using FastAPI + Next.js.

This repository is for teams, researchers, and builders who want to benchmark open models with a practical web UI, reproducible result artifacts, and an API that is easy to extend.

## Why Use This Repo

- Compare open LLMs with a question-by-question benchmark workflow.
- Run single-model or side-by-side model evaluations.
- Review leaderboard, category, hardness, question-level, and response-level results in the UI.
- Export results as JSON, Markdown, and table-friendly formats.
- Extend the benchmark by adding new questions, datasets, or product features.

## Two Ways To Use It

### 1. Use The Hosted App

You can try the deployed app here:

- https://huggingface.co/spaces/kmkarakaya/openLLMbenchmark

Use the hosted UI if you want to explore the benchmark without running the stack yourself.

Get a free Ollama Cloud key here:

- https://ollama.com/settings/keys

Public Space usage:

- The hosted app does not rely on a shared built-in Ollama Cloud key for all users.
- Each user should bring their own Ollama Cloud key.
- Open the Configure page and paste your key into the Ollama Cloud Access section for the current browser session.

For your own Hugging Face Space deployment, configure the Ollama Cloud key as a Space secret:

- `OLLAMA_API_KEY`

### 2. Run It Locally

Run locally if you want to:

- test your own changes,
- use local development workflows,
- modify datasets or benchmark logic,
- contribute features back to the repository.

## Runtime Architecture

- Backend: FastAPI (`api.py`)
- Frontend: Next.js (`frontend/`)
- Reverse proxy: Nginx (HF Spaces single-URL deployment)
- Streaming: SSE (`/runs/{run_id}/events`)
- Persistence: JSON/Markdown artifacts with file locking and atomic writes

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm
- Git

## Local Setup

Before starting the app locally, set your Ollama Cloud API key in your system environment:

Get a free Ollama Cloud key here:

- https://ollama.com/settings/keys
- `OLLAMA_API_KEY` is required for cloud-backed model requests.
- Store it as a system or user environment variable before launching the backend.
- `OLLAMA_HOST` is optional if you need a custom cloud endpoint.
- `OLLAMA_LOCAL_HOST` is optional if you also use a local Ollama instance.

You can also paste a key into the Configure page for the current browser session, but setting `OLLAMA_API_KEY` in your environment is still the recommended local-development path.

PowerShell example for the current session:

```powershell
$env:OLLAMA_API_KEY="your-api-key"
```

Persistent Windows example:

```powershell
setx OLLAMA_API_KEY "your-api-key"
```

If you plan to use cloud models, start a new terminal after `setx` so the updated environment variable is available.

## Local Run (Recommended)

Start backend + frontend from repo root:

```bat
.\run_local_stack.bat
```

Defaults:

- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Frontend UI: `http://localhost:3001`

Custom ports:

```bat
.\run_local_stack.bat 8001 3002
```

One-side launch modes:

```bat
.\run_local_stack.bat backend 8000
.\run_local_stack.bat frontend 8000 3001
```

## Local Run (Manual)

```bash
# 1) Backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000

# 2) Frontend (new terminal)
cd frontend
npm install
set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev -- -p 3001
```

Recommended local flow:

1. Set `OLLAMA_API_KEY` in your environment.
2. Start the app with `./run_local_stack.bat`.
3. Open the UI, go to Configure, choose dataset, mode, and models.
4. Run the benchmark and inspect the Results page.

## Validate Before Deploy

From repo root:

```bash
pytest -q
cd frontend
npm run typecheck
npm run build
npm run test:e2e
cd ..
docker build -t openllmbenchmark:local .
```

## Hugging Face Spaces Deployment (Single URL)

This repository is configured for HF Spaces Docker runtime:

- Public UI: `/`
- API: `/api/*` (Nginx strips `/api` and forwards to FastAPI root routes)

Container internals:

- FastAPI on `127.0.0.1:8000`
- Next.js on `127.0.0.1:3001`
- Nginx on `7860`

Smoke checks after deploy:

- `GET /api/health`
- `GET /api/docs`
- UI load at `/`

HF Space secrets to set:

- `OLLAMA_API_KEY` (required for cloud models)
- `OLLAMA_HOST` (optional)
- `OLLAMA_LOCAL_HOST` (optional)

Public hosted Space:

- https://huggingface.co/spaces/kmkarakaya/openLLMbenchmark

If you want your own deployment, fork the repo and deploy it to your own HF Space with the same secret names.

## Deployment Helper Script

Use:

```bat
.\devops_helper.bat check
.\devops_helper.bat github "your commit message"
.\devops_helper.bat hf
.\devops_helper.bat all "your commit message"
```

Actions:

- `check`: run local preflight checks (backend tests + frontend typecheck/build + Docker build smoke if Docker exists)
- `github`: stage/commit/push to `origin/<current-branch>`
- `hf`: deploy current clean HEAD snapshot to HF Space
- `all`: run `github` then `hf`

## Environment Variables

Active contract:

- `OLLAMA_API_KEY` (required for cloud models)
- `OLLAMA_HOST` (optional)
- `OLLAMA_LOCAL_HOST` (optional)
- `NEXT_PUBLIC_API_BASE_URL` (optional; defaults to `/api` in frontend)

## How To Contribute

Pull requests are welcome.

Good contribution paths include:

- adding new benchmark questions,
- adding new benchmark datasets,
- improving scoring or reporting,
- improving the FastAPI or Next.js code,
- fixing bugs,
- adding new product features.

If you want to contribute benchmark content:

- add or update benchmark questions in the repository datasets,
- include clear categories and hardness labels when relevant,
- keep the JSON structure consistent with the existing dataset format,
- open a PR explaining what was added and why it improves benchmark coverage.

If you want to contribute code:

1. Fork the repository.
2. Create a feature branch.
3. Run the local checks.
4. Open a PR with a focused description and screenshots for UI changes when helpful.

## Who This Repo Is For

- Developers evaluating open LLMs with a lightweight web UI.
- Researchers building reusable benchmark datasets.
- Teams comparing local and cloud-backed Ollama model runs.
- Contributors who want to extend the benchmark with questions, datasets, or features.

## API Surface (Current)

- `GET /health`
- `GET /models`
- `GET /datasets`
- `GET /datasets/template`
- `POST /datasets/upload`
- `DELETE /datasets/{dataset_key}`
- `GET /questions`
- `GET /results`
- `GET /results/export`
- `GET /results/table_export`
- `DELETE /results/model`
- `PATCH /results/manual`
- `POST /runs`
- `GET /runs/{run_id}/events`
- `GET /runs/{run_id}/status`
- `POST /runs/{run_id}/stop`
- `GET /ops/slo` (local/internal)

## Output Artifacts

- Default dataset:
  - `data/results.json`
  - `results.md`
- Uploaded datasets:
  - `data/results_by_dataset/<dataset_key>.json`
  - `data/results_by_dataset/<dataset_key>.md`
- Uploaded source files:
  - `data/uploaded_datasets/*.json`

## Notes

- Streamlit runtime is removed from active product path.
- Rollback strategy is git revert/redeploy.
