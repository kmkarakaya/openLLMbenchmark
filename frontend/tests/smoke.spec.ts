import { expect, test } from "@playwright/test";

const API_HOST_DIRECT = "http://(localhost|127\\.0\\.0\\.1):(8000|18000)";
const API_HOST_PROXY = "http://(localhost|127\\.0\\.0\\.1):3011/api";
const API_HOST = `(?:${API_HOST_DIRECT}|${API_HOST_PROXY})`;

async function mockBaseApi(page: import("@playwright/test").Page) {
  let resultsPayload = {
    dataset_key: "default_tr",
    results: [
      {
        question_id: "q001",
        model: "gemma3:4b",
        status: "success",
        reason: "ok",
        response: "Merhaba"
      }
    ],
    metrics: [
      {
        model: "gemma3:4b",
        accuracy_percent: 100,
        latency_score: 95,
        success_count: 2,
        scored_count: 2,
        median_ms: 1300
      }
    ],
    matrix: [
      {
        question_id: "q001",
        category: "GENEL",
        cells: { "gemma3:4b": "OK 1.30s" }
      }
    ]
  };

  await page.route(new RegExp(`${API_HOST}/health$`), async (route) => {
    await route.fulfill({ json: { status: "ok", version: "v1" } });
  });
  await page.route(new RegExp(`${API_HOST}/ops/slo$`), async (route) => {
    await route.fulfill({
      json: {
        window_minutes: 15,
        sse_disconnect_error_rate: 0.001,
        run_completion_success_rate: 1,
        p95_chunk_gap_ms: 250,
        breached: false,
        evaluated_at: "2026-04-07T10:00:00+00:00"
      }
    });
  });
  await page.route(new RegExp(`${API_HOST}/datasets$`), async (route) => {
    await route.fulfill({
      json: {
        datasets: [
          {
            key: "default_tr",
            label: "Default benchmark set (TR)",
            is_default: true,
            signature: "sig-default",
            question_count: 2
          },
          {
            key: "uploaded_demo",
            label: "Uploaded: demo",
            is_default: false,
            signature: "sig-uploaded",
            question_count: 1
          }
        ]
      }
    });
  });
  await page.route(new RegExp(`${API_HOST}/ollama/auth-status$`), async (route) => {
    await route.fulfill({ json: { server_api_key_configured: true } });
  });
  await page.route(new RegExp(`${API_HOST}/models$`), async (route) => {
    await route.fulfill({ json: { models: ["gemma3:4b", "qwen3:8b"] } });
  });
  await page.route(new RegExp(`${API_HOST}/questions\\?.+`), async (route) => {
    const url = new URL(route.request().url());
    const dataset = url.searchParams.get("dataset_key") ?? "default_tr";
    await route.fulfill({
      json: {
        dataset_key: dataset,
        instruction: "Answer in Turkish.",
        questions: [
          {
            id: "q001",
            prompt: "Merhaba?",
            expected_answer: "Merhaba",
            category: "GENEL",
            hardness_level: "easy",
            why_prepared: "baseline"
          },
          {
            id: "q002",
            prompt: "2+2?",
            expected_answer: "4",
            category: "MATH",
            hardness_level: "easy",
            why_prepared: "sanity"
          }
        ]
      }
    });
  });
  await page.route(new RegExp(`${API_HOST}/results\\?.+`), async (route) => {
    await route.fulfill({ json: resultsPayload });
  });
  await page.route(new RegExp(`${API_HOST}/results/model\\?.+`), async (route) => {
    if (route.request().method() !== "DELETE") {
      await route.fallback();
      return;
    }
    const url = new URL(route.request().url());
    const model = url.searchParams.get("model");
    const datasetKey = url.searchParams.get("dataset_key") ?? "default_tr";
    if (model !== "gemma3:4b") {
      await route.fulfill({ status: 404, json: { detail: "Model results not found for dataset" } });
      return;
    }
    resultsPayload = {
      dataset_key: datasetKey,
      results: [],
      metrics: [],
      matrix: []
    };
    await route.fulfill({
      status: 200,
      json: {
        status: "deleted",
        summary: {
          dataset_key: datasetKey,
          model,
          deleted_count: 1,
          remaining_count: 0
        }
      }
    });
  });
  await page.route(new RegExp(`${API_HOST}/runs$`), async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 201,
      json: { run_id: 123, status: "started", session_id: "ui-test-session" }
    });
  });
  await page.route(new RegExp(`${API_HOST}/runs/123/events\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: ["event: chunk", 'data: {"run_id":123,"model":"gemma3:4b","response":"stream"}', "", "event: run_completed", 'data: {"run_id":123}', ""].join("\n")
    });
  });
  await page.route(new RegExp(`${API_HOST}/runs/123/status\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        run_id: 123,
        session_id: "ui-test-session",
        dataset_key: "default_tr",
        question_id: "q001",
        running: false,
        completed: true,
        interrupted: false,
        error: "",
        entries: [{ model: "gemma3:4b", running: false, completed: true, interrupted: false, error: "", event: "completed", elapsed_ms: 900 }]
      }
    });
  });
  await page.route(new RegExp(`${API_HOST}/runs/123/stop\\?.+`), async (route) => {
    await route.fulfill({ status: 202, json: { status: "stop_requested" } });
  });
  await page.route(new RegExp(`${API_HOST}/results/manual$`), async (route) => {
    await route.fulfill({ status: 200, json: { status: "updated", result: {} } });
  });
  await page.route(new RegExp(`${API_HOST}/datasets/upload$`), async (route) => {
    await route.fulfill({ status: 201, json: { dataset: {} } });
  });
  await page.route(new RegExp(`${API_HOST}/datasets/default_tr$`), async (route) => {
    await route.fulfill({ status: 400, json: { detail: "Default dataset cannot be deleted." } });
  });
  await page.route(new RegExp(`${API_HOST}/datasets/uploaded_demo$`), async (route) => {
    await route.fulfill({ status: 200, json: { status: "deleted", summary: {} } });
  });
}

