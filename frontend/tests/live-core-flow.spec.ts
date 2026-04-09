import path from "node:path";

import { expect, test } from "@playwright/test";

async function selectFirstModel(page: import("@playwright/test").Page) {
  const primaryModelSelect = page.locator("label:has-text('Primary Model') select");
  await expect(primaryModelSelect).toBeVisible();

  const optionCount = await primaryModelSelect.locator("option").count();
  for (let index = 0; index < optionCount; index += 1) {
    const option = primaryModelSelect.locator("option").nth(index);
    const value = (await option.getAttribute("value"))?.trim() ?? "";
    if (value) {
      await primaryModelSelect.selectOption(value);
      return value;
    }
  }

  throw new Error("No selectable models were returned by /models.");
}

test("live core flow uses real backend API", async ({ page }) => {
  const uploadFilePath = path.join(__dirname, "fixtures", "playwright_upload_dataset.json");

  await page.goto("/datasets");
  await expect(page.getByRole("heading", { name: "Dataset Management", exact: true })).toBeVisible();

  const uploadInput = page.getByTestId("datasets-upload-input");
  await uploadInput.setInputFiles(uploadFilePath);

  const activeDatasetSelect = page.getByTestId("datasets-active-select");
  const uploadedOptions = activeDatasetSelect.locator("option", { hasText: "Uploaded:" });
  await expect(uploadedOptions).not.toHaveCount(0, { timeout: 10_000 });
  const uploadedOption = uploadedOptions.first();

  const uploadedDatasetKey = (await uploadedOption.getAttribute("value")) ?? "";
  expect(uploadedDatasetKey).not.toBe("");

  await activeDatasetSelect.selectOption(uploadedDatasetKey);

  await page.locator("aside").getByRole("link", { name: "Configure", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Configure Benchmark", exact: true })).toBeVisible();

  const configureDatasetSelect = page.getByTestId("configure-dataset");
  await configureDatasetSelect.selectOption(uploadedDatasetKey);
  await page.getByTestId("configure-mode").selectOption("single");
  await selectFirstModel(page);
  await expect(page.getByText("Resolved model set")).toBeVisible();

  await page.locator("aside").getByRole("link", { name: "Benchmark Run", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Benchmark Run", exact: true })).toBeVisible();

  const startButton = page.getByRole("button", { name: "Send", exact: true });
  await expect(startButton).toBeEnabled();
  await startButton.click();

  const stopButton = page.getByRole("button", { name: "Stop", exact: true });
  await page.waitForTimeout(300);
  if (await stopButton.isEnabled()) {
    await stopButton.click();
    await expect(page.getByText(/Stop requested:|Run interrupted:|Run completed:/)).toBeVisible({ timeout: 20_000 });
  } else {
    await expect(page.getByText(/Run completed:|Run interrupted:|Run error:/)).toBeVisible({ timeout: 20_000 });
  }

  const firstResponseBox = page.locator("[data-testid='run-responses-layout'] textarea").first();
  await expect(firstResponseBox).not.toHaveValue("", { timeout: 20_000 });

  await page.getByRole("button", { name: "Mark Successful" }).first().click();
  await expect(page.getByText(/Manual decision saved:/)).toBeVisible({ timeout: 10_000 });

  await page.locator("aside").getByRole("link", { name: "Results", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Results", exact: true })).toBeVisible();
  await page.getByTestId("results-dataset-select").selectOption(uploadedDatasetKey);
  await expect(page.getByText("Model Leader Board")).toBeVisible();

  const rawJsonDownloadPromise = page.waitForEvent("download");
  await page.getByTestId("results-export-raw-json").click();
  const rawJsonDownload = await rawJsonDownloadPromise;
  expect(rawJsonDownload.suggestedFilename()).toContain(".json");

  await page.getByTestId("results-export-open-model_leader_board").click();
  const tableJsonDownloadPromise = page.waitForEvent("download");
  await page.getByTestId("results-export-json-model_leader_board").click();
  const tableJsonDownload = await tableJsonDownloadPromise;
  expect(tableJsonDownload.suggestedFilename()).toContain("model_leader_board");

  await page.locator("aside").getByRole("link", { name: "Dataset Management", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Dataset Management", exact: true })).toBeVisible();
  await page.getByTestId("datasets-active-select").selectOption(uploadedDatasetKey);

  await page.getByRole("button", { name: "Delete Uploaded Dataset", exact: true }).click();
  await page.getByRole("button", { name: "Delete Permanently", exact: true }).click();

  await expect(page.getByText(/Dataset deleted:/)).toBeVisible({ timeout: 10_000 });
});
