import type {
  BenchmarkQuestion,
  DeleteModelResultsResponse,
  DatasetOption,
  DatasetTemplateRow,
  OllamaAuthStatus,
  ResultsTableKey,
  ResultsResponse,
  RunStartResponse,
  RunStatusResponse,
  SloStatus
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api";
const OLLAMA_API_KEY_HEADER = "X-Ollama-API-Key";

export class ApiError extends Error {
  status: number;
  payload: Record<string, unknown>;

  constructor(status: number, message: string, payload: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function parseResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    let payload: Record<string, unknown> = {};
    try {
      payload = (await res.json()) as Record<string, unknown>;
      const rawDetail = payload.detail;
      if (typeof rawDetail === "string" && rawDetail.trim()) {
        detail = rawDetail;
      }
    } catch {
      // keep default detail
    }
    throw new ApiError(res.status, detail, payload);
  }
  return (await res.json()) as T;
}

export function apiBaseUrl(): string {
  return API_BASE_URL;
}

export function runEventsUrl(runId: number, sessionId: string): string {
  return `${API_BASE_URL}/runs/${runId}/events?session_id=${encodeURIComponent(sessionId)}`;
}

export function datasetTemplateUrl(): string {
  return `${API_BASE_URL}/datasets/template`;
}

function buildHeaders(contentType?: string, ollamaApiKey?: string): HeadersInit {
  const headers: Record<string, string> = {};
  if (contentType) {
    headers["Content-Type"] = contentType;
  }
  if (typeof ollamaApiKey === "string" && ollamaApiKey.trim()) {
    headers[OLLAMA_API_KEY_HEADER] = ollamaApiKey.trim();
  }
  return headers;
}

export async function getHealth(): Promise<{ status: string; version: string }> {
  return parseResponse(await fetch(`${API_BASE_URL}/health`, { cache: "no-store" }));
}

export async function getOllamaAuthStatus(): Promise<OllamaAuthStatus> {
  return parseResponse(await fetch(`${API_BASE_URL}/ollama/auth-status`, { cache: "no-store" }));
}

export async function getModels(ollamaApiKey?: string): Promise<string[]> {
  const payload = await parseResponse<{ models: string[] }>(
    await fetch(`${API_BASE_URL}/models`, { cache: "no-store", headers: buildHeaders(undefined, ollamaApiKey) })
  );
  return payload.models;
}

export async function getDatasets(): Promise<DatasetOption[]> {
  const payload = await parseResponse<{ datasets: DatasetOption[] }>(
    await fetch(`${API_BASE_URL}/datasets`, { cache: "no-store" })
  );
  return payload.datasets;
}

export async function getQuestions(datasetKey: string): Promise<{ instruction: string; questions: BenchmarkQuestion[] }> {
  const payload = await parseResponse<{
    dataset_key: string;
    instruction: string;
    questions: BenchmarkQuestion[];
  }>(await fetch(`${API_BASE_URL}/questions?dataset_key=${encodeURIComponent(datasetKey)}`, { cache: "no-store" }));
  return { instruction: payload.instruction, questions: payload.questions };
}

export async function getResults(datasetKey: string): Promise<ResultsResponse> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/results?dataset_key=${encodeURIComponent(datasetKey)}`, { cache: "no-store" })
  );
}

export async function startRun(payload: {
  session_id: string;
  dataset_key: string;
  question_id: string;
  models: string[];
  system_prompt?: string;
}, ollamaApiKey?: string): Promise<RunStartResponse> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/runs`, {
      method: "POST",
      headers: buildHeaders("application/json", ollamaApiKey),
      body: JSON.stringify(payload)
    })
  );
}

export async function stopRun(runId: number, sessionId: string): Promise<{ status: string }> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/runs/${runId}/stop?session_id=${encodeURIComponent(sessionId)}`, {
      method: "POST"
    })
  );
}

export async function getRunStatus(runId: number, sessionId: string): Promise<RunStatusResponse> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/runs/${runId}/status?session_id=${encodeURIComponent(sessionId)}`, {
      cache: "no-store"
    })
  );
}

export async function applyManualDecision(payload: {
  dataset_key: string;
  question_id: string;
  model: string;
  status: "success" | "fail" | "manual_review";
  reason?: string;
}): Promise<{ status: string; result: Record<string, unknown> }> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/results/manual`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    })
  );
}

export async function uploadDataset(file: File): Promise<{ dataset: DatasetOption }> {
  const form = new FormData();
  form.append("file", file);
  return parseResponse(
    await fetch(`${API_BASE_URL}/datasets/upload`, {
      method: "POST",
      body: form
    })
  );
}

export async function deleteDataset(datasetKey: string): Promise<{ status: string; summary: Record<string, unknown> }> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(datasetKey)}`, {
      method: "DELETE"
    })
  );
}

export async function deleteModelResults(datasetKey: string, model: string): Promise<DeleteModelResultsResponse> {
  return parseResponse(
    await fetch(
      `${API_BASE_URL}/results/model?dataset_key=${encodeURIComponent(datasetKey)}&model=${encodeURIComponent(model)}`,
      {
        method: "DELETE"
      }
    )
  );
}

export async function getDatasetTemplate(): Promise<DatasetTemplateRow[]> {
  return parseResponse(await fetch(`${API_BASE_URL}/datasets/template`, { cache: "no-store" }));
}

export function exportLink(datasetKey: string, format: "json" | "xlsx"): string {
  return `${API_BASE_URL}/results/export?dataset_key=${encodeURIComponent(datasetKey)}&format=${format}`;
}

export function tableExportLink(datasetKey: string, table: ResultsTableKey, format: "json" | "xlsx"): string {
  return `${API_BASE_URL}/results/table_export?dataset_key=${encodeURIComponent(datasetKey)}&table=${encodeURIComponent(table)}&format=${format}`;
}

export async function getSloStatus(): Promise<SloStatus> {
  return parseResponse(await fetch(`${API_BASE_URL}/ops/slo`, { cache: "no-store" }));
}

export async function resetSloStatus(): Promise<{ status: string; slo: SloStatus }> {
  return parseResponse(
    await fetch(`${API_BASE_URL}/ops/slo/reset`, {
      method: "POST"
    })
  );
}
