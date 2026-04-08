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
import { exportLink, getDatasets, getQuestions, getResults, isApiDisabledError } from "../../lib/api";
import { useAppState } from "../../lib/app-state";
import type { BenchmarkQuestion, DatasetOption, ResultsResponse } from "../../lib/types";
import { buildMetadataDistributions, mapMatrix, mapMetrics } from "../../lib/view-models";

export default function ResultsPage() {
  const { config, setConfig } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [questions, setQuestions] = useState<BenchmarkQuestion[]>([]);
  const [readsDisabled, setReadsDisabled] = useState(false);
  const [lastExport, setLastExport] = useState<{
    format: "json" | "xlsx";
    at: string;
    datasetKey: string;
    status: "requested";
  } | null>(null);

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
  const metadata = useMemo(() => buildMetadataDistributions(questions), [questions]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      setReadsDisabled(false);
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
        const [resultsPayload, questionPayload] = await Promise.all([
          getResults(selectedDataset),
          getQuestions(selectedDataset)
        ]);
        if (!active) {
          return;
        }
        setResults(resultsPayload);
        setQuestions(questionPayload.questions);
      } catch (exc) {
        const message = exc instanceof Error ? exc.message : String(exc);
        if (isApiDisabledError(exc)) {
          setReadsDisabled(true);
        } else {
          setError(message);
          pushToast("danger", message);
        }
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
    try {
      const [resultsPayload, questionPayload] = await Promise.all([getResults(datasetKey), getQuestions(datasetKey)]);
      setResults(resultsPayload);
      setQuestions(questionPayload.questions);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setLoading(false);
    }
  };

  const onExportClick = (format: "json" | "xlsx") => {
    const at = new Date().toISOString();
    setLastExport({ format, at, datasetKey: config.datasetKey, status: "requested" });
    pushToast("info", `Export requested: ${format.toUpperCase()} for ${config.datasetKey}`);
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

  if (readsDisabled) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Results</h1>
          <p className="mt-1 text-sm text-muted">Metrics, question matrix, and detailed model outputs.</p>
        </header>
        <ErrorState title="Read endpoints disabled" message="FEATURE_API_READS is disabled, so results cannot be loaded." />
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

      <Card title="Scope">
        <div className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(260px,1fr)]">
          <Field label="Dataset">
            <Select value={config.datasetKey} onChange={(event) => void onDatasetChange(event.target.value)}>
              {datasets.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label} ({item.question_count})
                </option>
              ))}
            </Select>
          </Field>
          <div className="rounded-ui border border-border bg-slate-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Export Results</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <a
                className="focus-ring inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-primary/40 hover:bg-primary/5"
                href={exportLink(config.datasetKey, "json")}
                target="_blank"
                rel="noreferrer"
                onClick={() => onExportClick("json")}
              >
                <span className="inline-flex h-5 w-5 items-center justify-center rounded border border-border bg-slate-50 text-[10px] font-bold">J</span>
                Export JSON
              </a>
              <a
                className="focus-ring inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-2 text-sm font-semibold hover:border-primary/40 hover:bg-primary/5"
                href={exportLink(config.datasetKey, "xlsx")}
                target="_blank"
                rel="noreferrer"
                onClick={() => onExportClick("xlsx")}
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
                    Last export requested: {lastExport.format.toUpperCase()} | Dataset: {lastExport.datasetKey}
                  </span>
                  <span className="font-log">{new Date(lastExport.at).toLocaleString()}</span>
                </div>
              ) : (
                <span className="text-muted">No export request yet in this session.</span>
              )}
            </div>
          </div>
        </div>
      </Card>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Model Metrics">
          <DataTable
            rows={metrics}
            emptyMessage="No metrics available for this dataset yet."
            columns={[
              { key: "model", header: "Model", render: (row) => row.model },
              { key: "accuracy", header: "Accuracy %", render: (row) => row.accuracyPercent.toFixed(1) },
              { key: "speed", header: "Speed Score", render: (row) => row.latencyScore.toFixed(1) },
              { key: "success", header: "Success/Scored", render: (row) => row.successOverScored },
              { key: "median", header: "Median (s)", render: (row) => row.medianSeconds?.toFixed(2) ?? "-" }
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

      <Card title="Question-Level Matrix">
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

      <Card title="Per-Model Response Details">
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
