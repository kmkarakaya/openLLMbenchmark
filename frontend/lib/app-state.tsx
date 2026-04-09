"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type BenchmarkMode = "single" | "pair";

export type BenchmarkConfig = {
  datasetKey: string;
  mode: BenchmarkMode;
  model1: string;
  model2: string;
  systemPrompt: string;
  questionId: string;
};

export type RunHistoryItem = {
  runId: number;
  datasetKey: string;
  models: string[];
  startedAt: string;
  status: "started" | "running" | "completed" | "interrupted" | "error" | "stopped";
};

type AppStateValue = {
  sessionId: string;
  config: BenchmarkConfig;
  setConfig: (patch: Partial<BenchmarkConfig>) => void;
  ollamaApiKey: string;
  ollamaApiKeyHydrated: boolean;
  setOllamaApiKey: (value: string) => void;
  clearOllamaApiKey: () => void;
  runHistory: RunHistoryItem[];
  addRunHistory: (entry: RunHistoryItem) => void;
  updateRunHistory: (runId: number, status: RunHistoryItem["status"]) => void;
};

const OLLAMA_API_KEY_SESSION_STORAGE_KEY = "openllmbenchmark.ollamaApiKey";

const DEFAULT_CONFIG: BenchmarkConfig = {
  datasetKey: "default_tr",
  mode: "single",
  model1: "",
  model2: "",
  systemPrompt: "",
  questionId: ""
};

const AppStateContext = createContext<AppStateValue | null>(null);

function newSessionId(): string {
  const raw = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return `ui-${raw}`;
}

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [sessionId] = useState<string>(newSessionId);
  const [config, setConfigState] = useState<BenchmarkConfig>(DEFAULT_CONFIG);
  const [ollamaApiKey, setOllamaApiKeyState] = useState("");
  const [ollamaApiKeyHydrated, setOllamaApiKeyHydrated] = useState(false);
  const [runHistory, setRunHistory] = useState<RunHistoryItem[]>([]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    setOllamaApiKeyState(window.sessionStorage.getItem(OLLAMA_API_KEY_SESSION_STORAGE_KEY) ?? "");
    setOllamaApiKeyHydrated(true);
  }, []);

  useEffect(() => {
    if (!ollamaApiKeyHydrated || typeof window === "undefined") {
      return;
    }
    if (ollamaApiKey.trim()) {
      window.sessionStorage.setItem(OLLAMA_API_KEY_SESSION_STORAGE_KEY, ollamaApiKey.trim());
      return;
    }
    window.sessionStorage.removeItem(OLLAMA_API_KEY_SESSION_STORAGE_KEY);
  }, [ollamaApiKey, ollamaApiKeyHydrated]);

  const setConfig = (patch: Partial<BenchmarkConfig>) => {
    setConfigState((prev) => ({ ...prev, ...patch }));
  };

  const setOllamaApiKey = (value: string) => {
    setOllamaApiKeyState(value.trim());
  };

  const clearOllamaApiKey = () => {
    setOllamaApiKeyState("");
  };

  const addRunHistory = (entry: RunHistoryItem) => {
    setRunHistory((prev) => [entry, ...prev].slice(0, 10));
  };

  const updateRunHistory = (runId: number, status: RunHistoryItem["status"]) => {
    setRunHistory((prev) =>
      prev.map((item) => {
        if (item.runId !== runId) {
          return item;
        }
        return { ...item, status };
      })
    );
  };

  const value = useMemo<AppStateValue>(
    () => ({
      sessionId,
      config,
      setConfig,
      ollamaApiKey,
      ollamaApiKeyHydrated,
      setOllamaApiKey,
      clearOllamaApiKey,
      runHistory,
      addRunHistory,
      updateRunHistory
    }),
    [sessionId, config, ollamaApiKey, ollamaApiKeyHydrated, runHistory]
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateValue {
  const ctx = useContext(AppStateContext);
  if (!ctx) {
    throw new Error("useAppState must be used inside AppStateProvider");
  }
  return ctx;
}
