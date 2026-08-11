import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getBackendHealth,
  getEvaluationResults,
  getEvaluationRuns,
  getEvaluationSummary,
  getMonitoringRunDetail,
  getMonitoringRuns,
  getMonitoringSummary,
  ingestRepository,
  runAgenticResearch,
  runRagQuery,
  submitFeedback,
} from "./rag-client";
import type {
  EvaluationDashboardSummary,
  EvaluationResultList,
  EvaluationRunList,
  IngestSummary,
  MonitoringRunDetail,
  MonitoringRunList,
  MonitoringRunSummary,
  MonitoringSummary,
  RagRunResult,
  ResearchRunResult,
} from "./rag-types";

const okResult: RagRunResult = {
  answer: {
    question: "Where is config validated?",
    mode: "locate",
    summary: "Settings validates runtime config.",
    implementation_flow: [],
    evidence: [],
    relevant_files: ["src/repo_research/config.py"],
    relevant_symbols: ["Settings"],
    change_targets: [],
    risks: [],
    confidence: 0.8,
    unresolved_questions: [],
    insufficient_evidence: false,
  },
  trace: {
    request_id: "req-1",
    session_id: "session-1",
    repository_name: "repo_deep_research",
    branch: "dev",
    commit_hash: "abc123",
    question_mode: "locate",
    retrieval_mode: "hybrid",
    retrieval_limit: 5,
    retrieved_chunk_count: 1,
    unique_file_count: 1,
    latency_ms_total: 10,
    latency_ms_retrieval: 3,
    latency_ms_model: 7,
    model_usage: [],
    total_estimated_cost_usd: null,
    insufficient_evidence: false,
    error_type: null,
    error_message: null,
    tool_call_count: 0,
  },
};

const agenticResult: ResearchRunResult = {
  ...okResult,
  answer: {
    ...okResult.answer!,
    mode: "change",
    research_steps: [
      {
        sequence: 1,
        action: "Search repository evidence.",
        rationale: "Find code that handles feedback.",
        evidence_ids: ["E1"],
      },
    ],
  },
  trace: {
    ...okResult.trace!,
    question_mode: "change",
    tool_call_count: 3,
  },
};

const ingestSummary: IngestSummary = {
  repository: {
    name: "sample-repo",
    root_path: "/tmp/sample-repo",
    branch: "main",
    commit_hash: "abc123",
  },
  indexed_chunks: 12,
  skipped_files: [],
  index_updated: true,
};

const monitoringSummary: MonitoringSummary = {
  total_runs: 1,
  runs_by_kind: [{ run_kind: "direct", count: 1 }],
  average_latency_by_kind: [{ run_kind: "direct", average_latency_ms: 10 }],
  retrieval_volume: { retrieved_chunk_count: 1, unique_file_count: 1 },
  model_usage_by_model: [],
  feedback: { useful: 1, not_useful: 0 },
  errors_by_type: [],
};

const monitoringRunSummary: MonitoringRunSummary = {
  request_id: "req-1",
  session_id: "session-1",
  run_kind: "agentic",
  started_at: "2026-08-07T12:00:00Z",
  completed_at: "2026-08-07T12:00:02Z",
  repository_name: "repo_deep_research",
  branch: "main",
  commit_hash: "abcdef123456",
  question_mode: "change",
  retrieval_mode: "hybrid",
  retrieved_chunk_count: 12,
  unique_file_count: 5,
  evidence_count: 4,
  latency_ms_total: 2000,
  latency_ms_retrieval: 200,
  latency_ms_model: 1500,
  tool_call_count: 3,
  insufficient_evidence: false,
  has_error: false,
  feedback_useful: 1,
  feedback_not_useful: 0,
  total_estimated_cost_usd: "0.012",
};

const monitoringRuns: MonitoringRunList = {
  runs: [monitoringRunSummary],
};

