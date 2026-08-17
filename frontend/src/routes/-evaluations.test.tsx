import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./evaluations";
import {
  getEvaluationResults,
  getEvaluationRuns,
  getEvaluationSummary,
  getGroundTruthEvaluationResults,
  getRetrievalEvaluationResults,
} from "@/lib/rag-client";
import type {
  EvaluationDashboardSummary,
  EvaluationResultList,
  EvaluationRunList,
  GroundTruthEvaluationList,
  RetrievalEvaluationList,
} from "@/lib/rag-types";

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/rag-client", () => ({
  getEvaluationResults: vi.fn(),
  getEvaluationRuns: vi.fn(),
  getEvaluationSummary: vi.fn(),
  getGroundTruthEvaluationResults: vi.fn(),
  getRetrievalEvaluationResults: vi.fn(),
}));

const emptySummary: EvaluationDashboardSummary = {
  total_runs: 0,
  completed_runs: 0,
  failed_runs: 0,
  total_results: 0,
  average_score: null,
  unsupported_claim_rate: 0,
  average_by_run_kind: [],
  metric_averages: [],
};

const populatedSummary: EvaluationDashboardSummary = {
  total_runs: 2,
  completed_runs: 1,
  failed_runs: 1,
  total_results: 1,
  average_score: 4.8,
  unsupported_claim_rate: 0,
  average_by_run_kind: [
    {
      run_kind: "agentic",
      average_score: 4.8,
      result_count: 1,
      unsupported_claim_count: 0,
    },
  ],
  metric_averages: [
    { metric: "faithfulness", source_type: null, average_score: 5, result_count: 2 },
    { metric: "citation_precision", source_type: null, average_score: 4.5, result_count: 2 },
    { metric: "presentation_quality", source_type: null, average_score: 4, result_count: 2 },
  ],
};

const runList: EvaluationRunList = {
  runs: [
    {
      evaluation_run_id: "eval-run-1",
      source_type: "monitored_runs",
      source_label: "monitored-runs",
      context_labels: ["repo_deep_research"],
      judge_model: "gpt-5.1",
      status: "completed",
      started_at: "2026-08-11T12:00:00Z",
      completed_at: "2026-08-11T12:01:00Z",
      error_message: null,
      result_count: 1,
      average_score: 4.8,
      unsupported_claim_count: 0,
    },
  ],
};

const resultList: EvaluationResultList = {
  results: [
    {
      result_id: "result-1",
      evaluation_run_id: "eval-run-1",
      source_type: "monitored_runs",
      source_label: "monitored-runs",
      context_label: "repo_deep_research",
      repository_name: "repo_deep_research",
      branch: "dev",
      commit_hash: "abc123",
      record_id: null,
      request_id: "request-1",
      run_kind: "agentic",
      question: "Which modules changed for answer evaluation?",
      answer_correctness: null,
      faithfulness: 5,
      citation_precision: 5,
      reference_coverage: null,
      answer_relevance: 5,
      presentation_quality: 4,
      average_score: 4.8,
      unsupported_claim_count: 0,
      feedback_useful: 1,
      feedback_not_useful: 0,
      latency_ms_total: 1400,
      total_estimated_cost_usd: "0.012",
      notes: "Grounded.",
      created_at: "2026-08-11T12:02:00Z",
      answer_evidence: [
        {
          evidence_id: "E29",
          path: "app/services/file_reader.py",
          start_line: 22,
          end_line: 35,
          symbol: "_file_type_from_filename",
          score: 0.91,
          reason: "Maps filename suffixes to supported file types.",
          content: "def _file_type_from_filename(filename): ...",
        },
      ],
    },
    {
      result_id: "result-2",
      evaluation_run_id: "eval-run-1",
      source_type: "monitored_runs",
      source_label: "monitored-runs",
      context_label: "repo_deep_research",
      repository_name: "repo_deep_research",
      branch: "dev",
      commit_hash: "abc123",
      record_id: null,
      request_id: "request-2",
      run_kind: "direct",
      question: "Where are answer snapshots stored?",
      answer_correctness: null,
      faithfulness: 4,
      citation_precision: 4,
      reference_coverage: null,
      answer_relevance: 4,
      presentation_quality: 4,
      average_score: 4,
      unsupported_claim_count: 0,
      feedback_useful: 0,
      feedback_not_useful: 0,
      latency_ms_total: 1200,
      total_estimated_cost_usd: "0.006",
      notes: "Older snapshot without captured content.",
      created_at: "2026-08-11T12:03:00Z",
      answer_evidence: [
        {
          evidence_id: "E7",
          path: "src/repo_research/recording_store.py",
          start_line: 620,
          end_line: 648,
          symbol: null,
          score: 0.84,
          reason: "Defines persisted answer snapshot storage.",
        },
      ],
    },
  ],
};

