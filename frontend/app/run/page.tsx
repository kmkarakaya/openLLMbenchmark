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
import { evaluationLabelFromRecord, evaluationMethodLabelFromRecord, hasModelSelectionError, resolveActiveModels, runStateFromStatus } from "../../lib/view-models";

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
  const latest = findLatestSavedResult(rows, questionId, model);
  return latest ? String(latest.response ?? "") : "";
}

function findLatestSavedResult(
  rows: Array<Record<string, unknown>>,
  questionId: string,
  model: string
): Record<string, unknown> | null {
  const matches = rows.filter(
    (row) => String(row.question_id ?? "").trim() === questionId && String(row.model ?? "").trim() === model
  );
  if (!matches.length) {
    return null;
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

  return latestWithTimestamp ?? matches[matches.length - 1];
}

function formatElapsedSeconds(elapsedMs: number | undefined): string {
  if (typeof elapsedMs !== "number" || !Number.isFinite(elapsedMs) || elapsedMs < 0) {
    return "-";
  }
  return `${(elapsedMs / 1000).toFixed(1)}s`;
}

function estimateTokenCount(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) {
    return 0;
  }
  const chars = trimmed.length;
  const words = trimmed.split(/\s+/).filter(Boolean).length;
  return Math.max(words, Math.round(chars / 4));
}

type SavedResultMeta = {
  responseTimeMs?: number;
  generatedTokens: number;
  generatedTokensEstimated: boolean;
  eventLabel: string;
  evaluationLabel: string;
  evaluationMethodLabel: string;
};

function readGeneratedTokensMeta(savedResult: Record<string, unknown>, responseText: string): Pick<SavedResultMeta, "generatedTokens" | "generatedTokensEstimated"> {
  const rawGeneratedTokens = savedResult.generated_tokens;
  const explicitEstimated = savedResult.generated_tokens_estimated;
  if (typeof rawGeneratedTokens === "number" && Number.isFinite(rawGeneratedTokens)) {
    return {
      generatedTokens: Number(rawGeneratedTokens),
      generatedTokensEstimated: typeof explicitEstimated === "boolean" ? explicitEstimated : true
    };
  }
  return {
    generatedTokens: estimateTokenCount(responseText),
    generatedTokensEstimated: true
  };
}

function buildSavedResultMeta(savedResult: Record<string, unknown>): SavedResultMeta {
  const responseText = String(savedResult.response ?? "");
  const tokenMeta = readGeneratedTokensMeta(savedResult, responseText);
  return {
    responseTimeMs:
      typeof savedResult.response_time_ms === "number" && Number.isFinite(savedResult.response_time_ms)
        ? Number(savedResult.response_time_ms)
        : undefined,
    generatedTokens: tokenMeta.generatedTokens,
    generatedTokensEstimated: tokenMeta.generatedTokensEstimated,
    eventLabel: String(savedResult.status ?? "saved") || "saved",
    evaluationLabel: evaluationLabelFromRecord(savedResult),
    evaluationMethodLabel: evaluationMethodLabelFromRecord(savedResult)
  };
}

function statusBadgeClassName(label: string): string {
  const normalized = label.trim().toLowerCase();

  if (!normalized || normalized === "-" || normalized === "idle") {
    return "rounded-full border border-border bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700";
  }

  if (
    normalized === "completed" ||
    normalized === "success" ||
    normalized === "successful" ||
    normalized === "entry_completed"
  ) {
    return "rounded-full border border-success/25 bg-success/10 px-2 py-0.5 text-xs font-medium text-success";
  }

  if (normalized === "fail" || normalized === "failed" || normalized === "error" || normalized === "run_error") {
    return "rounded-full border border-danger/25 bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger";
  }

  if (
    normalized === "pending" ||
    normalized === "interrupted" ||
    normalized === "run_interrupted" ||
    normalized === "manual_review" ||
    normalized === "needs review"
  ) {
    return "rounded-full border border-warning/30 bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning";
  }

  if (
    normalized === "response being generated" ||
    normalized === "running" ||
    normalized === "run_started" ||
    normalized === "generating" ||
    normalized === "chunk"
  ) {
    return "rounded-full border border-accent/30 bg-accent/10 px-2 py-0.5 text-xs font-medium text-primary";
  }

  return "rounded-full border border-border bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700";
}

function neutralBadgeClassName(): string {
  return "rounded-full border border-border bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700";
}

