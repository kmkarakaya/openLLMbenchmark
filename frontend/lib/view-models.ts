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
  averageGeneratedTokens: number | null;
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

export type UiCategoryPerformanceRow = {
  group: string;
  questionCount: number;
  accuracies: Record<string, number | null>;
};

export function evaluationLabelFromRecord(record: Record<string, unknown>): string {
  const explicit = String(record.evaluation ?? "").trim();
  if (explicit) {
    return explicit;
  }
  const status = String(record.status ?? "").trim();
  return {
    success: "Successful",
    fail: "Fail",
    manual_review: "Needs Review"
  }[status] ?? (status || "Unknown");
}

export function evaluationMethodLabelFromRecord(record: Record<string, unknown>): string {
  const explicit = String(record.evaluation_method ?? "").trim();
  if (explicit) {
    return explicit;
  }
  return record.auto_scored === true ? "Automatic" : "Manual";
}

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
  const fallbackAverageTokensByModel = new Map<string, number>();
  const tokenRowsByModel = new Map<string, number[]>();
  for (const row of results.results) {
    const record = row as Record<string, unknown>;
    const model = String(record.model ?? "").trim();
    const rawTokens = record.generated_tokens;
    if (!model || typeof rawTokens !== "number" || !Number.isFinite(rawTokens) || record.interrupted === true) {
      continue;
    }
    const bucket = tokenRowsByModel.get(model) ?? [];
    bucket.push(Number(rawTokens));
    tokenRowsByModel.set(model, bucket);
  }
  for (const [model, tokenValues] of tokenRowsByModel.entries()) {
    const average = tokenValues.reduce((sum, value) => sum + value, 0) / tokenValues.length;
    fallbackAverageTokensByModel.set(model, average);
  }

  return results.metrics.map((row) => {
    const record = row as Record<string, unknown>;
    const model = String(record.model ?? "");
    const medianMs = Number(record.median_ms ?? 0);
    const meanMs = Number(record.mean_ms ?? 0);
    const p95Ms = Number(record.p95_ms ?? 0);
    const apiAverageTokens = record.avg_generated_tokens;
    return {
      model,
      accuracyPercent: Number(record.accuracy_percent ?? 0),
      latencyScore: Number(record.latency_score ?? 0),
      successOverScored: `${Number(record.success_count ?? 0)}/${Number(record.scored_count ?? 0)}`,
      medianSeconds: medianMs > 0 ? Number((medianMs / 1000).toFixed(2)) : null,
      meanSeconds: meanMs > 0 ? Number((meanMs / 1000).toFixed(2)) : null,
      p95Seconds: p95Ms > 0 ? Number((p95Ms / 1000).toFixed(2)) : null,
      averageGeneratedTokens:
        typeof apiAverageTokens === "number" && Number.isFinite(apiAverageTokens)
          ? Number(apiAverageTokens)
          : (fallbackAverageTokensByModel.get(model) ?? null)
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

function buildGroupedModelPerformance(
  questions: BenchmarkQuestion[],
  results: ResultsResponse | null,
  groupBy: (question: BenchmarkQuestion) => string
): { rows: UiCategoryPerformanceRow[]; models: string[] } {
  if (!results) {
    return { rows: [], models: [] };
  }

  const questionToGroup = new Map<string, string>();
  const groupQuestionCounts = new Map<string, number>();
  questions.forEach((question) => {
    const questionId = String(question.id ?? "").trim();
    const group = groupBy(question).trim() || "(missing)";
    if (questionId) {
      questionToGroup.set(questionId, group);
    }
    groupQuestionCounts.set(group, (groupQuestionCounts.get(group) ?? 0) + 1);
  });

  const models = Array.from(
    new Set(
      results.results
        .map((row) => String((row as Record<string, unknown>).model ?? "").trim())
        .filter(Boolean)
    )
  ).sort((a, b) => a.localeCompare(b));

  type Counter = { success: number; scored: number };
  const counters = new Map<string, Map<string, Counter>>();

  for (const row of results.results) {
    const record = row as Record<string, unknown>;
    const model = String(record.model ?? "").trim();
    const questionId = String(record.question_id ?? "").trim();
    const status = String(record.status ?? "").trim();
    if (!model || !questionId) {
      continue;
    }
    const group = questionToGroup.get(questionId) ?? "(missing)";
    if (!counters.has(group)) {
      counters.set(group, new Map<string, Counter>());
    }
    const byModel = counters.get(group);
    if (!byModel) {
      continue;
    }
    if (!byModel.has(model)) {
      byModel.set(model, { success: 0, scored: 0 });
    }
    const counter = byModel.get(model);
    if (!counter) {
      continue;
    }
    if (status === "success" || status === "fail") {
      counter.scored += 1;
      if (status === "success") {
        counter.success += 1;
      }
    }
  }

  const groups = Array.from(groupQuestionCounts.keys()).sort((a, b) => a.localeCompare(b));
  const rows: UiCategoryPerformanceRow[] = groups.map((group) => {
    const byModel = counters.get(group) ?? new Map<string, Counter>();
    const accuracies: Record<string, number | null> = {};
    models.forEach((model) => {
      const count = byModel.get(model);
      if (!count || count.scored === 0) {
        accuracies[model] = null;
      } else {
        accuracies[model] = Number(((count.success * 100) / count.scored).toFixed(1));
      }
    });
    return {
      group,
      questionCount: groupQuestionCounts.get(group) ?? 0,
      accuracies
    };
  });

  return { rows, models };
}

export function buildCategoryModelPerformance(
  questions: BenchmarkQuestion[],
  results: ResultsResponse | null
): { rows: UiCategoryPerformanceRow[]; models: string[] } {
  return buildGroupedModelPerformance(questions, results, (question) => String(question.category ?? "GENEL"));
}

export function buildHardnessModelPerformance(
  questions: BenchmarkQuestion[],
  results: ResultsResponse | null
): { rows: UiCategoryPerformanceRow[]; models: string[] } {
  return buildGroupedModelPerformance(questions, results, (question) => String(question.hardness_level ?? "(missing)"));
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
