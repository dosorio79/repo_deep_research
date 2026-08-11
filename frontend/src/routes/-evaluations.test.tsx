import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./evaluations";
import { getEvaluationResults, getEvaluationRuns, getEvaluationSummary } from "@/lib/rag-client";
import type {
  EvaluationDashboardSummary,
  EvaluationResultList,
  EvaluationRunList,
} from "@/lib/rag-types";

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/rag-client", () => ({
  getEvaluationResults: vi.fn(),
  getEvaluationRuns: vi.fn(),
  getEvaluationSummary: vi.fn(),
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
  total_results: 2,
  average_score: 4.2,
  unsupported_claim_rate: 0.5,
  average_by_run_kind: [
    {
      run_kind: "agentic",
      average_score: 4.8,
      result_count: 1,
      unsupported_claim_count: 0,
    },
    {
      run_kind: "direct",
      average_score: 3.6,
      result_count: 1,
      unsupported_claim_count: 1,
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
      judge_model: "gpt-5.1",
      status: "completed",
      started_at: "2026-08-11T12:00:00Z",
      completed_at: "2026-08-11T12:01:00Z",
      error_message: null,
      result_count: 2,
      average_score: 4.2,
      unsupported_claim_count: 1,
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
      record_id: null,
      request_id: "request-2",
      run_kind: "direct",
      question: "Where is evaluation stored?",
      answer_correctness: null,
      faithfulness: 4,
      citation_precision: 4,
      reference_coverage: null,
      answer_relevance: 4,
      presentation_quality: 3,
      average_score: 3.6,
      unsupported_claim_count: 1,
      feedback_useful: 0,
      feedback_not_useful: 1,
      latency_ms_total: 800,
      total_estimated_cost_usd: "0.006",
      notes: "Missed one caveat.",
      created_at: "2026-08-11T12:03:00Z",
      answer_evidence: [],
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
    vi.mocked(getEvaluationRuns).mockResolvedValue({ runs: [] });
    vi.mocked(getEvaluationResults).mockResolvedValue({ results: [] });
  });

  it("renders an honest empty state before persisted results exist", async () => {
    vi.mocked(getEvaluationSummary).mockResolvedValue(emptySummary);

    renderEvaluationsRoute();

    expect(
      await screen.findByText(/No persisted evaluation results are available/),
    ).toBeInTheDocument();
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

    renderEvaluationsRoute();

    expect(await screen.findByText("Evaluated answers")).toBeInTheDocument();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Average score").length).toBeGreaterThan(0);
    expect(screen.getAllByText("4.2").length).toBeGreaterThan(0);
    expect(screen.getByText("Unsupported claims")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("Average score by approach")).toBeInTheDocument();
    expect(screen.getByText("Score distribution by metric")).toBeInTheDocument();
    expect(screen.getByText("Recent feedback versus judge scores")).toBeInTheDocument();
    expect(screen.getByText("Recent quality compared with latency and cost")).toBeInTheDocument();
    expect(screen.getByText("Recent evaluation runs")).toBeInTheDocument();
    expect(screen.getAllByText("Evidence Audit").length).toBeGreaterThan(0);
    expect(screen.getByText("Lowest-scoring loaded answers")).toBeInTheDocument();
    expect(screen.getByText("Where is evaluation stored?")).toBeInTheDocument();
    expect(screen.getByText("Which modules changed for answer evaluation?")).toBeInTheDocument();
    expect(screen.getAllByText("n/a").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Open evidence E29" })).toBeInTheDocument();
  });

  it("opens evidence details from an evaluation result evidence id", async () => {
    const user = userEvent.setup();
    vi.mocked(getEvaluationSummary).mockResolvedValue(populatedSummary);
    vi.mocked(getEvaluationRuns).mockResolvedValue(runList);
    vi.mocked(getEvaluationResults).mockResolvedValue(resultList);

    renderEvaluationsRoute();

    await user.click(await screen.findByRole("button", { name: "Open evidence E29" }));

    expect(screen.getByRole("dialog", { name: "Evidence detail" })).toBeInTheDocument();
    expect(screen.getByText("app/services/file_reader.py")).toBeInTheDocument();
    expect(screen.getByText("_file_type_from_filename")).toBeInTheDocument();
    expect(screen.getByText("def _file_type_from_filename(filename): ...")).toBeInTheDocument();
  });
});
