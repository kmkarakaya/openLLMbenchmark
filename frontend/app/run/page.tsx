"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Card } from "../../components/card";
import { EmptyState } from "../../components/empty-state";
import { ErrorState } from "../../components/error-state";
import { StatusBanner } from "../../components/status-banner";
import { useToast } from "../../components/toast-host";
import { ApiError, applyManualDecision, getQuestions, getRunStatus, runEventsUrl, startRun, stopRun } from "../../lib/api";
import { useAppState } from "../../lib/app-state";
import type { BenchmarkQuestion, RunStatusResponse } from "../../lib/types";
import { hasModelSelectionError, resolveActiveModels, runStateFromStatus } from "../../lib/view-models";

export default function RunPage() {
  const { sessionId, config, setConfig, addRunHistory, updateRunHistory } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [questions, setQuestions] = useState<BenchmarkQuestion[]>([]);
  const [runId, setRunId] = useState<number | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [inlineBanner, setInlineBanner] = useState<{ tone: "info" | "warning" | "danger" | "success"; title: string; message: string } | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  const selectedModels = useMemo(() => resolveActiveModels(config), [config]);
  const configError = hasModelSelectionError(config);
  const questionIndex = useMemo(() => {
    if (!questions.length) return 0;
    const idx = questions.findIndex((item) => item.id === config.questionId);
    return idx < 0 ? 0 : idx;
  }, [questions, config.questionId]);
  const activeQuestion = questions[questionIndex] ?? null;
  const canStart = Boolean(activeQuestion && !configError && selectedModels.length > 0);
  const runState = runStatus
    ? runStateFromStatus({
        running: runStatus.running,
        completed: runStatus.completed,
        interrupted: runStatus.interrupted,
        error: runStatus.error
      })
    : "idle";

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const payload = await getQuestions(config.datasetKey);
        if (!active) {
          return;
        }
        setQuestions(payload.questions);
        if (!config.systemPrompt) {
          setConfig({ systemPrompt: payload.instruction || "" });
        }
        if (!config.questionId && payload.questions[0]) {
          setConfig({ questionId: payload.questions[0].id });
        }
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
  }, [config.datasetKey]);

  useEffect(() => {
    if (!runId) {
      return;
    }
    const interval = window.setInterval(async () => {
      try {
        const status = await getRunStatus(runId, sessionId);
        setRunStatus(status);
        const mappedResponses: Record<string, string> = {};
        status.entries.forEach((entry) => {
          if (entry.model) {
            mappedResponses[entry.model] = responses[entry.model] ?? "";
          }
        });
        if (Object.keys(mappedResponses).length) {
          setResponses((prev) => ({ ...prev, ...mappedResponses }));
        }
        const terminal = runStateFromStatus(status);
        if (terminal === "completed") {
          updateRunHistory(runId, "completed");
        } else if (terminal === "interrupted") {
          updateRunHistory(runId, "interrupted");
        } else if (terminal === "error") {
          updateRunHistory(runId, "error");
        }
      } catch {
        // Poll failures are expected during reconnect transitions.
      }
    }, 1000);
    return () => window.clearInterval(interval);
  }, [runId, sessionId, responses, updateRunHistory]);

  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
    };
  }, []);

  const openRunStream = (nextRunId: number) => {
    eventSourceRef.current?.close();
    const source = new EventSource(runEventsUrl(nextRunId, sessionId));
    source.addEventListener("chunk", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { model: string; response: string };
        if (!payload.model) {
          return;
        }
        setResponses((prev) => ({ ...prev, [payload.model]: payload.response ?? "" }));
      } catch {
        // ignore malformed events
      }
    });
    source.addEventListener("run_completed", () => {
      updateRunHistory(nextRunId, "completed");
      pushToast("success", `Run ${nextRunId} completed.`);
      setInlineBanner({ tone: "success", title: "Run completed:", message: `Run ${nextRunId} finished successfully.` });
      source.close();
    });
    source.addEventListener("run_interrupted", () => {
      updateRunHistory(nextRunId, "interrupted");
      pushToast("warning", `Run ${nextRunId} interrupted.`);
      setInlineBanner({ tone: "warning", title: "Run interrupted:", message: `Run ${nextRunId} was stopped by operator.` });
      source.close();
    });
    source.addEventListener("run_error", (event) => {
      updateRunHistory(nextRunId, "error");
      const data = (event as MessageEvent).data;
      pushToast("danger", `Run ${nextRunId} error: ${data || "unknown"}`);
      setInlineBanner({ tone: "danger", title: "Run error:", message: data || "Unknown stream error." });
      source.close();
    });
    source.onerror = () => {
      setInlineBanner({
        tone: "warning",
        title: "Stream disconnected:",
        message: "Live stream disconnected. Status polling is still active."
      });
      source.close();
    };
    eventSourceRef.current = source;
  };

  const handleStart = async () => {
    if (!activeQuestion || !canStart) {
      return;
    }
    setInlineBanner(null);
    try {
      const payload = await startRun({
        session_id: sessionId,
        dataset_key: config.datasetKey,
        question_id: activeQuestion.id,
        models: selectedModels,
        system_prompt: config.systemPrompt
      });
      setRunId(payload.run_id);
      setRunStatus(null);
      setResponses({});
      addRunHistory({
        runId: payload.run_id,
        datasetKey: config.datasetKey,
        models: selectedModels,
        startedAt: new Date().toISOString(),
        status: "started"
      });
      pushToast("success", `Run ${payload.run_id} started.`);
      openRunStream(payload.run_id);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      if (exc instanceof ApiError && exc.status === 503) {
        setInlineBanner({ tone: "warning", title: "Run unavailable:", message });
      } else {
        setInlineBanner({ tone: "danger", title: "Run start failed:", message });
      }
      pushToast("danger", message);
    }
  };

  const handleStop = async () => {
    if (!runId) {
      return;
    }
    try {
      await stopRun(runId, sessionId);
      updateRunHistory(runId, "stopped");
      pushToast("warning", "Stop request sent.");
      setInlineBanner({ tone: "warning", title: "Stop requested:", message: "Run interruption is in progress." });
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      pushToast("danger", message);
      setInlineBanner({ tone: "danger", title: "Stop failed:", message });
    }
  };

  const handleManual = async (model: string, status: "success" | "fail" | "manual_review") => {
    if (!activeQuestion) {
      return;
    }
    try {
      await applyManualDecision({
        dataset_key: config.datasetKey,
        question_id: activeQuestion.id,
        model,
        status
      });
      pushToast("success", `Manual decision saved: ${model} -> ${status}`);
    } catch (exc) {
      pushToast("danger", exc instanceof Error ? exc.message : String(exc));
    }
  };

  if (loading) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Benchmark Run</h1>
          <p className="mt-1 text-sm text-muted">Run question-by-question benchmark with live stream and operator controls.</p>
        </header>
        <Card title="Loading question set">
          <div className="h-24 animate-pulse rounded-ui bg-slate-200" />
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Benchmark Run</h1>
          <p className="mt-1 text-sm text-muted">Run question-by-question benchmark with live stream and operator controls.</p>
        </header>
        <ErrorState title="Unable to load questions" message={error} />
      </div>
    );
  }

  if (!questions.length) {
    return (
      <div className="grid gap-5">
        <header>
          <h1 className="text-2xl font-semibold">Benchmark Run</h1>
          <p className="mt-1 text-sm text-muted">Run question-by-question benchmark with live stream and operator controls.</p>
        </header>
        <EmptyState title="No questions available" message="Select another dataset in Configure or upload a dataset." />
      </div>
    );
  }

  return (
    <div className="grid gap-5">
      <header>
        <h1 className="text-2xl font-semibold">Benchmark Run</h1>
        <p className="mt-1 text-sm text-muted">Live run controls with stop and manual decision support.</p>
      </header>

      {configError ? <StatusBanner tone="warning" title="Configuration issue:" message={configError} /> : null}
      {inlineBanner ? <StatusBanner tone={inlineBanner.tone} title={inlineBanner.title} message={inlineBanner.message} /> : null}

      <section className="grid gap-4 lg:grid-cols-2">
        <Card title="Question Navigator">
          <div className="grid gap-3">
            <div className="flex items-center gap-2">
              <button
                className="focus-ring rounded-ui border border-border px-3 py-2 text-sm"
                onClick={() => setConfig({ questionId: questions[Math.max(0, questionIndex - 1)].id })}
                disabled={questionIndex <= 0}
              >
                Previous
              </button>
              <span className="text-sm text-muted">
                {questionIndex + 1} / {questions.length}
              </span>
              <button
                className="focus-ring rounded-ui border border-border px-3 py-2 text-sm"
                onClick={() => setConfig({ questionId: questions[Math.min(questions.length - 1, questionIndex + 1)].id })}
                disabled={questionIndex >= questions.length - 1}
              >
                Next
              </button>
            </div>
            <article className="rounded-ui border border-border bg-slate-50 p-3">
              <p className="text-sm font-semibold">{activeQuestion?.id}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm">{activeQuestion?.prompt}</p>
              <p className="mt-2 text-xs text-muted">Expected: {activeQuestion?.expected_answer || "-"}</p>
            </article>
          </div>
        </Card>

        <Card title="Run Controls">
          <div className="grid gap-3">
            <p className="text-sm text-muted">Dataset: {config.datasetKey}</p>
            <p className="text-sm text-muted">Models: {selectedModels.join(", ") || "-"}</p>
            <p className="text-sm text-muted">State: {runState}</p>
            <div className="flex flex-wrap gap-2">
              <button
                className="focus-ring rounded-ui bg-primary px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleStart}
                disabled={!canStart || runState === "running"}
              >
                Start Run
              </button>
              <button
                className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleStop}
                disabled={!runId || runState !== "running"}
              >
                Stop
              </button>
            </div>
          </div>
        </Card>
      </section>

      <Card title="Live Model Responses">
        <div className="grid gap-3">
          {selectedModels.map((model) => (
            <article key={model} className="rounded-ui border border-border bg-white p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold">{model}</h3>
                <span className="text-xs text-muted">
                  {runStatus?.entries.find((entry) => entry.model === model)?.event ?? "idle"}
                </span>
              </div>
              <textarea
                readOnly
                value={responses[model] ?? ""}
                className="font-log focus-ring min-h-32 w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-xs"
              />
              <div className="mt-2 flex flex-wrap gap-2">
                <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleManual(model, "success")}>
                  Mark Successful
                </button>
                <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleManual(model, "fail")}>
                  Mark Failed
                </button>
                <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleManual(model, "manual_review")}>
                  Needs Review
                </button>
              </div>
            </article>
          ))}
        </div>
      </Card>
    </div>
  );
}
