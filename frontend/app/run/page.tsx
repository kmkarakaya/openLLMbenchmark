"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { Card } from "../../components/card";
import { EmptyState } from "../../components/empty-state";
import { ErrorState } from "../../components/error-state";
import { StatusBanner } from "../../components/status-banner";
import { useToast } from "../../components/toast-host";
import { ApiError, applyManualDecision, getQuestions, getResults, getRunStatus, runEventsUrl, startRun, stopRun } from "../../lib/api";
import { useAppState } from "../../lib/app-state";
import type { BenchmarkQuestion, RunStatusResponse } from "../../lib/types";
import { hasModelSelectionError, resolveActiveModels, runStateFromStatus } from "../../lib/view-models";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function applyInlineMarkdown(text: string): string {
  return text
    .replace(/`([^`]+)`/g, "<code class=\"rounded bg-slate-100 px-1 py-0.5\">$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function markdownToSafeHtml(markdown: string): string {
  const escaped = escapeHtml(markdown || "");
  const blocks = escaped.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  if (!blocks.length) {
    return "<p class=\"text-muted\">No response yet.</p>";
  }
  return blocks
    .map((block) => {
      if (block.startsWith("### ")) {
        return `<h3 class="mt-2 text-sm font-semibold">${applyInlineMarkdown(block.slice(4))}</h3>`;
      }
      if (block.startsWith("## ")) {
        return `<h2 class="mt-2 text-base font-semibold">${applyInlineMarkdown(block.slice(3))}</h2>`;
      }
      if (block.startsWith("# ")) {
        return `<h1 class="mt-2 text-lg font-semibold">${applyInlineMarkdown(block.slice(2))}</h1>`;
      }
      const lines = block.split("\n").map((line) => line.trimEnd());
      if (lines.every((line) => /^[-*]\s+/.test(line))) {
        const items = lines.map((line) => `<li>${applyInlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>`).join("");
        return `<ul class="list-disc pl-5">${items}</ul>`;
      }
      return `<p>${applyInlineMarkdown(block.replace(/\n/g, "<br/>"))}</p>`;
    })
    .join("");
}

function findLatestSavedResponse(rows: Array<Record<string, unknown>>, questionId: string, model: string): string {
  const matches = rows.filter(
    (row) => String(row.question_id ?? "").trim() === questionId && String(row.model ?? "").trim() === model
  );
  if (!matches.length) {
    return "";
  }

  let latestWithTimestamp: Record<string, unknown> | null = null;
  let latestTimestamp = Number.NEGATIVE_INFINITY;
  for (const row of matches) {
    const rawTimestamp = String(row.timestamp ?? "").trim();
    const parsedTimestamp = Date.parse(rawTimestamp);
    if (Number.isFinite(parsedTimestamp) && parsedTimestamp > latestTimestamp) {
      latestTimestamp = parsedTimestamp;
      latestWithTimestamp = row;
    }
  }

  const chosen = latestWithTimestamp ?? matches[matches.length - 1];
  return String(chosen.response ?? "");
}

export default function RunPage() {
  const { sessionId, config, setConfig, addRunHistory, updateRunHistory } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [questions, setQuestions] = useState<BenchmarkQuestion[]>([]);
  const [runId, setRunId] = useState<number | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [questionLayout, setQuestionLayout] = useState<"vertical" | "horizontal">("vertical");
  const [responseLayout, setResponseLayout] = useState<"vertical" | "horizontal">("vertical");
  const [responseFormat, setResponseFormat] = useState<"plain" | "markdown">("plain");
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
  const selectedModelsKey = useMemo(() => selectedModels.join("|"), [selectedModels]);

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

  useEffect(() => {
    let active = true;

    const loadPreviousResponses = async () => {
      if (!activeQuestion || !selectedModels.length) {
        setResponses({});
        return;
      }
      if (runState === "running") {
        return;
      }

      try {
        const payload = await getResults(config.datasetKey);
        if (!active) {
          return;
        }
        const mapped: Record<string, string> = {};
        for (const model of selectedModels) {
          mapped[model] = findLatestSavedResponse(payload.results, activeQuestion.id, model);
        }
        setResponses(mapped);
      } catch {
        if (active) {
          setResponses({});
        }
      }
    };

    void loadPreviousResponses();
    return () => {
      active = false;
    };
  }, [config.datasetKey, activeQuestion?.id, selectedModelsKey, runState]);

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

  const handleCopyResponse = async (model: string) => {
    const response = responses[model] ?? "";
    if (!response.trim()) {
      pushToast("warning", `No response available to copy for ${model}.`);
      return;
    }

    try {
      await navigator.clipboard.writeText(response);
      pushToast("success", `Response copied for ${model}.`);
    } catch {
      pushToast("danger", "Unable to copy response. Please try again.");
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

      {configError ? (
        <div className="rounded-ui border border-warning/30 bg-warning/10 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/configure"
              className="focus-ring rounded-ui border border-warning/40 bg-white px-3 py-1.5 text-sm font-medium text-warning hover:bg-warning/5"
            >
              Configure
            </Link>
            <p className="text-sm text-warning">
              <span className="font-semibold">Configuration issue:</span> {configError}
            </p>
          </div>
        </div>
      ) : null}
      {inlineBanner ? <StatusBanner tone={inlineBanner.tone} title={inlineBanner.title} message={inlineBanner.message} /> : null}

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="lg:col-span-2">
          <div className="overflow-x-auto rounded-card border border-border bg-surface p-3 shadow-soft md:p-4">
            <div className="inline-flex min-w-full flex-nowrap items-center gap-2 whitespace-nowrap">
              <div className="inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Dataset</span>
                <span className="text-sm font-medium">{config.datasetKey || "-"}</span>
              </div>
              <div className="inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">Models</span>
                <span className="text-sm font-medium">{selectedModels.join(", ") || "-"}</span>
              </div>
              <div className="inline-flex items-center gap-2 rounded-ui border border-border bg-white px-3 py-1.5">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted">State</span>
                <span className="text-sm font-medium">{runState}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="lg:col-span-2">
          <Card
            title="Question Navigator"
            actions={
              <div className="inline-flex rounded-ui border border-border bg-white p-1 text-xs font-medium">
                <button
                  type="button"
                  className={`focus-ring rounded-ui px-2 py-1 ${questionLayout === "vertical" ? "bg-primary text-white" : "text-muted hover:bg-slate-50"}`}
                  onClick={() => setQuestionLayout("vertical")}
                  aria-pressed={questionLayout === "vertical"}
                  data-testid="run-question-layout-vertical"
                >
                  Vertical
                </button>
                <button
                  type="button"
                  className={`focus-ring rounded-ui px-2 py-1 ${questionLayout === "horizontal" ? "bg-primary text-white" : "text-muted hover:bg-slate-50"}`}
                  onClick={() => setQuestionLayout("horizontal")}
                  aria-pressed={questionLayout === "horizontal"}
                  data-testid="run-question-layout-horizontal"
                >
                  Horizontal
                </button>
              </div>
            }
          >
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
              <p className="mb-1 text-sm font-semibold">{activeQuestion?.id}</p>
              <div
                className={questionLayout === "horizontal" ? "grid items-start gap-3 md:grid-cols-2" : "grid gap-3"}
                data-testid="run-question-layout"
              >
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Question</label>
                  <textarea
                    readOnly
                    value={activeQuestion?.prompt ?? ""}
                    className="font-log focus-ring min-h-40 w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">Expected Answer</label>
                  <textarea
                    readOnly
                    value={activeQuestion?.expected_answer ?? "-"}
                    className={`font-log focus-ring w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-sm ${
                      questionLayout === "horizontal" ? "min-h-40" : "min-h-24"
                    }`}
                  />
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-2">
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
        </div>
      </section>

      <Card
        title="Model Responses"
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="inline-flex rounded-ui border border-border bg-white p-1 text-xs font-medium">
              <button
                type="button"
                className={`focus-ring rounded-ui px-2 py-1 ${responseFormat === "plain" ? "bg-primary text-white" : "text-muted hover:bg-slate-50"}`}
                onClick={() => setResponseFormat("plain")}
                aria-pressed={responseFormat === "plain"}
                data-testid="run-response-format-plain"
              >
                Plain Text
              </button>
              <button
                type="button"
                className={`focus-ring rounded-ui px-2 py-1 ${responseFormat === "markdown" ? "bg-primary text-white" : "text-muted hover:bg-slate-50"}`}
                onClick={() => setResponseFormat("markdown")}
                aria-pressed={responseFormat === "markdown"}
                data-testid="run-response-format-markdown"
              >
                MD Format
              </button>
            </div>
            <div className="inline-flex rounded-ui border border-border bg-white p-1 text-xs font-medium">
              <button
                type="button"
                className={`focus-ring rounded-ui px-2 py-1 ${responseLayout === "vertical" ? "bg-primary text-white" : "text-muted hover:bg-slate-50"}`}
                onClick={() => setResponseLayout("vertical")}
                aria-pressed={responseLayout === "vertical"}
                data-testid="run-layout-vertical"
              >
                Vertical
              </button>
              <button
                type="button"
                className={`focus-ring rounded-ui px-2 py-1 ${responseLayout === "horizontal" ? "bg-primary text-white" : "text-muted hover:bg-slate-50"}`}
                onClick={() => setResponseLayout("horizontal")}
                aria-pressed={responseLayout === "horizontal"}
                data-testid="run-layout-horizontal"
              >
                Horizontal
              </button>
            </div>
          </div>
        }
      >
        <div className={responseLayout === "horizontal" ? "grid gap-3 md:grid-cols-2" : "grid gap-3"} data-testid="run-responses-layout">
          {selectedModels.map((model) => (
            <article key={model} className="rounded-ui border border-border bg-white p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold">{model}</h3>
                <div className="flex flex-wrap gap-2">
                  <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleManual(model, "success")}>
                    Mark Successful
                  </button>
                  <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleManual(model, "fail")}>
                    Mark Failed
                  </button>
                  <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleManual(model, "manual_review")}>
                    Needs Review
                  </button>
                  <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleCopyResponse(model)}>
                    Copy
                  </button>
                </div>
                <span className="ml-auto text-xs text-muted">
                  {runStatus?.entries.find((entry) => entry.model === model)?.event ?? "idle"}
                </span>
              </div>
              {responseFormat === "plain" ? (
                <textarea
                  readOnly
                  value={responses[model] ?? ""}
                  className="font-log focus-ring min-h-32 w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-xs"
                />
              ) : (
                <div
                  className="min-h-32 rounded-ui border border-border bg-slate-50 px-3 py-2 text-xs leading-6"
                  dangerouslySetInnerHTML={{ __html: markdownToSafeHtml(responses[model] ?? "") }}
                />
              )}
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
                <button className="focus-ring rounded-ui border border-border bg-white px-2 py-1 text-xs" onClick={() => void handleCopyResponse(model)}>
                  Copy
                </button>
              </div>
            </article>
          ))}
        </div>
      </Card>
    </div>
  );
}