test("navigation: sidebar/topbar with required pages", async ({ page }) => {
  await mockBaseApi(page);
  await page.goto("/");

  await expect(page.getByText("System Status")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();

  await page.locator("aside").getByRole("link", { name: "Configure", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Configure Benchmark", exact: true })).toBeVisible();

  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();

  await page.locator("aside").getByRole("link", { name: "Results", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Results", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Export JSON/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Export Excel/ })).toBeVisible();

  await page.locator("aside").getByRole("link", { name: "Dataset Management", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dataset Management", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Export JSON/ })).toHaveCount(0);
  await expect(page.getByRole("link", { name: /Export Excel/ })).toHaveCount(0);
});

test("configure page is strict setup-only", async ({ page }) => {
  await mockBaseApi(page);
  await page.goto("/configure");

  await expect(page.getByTestId("configure-dataset")).toBeVisible();
  await expect(page.getByTestId("configure-mode")).toBeVisible();
  await expect(page.getByText("Primary Model", { exact: true })).toBeVisible();
  await expect(page.getByText("Secondary Model", { exact: true })).toBeVisible();
  await expect(page.getByText("Ollama Cloud Access", { exact: true })).toBeVisible();
  await expect(page.getByTestId("configure-system-prompt")).toBeVisible();

  await expect(page.getByText("Question Preview")).toHaveCount(0);
  await expect(page.getByText("Run Simulation")).toHaveCount(0);
  await expect(page.getByText("Review Results Layout")).toHaveCount(0);
  await expect(page.getByText("Run state")).toHaveCount(0);
});

test("configure page lets user enter session Ollama key when server key is missing", async ({ page }) => {
  await mockBaseApi(page);

  await page.route(new RegExp(`${API_HOST}/ollama/auth-status$`), async (route) => {
    await route.fulfill({ json: { server_api_key_configured: false } });
  });
  await page.route(new RegExp(`${API_HOST}/models$`), async (route) => {
    const sessionKey = route.request().headers()["x-ollama-api-key"] ?? "";
    if (!sessionKey) {
      await route.fulfill({ status: 503, json: { detail: "Enter Ollama API Key to be able to use Ollama Cloud models." } });
      return;
    }
    await route.fulfill({ json: { models: ["gemma3:4b:cloud", "llama3.2:local"] } });
  });

  await page.goto("/configure");

  await expect(page.getByText("Enter Ollama API Key to be able to use Ollama Cloud models.")).toBeVisible();
  await page.getByTestId("configure-ollama-api-key-input").fill("session-key");
  await page.getByTestId("configure-ollama-api-key-save").click();

  await expect(page.getByTestId("configure-ollama-session-key")).toHaveValue("******");
  await expect(page.locator("label:has-text('Primary Model') select option[value='gemma3:4b:cloud']")).toHaveCount(1);
});

test("responsive smoke on desktop and mobile", async ({ page }) => {
  await mockBaseApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/run");
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();
  await expect(page.getByTestId("run-question-layout-vertical")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("run-question-layout-horizontal").click();
  await expect(page.getByTestId("run-question-layout-horizontal")).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("run-layout-vertical")).toHaveAttribute("aria-pressed", "true");
  await page.getByTestId("run-layout-horizontal").click();
  await expect(page.getByTestId("run-layout-horizontal")).toHaveAttribute("aria-pressed", "true");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/datasets");
  await expect(page.getByRole("heading", { name: "Dataset Management", exact: true })).toBeVisible();
  await expect(page.getByText("Upload Dataset JSON")).toBeVisible();
});

test("state handling: configure shows fatal error when dataset load fails", async ({ page }) => {
  await mockBaseApi(page);
  await page.route(/(?:http:\/\/(localhost|127\.0\.0\.1):(8000|18000)\/datasets|http:\/\/(localhost|127\.0\.0\.1):3011\/api\/datasets)$/, async (route) => {
    await route.fulfill({ status: 500, json: { detail: "Dataset service unavailable" } });
  });
  await page.goto("/configure");
  await expect(page.getByText("Failed to load configuration data")).toBeVisible();
});

test("state handling: toast + banner shown on run start failure", async ({ page }) => {
  await mockBaseApi(page);
  await page.goto("/configure");
  await expect(page.getByText("Resolved model set")).toBeVisible();

  await page.route(/(?:http:\/\/(localhost|127\.0\.0\.1):(8000|18000)\/runs|http:\/\/(localhost|127\.0\.0\.1):3011\/api\/runs)$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 503, json: { detail: "Runs are temporarily unavailable due to SSE SLO breach." } });
  });
  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("Run unavailable:")).toBeVisible();
  await expect(page.getByText("Runs are temporarily unavailable due to SSE SLO breach.").first()).toBeVisible();
});

test("run page refreshes evaluation badges from persisted results after completion", async ({ page }) => {
  await mockBaseApi(page);

  const API_HOST_DIRECT = "http://(localhost|127\\.0\\.0\\.1):(8000|18000)";
  const API_HOST_PROXY = "http://(localhost|127\\.0\\.0\\.1):3011/api";
  const API_HOST = `(?:${API_HOST_DIRECT}|${API_HOST_PROXY})`;
  let resultsRequestCount = 0;

  await page.route(new RegExp(`${API_HOST}/models$`), async (route) => {
    await route.fulfill({ json: { models: ["nemotron-3-super:cloud"] } });
  });

  await page.route(new RegExp(`${API_HOST}/results\\?.+`), async (route) => {
    resultsRequestCount += 1;
    const url = new URL(route.request().url());
    const datasetKey = url.searchParams.get("dataset_key") ?? "default_tr";
    const completedResults = resultsRequestCount >= 2;
    await route.fulfill({
      json: {
        dataset_key: datasetKey,
        results: completedResults
          ? [
              {
                question_id: "q001",
                model: "nemotron-3-super:cloud",
                status: "success",
                response: "nemotron completed response",
                response_time_ms: 14875.58,
                generated_tokens: 1042,
                generated_tokens_estimated: false,
                evaluation: "Successful",
                evaluation_method: "Automatic",
                timestamp: "2026-04-09T16:31:57Z",
                auto_scored: true
              }
            ]
          : [],
        metrics: [],
        matrix: []
      }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs$`), async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 201,
      json: { run_id: 400, status: "started", session_id: "ui-test-session" }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/400/events\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: [
        "event: chunk",
        'data: {"run_id":400,"model":"nemotron-3-super:cloud","response":"nemotron completed response"}',
        "",
        "event: entry_completed",
        'data: {"run_id":400,"model":"nemotron-3-super:cloud","elapsed_ms":14875.58}',
        "",
        "event: run_completed",
        'data: {"run_id":400}',
        ""
      ].join("\n")
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/400/status\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        run_id: 400,
        session_id: "ui-test-session",
        dataset_key: "default_tr",
        question_id: "q001",
        running: false,
        completed: true,
        interrupted: false,
        error: "",
        entries: [
          {
            model: "nemotron-3-super:cloud",
            running: false,
            completed: true,
            interrupted: false,
            error: "",
            event: "completed",
            elapsed_ms: 14875.58,
            generated_tokens: 1042,
            prompt_tokens: 181
          }
        ]
      }
    });
  });

  await page.goto("/configure");
  await page.getByTestId("configure-mode").selectOption("single");
  await page.locator("label:has-text('Primary Model') select").selectOption("nemotron-3-super:cloud");

  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Send", exact: true }).click();

  await expect(page.locator("[data-testid='run-responses-layout'] textarea").first()).toHaveValue("nemotron completed response");
  await expect.poll(() => resultsRequestCount).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("Evaluation: Successful", { exact: true })).toBeVisible();
  await expect(page.getByText("Evaluation Method: Automatic", { exact: true })).toBeVisible();
});

test("run page comparison mode updates completed model evaluation before peer run finishes", async ({ page }) => {
  await mockBaseApi(page);

  const API_HOST_DIRECT = "http://(localhost|127\\.0\\.0\\.1):(8000|18000)";
  const API_HOST_PROXY = "http://(localhost|127\\.0\\.0\\.1):3011/api";
  const API_HOST = `(?:${API_HOST_DIRECT}|${API_HOST_PROXY})`;
  let resultsRequestCount = 0;

  await page.route(new RegExp(`${API_HOST}/results\\?.+`), async (route) => {
    resultsRequestCount += 1;
    const url = new URL(route.request().url());
    const datasetKey = url.searchParams.get("dataset_key") ?? "default_tr";
    const includeCompletedEntry = resultsRequestCount >= 2;
    await route.fulfill({
      json: {
        dataset_key: datasetKey,
        results: includeCompletedEntry
          ? [
              {
                question_id: "q001",
                model: "gemma3:4b",
                status: "success",
                response: "gemma completed response",
                response_time_ms: 910,
                generated_tokens: 111,
                generated_tokens_estimated: false,
                evaluation: "Successful",
                evaluation_method: "Automatic",
                timestamp: "2026-04-09T16:50:00Z",
                auto_scored: true
              }
            ]
          : [],
        metrics: [],
        matrix: []
      }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs$`), async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }

    await route.fulfill({
      status: 201,
      json: { run_id: 450, status: "started", session_id: "ui-test-session" }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/450/events\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: [
        "event: chunk",
        'data: {"run_id":450,"model":"gemma3:4b","response":"gemma completed response"}',
        "",
        "event: entry_completed",
        'data: {"run_id":450,"model":"gemma3:4b","elapsed_ms":910}',
        "",
        "event: chunk",
        'data: {"run_id":450,"model":"qwen3:8b","response":"qwen still running"}',
        ""
      ].join("\n")
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/450/status\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      json: {
        run_id: 450,
        session_id: "ui-test-session",
        dataset_key: "default_tr",
        question_id: "q001",
        running: true,
        completed: false,
        interrupted: false,
        error: "",
        entries: [
          {
            model: "gemma3:4b",
            running: false,
            completed: true,
            interrupted: false,
            error: "",
            event: "completed",
            elapsed_ms: 910,
            generated_tokens: 111,
            prompt_tokens: 37
          },
          {
            model: "qwen3:8b",
            running: true,
            completed: false,
            interrupted: false,
            error: "",
            event: "chunk",
            elapsed_ms: 2400
          }
        ]
      }
    });
  });

  await page.goto("/configure");
  await page.getByTestId("configure-mode").selectOption("pair");
  await page.locator("label:has-text('Primary Model') select").selectOption("gemma3:4b");
  await page.locator("label:has-text('Secondary Model') select").selectOption("qwen3:8b");

  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Send", exact: true }).click();

  const responseCards = page.locator("[data-testid='run-responses-layout'] article");
  const gemmaCard = responseCards.filter({ hasText: "gemma3:4b" }).first();
  const qwenCard = responseCards.filter({ hasText: "qwen3:8b" }).first();

  await expect.poll(() => resultsRequestCount).toBeGreaterThanOrEqual(2);
  await expect(page.getByText("Response being generated", { exact: true })).toBeVisible();
  await expect(gemmaCard.getByText("Evaluation: Successful", { exact: true })).toBeVisible();
  await expect(gemmaCard.getByText("Evaluation Method: Automatic", { exact: true })).toBeVisible();
  await expect(gemmaCard.getByText("Tokens: 111", { exact: false })).toBeVisible();
  await expect(qwenCard.getByText("generating", { exact: false })).toBeVisible();
});

test("run page only auto-sends after navigator move", async ({ page }) => {
  await mockBaseApi(page);

  const API_HOST_DIRECT = "http://(localhost|127\\.0\\.0\\.1):(8000|18000)";
  const API_HOST_PROXY = "http://(localhost|127\\.0\\.0\\.1):3011/api";
  const API_HOST = `(?:${API_HOST_DIRECT}|${API_HOST_PROXY})`;
  const runBodies: Array<{ question_id: string; models: string[] }> = [];
  const runPayloadById = new Map<number, { question_id: string; models: string[] }>();
  const emptyResultsPayload = {
    dataset_key: "default_tr",
    results: [],
    metrics: [],
    matrix: []
  };
  let nextRunId = 200;

  await page.route(new RegExp(`${API_HOST}/runs$`), async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }

    const body = route.request().postDataJSON() as { question_id: string; models: string[] };
    await new Promise((resolve) => setTimeout(resolve, 200));
    const runId = nextRunId;
    nextRunId += 1;
    runBodies.push(body);
    runPayloadById.set(runId, body);
    await route.fulfill({
      status: 201,
      json: { run_id: runId, status: "started", session_id: "ui-test-session" }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/\\d+/events\\?.+`), async (route) => {
    const match = route.request().url().match(/\/runs\/(\d+)\/events/);
    const runId = match ? Number(match[1]) : 0;
    const body = runPayloadById.get(runId);
    const model = body?.models[0] ?? "gemma3:4b";
    const questionId = body?.question_id ?? "q001";
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: [
        "event: chunk",
        `data: {"run_id":${runId},"model":"${model}","response":"${questionId}-auto-response"}`,
        "",
        "event: entry_completed",
        `data: {"run_id":${runId},"model":"${model}","elapsed_ms":850}`,
        "",
        "event: run_completed",
        `data: {"run_id":${runId}}`,
        ""
      ].join("\n")
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/\\d+/status\\?.+`), async (route) => {
    const match = route.request().url().match(/\/runs\/(\d+)\/status/);
    const runId = match ? Number(match[1]) : 0;
    const body = runPayloadById.get(runId);
    const model = body?.models[0] ?? "gemma3:4b";
    const questionId = body?.question_id ?? "q001";
    await route.fulfill({
      status: 200,
      json: {
        run_id: runId,
        session_id: "ui-test-session",
        dataset_key: "default_tr",
        question_id: questionId,
        running: false,
        completed: true,
        interrupted: false,
        error: "",
        entries: [
          {
            model,
            running: false,
            completed: true,
            interrupted: false,
            error: "",
            event: "completed",
            elapsed_ms: 850
          }
        ]
      }
    });
  });

  await page.route(new RegExp(`${API_HOST}/results\\?.+`), async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 200));
    await route.fulfill({
      json: emptyResultsPayload
    });
  });

  await page.goto("/configure");
  await page.getByTestId("configure-mode").selectOption("single");
  await page.locator("label:has-text('Primary Model') select").selectOption("gemma3:4b");

  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();
  await expect(page.locator("[data-testid='run-responses-layout'] textarea").first()).toHaveValue("");
  await page.waitForTimeout(700);
  expect(runBodies.length).toBe(0);

  const previousButton = page.getByRole("button", { name: "Previous", exact: true });
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(previousButton).toBeDisabled();

  await expect.poll(() => runBodies.length).toBe(1);
  expect(runBodies[0]?.question_id).toBe("q002");
  expect(runBodies[0]?.models).toEqual(["gemma3:4b"]);
  await expect(page.locator("[data-testid='run-responses-layout'] textarea").first()).toHaveValue("q002-auto-response");
  await expect(previousButton).toBeEnabled();
});

