import type { BenchmarkConfig } from "./app-state";
import type { BenchmarkQuestion, ResultsResponse } from "./types";

export type UiMetricRow = {
  model: string;
  accuracyPercent: number;
  latencyScore: number;
  successOverScored: string;
  medianSeconds: number | null;
  meanSeconds: number | null;
  p95Seconds: number | null;
};

export type UiMatrixRow = {
  questionId: string;
  category: string;
  cells: Record<string, string>;
};

export type UiDistributionRow = {
  key: string;
  count: number;
  percent: number;
};

export function resolveActiveModels(config: BenchmarkConfig): string[] {
  const model1 = (config.model1 || "").trim();
  const model2 = (config.model2 || "").trim();
  if (config.mode === "single") {
    return model1 ? [model1] : [];
  }
  return Array.from(new Set([model1, model2].filter(Boolean)));
}

export function hasModelSelectionError(config: BenchmarkConfig): string | null {
  const selected = resolveActiveModels(config);
  if (config.mode === "single" && selected.length < 1) {
    return "Select one model.";
  }
  if (config.mode === "pair" && selected.length < 2) {
    return "Comparison mode requires two different models.";
  }
  return null;
}

export function mapMetrics(results: ResultsResponse | null): UiMetricRow[] {
  if (!results) {
    return [];
  }
  return results.metrics.map((row) => {
    const record = row as Record<string, unknown>;
    const medianMs = Number(record.median_ms ?? 0);
    const meanMs = Number(record.mean_ms ?? 0);
    const p95Ms = Number(record.p95_ms ?? 0);
    return {
      model: String(record.model ?? ""),
      accuracyPercent: Number(record.accuracy_percent ?? 0),
      latencyScore: Number(record.latency_score ?? 0),
      successOverScored: `${Number(record.success_count ?? 0)}/${Number(record.scored_count ?? 0)}`,
      medianSeconds: medianMs > 0 ? Number((medianMs / 1000).toFixed(2)) : null,
      meanSeconds: meanMs > 0 ? Number((meanMs / 1000).toFixed(2)) : null,
      p95Seconds: p95Ms > 0 ? Number((p95Ms / 1000).toFixed(2)) : null
    };
  });
}

export function mapMatrix(results: ResultsResponse | null): UiMatrixRow[] {
  if (!results) {
    return [];
  }
  return results.matrix.map((row) => {
    const record = row as Record<string, unknown>;
    const cells = (record.cells as Record<string, string>) ?? {};
    return {
      questionId: String(record.question_id ?? ""),
      category: String(record.category ?? ""),
      cells
    };
  });
}

function distribution(values: string[]): UiDistributionRow[] {
  if (!values.length) {
    return [];
  }
  const map = new Map<string, number>();
  values.forEach((value) => {
    const key = value.trim() || "(missing)";
    map.set(key, (map.get(key) ?? 0) + 1);
  });
  const total = values.length;
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([key, count]) => ({
      key,
      count,
      percent: Number(((count / total) * 100).toFixed(1))
    }));
}

export function buildMetadataDistributions(questions: BenchmarkQuestion[]) {
  return {
    categories: distribution(questions.map((item) => String(item.category ?? ""))),
    hardness: distribution(questions.map((item) => String(item.hardness_level ?? "")))
  };
}

export function runStateFromStatus(payload: {
  running: boolean;
  completed: boolean;
  interrupted: boolean;
  error: string;
}): "idle" | "running" | "completed" | "interrupted" | "error" {
  if (payload.error.trim()) {
    return "error";
  }
  if (payload.interrupted) {
    return "interrupted";
  }
  if (payload.completed) {
    return "completed";
  }
  if (payload.running) {
    return "running";
  }
  return "idle";
}
