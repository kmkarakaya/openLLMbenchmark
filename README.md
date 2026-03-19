# Turkish LLM Benchmark (MVP)

Real-time Streamlit app for quickly evaluating open-source LLMs on Ollama Cloud with a simple Turkish Q/A benchmark.

## Live App

You can access the online running version here:

https://openllmbenchmark.streamlit.app/

## Source Code

GitHub repository:

https://github.com/kmkarakaya/openLLMbenchmark

## Social Links

- YouTube: https://www.youtube.com/c/muratkarakayaakademi
- Blog: https://www.muratkarakaya.net/
- GitHub: https://github.com/kmkarakaya
- LinkedIn: https://www.linkedin.com/in/muratkarakaya/

## Overview

- This app uses a simple Turkish question-answer set to provide a fast baseline evaluation for Ollama Cloud models.
- The questions were prepared by Murat Karakaya for instructional purposes.
- The app provides a lightweight UI and backend to run evaluations, compare models, and record results automatically.

## Contributing Questions

To update existing questions or add new ones, open a Pull Request on GitHub by editing `data/benchmark.json`.
If preferred, users can also add their own questions directly to [benchmark.json](data/benchmark.json) by following the example format.

Rules:

- Follow the existing JSON structure.
- Fill in all fields correctly.
- Assign a new unique `id` in `qNNN` format.
- Use the next available number.
- Do not renumber existing IDs.

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Environment Variables

- `OLLAMA_API_KEY` (required)
- `OLLAMA_HOST` (optional, default: `https://ollama.com`)

If `OLLAMA_API_KEY` is missing at startup, the app asks for it in the UI using a masked input.

## Dataset

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

Dataset loading, validation, and writes are handled by:

- `data/benchmark.py`

## Runtime Outputs

- `data/results.json`: canonical run results
- `results.md`: auto-generated comparison report (accuracy + latency + matrix)

## Current Results (Snapshot)

Latest full report is in `results.md`. Current model comparison snapshot:

| Model        | Accuracy % | Success/Scored | Median (s) | Mean (s) | P95 (s) | Latency Score |
| ------------ | ---------: | -------------: | ---------: | -------: | ------: | ------------: |
| qwen3.5:397b |      100.0 |          23/23 |      13.18 |    15.01 |   37.47 |          24.1 |
| gemma3:27b   |       82.6 |          19/23 |       6.02 |     6.50 |   10.77 |          52.8 |
| gemma3:12b   |       69.6 |          16/23 |       3.18 |     4.46 |    6.60 |         100.0 |
| gemma3:4b    |       34.8 |           8/23 |       3.43 |     4.14 |    9.38 |          92.8 |

## Question Distribution by Topic

| Topic             | Question Count |          Share |
| ----------------- | -------------: | -------------: |
| Turkish           |              6 |          26.1% |
| Memory            |              4 |          17.4% |
| General Knowledge |              4 |          17.4% |
| Logic             |              4 |          17.4% |
| Finance           |              2 |           8.7% |
| Geography         |              1 |           4.3% |
| Coding            |              1 |           4.3% |
| History           |              1 |           4.3% |
| **Total**   |   **23** | **100%** |

## Current Behavior

- Questions are loaded only from `data/benchmark.json`.
- If `OLLAMA_API_KEY` is missing at startup, the app shows a masked input and blocks execution until a key is provided.
- Sidebar flow is grouped as `Data & System`, `Usage Mode`, and `Model Selection`.
- `Usage Mode` has two explicit options: `Single model` and `Comparison (2 models)`.
- In `Single model`, only Model 1 is used; in `Comparison`, Model 1 and Model 2 must both be set and different before run can start.
- If you switch from comparison to single mode, Model 2 is kept as a hidden backup and restored when you switch back.
- The main title area includes quick profile links (`YouTube`, `Blog`, `GitHub`, `LinkedIn`) as pill buttons.
- Selected active models and the current question are processed together with live streaming output per model.
- If you move to a question that has no saved record for the active model list, the app auto-starts those missing runs.
- The expected answer is displayed as read-only.
- The response area supports two modes: `Plain text` and `Render (MD/HTML)`, and the selected mode is preserved across reruns.
- When two models are selected, their responses and manual evaluation controls are shown side by side.
- If a selected model has no saved record for the current question, that response box is shown empty.
- `Copy` is available next to the response header and is disabled while generation is running or when there is no text to copy.
- `Stop` sends a stop request; interrupted runs are saved as `manual_review`.
- Automatic scoring is applied on completed runs, and manual override buttons (`Successful`, `Failed`, `Review`) can update the saved result.
- Status chips show `Status` and scoring type (`Auto-scored` or `Manually scored`); chip state is refreshed immediately after manual override.
- The in-app `Model Comparison` table uses `Performance Score` and `Response Speed Score` as score columns.
- A note under `Model Comparison` warns that Ollama Cloud network/infrastructure can affect timing metrics; latency values should be interpreted relatively.
- Every run/decision is saved to `data/results.json` and `results.md` is regenerated automatically.
- The default system prompt enforces Turkish-only answers.
