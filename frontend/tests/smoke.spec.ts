import { expect, test } from "@playwright/test";

async function mockBaseApi(page: import("@playwright/test").Page) {
  const API_HOST = /http:\/\/(localhost|127\.0\.0\.1):8000/;
  await page.route(new RegExp(`${API_HOST.source}/health$`), async (route) => {
    await route.fulfill({ json: { status: "ok", version: "v1" } });
  });
  await page.route(new RegExp(`${API_HOST.source}/ops/slo$`), async (route) => {
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
  await page.route(new RegExp(`${API_HOST.source}/datasets$`), async (route) => {
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
  await page.route(new RegExp(`${API_HOST.source}/models$`), async (route) => {
    await route.fulfill({ json: { models: ["gemma3:4b", "qwen3:8b"] } });
  });
  await page.route(new RegExp(`${API_HOST.source}/questions\\?.+`), async (route) => {
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
  await page.route(new RegExp(`${API_HOST.source}/results\\?.+`), async (route) => {
    await route.fulfill({
      json: {
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
            cells: { "gemma3:4b": "✅" }
          }
        ]
      }
    });
  });
  await page.route(new RegExp(`${API_HOST.source}/runs$`), async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 201,
      json: { run_id: 123, status: "started", session_id: "ui-test-session" }
    });
  });
  await page.route(new RegExp(`${API_HOST.source}/runs/123/events\\?.+`), async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream" },
      body: ["event: chunk", 'data: {"run_id":123,"model":"gemma3:4b","response":"stream"}', "", "event: run_completed", 'data: {"run_id":123}', ""].join("\n")
    });
  });
  await page.route(new RegExp(`${API_HOST.source}/runs/123/status\\?.+`), async (route) => {
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
  await page.route(new RegExp(`${API_HOST.source}/runs/123/stop\\?.+`), async (route) => {
    await route.fulfill({ status: 202, json: { status: "stop_requested" } });
  });
  await page.route(new RegExp(`${API_HOST.source}/results/manual$`), async (route) => {
    await route.fulfill({ status: 200, json: { status: "updated", result: {} } });
  });
  await page.route(new RegExp(`${API_HOST.source}/datasets/upload$`), async (route) => {
    await route.fulfill({ status: 201, json: { dataset: {} } });
  });
  await page.route(new RegExp(`${API_HOST.source}/datasets/default_tr$`), async (route) => {
    await route.fulfill({ status: 400, json: { detail: "Default dataset cannot be deleted." } });
  });
  await page.route(new RegExp(`${API_HOST.source}/datasets/uploaded_demo$`), async (route) => {
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
  await expect(page.getByTestId("configure-system-prompt")).toBeVisible();

  await expect(page.getByText("Question Preview")).toHaveCount(0);
  await expect(page.getByText("Run Simulation")).toHaveCount(0);
  await expect(page.getByText("Review Results Layout")).toHaveCount(0);
  await expect(page.getByText("Run state")).toHaveCount(0);
});

test("responsive smoke on desktop and mobile", async ({ page }) => {
  await mockBaseApi(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/run");
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/datasets");
  await expect(page.getByRole("heading", { name: "Dataset Management", exact: true })).toBeVisible();
  await expect(page.getByText("Upload Dataset JSON")).toBeVisible();
});

test("state handling: reads-disabled banner appears on configure", async ({ page }) => {
  await mockBaseApi(page);
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):8000\/models$/, async (route) => {
    await route.fulfill({ status: 404, json: { detail: "API reads are disabled" } });
  });
  await page.goto("/configure");
  await expect(page.getByText("Reads disabled:")).toBeVisible();
});

test("state handling: toast + banner shown on run start failure", async ({ page }) => {
  await mockBaseApi(page);
  await page.goto("/configure");
  await expect(page.getByText("Resolved model set")).toBeVisible();

  await page.route(/http:\/\/(localhost|127\.0\.0\.1):8000\/runs$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.fallback();
      return;
    }
    await route.fulfill({ status: 503, json: { detail: "Runs are temporarily disabled due to SSE SLO breach." } });
  });
  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await page.getByRole("button", { name: "Start Run" }).click();
  await expect(page.getByText("Run unavailable:")).toBeVisible();
  await expect(page.getByText("Runs are temporarily disabled due to SSE SLO breach.").first()).toBeVisible();
});