test("run page comparison mode auto-sends only the missing model after next", async ({ page }) => {
  await mockBaseApi(page);

  const API_HOST_DIRECT = "http://(localhost|127\\.0\\.0\\.1):(8000|18000)";
  const API_HOST_PROXY = "http://(localhost|127\\.0\\.0\\.1):3011/api";
  const API_HOST = `(?:${API_HOST_DIRECT}|${API_HOST_PROXY})`;
  const runBodies: Array<{ question_id: string; models: string[] }> = [];
  const runPayloadById = new Map<number, { question_id: string; models: string[] }>();
  let nextRunId = 300;

  await page.route(new RegExp(`${API_HOST}/results\\?.+`), async (route) => {
    const url = new URL(route.request().url());
    const datasetKey = url.searchParams.get("dataset_key") ?? "default_tr";
    await route.fulfill({
      json: {
        dataset_key: datasetKey,
        results: [
          {
            question_id: "q001",
            model: "gemma3:4b",
            status: "success",
            response: "q001-model1",
            timestamp: "2026-04-09T10:00:00Z"
          },
          {
            question_id: "q001",
            model: "qwen3:8b",
            status: "success",
            response: "q001-model2",
            timestamp: "2026-04-09T10:00:01Z"
          },
          {
            question_id: "q002",
            model: "gemma3:4b",
            status: "success",
            response: "q002-model1-existing",
            timestamp: "2026-04-09T10:00:02Z"
          }
        ],
        metrics: [],
        matrix: []
      }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs$`), async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }

    const body = route.request().postDataJSON() as { question_id: string; models: string[] };
    const runId = nextRunId;
    nextRunId += 1;
    runBodies.push(body);
    runPayloadById.set(runId, body);
    await route.fulfill({
      status: 201,
      json: { run_id: runId, status: "started", session_id: "ui-test-session" }
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/\\d+/events\\?.+`), async (route) => {
    const match = route.request().url().match(/\/runs\/(\d+)\/events/);
    const runId = match ? Number(match[1]) : 0;
    const body = runPayloadById.get(runId);
    const model = body?.models[0] ?? "qwen3:8b";
    const questionId = body?.question_id ?? "q002";
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: [
        "event: chunk",
        `data: {"run_id":${runId},"model":"${model}","response":"${questionId}-${model}-generated"}`,
        "",
        "event: entry_completed",
        `data: {"run_id":${runId},"model":"${model}","elapsed_ms":920}`,
        "",
        "event: run_completed",
        `data: {"run_id":${runId}}`,
        ""
      ].join("\n")
    });
  });

  await page.route(new RegExp(`${API_HOST}/runs/\\d+/status\\?.+`), async (route) => {
    const match = route.request().url().match(/\/runs\/(\d+)\/status/);
    const runId = match ? Number(match[1]) : 0;
    const body = runPayloadById.get(runId);
    const model = body?.models[0] ?? "qwen3:8b";
    const questionId = body?.question_id ?? "q002";
    await route.fulfill({
      status: 200,
      json: {
        run_id: runId,
        session_id: "ui-test-session",
        dataset_key: "default_tr",
        question_id: questionId,
        running: false,
        completed: true,
        interrupted: false,
        error: "",
        entries: [
          {
            model,
            running: false,
            completed: true,
            interrupted: false,
            error: "",
            event: "completed",
            elapsed_ms: 920
          }
        ]
      }
    });
  });

  await page.goto("/configure");
  await page.getByTestId("configure-mode").selectOption("pair");
  await page.locator("label:has-text('Primary Model') select").selectOption("gemma3:4b");
  await page.locator("label:has-text('Secondary Model') select").selectOption("qwen3:8b");

  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();

  const responseBoxes = page.locator("[data-testid='run-responses-layout'] textarea");
  await expect(responseBoxes.nth(0)).toHaveValue("q001-model1");
  await expect(responseBoxes.nth(1)).toHaveValue("q001-model2");

  await page.getByRole("button", { name: "Next", exact: true }).click();

  await expect.poll(() => runBodies.length).toBe(1);
  expect(runBodies[0]?.question_id).toBe("q002");
  expect(runBodies[0]?.models).toEqual(["qwen3:8b"]);
  await expect(responseBoxes.nth(0)).toHaveValue("q002-model1-existing");
  await expect(responseBoxes.nth(1)).toHaveValue("q002-qwen3:8b-generated");
});

