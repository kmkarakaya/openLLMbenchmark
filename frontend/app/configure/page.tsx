"use client";

import Link from "next/link";
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
import { ApiError, getDatasets, getModels, getOllamaAuthStatus, getQuestions } from "../../lib/api";
import { useAppState } from "../../lib/app-state";
import type { DatasetOption, OllamaAuthStatus } from "../../lib/types";
import { hasModelSelectionError, resolveActiveModels } from "../../lib/view-models";

const MISSING_CLOUD_KEY_MESSAGE = "Enter Ollama API Key to be able to use Ollama Cloud models.";

function modelNeedsCloudKey(model: string): boolean {
  const normalized = model.trim().toLowerCase();
  return Boolean(normalized) && !normalized.endsWith(":local");
}

export default function ConfigurePage() {
  const router = useRouter();
  const { config, setConfig, ollamaApiKey, ollamaApiKeyHydrated, setOllamaApiKey, clearOllamaApiKey } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [datasets, setDatasets] = useState<DatasetOption[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [ollamaAuthStatus, setOllamaAuthStatus] = useState<OllamaAuthStatus | null>(null);
  const [ollamaApiKeyInput, setOllamaApiKeyInput] = useState("");
  const [ollamaApiKeyBusy, setOllamaApiKeyBusy] = useState(false);
  const [ollamaApiKeyError, setOllamaApiKeyError] = useState("");
  const [error, setError] = useState<string>("");

  const selectionError = hasModelSelectionError(config);
  const activeModels = useMemo(() => resolveActiveModels(config), [config]);
  const hasEffectiveCloudKey = Boolean(ollamaApiKey.trim() || ollamaAuthStatus?.server_api_key_configured);
  const runBlockedByMissingCloudKey = activeModels.some(modelNeedsCloudKey) && !hasEffectiveCloudKey;
  const canRunBenchmark = Boolean(
    config.datasetKey.trim() &&
      config.questionId.trim() &&
      config.systemPrompt.trim() &&
      !selectionError &&
      !runBlockedByMissingCloudKey &&
      activeModels.length > 0
  );

  const applyAvailableModels = (availableModels: string[]) => {
    setModels(availableModels);
    const patch: Partial<typeof config> = {};
    if (config.model1 && !availableModels.includes(config.model1)) {
      patch.model1 = "";
    }
    if (config.model2 && !availableModels.includes(config.model2)) {
      patch.model2 = "";
    }
    if (Object.keys(patch).length) {
      setConfig(patch);
    }
  };

  useEffect(() => {
    if (!ollamaApiKeyHydrated) {
      return;
    }
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [datasetsPayload, authStatus] = await Promise.all([getDatasets(), getOllamaAuthStatus()]);
        if (!active) {
          return;
        }
        setDatasets(datasetsPayload);
        setOllamaAuthStatus(authStatus);
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
        const modelPayload = await getModels(ollamaApiKey);
        if (!active) {
          return;
        }
        applyAvailableModels(modelPayload);
      } catch (exc) {
        const message = exc instanceof Error ? exc.message : String(exc);
        if (!active) {
          return;
        }
        applyAvailableModels([]);
        const isExpectedMissingKey = message.includes(MISSING_CLOUD_KEY_MESSAGE);
        if (!isExpectedMissingKey) {
          pushToast("warning", `Model list unavailable: ${message}`);
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
  }, [ollamaApiKeyHydrated]);

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

  const handleSaveOllamaApiKey = async () => {
    const nextApiKey = ollamaApiKeyInput.trim();
    if (!nextApiKey) {
      setOllamaApiKeyError(MISSING_CLOUD_KEY_MESSAGE);
      return;
    }

    setOllamaApiKeyBusy(true);
    setOllamaApiKeyError("");
    try {
      const modelPayload = await getModels(nextApiKey);
      setOllamaApiKey(nextApiKey);
      applyAvailableModels(modelPayload);
      setOllamaApiKeyInput("");
      pushToast("success", "Ollama API key enabled for this browser session.");
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      setOllamaApiKeyError(message);
      pushToast("danger", message);
    } finally {
      setOllamaApiKeyBusy(false);
    }
  };

  const handleClearOllamaApiKey = async () => {
    clearOllamaApiKey();
    setOllamaApiKeyInput("");
    setOllamaApiKeyError("");
    setOllamaApiKeyBusy(true);
    try {
      const modelPayload = await getModels();
      applyAvailableModels(modelPayload);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      applyAvailableModels([]);
      if (!message.includes(MISSING_CLOUD_KEY_MESSAGE)) {
        pushToast("warning", `Model list unavailable: ${message}`);
      }
    } finally {
      setOllamaApiKeyBusy(false);
    }
    pushToast("warning", "Browser-session Ollama API key cleared.");
  };

  const cloudAccessSummary = ollamaApiKey.trim()
    ? ollamaAuthStatus?.server_api_key_configured
      ? "Using browser session key. It overrides the system environment key for this session."
      : "Using browser session key for this session."
    : ollamaAuthStatus?.server_api_key_configured
      ? "A system environment key is configured on the server. You can still override it for this browser session."
      : `${MISSING_CLOUD_KEY_MESSAGE} Local Ollama models can still run without a cloud key.`;

  return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-2xl font-semibold">Configure Benchmark</h1>
        <p className="mt-1 text-sm text-muted">Setup only: dataset, mode, model selection, and system prompt.</p>
      </header>
      <Card title="Ollama Cloud Access">
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="System Environment Key" helper="Detected from the server environment only; the real key is never shown.">
            <input
              type="password"
              readOnly
              value={ollamaAuthStatus?.server_api_key_configured ? "******" : ""}
              placeholder="Not configured on server"
              className="focus-ring w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-sm text-muted"
              data-testid="configure-ollama-env-key"
            />
          </Field>

          <Field label="Browser Session Key" helper="Stored only in this browser session and cleared when the session ends.">
            <input
              type="password"
              readOnly
              value={ollamaApiKey.trim() ? "******" : ""}
              placeholder="Not set for this session"
              className="focus-ring w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-sm text-muted"
              data-testid="configure-ollama-session-key"
            />
          </Field>

          <div className="md:col-span-2 rounded-ui border border-border bg-slate-50 p-3 text-sm text-slate-700">
            <p className="font-medium">Cloud access status</p>
            <p className="mt-1">{cloudAccessSummary}</p>
            <p className="mt-2 text-xs text-muted">
              Get a free Ollama Cloud key at{" "}
              <Link href="https://ollama.com/settings/keys" target="_blank" rel="noreferrer" className="underline">
                ollama.com/settings/keys
              </Link>
              .
            </p>
          </div>

          <div className="md:col-span-2">
            <Field
              label={ollamaApiKey.trim() ? "Replace Ollama API Key" : "Enter Ollama API Key"}
              helper="Use your own Ollama Cloud key for this browser session."
              error={ollamaApiKeyError || (runBlockedByMissingCloudKey ? MISSING_CLOUD_KEY_MESSAGE : null)}
            >
              <div className="flex flex-col gap-2 md:flex-row">
                <input
                  type="password"
                  value={ollamaApiKeyInput}
                  onChange={(event) => setOllamaApiKeyInput(event.target.value)}
                  placeholder="Paste your Ollama API key"
                  className="focus-ring min-w-0 flex-1 rounded-ui border border-border bg-white px-3 py-2 text-sm"
                  data-testid="configure-ollama-api-key-input"
                />
                <button
                  type="button"
                  className="focus-ring rounded-ui bg-primary px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={handleSaveOllamaApiKey}
                  disabled={ollamaApiKeyBusy || !ollamaApiKeyInput.trim()}
                  data-testid="configure-ollama-api-key-save"
                >
                  {ollamaApiKeyBusy ? "Checking..." : "Use This Session Key"}
                </button>
                <button
                  type="button"
                  className="focus-ring rounded-ui border border-border bg-white px-4 py-2 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={handleClearOllamaApiKey}
                  disabled={ollamaApiKeyBusy || !ollamaApiKey.trim()}
                  data-testid="configure-ollama-api-key-clear"
                >
                  Clear Session Key
                </button>
              </div>
            </Field>
          </div>
        </div>
      </Card>
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
          {runBlockedByMissingCloudKey ? <p className="mt-2 text-danger">{MISSING_CLOUD_KEY_MESSAGE}</p> : null}
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
