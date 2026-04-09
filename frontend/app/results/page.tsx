"use client";

import { useEffect, useMemo, useState } from "react";

import { Card } from "../../components/card";
import { DataTable } from "../../components/data-table";
import { EmptyState } from "../../components/empty-state";
import { ErrorState } from "../../components/error-state";
import { Field } from "../../components/field";
import { LoadingSkeleton } from "../../components/loading-skeleton";
import { Select } from "../../components/select";
import { useToast } from "../../components/toast-host";
import {
  deleteModelResults,
  exportLink,
  getDatasets,
  getQuestions,
  getResults,
  tableExportLink
} from "../../lib/api";
import { useAppState } from "../../lib/app-state";
import type { BenchmarkQuestion, DatasetOption, ResultsResponse, ResultsTableKey } from "../../lib/types";
import {
  buildCategoryModelPerformance,
  buildHardnessModelPerformance,
  buildMetadataDistributions,
  mapMatrix,
  mapMetrics
} from "../../lib/view-models";

const TABLE_LABELS: Record<ResultsTableKey, string> = {
  model_leader_board: "Model Leader Board",
  category_level_model_performance: "Category-Level Model Performance",
  hardness_level_model_performance: "Hardness-Level Model Performance",
  question_level_model_performance: "Question-Level Model Performance",
  response_level_model_performance: "Response-Level Model Performance"
};

type GroupedPerformance = {
  rows: Array<{
    group: string;
    questionCount: number;
    accuracies: Record<string, number | null>;
  }>;
  models: string[];
};

type TransposedPerformance = {
  groups: Array<{ key: string; questionCount: number }>;
  rows: Array<{ model: string; values: Record<string, number | null> }>;
};

function transposeGroupedPerformance(perf: GroupedPerformance): TransposedPerformance {
  const groups = perf.rows.map((row) => ({ key: row.group || "-", questionCount: row.questionCount }));
  const rows = perf.models.map((model) => {
    const values: Record<string, number | null> = {};
    for (const group of groups) {
      const sourceRow = perf.rows.find((row) => (row.group || "-") === group.key);
      values[group.key] = sourceRow?.accuracies[model] ?? null;
    }
    return { model, values };
  });
  return { groups, rows };
}