test("results page allows model history deletion and refreshes data", async ({ page }) => {
  await mockBaseApi(page);
  page.on("dialog", async (dialog) => {
    await dialog.accept();
  });

  await page.goto("/results");
  await expect(page.getByTestId("results-delete-model-select")).toBeVisible();
  await expect(page.getByTestId("results-delete-model-button")).toBeEnabled();

  await page.getByTestId("results-delete-model-button").click();

  await expect(page.getByText("Deleted 1 records for gemma3:4b.")).toBeVisible();
  await expect(page.getByText("No detailed responses available yet.")).toBeVisible();
  await expect(page.getByTestId("results-delete-model-button")).toBeDisabled();
});

test("results page orders response-level rows by question id", async ({ page }) => {
  await mockBaseApi(page);

  await page.route(/(?:http:\/\/(localhost|127\.0\.0\.1):(8000|18000)\/results\?.+|http:\/\/(localhost|127\.0\.0\.1):3011\/api\/results\?.+)$/, async (route) => {
    await route.fulfill({
      json: {
        dataset_key: "default_tr",
        results: [
          {
            question_id: "q010",
            model: "gemma3:4b",
            status: "success",
            response: "response q010",
            timestamp: "2026-04-09T10:00:02Z"
          },
          {
            question_id: "q002",
            model: "gemma3:4b",
            status: "success",
            response: "response q002",
            timestamp: "2026-04-09T10:00:03Z"
          },
          {
            question_id: "q001",
            model: "gemma3:4b",
            status: "success",
            response: "response q001",
            timestamp: "2026-04-09T10:00:04Z"
          }
        ],
        metrics: [],
        matrix: []
      }
    });
  });

  await page.goto("/results");

  const responseLevelCard = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Response-Level Model Performance", exact: true })
  });
  const questionCells = responseLevelCard.locator("tbody tr td:first-child");

  await expect(questionCells).toHaveText(["q001", "q002", "q010"]);
});

