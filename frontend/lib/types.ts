export type DatasetOption = {
  key: string;
  label: string;
  is_default: boolean;
  signature: string;
  question_count: number;
};

export type BenchmarkQuestion = {
  id: string;
  prompt: string;
  expected_answer: string;
  category: string;
  hardness_level?: string;
  why_prepared?: string;
};

export type RunStartResponse = {
  run_id: number;
  status: "started";
  session_id: string;
};

export type RunEntryStatus = {
  model: string;
  running: boolean;
  completed: boolean;
  interrupted: boolean;
  error: string;
  event: string;
  elapsed_ms: number;
};

export type RunStatusResponse = {
  run_id: number;
  session_id: string;
  dataset_key: string;
  question_id: string;
  running: boolean;
  completed: boolean;
  interrupted: boolean;
  error: string;
  entries: RunEntryStatus[];
};

export type ResultsResponse = {
  dataset_key: string;
  results: Array<Record<string, unknown>>;
  metrics: Array<Record<string, unknown>>;
  matrix: Array<Record<string, unknown>>;
};

export type SloStatus = {
  window_minutes: number;
  sse_disconnect_error_rate: number;
  run_completion_success_rate: number;
  p95_chunk_gap_ms: number;
  breached: boolean;
  evaluated_at: string;
};

export type DatasetTemplateRow = {
  id: string;
  question: string;
  expected_answer: string;
  topic: string;
  hardness_level: string;
  why_prepared: string;
};
