"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Card } from "../../components/card";
import { EmptyState } from "../../components/empty-state";
import { ErrorState } from "../../components/error-state";
import { Field } from "../../components/field";
import { LoadingSkeleton } from "../../components/loading-skeleton";
import { ModelPicker } from "../../components/model-picker";
import { Select } from "../../components/select";
import { useToast } from "../../components/toast-host";
import { getDatasets, getModels, getQuestions } from "../../lib/api";
import { useAppState } from "../../lib/app-state";
import type { DatasetOption } from "../../lib/types";
import { hasModelSelectionError, resolveActiveModels } from "../../lib/view-models";

export default function ConfigurePage() {
  const router = useRouter();
  const { config, setConfig } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [error, setError] = useState<string>("");

  const selectionError = hasModelSelectionError(config);
  const activeModels = useMemo(() => resolveActiveModels(config), [config]);
  const canRunBenchmark = Boolean(
    config.datasetKey.trim() && config.questionId.trim() && config.systemPrompt.trim() && !selectionError && activeModels.length > 0
  );

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

        if (selectedDataset) {
          const questionPayload = await getQuestions(selectedDataset);
          if (!active) {
            return;
          }
          setConfig({
            systemPrompt: config.systemPrompt || questionPayload.instruction || "",
            questionId: questionPayload.questions[0]?.id ?? ""
          });
        }
      } catch (exc) {
        const message = exc instanceof Error ? exc.message : String(exc);
        setError(message);
      }

      try {
        const modelPayload = await getModels();
        if (!active) {
          return;
        }
        setModels(modelPayload);
      } catch (exc) {
        const message = exc instanceof Error ? exc.message : String(exc);
        pushToast("warning", `Model list unavailable: ${message}`);
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

  useEffect(() => {
    if (!config.datasetKey) {
      return;
    }
    let active = true;
    const syncDatasetInstruction = async () => {
      try {
        const payload = await getQuestions(config.datasetKey);
        if (!active) {
          return;
        }
        if (!config.systemPrompt) {
          setConfig({ systemPrompt: payload.instruction || "" });
        }
        if (!config.questionId && payload.questions[0]) {
          setConfig({ questionId: payload.questions[0].id });
        }
      } catch {
        // Keep existing prompt in case question fetch is unavailable.
      }
    };
    void syncDatasetInstruction();
    return () => {
      active = false;
    };
  }, [config.datasetKey]);

  if (loading) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Configure Benchmark</h1>
          <p className="mt-1 text-sm text-muted">Set benchmark inputs before running question-by-question evaluation.</p>
        </header>
        <Card title="Loading Configuration">
          <LoadingSkeleton lines={7} />
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Configure Benchmark</h1>
          <p className="mt-1 text-sm text-muted">Set benchmark inputs before running question-by-question evaluation.</p>
        </header>
        <ErrorState title="Failed to load configuration data" message={error} />
      </div>
    );
  }

  if (!datasets.length) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Configure Benchmark</h1>
          <p className="mt-1 text-sm text-muted">Set benchmark inputs before running question-by-question evaluation.</p>
        </header>
        <EmptyState title="No datasets found" message="Upload a dataset from Dataset Management to continue." />
      </div>
    );
  }

  const handleRunBenchmark = () => {
    if (!canRunBenchmark) {
      return;
    }
    router.push("/run");
  };

  return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-2xl font-semibold">Configure Benchmark</h1>
        <p className="mt-1 text-sm text-muted">Setup only: dataset, mode, model selection, and system prompt.</p>
      </header>
      <Card title="Benchmark Setup">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Dataset">
            <Select
              value={config.datasetKey}
              onChange={(event) => setConfig({ datasetKey: event.target.value })}
              data-testid="configure-dataset"
            >
              {datasets.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label} ({item.question_count})
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Mode">
            <Select
              value={config.mode}
              onChange={(event) => setConfig({ mode: event.target.value as "single" | "pair" })}
              data-testid="configure-mode"
            >
              <option value="single">Single model</option>
              <option value="pair">Comparison (2 models)</option>
            </Select>
          </Field>

          <ModelPicker
            label="Primary Model"
            options={models}
            selected={config.model1}
            onSelectedChange={(value) => setConfig({ model1: value })}
          />

          <ModelPicker
            label="Secondary Model"
            options={models.filter((item) => item !== config.model1)}
            selected={config.model2}
            onSelectedChange={(value) => setConfig({ model2: value })}
            disabled={config.mode !== "pair"}
          />

          <div className="md:col-span-2">
            <Field label="System Prompt" error={selectionError}>
              <textarea
                value={config.systemPrompt}
                onChange={(event) => setConfig({ systemPrompt: event.target.value })}
                className="focus-ring min-h-32 w-full rounded-ui border border-border bg-white px-3 py-2 text-sm"
                placeholder="Enter system instruction..."
                data-testid="configure-system-prompt"
              />
            </Field>
          </div>
        </div>
        <div className="mt-4 rounded-ui border border-border bg-slate-50 p-3 text-sm">
          <p className="font-medium">Resolved model set</p>
          <p className="mt-1 text-muted">{activeModels.join(", ") || "No model selected yet."}</p>
        </div>
        <div className="mt-4 flex justify-center">
          <button
            type="button"
            className="focus-ring rounded-ui bg-primary px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canRunBenchmark}
            onClick={handleRunBenchmark}
            data-testid="configure-run-benchmark"
          >
            Run Benchmark
          </button>
        </div>
      </Card>
    </div>
  );
}