test("results page supports sorting requested leaderboard tables by clicked column", async ({ page }) => {
  await mockBaseApi(page);

  await page.route(/(?:http:\/\/(localhost|127\.0\.0\.1):(8000|18000)\/questions\?.+|http:\/\/(localhost|127\.0\.0\.1):3011\/api\/questions\?.+)$/, async (route) => {
    const url = new URL(route.request().url());
    const dataset = url.searchParams.get("dataset_key") ?? "default_tr";
    await route.fulfill({
      json: {
        dataset_key: dataset,
        instruction: "Answer in Turkish.",
        questions: [
          { id: "q001", prompt: "Q1", expected_answer: "A1", category: "CAT-A", hardness_level: "easy" },
          { id: "q002", prompt: "Q2", expected_answer: "A2", category: "CAT-A", hardness_level: "hard" },
          { id: "q003", prompt: "Q3", expected_answer: "A3", category: "CAT-B", hardness_level: "easy" },
          { id: "q004", prompt: "Q4", expected_answer: "A4", category: "CAT-B", hardness_level: "hard" }
        ]
      }
    });
  });

  await page.route(/(?:http:\/\/(localhost|127\.0\.0\.1):(8000|18000)\/results\?.+|http:\/\/(localhost|127\.0\.0\.1):3011\/api\/results\?.+)$/, async (route) => {
    await route.fulfill({
      json: {
        dataset_key: "default_tr",
        results: [
          { question_id: "q001", model: "model-low", status: "success", response: "r1" },
          { question_id: "q002", model: "model-low", status: "fail", response: "r2" },
          { question_id: "q003", model: "model-low", status: "fail", response: "r3" },
          { question_id: "q004", model: "model-low", status: "fail", response: "r4" },
          { question_id: "q001", model: "model-mid", status: "success", response: "r5" },
          { question_id: "q002", model: "model-mid", status: "success", response: "r6" },
          { question_id: "q003", model: "model-mid", status: "fail", response: "r7" },
          { question_id: "q004", model: "model-mid", status: "fail", response: "r8" },
          { question_id: "q001", model: "model-high", status: "success", response: "r9" },
          { question_id: "q002", model: "model-high", status: "fail", response: "r10" },
          { question_id: "q003", model: "model-high", status: "success", response: "r11" },
          { question_id: "q004", model: "model-high", status: "success", response: "r12" }
        ],
        metrics: [
          {
            model: "model-mid",
            accuracy_percent: 50,
            latency_score: 70,
            success_count: 2,
            scored_count: 4,
            median_ms: 1800,
            avg_generated_tokens: 210
          },
          {
            model: "model-low",
            accuracy_percent: 25,
            latency_score: 40,
            success_count: 1,
            scored_count: 4,
            median_ms: 2400,
            avg_generated_tokens: 180
          },
          {
            model: "model-high",
            accuracy_percent: 75,
            latency_score: 90,
            success_count: 3,
            scored_count: 4,
            median_ms: 900,
            avg_generated_tokens: 260
          }
        ],
        matrix: []
      }
    });
  });

  await page.goto("/results");

  const leaderboardCard = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Model Leader Board", exact: true })
  });
  await leaderboardCard.getByRole("button", { name: "Sort by Accuracy %" }).click();
  await expect(leaderboardCard.locator("tbody tr td:first-child").first()).toHaveText("model-high");

  const categoryCard = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Category-Level Model Performance", exact: true })
  });
  await categoryCard.getByRole("button", { name: "Sort by CAT-A (2)" }).click();
  await expect(categoryCard.locator("tbody tr td:first-child").first()).toHaveText("model-mid");

  const hardnessCard = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Hardness-Level Model Performance", exact: true })
  });
  await hardnessCard.getByRole("button", { name: "Sort by easy (2)" }).click();
  await expect(hardnessCard.locator("tbody tr td:first-child").first()).toHaveText("model-high");
});
