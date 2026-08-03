export type QuestionMode = "auto" | "locate" | "flow" | "change";
export type RetrievalMode = "dense" | "sparse" | "hybrid";

export interface RagRequest {
  question: string;
  mode: QuestionMode;
  retrieval_mode: RetrievalMode;
  limit: number;
  repository_path?: string;
}

export interface EvidenceItem {
  evidence_id: string;
  path: string;
  start_line: number;
  end_line: number;
  symbol: string | null;
  score: number;
  reason: string;
}

export interface ChangeTarget {
  path: string;
  symbol: string | null;
  reason: string;
  evidence_ids: string[];
}

export interface RagAnswer {
  question: string;
  mode: QuestionMode;
  summary: string | null;
  implementation_flow: string[] | null;
  evidence: EvidenceItem[] | null;
  relevant_files: string[] | null;
  relevant_symbols: string[] | null;
  change_targets: ChangeTarget[] | null;
  risks: string[] | null;
  confidence: number | string | null;
  unresolved_questions: string[] | null;
  insufficient_evidence: boolean | null;
}

export interface ModelUsage {
  provider?: string | null;
  model?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
  cached_input_tokens?: number | null;
  reasoning_tokens?: number | null;
  estimated_cost_usd?: number | string | null;
  pricing_source?: string | null;
  pricing_version?: string | null;
  [key: string]: unknown;
}

export interface RagTrace {
  request_id: string;
  started_at?: string | null;
  completed_at?: string | null;
  repository_id?: string | null;
  repository_name: string;
  branch: string;
  commit_hash: string;
  question_mode: string;
  retrieval_mode: string;
  retrieval_limit: number;
  retrieved_chunk_count: number;
  unique_file_count: number;
  evidence_ids?: string[] | null;
  latency_ms_total: number;
  latency_ms_retrieval: number;
  latency_ms_model: number | null;
  model_usage: ModelUsage[];
  total_estimated_cost_usd: number | string | null;
  insufficient_evidence: boolean;
  error_type: string | null;
  error_message: string | null;
  tool_call_count: number;
}

export interface RagRunResult {
  answer: RagAnswer | null;
  trace: RagTrace | null;
}

export interface ApiErrorShape {
  title: string;
  detail: string;
  status?: number;
}