export default function RunPage() {
  const { sessionId, config, setConfig, ollamaApiKey, addRunHistory, updateRunHistory } = useAppState();
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [questions, setQuestions] = useState<BenchmarkQuestion[]>([]);
  const [runId, setRunId] = useState<number | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatusResponse | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [savedResultMeta, setSavedResultMeta] = useState<Record<string, SavedResultMeta>>({});
  const [questionLayout, setQuestionLayout] = useState<"vertical" | "horizontal">("vertical");
  const [responseLayout, setResponseLayout] = useState<"vertical" | "horizontal">("vertical");
  const [responseFormat, setResponseFormat] = useState<"plain" | "markdown">("plain");
  const [isStarting, setIsStarting] = useState(false);
  const [runStartedAtMs, setRunStartedAtMs] = useState<number | null>(null);
  const [liveClockMs, setLiveClockMs] = useState(() => Date.now());
  const [completedEntryElapsedMs, setCompletedEntryElapsedMs] = useState<Record<string, number>>({});
  const [activeRunModels, setActiveRunModels] = useState<string[]>([]);
  const [savedResponsesStatus, setSavedResponsesStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [savedResponsesReloadToken, setSavedResponsesReloadToken] = useState(0);
  const [pendingAutoStartKey, setPendingAutoStartKey] = useState<string>("");
  const [inlineBanner, setInlineBanner] = useState<{ tone: "info" | "warning" | "danger" | "success"; title: string; message: string } | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const terminalSavedResponsesRefreshKeyRef = useRef("");
  const completedEntryRefreshKeysRef = useRef(new Set<string>());

  const rememberCompletedElapsedMs = (model: string, elapsedMs: number) => {
    if (!model || !Number.isFinite(elapsedMs) || elapsedMs < 0) {
      return;
    }
    setCompletedEntryElapsedMs((prev) => {
      if (prev[model] === elapsedMs) {
        return prev;
      }
      return { ...prev, [model]: elapsedMs };
    });
  };

  const requestSavedResponsesRefresh = () => {
    setSavedResponsesStatus("loading");
    setSavedResponsesReloadToken((prev) => prev + 1);
  };

  const requestCompletedEntryRefresh = (completedRunId: number, model: string) => {
    const normalizedModel = model.trim();
    if (!completedRunId || !normalizedModel) {
      return;
    }
    const refreshKey = `${completedRunId}:${normalizedModel}`;
    if (completedEntryRefreshKeysRef.current.has(refreshKey)) {
      return;
    }
    completedEntryRefreshKeysRef.current.add(refreshKey);
    requestSavedResponsesRefresh();
  };

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
  const isAwaitingRunStatus = runId !== null && runStatus === null;
  const runInProgress = isStarting || runState === "running" || isAwaitingRunStatus;
  const autoStartPending = pendingAutoStartKey.length > 0;
  const navigatorLocked = runInProgress || autoStartPending;
  const stateLabel = runInProgress ? "Response being generated" : runState;
  const selectedModelsKey = useMemo(() => selectedModels.join("|"), [selectedModels]);
  const activeQuestionLookupKey = useMemo(() => {
    if (!activeQuestion) {
      return "";
    }
    return `${config.datasetKey}::${activeQuestion.id}::${selectedModelsKey}`;
  }, [config.datasetKey, activeQuestion, selectedModelsKey]);

  useEffect(() => {
    if (!runInProgress) {
      return;
    }
    const interval = window.setInterval(() => {
      setLiveClockMs(Date.now());
    }, 200);
    return () => window.clearInterval(interval);
  }, [runInProgress]);

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
        status.entries.forEach((entry) => {
          if (entry.completed && typeof entry.elapsed_ms === "number") {
            rememberCompletedElapsedMs(entry.model, entry.elapsed_ms);
          }
          if (entry.completed && !entry.interrupted && activeRunModels.includes(entry.model)) {
            requestCompletedEntryRefresh(runId, entry.model);
          }
        });
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
  }, [activeRunModels, runId, sessionId, updateRunHistory]);

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
        setSavedResultMeta({});
        setSavedResponsesStatus("idle");
        return;
      }

      setSavedResponsesStatus("loading");

      try {
        const payload = await getResults(config.datasetKey);
        if (!active) {
          return;
        }
        const preserveLiveResponses = runInProgress;
        const mapped: Record<string, string> = {};
        const savedMetaByModel: Record<string, SavedResultMeta> = {};
        for (const model of selectedModels) {
          const savedResult = findLatestSavedResult(payload.results, activeQuestion.id, model);
          mapped[model] = savedResult ? String(savedResult.response ?? "") : "";
          if (savedResult) {
            savedMetaByModel[model] = buildSavedResultMeta(savedResult);
          }
        }
        setResponses((prev) => {
          if (!preserveLiveResponses) {
            return mapped;
          }

          const next = { ...prev };
          for (const model of selectedModels) {
            const hasSavedResult = Boolean(savedMetaByModel[model]);
            const keepLiveResponse = activeRunModels.includes(model) && !hasSavedResult;
            next[model] = keepLiveResponse ? (prev[model] ?? "") : mapped[model];
          }
          return next;
        });
        setSavedResultMeta((prev) => {
          if (!preserveLiveResponses) {
            return savedMetaByModel;
          }

          const next = { ...prev };
          for (const model of selectedModels) {
            if (savedMetaByModel[model]) {
              next[model] = savedMetaByModel[model];
            } else if (!activeRunModels.includes(model)) {
              delete next[model];
            }
          }
          return next;
        });
        if (!preserveLiveResponses) {
          setCompletedEntryElapsedMs({});
        }
        setSavedResponsesStatus("ready");
      } catch {
        if (active) {
          if (!runInProgress) {
            setResponses({});
            setSavedResultMeta({});
            setCompletedEntryElapsedMs({});
          }
          completedEntryRefreshKeysRef.current.clear();
          setSavedResponsesStatus("error");
        }
      }
    };

    void loadPreviousResponses();
    return () => {
      active = false;
    };
  }, [config.datasetKey, activeQuestion?.id, selectedModelsKey, savedResponsesReloadToken]);

  useEffect(() => {
    if (runId === null || !runStatus || !activeQuestionLookupKey) {
      return;
    }

    const terminalState = runStateFromStatus({
      running: runStatus.running,
      completed: runStatus.completed,
      interrupted: runStatus.interrupted,
      error: runStatus.error
    });
    if (terminalState === "idle" || terminalState === "running") {
      return;
    }

    const refreshKey = `${runId}:${terminalState}:${activeQuestionLookupKey}`;
    if (terminalSavedResponsesRefreshKeyRef.current === refreshKey) {
      return;
    }

    terminalSavedResponsesRefreshKeyRef.current = refreshKey;
    requestSavedResponsesRefresh();
  }, [activeQuestionLookupKey, runId, runStatus]);

  const handleStart = async (modelsOverride?: string[]) => {
    const modelsToRun = Array.from(new Set((modelsOverride ?? selectedModels).map((model) => model.trim()).filter(Boolean)));
    if (!activeQuestion || !canStart || isStarting || !modelsToRun.length) {
      return;
    }
    setIsStarting(true);
    setInlineBanner(null);
    terminalSavedResponsesRefreshKeyRef.current = "";
    completedEntryRefreshKeysRef.current.clear();
    try {
      const payload = await startRun({
        session_id: sessionId,
        dataset_key: config.datasetKey,
        question_id: activeQuestion.id,
        models: modelsToRun,
        system_prompt: config.systemPrompt
      }, ollamaApiKey);
      setRunStartedAtMs(Date.now());
      setCompletedEntryElapsedMs({});
      setActiveRunModels(modelsToRun);
      setRunId(payload.run_id);
      setRunStatus(null);
      setResponses((prev) => {
        const next = { ...prev };
        modelsToRun.forEach((model) => {
          next[model] = "";
        });
        return next;
      });
      setSavedResultMeta((prev) => {
        const next = { ...prev };
        modelsToRun.forEach((model) => {
          delete next[model];
        });
        return next;
      });
      addRunHistory({
        runId: payload.run_id,
        datasetKey: config.datasetKey,
        models: modelsToRun,
        startedAt: new Date().toISOString(),
        status: "started"
      });
      pushToast("success", `Run ${payload.run_id} started.`);
      openRunStream(payload.run_id);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      if (exc instanceof ApiError && exc.status === 503) {
        setInlineBanner({ tone: "warning", title: "Run unavailable:", message });
      } else if (exc instanceof ApiError && exc.status === 409) {
        const conflictRunId = Number(exc.payload.run_id ?? 0);
        if (Number.isFinite(conflictRunId) && conflictRunId > 0) {
          setRunStartedAtMs(Date.now());
          setCompletedEntryElapsedMs({});
          setActiveRunModels(modelsToRun);
          setRunId(conflictRunId);
          setSavedResultMeta((prev) => {
            const next = { ...prev };
            modelsToRun.forEach((model) => {
              delete next[model];
            });
            return next;
          });
          openRunStream(conflictRunId);
          setInlineBanner({
            tone: "warning",
            title: "Run already active:",
            message: `Attached to active run ${conflictRunId} for this session.`
          });
          pushToast("warning", `Attached to active run ${conflictRunId}.`);
        } else {
          setInlineBanner({
            tone: "warning",
            title: "Run already active:",
            message: "A run is already active for this session. Wait for completion or stop it first."
          });
          pushToast("warning", "A run is already active for this session.");
        }
      } else {
        setInlineBanner({ tone: "danger", title: "Run start failed:", message });
        pushToast("danger", message);
      }
    } finally {
      setIsStarting(false);
    }
  };

  const handleQuestionNavigation = (nextQuestionId: string) => {
    const normalizedQuestionId = String(nextQuestionId || "").trim();
    if (!normalizedQuestionId || normalizedQuestionId === config.questionId) {
      return;
    }
    setSavedResponsesStatus("loading");
    setPendingAutoStartKey(`${config.datasetKey}::${normalizedQuestionId}::${selectedModelsKey}`);
    setConfig({ questionId: normalizedQuestionId });
  };

  useEffect(() => {
    if (!activeQuestion || !activeQuestionLookupKey) {
      return;
    }
    if (pendingAutoStartKey !== activeQuestionLookupKey) {
      return;
    }
    if (savedResponsesStatus === "error") {
      setPendingAutoStartKey("");
      return;
    }
    if (savedResponsesStatus !== "ready" || runInProgress || !canStart) {
      return;
    }

    const missingModels = selectedModels.filter((model) => !savedResultMeta[model]);
    setPendingAutoStartKey("");
    if (!missingModels.length) {
      return;
    }
    void handleStart(missingModels);
  }, [activeQuestion, activeQuestionLookupKey, canStart, pendingAutoStartKey, runInProgress, savedResponsesStatus, savedResultMeta, selectedModels]);

  const openRunStream = (nextRunId: number) => {
    eventSourceRef.current?.close();
    const source = new EventSource(runEventsUrl(nextRunId, sessionId));
    let interruptedNotified = false;
    let errorNotified = false;
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
    source.addEventListener("entry_completed", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { model?: string; elapsed_ms?: number };
        if (payload.model && typeof payload.elapsed_ms === "number") {
          rememberCompletedElapsedMs(payload.model, payload.elapsed_ms);
        }
        if (payload.model) {
          requestCompletedEntryRefresh(nextRunId, payload.model);
        }
      } catch {
        // ignore malformed completion events
      }
    });
    source.addEventListener("run_completed", () => {
      updateRunHistory(nextRunId, "completed");
      pushToast("success", `Run ${nextRunId} completed.`);
      setInlineBanner({ tone: "success", title: "Run completed:", message: `Run ${nextRunId} finished successfully.` });
      source.close();
    });
    source.addEventListener("run_interrupted", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { model?: string; elapsed_ms?: number };
        if (payload.model && typeof payload.elapsed_ms === "number") {
          rememberCompletedElapsedMs(payload.model, payload.elapsed_ms);
        }
      } catch {
        // ignore malformed interruption events
      }
      if (interruptedNotified) {
        return;
      }
      interruptedNotified = true;
      updateRunHistory(nextRunId, "interrupted");
      pushToast("warning", `Run ${nextRunId} interrupted.`);
      setInlineBanner({ tone: "warning", title: "Run interrupted:", message: `Run ${nextRunId} was stopped by operator.` });
    });
    source.addEventListener("run_error", (event) => {
      if (errorNotified) {
        return;
      }
      errorNotified = true;
      updateRunHistory(nextRunId, "error");
      const data = (event as MessageEvent).data;
      pushToast("danger", `Run ${nextRunId} error: ${data || "unknown"}`);
      setInlineBanner({ tone: "danger", title: "Run error:", message: data || "Unknown stream error." });
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

  const handleStop = async () => {
    if (!runId) {
      return;
    }
    try {
      await stopRun(runId, sessionId);
      try {
        const latestStatus = await getRunStatus(runId, sessionId);
        setRunStatus(latestStatus);
      } catch {
        // Polling loop will reconcile status if this immediate refresh fails.
      }
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
      const payload = await applyManualDecision({
        dataset_key: config.datasetKey,
        question_id: activeQuestion.id,
        model,
        status
      });
      const updatedResult = payload.result;
      setSavedResultMeta((prev) => ({
        ...prev,
        [model]: buildSavedResultMeta(updatedResult)
      }));
      setResponses((prev) => ({
        ...prev,
        [model]: String(updatedResult.response ?? prev[model] ?? "")
      }));
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
                <span className={statusBadgeClassName(stateLabel)}>{stateLabel}</span>
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
              <div className="flex flex-wrap items-center gap-2">
                <button
                  className="focus-ring rounded-ui border border-border px-3 py-2 text-sm"
                  onClick={() => handleQuestionNavigation(questions[Math.max(0, questionIndex - 1)].id)}
                  disabled={questionIndex <= 0 || navigatorLocked}
                >
                  Previous
                </button>
                <span className="text-sm text-muted">
                  {questionIndex + 1} / {questions.length}
                </span>
                <button
                  className="focus-ring rounded-ui border border-border px-3 py-2 text-sm"
                  onClick={() => handleQuestionNavigation(questions[Math.min(questions.length - 1, questionIndex + 1)].id)}
                  disabled={questionIndex >= questions.length - 1 || navigatorLocked}
                >
                  Next
                </button>
                <button
                  className="focus-ring rounded-ui bg-primary px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleStart()}
                  disabled={!canStart || navigatorLocked}
                >
                  {isStarting ? "Sending..." : "Send"}
                </button>
                <button
                  className="focus-ring rounded-ui border border-border bg-white px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={handleStop}
                  disabled={!runId || !runInProgress}
                >
                  Stop
                </button>
              </div>
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
          {selectedModels.map((model) => {
            const responseText = responses[model] ?? "";
            const statusEntry = runStatus?.entries.find((entry) => entry.model === model);
            const persistedMeta = savedResultMeta[model];
            const statusElapsedMs = typeof statusEntry?.elapsed_ms === "number" ? statusEntry.elapsed_ms : undefined;
            const liveElapsedMs = runStartedAtMs !== null ? Math.max(0, liveClockMs - runStartedAtMs) : undefined;
            const completedElapsedMs = completedEntryElapsedMs[model];
            const modelIsInActiveRun = activeRunModels.includes(model);
            const entryInProgress = statusEntry
              ? statusEntry.running && !statusEntry.completed
              : runInProgress && modelIsInActiveRun;
            const durationMs = typeof completedElapsedMs === "number"
              ? completedElapsedMs
              : entryInProgress
              ? Math.max(statusElapsedMs ?? 0, liveElapsedMs ?? 0)
              : statusElapsedMs ?? persistedMeta?.responseTimeMs;
            const durationText = formatElapsedSeconds(durationMs);
            const generatedTokens =
              typeof statusEntry?.generated_tokens === "number"
                ? Number(statusEntry.generated_tokens)
                : persistedMeta?.generatedTokens ?? estimateTokenCount(responseText);
            const generatedTokensEstimated =
              typeof statusEntry?.generated_tokens === "number"
                ? false
                : persistedMeta?.generatedTokensEstimated ?? true;
            const eventLabel = statusEntry?.event ?? (runInProgress && modelIsInActiveRun ? "generating" : persistedMeta?.eventLabel ?? "idle");
            const evaluationLabel = persistedMeta?.evaluationLabel ?? (responseText.trim() ? "Pending" : "-");
            const evaluationMethodLabel = persistedMeta?.evaluationMethodLabel ?? (responseText.trim() ? "Pending" : "-");

            return (
            <article key={model} className="rounded-ui border border-border bg-white p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-semibold">{model}</h3>
                  <span className={statusBadgeClassName(evaluationLabel)}>
                    Evaluation: {evaluationLabel}
                  </span>
                  <span className={neutralBadgeClassName()}>
                    Evaluation Method: {evaluationMethodLabel}
                  </span>
                </div>
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
                <div className="ml-auto flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span className={statusBadgeClassName(eventLabel)}>{eventLabel}</span>
                  <span>Duration: {durationText}</span>
                  <span>Tokens: {generatedTokens}{generatedTokensEstimated ? " (est.)" : ""}</span>
                </div>
              </div>
              {responseFormat === "plain" ? (
                <textarea
                  readOnly
                  value={responseText}
                  className="font-log focus-ring min-h-32 w-full rounded-ui border border-border bg-slate-50 px-3 py-2 text-xs"
                />
              ) : (
                <div
                  className="min-h-32 rounded-ui border border-border bg-slate-50 px-3 py-2 text-xs leading-6"
                  dangerouslySetInnerHTML={{ __html: markdownToSafeHtml(responseText) }}
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
          );})}
        </div>
      </Card>
    </div>
  );
}