const groundTruthEvaluationList: GroundTruthEvaluationList = {
  results: [
    {
      dataset: "eval/held_out.json",
      source_label: "datapeek held-out answer comparison",
      run_kind: "direct",
      record_count: 15,
      answer_correctness: 2.667,
      faithfulness: 4.3,
      citation_precision: 4.667,
      reference_coverage: 2.267,
      answer_relevance: 4.167,
      presentation_quality: 4.133,
      unsupported_claim_count: 20,
      unsupported_claim_rate: 0.733,
      average_latency_ms: 16600,
      total_estimated_cost_usd: "0.0518",
      measured_at: "2026-08-16T00:00:00Z",
    },
    {
      dataset: "eval/held_out.json",
      source_label: "datapeek held-out answer comparison",
      run_kind: "agentic",
      record_count: 15,
      answer_correctness: 3.867,
      faithfulness: 4.7,
      citation_precision: 4.733,
      reference_coverage: 3.667,
      answer_relevance: 4.4,
      presentation_quality: 4.267,
      unsupported_claim_count: 12,
      unsupported_claim_rate: 0.533,
      average_latency_ms: 116700,
      total_estimated_cost_usd: "0.1400",
      measured_at: "2026-08-16T00:00:00Z",
    },
  ],
};

const retrievalEvaluationList: RetrievalEvaluationList = {
  results: [
    {
      dataset: "Held-out",
      mode: "dense",
      source_label: "legacy self-repo held-out smoke",
      limit: 5,
      record_count: 15,
      file_hit_rate: 0.456,
      file_mrr: 0.313,
      file_recall: 0.311,
      file_precision: 0.2,
      symbol_hit_rate: 0.4,
      selected: true,
      measured_at: "2026-08-13T00:00:00Z",
    },
    {
      dataset: "Development",
      mode: "dense",
      source_label: "repo_deep_research development retrieval",
      limit: 5,
      record_count: 15,
      file_hit_rate: 0.733,
      file_mrr: 0.528,
      file_recall: 0.339,
      file_precision: 0.24,
      symbol_hit_rate: 0.267,
      selected: true,
      measured_at: "2026-08-14T00:00:00Z",
    },
    {
      dataset: "Datapeek held-out",
      mode: "dense",
      source_label: "datapeek held-out retrieval",
      limit: 5,
      record_count: 15,
      file_hit_rate: 0.8,
      file_mrr: 0.602,
      file_recall: 0.542,
      file_precision: 0.319,
      symbol_hit_rate: 0.6,
      selected: true,
      measured_at: "2026-08-14T00:00:00Z",
    },
    {
      dataset: "Datapeek held-out",
      mode: "hybrid",
      source_label: "datapeek held-out retrieval",
      limit: 5,
      record_count: 15,
      file_hit_rate: 0.867,
      file_mrr: 0.544,
      file_recall: 0.529,
      file_precision: 0.277,
      symbol_hit_rate: 0.533,
      selected: false,
      measured_at: "2026-08-14T00:00:00Z",
    },
    {
      dataset: "Datapeek held-out",
      mode: "sparse",
      source_label: "datapeek held-out retrieval",
      limit: 5,
      record_count: 15,
      file_hit_rate: 0.667,
      file_mrr: 0.393,
      file_recall: 0.382,
      file_precision: 0.213,
      symbol_hit_rate: 0.467,
      selected: false,
      measured_at: "2026-08-14T00:00:00Z",
    },
  ],
};

