"use client";

import Link from "next/link";

import { Card } from "../components/card";
import { DataTable } from "../components/data-table";
import { MetricCard } from "../components/metric-card";
import { useAppState } from "../lib/app-state";

export default function HomePage() {
  const { config, runHistory } = useAppState();

  return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <p className="mt-1 text-sm text-muted">Operational summary and quick actions for the benchmark workflow.</p>
      </header>

      <section className="grid gap-3 md:grid-cols-3">
        <MetricCard label="Selected Dataset" value={config.datasetKey || "-"} tone="accent" />
        <MetricCard label="Mode" value={config.mode === "pair" ? "Comparison" : "Single"} />
        <MetricCard label="Recent Runs" value={String(runHistory.length)} tone="success" />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Quick Actions">
          <div className="grid gap-2 sm:grid-cols-2">
            <Link className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50" href="/configure">
              Configure Benchmark
            </Link>
            <Link className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50" href="/run">
              Start / Monitor Run
            </Link>
            <Link className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50" href="/results">
              View Results
            </Link>
            <Link className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50" href="/datasets">
              Manage Datasets
            </Link>
          </div>
        </Card>

        <Card title="Current Configuration">
          <dl className="grid gap-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Dataset</dt>
              <dd className="font-medium">{config.datasetKey || "-"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Mode</dt>
              <dd className="font-medium">{config.mode === "pair" ? "Comparison" : "Single"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Model 1</dt>
              <dd className="font-medium">{(config.manualModel1 || config.model1 || "-").trim() || "-"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Model 2</dt>
              <dd className="font-medium">{(config.manualModel2 || config.model2 || "-").trim() || "-"}</dd>
            </div>
          </dl>
        </Card>
      </section>

      <Card title="Recent Runs">
        <DataTable
          rows={runHistory}
          emptyMessage="No run history yet. Start a benchmark from the Run page."
          columns={[
            { key: "runId", header: "Run ID", render: (row) => row.runId },
            { key: "dataset", header: "Dataset", render: (row) => row.datasetKey },
            { key: "models", header: "Models", render: (row) => row.models.join(", ") || "-" },
            { key: "status", header: "Status", render: (row) => row.status },
            { key: "startedAt", header: "Started", render: (row) => new Date(row.startedAt).toLocaleString() }
          ]}
        />
      </Card>
    </div>
  );
}
