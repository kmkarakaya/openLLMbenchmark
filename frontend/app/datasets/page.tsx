"use client";

import { useEffect, useMemo, useState } from "react";

import { Card } from "../../components/card";
import { ConfirmDialog } from "../../components/confirm-dialog";
import { DataTable } from "../../components/data-table";
import { EmptyState } from "../../components/empty-state";
import { ErrorState } from "../../components/error-state";
import { Field } from "../../components/field";
import { LoadingSkeleton } from "../../components/loading-skeleton";
import { Select } from "../../components/select";
import { useToast } from "../../components/toast-host";
import { datasetTemplateUrl, deleteDataset, getDatasets, uploadDataset } from "../../lib/api";
import type { DatasetOption } from "../../lib/types";

export default function DatasetsPage() {
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [selected, setSelected] = useState<string>("default_tr");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const selectedDataset = useMemo(() => datasets.find((item) => item.key === selected) ?? null, [datasets, selected]);
  const deleteDisabled = !selectedDataset || selectedDataset.is_default;

  const loadDatasets = async () => {
    const data = await getDatasets();
    setDatasets(data);
    if (!data.find((item) => item.key === selected)) {
      setSelected(data[0]?.key ?? "default_tr");
    }
  };

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await getDatasets();
        if (!active) {
          return;
        }
        setDatasets(data);
        setSelected(data[0]?.key ?? "default_tr");
      } catch (exc) {
        if (active) {
          setError(exc instanceof Error ? exc.message : String(exc));
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
  }, []);

  const handleUpload: React.ChangeEventHandler<HTMLInputElement> = async (event) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      await uploadDataset(file);
      pushToast("success", `Dataset uploaded: ${file.name}`);
      await loadDatasets();
    } catch (exc) {
      pushToast("danger", exc instanceof Error ? exc.message : String(exc));
    } finally {
      event.target.value = "";
    }
  };

  const handleDelete = async () => {
    if (!selectedDataset || selectedDataset.is_default) {
      return;
    }
    try {
      await deleteDataset(selectedDataset.key);
      pushToast("success", `Dataset deleted: ${selectedDataset.label}`);
      setConfirmOpen(false);
      await loadDatasets();
    } catch (exc) {
      pushToast("danger", exc instanceof Error ? exc.message : String(exc));
    }
  };

  if (loading) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Dataset Management</h1>
          <p className="mt-1 text-sm text-muted">Upload, select, and delete datasets. Export is available from Results.</p>
        </header>
        <Card title="Loading Datasets">
          <LoadingSkeleton lines={6} />
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Dataset Management</h1>
          <p className="mt-1 text-sm text-muted">Upload, select, and delete datasets. Export is available from Results.</p>
        </header>
        <ErrorState title="Failed to load datasets" message={error} />
      </div>
    );
  }

  if (!datasets.length) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Dataset Management</h1>
          <p className="mt-1 text-sm text-muted">Upload, select, and delete datasets. Export is available from Results.</p>
        </header>
        <EmptyState title="No datasets available" message="Create a dataset by uploading a benchmark JSON file." />
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-2xl font-semibold">Dataset Management</h1>
        <p className="mt-1 text-sm text-muted">Upload, select, and delete datasets. Export is available from Results.</p>
      </header>

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Dataset Actions">
          <div className="grid gap-3">
            <Field label="Active Dataset">
              <Select value={selected} onChange={(event) => setSelected(event.target.value)} data-testid="datasets-active-select">
                {datasets.map((item) => (
                  <option key={item.key} value={item.key}>
                    {item.label} ({item.question_count})
                  </option>
                ))}
              </Select>
            </Field>

            <label className="focus-ring inline-flex w-fit cursor-pointer items-center rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50">
              Upload Dataset JSON
              <input type="file" className="hidden" accept=".json,application/json" onChange={handleUpload} data-testid="datasets-upload-input" />
            </label>

            <div className="flex flex-wrap gap-2">
              <button
                className="focus-ring rounded-ui bg-danger px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => setConfirmOpen(true)}
                disabled={deleteDisabled}
              >
                Delete Uploaded Dataset
              </button>
              <a className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-medium hover:bg-slate-50" href={datasetTemplateUrl()} target="_blank" rel="noreferrer">
                Download Template
              </a>
            </div>

          </div>
        </Card>

        <Card title="Selected Dataset Summary">
          <dl className="grid gap-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Key</dt>
              <dd className="font-medium">{selectedDataset?.key ?? "-"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Label</dt>
              <dd className="font-medium">{selectedDataset?.label ?? "-"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Questions</dt>
              <dd className="font-medium">{selectedDataset?.question_count ?? 0}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Default dataset</dt>
              <dd className="font-medium">{selectedDataset?.is_default ? "Yes" : "No"}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-muted">Signature</dt>
              <dd className="font-log text-xs">{selectedDataset?.signature ?? "-"}</dd>
            </div>
          </dl>
        </Card>
      </section>

      <Card title="Available Datasets">
        <DataTable
          rows={datasets}
          emptyMessage="No datasets."
          columns={[
            { key: "key", header: "Key", render: (row) => row.key },
            { key: "label", header: "Label", render: (row) => row.label },
            { key: "count", header: "Questions", render: (row) => row.question_count },
            { key: "default", header: "Default", render: (row) => (row.is_default ? "Yes" : "No") },
            { key: "signature", header: "Signature", render: (row) => <span className="font-log text-xs">{row.signature}</span> }
          ]}
        />
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        title="Delete uploaded dataset?"
        message="This removes dataset file and related dataset artifacts. This cannot be undone."
        confirmLabel="Delete Permanently"
        cancelLabel="Keep Dataset"
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() => void handleDelete()}
      />
    </div>
  );
}