function renderEvaluationsRoute() {
  const EvaluationsComponent = Route.options.component as ComponentType;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <EvaluationsComponent />
    </QueryClientProvider>,
  );
}

describe("Evaluations route", () => {
  beforeEach(() => {
    vi.mocked(getEvaluationResults).mockReset();
    vi.mocked(getEvaluationRuns).mockReset();
    vi.mocked(getEvaluationSummary).mockReset();
    vi.mocked(getGroundTruthEvaluationResults).mockReset();
    vi.mocked(getRetrievalEvaluationResults).mockReset();
    vi.mocked(getEvaluationRuns).mockResolvedValue({ runs: [] });
    vi.mocked(getEvaluationResults).mockResolvedValue({ results: [] });
    vi.mocked(getGroundTruthEvaluationResults).mockResolvedValue({ results: [] });
    vi.mocked(getRetrievalEvaluationResults).mockResolvedValue(retrievalEvaluationList);
  });

  it("renders an honest empty state before persisted results exist", async () => {
    vi.mocked(getEvaluationSummary).mockResolvedValue(emptySummary);

    renderEvaluationsRoute();

    expect(await screen.findByText("Search evaluation highlights")).toBeInTheDocument();
    expect(screen.getByText("Production default")).toBeInTheDocument();
    expect(screen.getAllByText("Datapeek held-out").length).toBeGreaterThan(0);
    expect(screen.getAllByText("80%").length).toBeGreaterThan(0);
    expect(screen.queryByText("Held-out")).not.toBeInTheDocument();
    expect(screen.queryByText("46%")).not.toBeInTheDocument();
    expect(screen.getByText("Output quality evaluation")).toBeInTheDocument();
    expect(screen.getByText(/No persisted evaluation results are available/)).toBeInTheDocument();
  });

  it("shows an API error without also claiming there are no results", async () => {
    vi.mocked(getEvaluationSummary).mockRejectedValue({
      title: "Network error",
      detail: "Could not reach the backend.",
    });

    renderEvaluationsRoute();

    expect(await screen.findByRole("alert")).toHaveTextContent("Network error");
    expect(
      screen.queryByText(/No persisted evaluation results are available/),
    ).not.toBeInTheDocument();
  });

  it("renders persisted evaluation summary, charts, runs, and result rows", async () => {
    vi.mocked(getEvaluationSummary).mockResolvedValue(populatedSummary);
    vi.mocked(getEvaluationRuns).mockResolvedValue(runList);
    vi.mocked(getEvaluationResults).mockResolvedValue(resultList);
    vi.mocked(getGroundTruthEvaluationResults).mockResolvedValue(groundTruthEvaluationList);

    renderEvaluationsRoute();

    expect(await screen.findByText("Search evaluation highlights")).toBeInTheDocument();
    expect(screen.getByText("Production default")).toBeInTheDocument();
    expect(screen.getByText("Development")).toBeInTheDocument();
    expect(screen.getAllByText("Datapeek held-out").length).toBeGreaterThan(0);
    expect(screen.queryByText("Held-out")).not.toBeInTheDocument();
    expect(screen.queryByText("46%")).not.toBeInTheDocument();
    expect(screen.getByText("Output quality evaluation")).toBeInTheDocument();
    expect(
      screen.getByText(/These metrics are separate from the search retrieval checks above/),
    ).toBeInTheDocument();
    expect(screen.getByText("Evaluated answers")).toBeInTheDocument();
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Average score").length).toBeGreaterThan(0);
    expect(screen.getAllByText("4.8").length).toBeGreaterThan(0);
    expect(screen.getByText("Unsupported claims")).toBeInTheDocument();
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(screen.getByText("Average score by approach")).toBeInTheDocument();
    expect(screen.getByText("Score distribution by metric")).toBeInTheDocument();
    expect(screen.getByText("Recent feedback versus judge scores")).toBeInTheDocument();
    expect(screen.getByText("Recent quality compared with latency and cost")).toBeInTheDocument();
    expect(screen.getByText("Recent evaluation runs")).toBeInTheDocument();
    expect(screen.getAllByText("Evidence Audit").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Repository or dataset")).toHaveValue("all");
    expect(screen.getAllByText("repo_deep_research").length).toBeGreaterThan(0);
    expect(screen.getByText("Answer reviews")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Ground Truth Assessments (2)" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Post-hoc LLM Review (lowest 2 of 2)" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("eval/held_out.json").length).toBe(2);
    expect(screen.getByText("agentic")).toBeInTheDocument();
    expect(screen.getByText("direct")).toBeInTheDocument();
    expect(
      screen.queryByText("Which modules changed for answer evaluation?"),
    ).not.toBeInTheDocument();
  });

  it("switches between ground truth and post-hoc review tables", async () => {
    const user = userEvent.setup();
    vi.mocked(getEvaluationSummary).mockResolvedValue(populatedSummary);
    vi.mocked(getEvaluationRuns).mockResolvedValue(runList);
    vi.mocked(getEvaluationResults).mockResolvedValue(resultList);
    vi.mocked(getGroundTruthEvaluationResults).mockResolvedValue(groundTruthEvaluationList);

    renderEvaluationsRoute();

    expect((await screen.findAllByText("eval/held_out.json")).length).toBe(2);
    await user.click(screen.getByRole("tab", { name: "Post-hoc LLM Review (lowest 2 of 2)" }));

    expect(screen.getByText("Which modules changed for answer evaluation?")).toBeInTheDocument();
    expect(screen.queryAllByText("eval/held_out.json")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Open evidence E29" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open evidence E7" })).toBeInTheDocument();
    expect(screen.getByText("metadata only")).toBeInTheDocument();
  });

  it("opens evidence details from an evaluation result evidence id", async () => {
    const user = userEvent.setup();
    vi.mocked(getEvaluationSummary).mockResolvedValue(populatedSummary);
    vi.mocked(getEvaluationRuns).mockResolvedValue(runList);
    vi.mocked(getEvaluationResults).mockResolvedValue(resultList);
    vi.mocked(getGroundTruthEvaluationResults).mockResolvedValue(groundTruthEvaluationList);

    renderEvaluationsRoute();

    await user.click(
      await screen.findByRole("tab", { name: "Post-hoc LLM Review (lowest 2 of 2)" }),
    );
    await user.click(await screen.findByRole("button", { name: "Open evidence E29" }));

    expect(screen.getByRole("dialog", { name: "Evidence detail" })).toBeInTheDocument();
    expect(screen.getByText("app/services/file_reader.py")).toBeInTheDocument();
    expect(screen.getByText("_file_type_from_filename")).toBeInTheDocument();
    expect(screen.getByText("def _file_type_from_filename(filename): ...")).toBeInTheDocument();
  });

  it("opens metadata-only evidence details for older monitored snapshots", async () => {
    const user = userEvent.setup();
    vi.mocked(getEvaluationSummary).mockResolvedValue(populatedSummary);
    vi.mocked(getEvaluationRuns).mockResolvedValue(runList);
    vi.mocked(getEvaluationResults).mockResolvedValue(resultList);
    vi.mocked(getGroundTruthEvaluationResults).mockResolvedValue(groundTruthEvaluationList);

    renderEvaluationsRoute();

    await user.click(
      await screen.findByRole("tab", { name: "Post-hoc LLM Review (lowest 2 of 2)" }),
    );
    await user.click(await screen.findByRole("button", { name: "Open evidence E7" }));

    expect(screen.getByRole("dialog", { name: "Evidence detail" })).toBeInTheDocument();
    expect(screen.getByText("src/repo_research/recording_store.py")).toBeInTheDocument();
    expect(
      screen.getByText("No content snippet captured for this older recorded answer."),
    ).toBeInTheDocument();
  });
});