export default function ResultsPage() {
  const { config, setConfig } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [questions, setQuestions] = useState<BenchmarkQuestion[]>([]);
  const [modelToDelete, setModelToDelete] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deletingModel, setDeletingModel] = useState(false);
  const [lastExport, setLastExport] = useState<{
    format: "json" | "xlsx";
    at: string;
    datasetKey: string;
    scope: "dataset" | ResultsTableKey;
    status: "requested";
  } | null>(null);
  const [openTableExport, setOpenTableExport] = useState<ResultsTableKey | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const metrics = useMemo(() => mapMetrics(results), [results]);
  const matrixRows = useMemo(() => mapMatrix(results), [results]);
  const matrixModels = useMemo(
    () =>
      Array.from(
        new Set(
          matrixRows.flatMap((item) => Object.keys(item.cells))
        )
      ),
    [matrixRows]
  );
  const categoryPerformance = useMemo(
    () => buildCategoryModelPerformance(questions, results),
    [questions, results]
  );
  const hardnessPerformance = useMemo(
    () => buildHardnessModelPerformance(questions, results),
    [questions, results]
  );
  const categoryPerformanceTransposed = useMemo(
    () => transposeGroupedPerformance(categoryPerformance),
    [categoryPerformance]
  );
  const hardnessPerformanceTransposed = useMemo(
    () => transposeGroupedPerformance(hardnessPerformance),
    [hardnessPerformance]
  );
  const availableResultModels = useMemo(
    () =>
      Array.from(
        new Set(
          (results?.results ?? [])
            .map((row) => String((row as Record<string, unknown>).model ?? "").trim())
            .filter(Boolean)
        )
      ).sort((a, b) => a.localeCompare(b)),
    [results]
  );
  const metadata = useMemo(() => buildMetadataDistributions(questions), [questions]);

  const loadDatasetSnapshot = async (datasetKey: string): Promise<ResultsResponse> => {
    const [resultsPayload, questionPayload] = await Promise.all([getResults(datasetKey), getQuestions(datasetKey)]);
    setResults(resultsPayload);
    setQuestions(questionPayload.questions);
    return resultsPayload;
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const datasetsPayload = await getDatasets();
        if (!active) {
          return;
        }
        setDatasets(datasetsPayload);
        const selectedDataset = datasetsPayload.find((item) => item.key === config.datasetKey)
          ? config.datasetKey
          : (datasetsPayload[0]?.key ?? "");
        setConfig({ datasetKey: selectedDataset });
        if (!selectedDataset) {
          setResults(null);
          setQuestions([]);
          return;
        }
        const [resultsPayload, questionPayload] = await Promise.all([getResults(selectedDataset), getQuestions(selectedDataset)]);
        if (!active) {
          return;
        }
        setResults(resultsPayload);
        setQuestions(questionPayload.questions);
      } catch (exc) {
        const message = exc instanceof Error ? exc.message : String(exc);
        setError(message);
        pushToast("danger", message);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [config.datasetKey]);

  const onDatasetChange = async (datasetKey: string) => {
    setConfig({ datasetKey });
    setLoading(true);
    setError("");
    setDeleteError("");
    try {
      await loadDatasetSnapshot(datasetKey);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!availableResultModels.length) {
      if (modelToDelete) {
        setModelToDelete("");
      }
      return;
    }
    if (!modelToDelete || !availableResultModels.includes(modelToDelete)) {
      setModelToDelete(availableResultModels[0]);
    }
  }, [availableResultModels, modelToDelete]);

  const onExportClick = (format: "json" | "xlsx") => {
    const at = new Date().toISOString();
    setLastExport({ format, at, datasetKey: config.datasetKey, scope: "dataset", status: "requested" });
    pushToast("info", `Export requested: ${format.toUpperCase()} for ${config.datasetKey}`);
  };

  const onTableExportClick = (table: ResultsTableKey, format: "json" | "xlsx") => {
    const at = new Date().toISOString();
    setLastExport({ format, at, datasetKey: config.datasetKey, scope: table, status: "requested" });
    setOpenTableExport(null);
    pushToast("info", `Export requested: ${TABLE_LABELS[table]} (${format.toUpperCase()})`);
  };

  const extractFilename = (headerValue: string | null, fallback: string): string => {
    if (!headerValue) {
      return fallback;
    }
    const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(headerValue);
    if (utf8Match && utf8Match[1]) {
      return decodeURIComponent(utf8Match[1]);
    }
    const simpleMatch = /filename="([^"]+)"/i.exec(headerValue) ?? /filename=([^;]+)/i.exec(headerValue);
    if (simpleMatch && simpleMatch[1]) {
      return simpleMatch[1].trim();
    }
    return fallback;
  };

  const requestAndDownload = async (url: string, fallbackFilename: string) => {
    if (isExporting) {
      return;
    }
    setIsExporting(true);
    try {
      const response = await fetch(url, { method: "GET" });
      if (!response.ok) {
        let detail = `Export failed (${response.status})`;
        try {
          const payload = (await response.json()) as { detail?: string };
          if (payload.detail) {
            detail = payload.detail;
          }
        } catch {
          // keep default detail
        }
        if (response.status === 404) {
          detail = `${detail}. If this endpoint is newly added, restart backend and retry.`;
        }
        throw new Error(detail);
      }
      const blob = await response.blob();
      const filename = extractFilename(response.headers.get("content-disposition"), fallbackFilename);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(objectUrl);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      pushToast("danger", message);
    } finally {
      setIsExporting(false);
    }
  };

  const renderTableExportActions = (table: ResultsTableKey) => {
    if (openTableExport !== table) {
      return (
        <button
          type="button"
          className="focus-ring rounded-ui border border-border bg-white px-3 py-1.5 text-xs font-semibold hover:border-primary/40 hover:bg-primary/5"
          onClick={() => setOpenTableExport(table)}
          data-testid={`results-export-open-${table}`}
        >
          Export
        </button>
      );
    }
    return (
      <div className="flex flex-wrap items-center justify-end gap-1.5">
        <a
          className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs font-semibold hover:border-primary/40 hover:bg-primary/5"
          href={tableExportLink(config.datasetKey, table, "json")}
          onClick={(event) => {
            event.preventDefault();
            onTableExportClick(table, "json");
            void requestAndDownload(
              tableExportLink(config.datasetKey, table, "json"),
              `${config.datasetKey}_${table}.json`
            );
          }}
          data-testid={`results-export-json-${table}`}
        >
          JSON
        </a>
        <a
          className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs font-semibold hover:border-primary/40 hover:bg-primary/5"
          href={tableExportLink(config.datasetKey, table, "xlsx")}
          onClick={(event) => {
            event.preventDefault();
            onTableExportClick(table, "xlsx");
            void requestAndDownload(
              tableExportLink(config.datasetKey, table, "xlsx"),
              `${config.datasetKey}_${table}.xlsx`
            );
          }}
          data-testid={`results-export-xlsx-${table}`}
        >
          Excel
        </a>
        <button
          type="button"
          className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs hover:bg-slate-100"
          onClick={() => setOpenTableExport(null)}
        >
          Cancel
        </button>
      </div>
    );
  };

  const onDeleteModelHistory = async () => {
    if (!modelToDelete || deletingModel) {
      return;
    }
    const confirmed = window.confirm(
      `Delete all saved responses for "${modelToDelete}" in dataset "${config.datasetKey}"? This cannot be undone.`
    );
    if (!confirmed) {
      return;
    }
    setDeletingModel(true);
    setDeleteError("");
    try {
      const response = await deleteModelResults(config.datasetKey, modelToDelete);
      await loadDatasetSnapshot(config.datasetKey);
      pushToast("success", `Deleted ${response.summary.deleted_count} records for ${response.summary.model}.`);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      setDeleteError(message);
      pushToast("danger", message);
    } finally {
      setDeletingModel(false);
    }
  };

  if (loading) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Results</h1>
          <p className="mt-1 text-sm text-muted">Metrics, question matrix, and detailed model outputs.</p>
        </header>
        <Card title="Loading Results">
          <LoadingSkeleton lines={8} />
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Results</h1>
          <p className="mt-1 text-sm text-muted">Metrics, question matrix, and detailed model outputs.</p>
        </header>
        <ErrorState title="Failed to load results" message={error} />
      </div>
    );
  }

  if (!datasets.length) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Results</h1>
          <p className="mt-1 text-sm text-muted">Metrics, question matrix, and detailed model outputs.</p>
        </header>
        <EmptyState title="No datasets available" message="Upload a dataset from Dataset Management." />
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-2xl font-semibold">Results</h1>
        <p className="mt-1 text-sm text-muted">Metrics, question matrix, and detailed model outputs.</p>
      </header>

      <section className="grid items-stretch gap-4 lg:grid-cols-2">
        <Card title="Select Dataset" className="h-full">
          <Field label="Dataset">
            <Select
              value={config.datasetKey}
              onChange={(event) => void onDatasetChange(event.target.value)}
              data-testid="results-dataset-select"
            >
              {datasets.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label} ({item.question_count})
                </option>
              ))}
            </Select>
          </Field>
        </Card>

        <Card title="Actions" className="h-full">
          <div className="rounded-ui border border-border bg-slate-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Export Raw Results</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <a
                className="focus-ring inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-primary/40 hover:bg-primary/5"
                href={exportLink(config.datasetKey, "json")}
                data-testid="results-export-raw-json"
                onClick={(event) => {
                  event.preventDefault();
                  onExportClick("json");
                  void requestAndDownload(
                    exportLink(config.datasetKey, "json"),
                    `${config.datasetKey}_raw_results.json`
                  );
                }}
              >
                <span className="inline-flex h-5 w-5 items-center justify-center rounded border border-border bg-slate-50 text-[10px] font-bold">J</span>
                Export JSON
              </a>
              <a
                className="focus-ring inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-primary/40 hover:bg-primary/5"
                href={exportLink(config.datasetKey, "xlsx")}
                data-testid="results-export-raw-xlsx"
                onClick={(event) => {
                  event.preventDefault();
                  onExportClick("xlsx");
                  void requestAndDownload(
                    exportLink(config.datasetKey, "xlsx"),
                    `${config.datasetKey}_raw_results.xlsx`
                  );
                }}
              >
                <span className="inline-flex h-5 w-5 items-center justify-center rounded border border-border bg-slate-50 text-[10px] font-bold">X</span>
                Export Excel
              </a>
            </div>
            <div className="mt-2 rounded-ui border border-border bg-white p-2 text-xs">
              {lastExport ? (
                <div className="flex flex-wrap items-center gap-2 text-muted">
                  <span className="inline-flex rounded-full border border-accent/40 bg-sky-50 px-2 py-0.5 font-semibold text-sky-800">
                    {lastExport.status.toUpperCase()}
                  </span>
                  <span>
                    Last export requested:{" "}
                    {lastExport.scope === "dataset" ? "All Results" : TABLE_LABELS[lastExport.scope]} ({lastExport.format.toUpperCase()}) |
                    {" "}Dataset: {lastExport.datasetKey}
                  </span>
                  <span className="font-log">{new Date(lastExport.at).toLocaleString()}</span>
                </div>
              ) : (
                <span className="text-muted">No export request yet in this session.</span>
              )}
            </div>
            <div className="mt-3 rounded-ui border border-danger/30 bg-rose-50 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-danger">Remove model history</p>
              <p className="mt-1 text-xs text-muted">Delete all saved responses for one model in this selected dataset.</p>
              <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
                <Select
                  value={modelToDelete}
                  onChange={(event) => setModelToDelete(event.target.value)}
                  disabled={!availableResultModels.length || deletingModel}
                  data-testid="results-delete-model-select"
                >
                  {!availableResultModels.length ? <option value="">No model history found</option> : null}
                  {availableResultModels.map((model) => (
                    <option key={model} value={model}>
                      {model}
                    </option>
                  ))}
                </Select>
                <button
                  type="button"
                  className="focus-ring rounded-ui border border-danger bg-danger px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void onDeleteModelHistory()}
                  disabled={!modelToDelete || !availableResultModels.length || deletingModel}
                  data-testid="results-delete-model-button"
                >
                  {deletingModel ? "Deleting..." : "Delete Model History"}
                </button>
              </div>
              {deleteError ? <p className="mt-2 text-xs text-danger">{deleteError}</p> : null}
            </div>
          </div>
        </Card>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Model Leader Board" actions={renderTableExportActions("model_leader_board")}>
          <DataTable
            rows={metrics}
            emptyMessage="No metrics available for this dataset yet."
            columns={[
              {
                key: "model",
                header: "Model",
                headerHelp: "Evaluated Ollama model name. This column is not a higher/lower-is-better metric.",
                render: (row) => row.model
              },
              {
                key: "accuracy",
                header: "Accuracy %",
                headerHelp: "(Successful answers / scored questions) x 100. Higher is better.",
                render: (row) => row.accuracyPercent.toFixed(1)
              },
              {
                key: "speed",
                header: "Speed Score",
                headerHelp: "Speed score normalized by the fastest model median (0-100). Higher is better.",
                render: (row) => row.latencyScore.toFixed(1)
              },
              {
                key: "success",
                header: "Success/Scored",
                headerHelp: "Successful answers / total scored questions. This column is not a higher/lower-is-better metric.",
                render: (row) => row.successOverScored
              },
              {
                key: "median",
                header: "Median (s)",
                headerHelp: "Median response time in seconds. Lower is better.",
                render: (row) => row.medianSeconds?.toFixed(2) ?? "-"
              }
            ]}
          />
        </Card>

        <Card title="Metadata Charts">
          {!metadata.categories.length && !metadata.hardness.length ? (
            <p className="text-sm text-muted">No metadata values found in the dataset questions.</p>
          ) : (
            <div className="grid gap-3">
              <div>
                <h3 className="text-sm font-semibold">Category Distribution</h3>
                <div className="mt-2 grid gap-2">
                  {metadata.categories.map((row) => (
                    <div key={row.key}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span>{row.key}</span>
                        <span>{row.percent}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-200">
                        <div className="h-2 rounded-full bg-primary" style={{ width: `${row.percent}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-sm font-semibold">Hardness Distribution</h3>
                <div className="mt-2 grid gap-2">
                  {metadata.hardness.map((row) => (
                    <div key={row.key}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span>{row.key}</span>
                        <span>{row.percent}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-200">
                        <div className="h-2 rounded-full bg-accent" style={{ width: `${row.percent}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </Card>
      </section>

      <Card title="Category-Level Model Performance" actions={renderTableExportActions("category_level_model_performance")}>
        <DataTable
          rows={categoryPerformanceTransposed.rows}
          emptyMessage="No category-level performance available yet."
          columns={[
            {
              key: "model",
              header: "Model",
              headerHelp: "Model identifier; each row shows per-category accuracy for that model.",
              render: (row) => row.model
            },
            ...categoryPerformanceTransposed.groups.map((group) => ({
              key: group.key,
              header: `${group.key} (${group.questionCount})`,
              headerHelp: "Category-level accuracy based on scored results (success/fail).",
              render: (row: (typeof categoryPerformanceTransposed.rows)[number]) => {
                const value = row.values[group.key];
                return typeof value === "number" ? `${value.toFixed(1)}%` : "-";
              }
            }))
          ]}
        />
      </Card>

      <Card title="Hardness-Level Model Performance" actions={renderTableExportActions("hardness_level_model_performance")}>
        <DataTable
          rows={hardnessPerformanceTransposed.rows}
          emptyMessage="No hardness-level performance available yet."
          columns={[
            {
              key: "model",
              header: "Model",
              headerHelp: "Model identifier; each row shows per-hardness accuracy for that model.",
              render: (row) => row.model
            },
            ...hardnessPerformanceTransposed.groups.map((group) => ({
              key: group.key,
              header: `${group.key} (${group.questionCount})`,
              headerHelp: "Hardness-level accuracy based on scored results (success/fail).",
              render: (row: (typeof hardnessPerformanceTransposed.rows)[number]) => {
                const value = row.values[group.key];
                return typeof value === "number" ? `${value.toFixed(1)}%` : "-";
              }
            }))
          ]}
        />
      </Card>

      <Card title="Question-Level Model Performance" actions={renderTableExportActions("question_level_model_performance")}>
        <DataTable
          rows={matrixRows}
          emptyMessage="No matrix rows available yet."
          columns={[
            { key: "question", header: "Question", render: (row) => row.questionId },
            { key: "category", header: "Category", render: (row) => row.category || "-" },
            ...matrixModels.map((model) => ({
              key: model,
              header: model,
              render: (row: (typeof matrixRows)[number]) => row.cells[model] ?? "-"
            }))
          ]}
        />
      </Card>

      <Card title="Response-Level Model Performance" actions={renderTableExportActions("response_level_model_performance")}>
        <DataTable
          rows={results?.results ?? []}
          emptyMessage="No detailed responses available yet."
          columns={[
            { key: "q", header: "Question", render: (row) => String((row as Record<string, unknown>).question_id ?? "-") },
            { key: "model", header: "Model", render: (row) => String((row as Record<string, unknown>).model ?? "-") },
            { key: "status", header: "Status", render: (row) => String((row as Record<string, unknown>).status ?? "-") },
            { key: "reason", header: "Reason", render: (row) => String((row as Record<string, unknown>).reason ?? "-") },
            {
              key: "response",
              header: "Response",
              render: (row) => {
                const text = String((row as Record<string, unknown>).response ?? "");
                return <span title={text}>{text.length > 120 ? `${text.slice(0, 120)}...` : text || "-"}</span>;
              }
            }
          ]}
        />
      </Card>
    </div>
  );
}
