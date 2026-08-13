export type QuestionMode = "auto" | "locate" | "flow" | "change";
export type RetrievalMode = "dense" | "sparse" | "hybrid";
export type ResearchKind = "direct" | "agentic";

export interface RagRequest {
  question: string;
  mode: QuestionMode;
  retrieval_mode: RetrievalMode;
  limit: number;
  repository_path?: string;
  session_id?: string;
}

export interface ResearchBudget {
  max_searches: number;
  max_file_reads: number;
  max_total_tool_calls: number;
}

export interface ResearchRequest {
  question: string;
  mode: QuestionMode;
  retrieval_mode: RetrievalMode;
  retrieval_limit: number;
  repository_path?: string;
  budget?: ResearchBudget;
  session_id?: string;
}

export interface RepositoryIdentity {
  name: string;
  root_path: string;
  branch: string;
  commit_hash: string;
}

export interface IngestionIssue {
  path: string;
  error_type: string;
  message: string;
}

export interface RepositoryIngestRequest {
  repository_address: string;
}

export interface IngestSummary {
  repository: RepositoryIdentity;
  indexed_chunks: number;
  skipped_files: IngestionIssue[];
  index_updated: boolean;
}

export interface BackendHealth {
  status: string;
  qdrant: boolean;
}

export interface EvidenceItem {
  evidence_id: string;
  path: string;
  start_line: number | null;
  end_line: number | null;
  symbol: string | null;
  score: number;
  reason: string;
  content?: string | null;
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
  research_steps?: ResearchStep[] | null;
}

export interface ResearchStep {
  sequence: number;
  action: string;
  rationale: string;
  evidence_ids: string[];
}

export type ResearchAnswer = RagAnswer;

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
  session_id: string;
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

export interface ResearchRunResult {
  answer: ResearchAnswer | null;
  trace: RagTrace | null;
}

export type ResearchResult = RagRunResult | ResearchRunResult;

export interface FeedbackRequest {
  session_id?: string;
  request_id?: string;
  run_kind?: ResearchKind;
  useful: boolean;
  comment?: string;
}

export interface FeedbackEvent {
  feedback_id: string;
  session_id: string;
  request_id: string | null;
  run_kind: ResearchKind | null;
  useful: boolean;
  comment: string | null;
  submitted_at: string;
}

export interface RunKindCount {
  run_kind: ResearchKind;
  count: number;
}

export interface LatencyByRunKind {
  run_kind: ResearchKind;
  average_latency_ms: number;
}

export interface RetrievalVolumeSummary {
  retrieved_chunk_count: number;
  unique_file_count: number;
}

export interface ModelUsageSummary {
  provider: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost_usd: number | string | null;
}

export interface FeedbackUsefulSummary {
  useful: number;
  not_useful: number;
}

export interface ErrorCountSummary {
  error_type: string;
  count: number;
}

export interface MonitoringSummary {
  total_runs: number;
  runs_by_kind: RunKindCount[];
  average_latency_by_kind: LatencyByRunKind[];
  retrieval_volume: RetrievalVolumeSummary;
  model_usage_by_model: ModelUsageSummary[];
  feedback: FeedbackUsefulSummary;
  errors_by_type: ErrorCountSummary[];
}

export type MonitoringFeedbackFilter = "all" | "useful" | "not_useful" | "none";

export interface MonitoringRunSummary {
  request_id: string;
  session_id: string;
  run_kind: ResearchKind;
  started_at: string;
  completed_at: string;
  repository_name: string;
  branch: string;
  commit_hash: string;
  question_mode: QuestionMode;
  retrieval_mode: RetrievalMode;
  retrieved_chunk_count: number;
  unique_file_count: number;
  evidence_count: number;
  latency_ms_total: number;
  latency_ms_retrieval: number;
  latency_ms_model: number | null;
  tool_call_count: number;
  insufficient_evidence: boolean;
  has_error: boolean;
  feedback_useful: number;
  feedback_not_useful: number;
  total_estimated_cost_usd: number | string | null;
}

export interface MonitoringRunFeedback {
  feedback_id: string;
  useful: boolean;
  comment: string | null;
  submitted_at: string;
}

export interface MonitoringRunDetail extends MonitoringRunSummary {
  repository_id: string;
  retrieval_limit: number;
  error_type: string | null;
  error_message: string | null;
  model_usage: ModelUsage[];
  feedback_events: MonitoringRunFeedback[];
}

export interface MonitoringRunList {
  runs: MonitoringRunSummary[];
}

export interface MonitoringRunListParams {
  limit?: number;
  run_kind?: ResearchKind;
  repository_name?: string;
  has_error?: boolean;
  feedback?: MonitoringFeedbackFilter;
}

export type EvaluationSourceType = "dataset" | "monitored_runs";
export type EvaluationRunStatus = "pending" | "running" | "completed" | "failed";

export interface EvaluationMetricAverage {
  metric: string;
  source_type: EvaluationSourceType | null;
  average_score: number;
  result_count: number;
}

export interface EvaluationRunKindAverage {
  run_kind: ResearchKind | null;
  average_score: number;
  result_count: number;
  unsupported_claim_count: number;
}

export interface EvaluationDashboardSummary {
  total_runs: number;
  completed_runs: number;
  failed_runs: number;
  total_results: number;
  average_score: number | null;
  unsupported_claim_rate: number;
  average_by_run_kind: EvaluationRunKindAverage[];
  metric_averages: EvaluationMetricAverage[];
}

export interface RetrievalEvaluationSummary {
  dataset: string;
  mode: RetrievalMode;
  source_label: string;
  limit: number;
  record_count: number;
  file_hit_rate: number;
  file_mrr: number;
  file_recall: number;
  file_precision: number;
  symbol_hit_rate: number;
  selected: boolean;
  measured_at: string;
}

export interface RetrievalEvaluationList {
  results: RetrievalEvaluationSummary[];
}

export interface EvaluationRunSummary {
  evaluation_run_id: string;
  source_type: EvaluationSourceType;
  source_label: string;
  context_labels: string[];
  judge_model: string;
  status: EvaluationRunStatus;
  started_at: string;
  completed_at: string | null;
  error_message: string | null;
  result_count: number;
  average_score: number | null;
  unsupported_claim_count: number;
}

export interface EvaluationRunList {
  runs: EvaluationRunSummary[];
}

export interface EvaluationResultSummary {
  result_id: string;
  evaluation_run_id: string;
  source_type: EvaluationSourceType;
  source_label: string;
  context_label: string;
  repository_name: string | null;
  branch: string | null;
  commit_hash: string | null;
  record_id: string | null;
  request_id: string | null;
  run_kind: ResearchKind | null;
  question: string;
  answer_correctness: number | null;
  faithfulness: number | null;
  citation_precision: number | null;
  reference_coverage: number | null;
  answer_relevance: number | null;
  presentation_quality: number | null;
  average_score: number;
  unsupported_claim_count: number;
  feedback_useful: number;
  feedback_not_useful: number;
  latency_ms_total: number | null;
  total_estimated_cost_usd: number | string | null;
  notes: string;
  created_at: string;
  answer_evidence?: EvidenceItem[];
}

export interface EvaluationResultList {
  results: EvaluationResultSummary[];
}

export interface EvaluationRunListParams {
  limit?: number;
  source_type?: EvaluationSourceType;
  status?: EvaluationRunStatus;
}

export interface EvaluationResultListParams {
  limit?: number;
  source_type?: EvaluationSourceType;
  run_kind?: ResearchKind;
  context_label?: string;
}

export interface ApiErrorShape {
  title: string;
  detail: string;
  status?: number;
}