const monitoringRunDetail: MonitoringRunDetail = {
  ...monitoringRunSummary,
  repository_id: "repo-id",
  retrieval_limit: 5,
  error_type: null,
  error_message: null,
  model_usage: [
    {
      provider: "openai",
      model: "gpt-5-mini",
      input_tokens: 10,
      output_tokens: 5,
      total_tokens: 15,
      estimated_cost_usd: "0.012",
    },
  ],
  feedback_events: [
    {
      feedback_id: "feedback-1",
      useful: true,
      comment: "Grounded enough.",
      submitted_at: "2026-08-07T12:05:00Z",
    },
  ],
};

const evaluationSummary: EvaluationDashboardSummary = {
  total_runs: 1,
  completed_runs: 1,
  failed_runs: 0,
  total_results: 2,
  average_score: 4.4,
  unsupported_claim_rate: 0.5,
  average_by_run_kind: [
    {
      run_kind: "agentic",
      average_score: 4.5,
      result_count: 1,
      unsupported_claim_count: 1,
    },
  ],
  metric_averages: [
    { metric: "faithfulness", source_type: null, average_score: 5, result_count: 2 },
  ],
};

const evaluationRuns: EvaluationRunList = {
  runs: [
    {
      evaluation_run_id: "eval-run-1",
      source_type: "monitored_runs",
      source_label: "monitored-runs",
      judge_model: "gpt-5.1",
      status: "completed",
      started_at: "2026-08-11T12:00:00Z",
      completed_at: "2026-08-11T12:01:00Z",
      error_message: null,
      result_count: 2,
      average_score: 4.4,
      unsupported_claim_count: 1,
    },
  ],
};

const evaluationResults: EvaluationResultList = {
  results: [
    {
      result_id: "result-1",
      evaluation_run_id: "eval-run-1",
      source_type: "monitored_runs",
      source_label: "monitored-runs",
      record_id: null,
      request_id: "req-1",
      run_kind: "agentic",
      question: "Which modules changed?",
      answer_correctness: null,
      faithfulness: 5,
      citation_precision: 5,
      reference_coverage: null,
      answer_relevance: 4,
      presentation_quality: 4,
      average_score: 4.4,
      unsupported_claim_count: 0,
      feedback_useful: 1,
      feedback_not_useful: 0,
      latency_ms_total: 1200,
      total_estimated_cost_usd: "0.012",
      notes: "Grounded.",
      created_at: "2026-08-11T12:02:00Z",
      answer_evidence: [
        {
          evidence_id: "E1",
          path: "src/repo_research/answer_evaluation.py",
          start_line: 10,
          end_line: 20,
          symbol: "evaluate_answers",
          score: 0.9,
          reason: "Shows the evaluator entrypoint.",
          content: "def evaluate_answers(): ...",
        },
      ],
    },
  ],
};

