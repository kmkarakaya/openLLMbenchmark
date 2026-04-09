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

API-first benchmark platform for open LLM evaluation using **FastAPI + Next.js**.

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
