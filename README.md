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

## Environment Variables

- `OLLAMA_API_KEY` (required)
- `OLLAMA_HOST` (optional, default: `https://ollama.com`)

If `OLLAMA_API_KEY` is missing at startup, the app asks for it via masked input in the UI.

## Runtime Outputs

- `data/results.json`: canonical run results
- `results.md`: auto-generated comparison report (scores + latency + question matrix)

## Current UI Behavior

- Sidebar groups: `Status`, `Benchmark Config`, `Download Results`, `Quick User Manual`.
- `Status` shows dynamic run context: API key status, usage mode, selected model(s), total questions, tested model count.
- Usage modes: `Single model` and `Comparison (2 models)`.
- `Benchmark Config` contains both usage mode and model selection controls.
- Response view modes: `Plain text` and `Render (MD/HTML)`.
- In comparison mode, both models must be set and different.
- Model 2 value is preserved when switching modes.
- `Download Results` lets you choose format (`JSON` / `Excel`) and download the selected format.
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