describe("runRagQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts a RAG request to the backend /rag endpoint", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(okResult), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      runRagQuery(
        "http://localhost:8000///",
        {
          question: "Where is config validated?",
          mode: "locate",
          retrieval_mode: "hybrid",
          limit: 5,
          session_id: "session-1",
        },
        controller.signal,
      ),
    ).resolves.toEqual(okResult);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/rag",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "Where is config validated?",
          mode: "locate",
          retrieval_mode: "hybrid",
          limit: 5,
          session_id: "session-1",
        }),
        signal: controller.signal,
      }),
    );
  });

  it("posts an agentic research request to the backend /research endpoint", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(agenticResult), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      runAgenticResearch(
        "http://localhost:8000///",
        {
          question: "Which modules must change for feedback?",
          mode: "change",
          retrieval_mode: "dense",
          retrieval_limit: 5,
          session_id: "session-1",
        },
        controller.signal,
      ),
    ).resolves.toEqual(agenticResult);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/research",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "Which modules must change for feedback?",
          mode: "change",
          retrieval_mode: "dense",
          retrieval_limit: 5,
          session_id: "session-1",
        }),
        signal: controller.signal,
      }),
    );
  });

  it("posts a repository ingestion request to the backend ingest endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(ingestSummary), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      ingestRepository("http://localhost:8000///", {
        repository_address: "/tmp/sample-repo",
      }),
    ).resolves.toEqual(ingestSummary);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/repositories/ingest",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_address: "/tmp/sample-repo",
        }),
      }),
    );
  });

  it("checks backend health at the configured base URL", async () => {
    const health = { status: "ok", qdrant: true };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(health), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBackendHealth("http://localhost:8000///")).resolves.toEqual(health);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ signal: null }),
    );
  });

  it("posts feedback to the backend feedback endpoint", async () => {
    const event = {
      feedback_id: "feedback-1",
      session_id: "session-1",
      request_id: "req-1",
      run_kind: "direct",
      useful: true,
      comment: "Grounded enough.",
      submitted_at: "2026-08-07T12:00:00Z",
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(event), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      submitFeedback("http://localhost:8000///", {
        session_id: "session-1",
        request_id: "req-1",
        run_kind: "direct",
        useful: true,
        comment: "Grounded enough.",
      }),
    ).resolves.toEqual(event);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/feedback",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: "session-1",
          request_id: "req-1",
          run_kind: "direct",
          useful: true,
          comment: "Grounded enough.",
        }),
      }),
    );
  });

  it("loads monitoring summary from the backend endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(monitoringSummary), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getMonitoringSummary("http://localhost:8000///")).resolves.toEqual(
      monitoringSummary,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/monitoring/summary",
      expect.objectContaining({ signal: null }),
    );
  });

  it("loads monitoring run history with filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(monitoringRuns), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getMonitoringRuns("http://localhost:8000///", {
        limit: 25,
        run_kind: "agentic",
        has_error: false,
        feedback: "useful",
      }),
    ).resolves.toEqual(monitoringRuns);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/monitoring/runs?limit=25&run_kind=agentic&has_error=false&feedback=useful",
      expect.objectContaining({ signal: null }),
    );
  });

  it("loads one monitoring run detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(monitoringRunDetail), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getMonitoringRunDetail("http://localhost:8000///", "req-1")).resolves.toEqual(
      monitoringRunDetail,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/monitoring/runs/req-1",
      expect.objectContaining({ signal: null }),
    );
  });

  it("loads evaluation summary from the backend endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(evaluationSummary), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getEvaluationSummary("http://localhost:8000///")).resolves.toEqual(
      evaluationSummary,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/evaluations/summary",
      expect.objectContaining({ signal: null }),
    );
  });

  it("loads evaluation runs with filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(evaluationRuns), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getEvaluationRuns("http://localhost:8000///", {
        limit: 10,
        source_type: "monitored_runs",
        status: "completed",
      }),
    ).resolves.toEqual(evaluationRuns);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/evaluations/runs?limit=10&source_type=monitored_runs&status=completed",
      expect.objectContaining({ signal: null }),
    );
  });

  it("loads evaluation results with filters", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(evaluationResults), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getEvaluationResults("http://localhost:8000///", {
        limit: 25,
        source_type: "monitored_runs",
        run_kind: "agentic",
      }),
    ).resolves.toEqual(evaluationResults);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/evaluations/results?limit=25&run_kind=agentic&source_type=monitored_runs",
      expect.objectContaining({ signal: null }),
    );
  });

  it("supports a same-origin proxied API base URL", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", qdrant: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBackendHealth("/api")).resolves.toEqual({ status: "ok", qdrant: true });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({ signal: null }),
    );
  });

  it("surfaces FastAPI validation errors without exposing a stack trace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [
              {
                loc: ["body", "limit"],
                msg: "Input should be less than or equal to 20",
              },
            ],
          }),
          { status: 422, statusText: "Unprocessable Entity" },
        ),
      ),
    );

    await expect(
      runRagQuery("http://localhost:8000", {
        question: "Where is config validated?",
        mode: "locate",
        retrieval_mode: "hybrid",
        limit: 21,
      }),
    ).rejects.toMatchObject({
      title: "Backend returned 422 Unprocessable Entity",
      detail: "body.limit: Input should be less than or equal to 20",
      status: 422,
    });
  });

  it("reports network failures with the exact backend URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

    await expect(
      runRagQuery("http://localhost:8000", {
        question: "Where is config validated?",
        mode: "locate",
        retrieval_mode: "hybrid",
        limit: 5,
      }),
    ).rejects.toMatchObject({
      title: "Network error",
      detail: expect.stringContaining("http://localhost:8000/rag"),
    });
  });
});
