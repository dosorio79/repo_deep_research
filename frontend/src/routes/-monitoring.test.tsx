import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./monitoring";
import { getMonitoringRunDetail, getMonitoringRuns, getMonitoringSummary } from "@/lib/rag-client";
import type {
  MonitoringRunDetail,
  MonitoringRunList,
  MonitoringRunSummary,
  MonitoringSummary,
} from "@/lib/rag-types";

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/rag-client", () => ({
  getMonitoringRunDetail: vi.fn(),
  getMonitoringRuns: vi.fn(),
  getMonitoringSummary: vi.fn(),
}));

const summary: MonitoringSummary = {
  total_runs: 2,
  runs_by_kind: [
    { run_kind: "agentic", count: 1 },
    { run_kind: "direct", count: 1 },
  ],
  average_latency_by_kind: [
    { run_kind: "agentic", average_latency_ms: 300 },
    { run_kind: "direct", average_latency_ms: 100 },
  ],
  retrieval_volume: { retrieved_chunk_count: 7, unique_file_count: 5 },
  model_usage_by_model: [
    {
      provider: "openai",
      model: "gpt-5-mini",
      input_tokens: 30,
      output_tokens: 15,
      total_tokens: 45,
      estimated_cost_usd: "0.036",
    },
  ],
  feedback: { useful: 1, not_useful: 2 },
  errors_by_type: [{ error_type: "ResearchBudgetExceeded", count: 1 }],
};

const runSummary: MonitoringRunSummary = {
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

const runList: MonitoringRunList = {
  runs: [runSummary],
};

const runDetail: MonitoringRunDetail = {
  ...runSummary,
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

function renderMonitoringRoute() {
  const MonitoringComponent = Route.options.component as ComponentType;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MonitoringComponent />
    </QueryClientProvider>,
  );
}

describe("Monitoring route", () => {
  beforeEach(() => {
    vi.mocked(getMonitoringRunDetail).mockReset();
    vi.mocked(getMonitoringRuns).mockReset();
    vi.mocked(getMonitoringSummary).mockReset();
    vi.mocked(getMonitoringRuns).mockResolvedValue(runList);
    vi.mocked(getMonitoringRunDetail).mockResolvedValue(runDetail);
  });

  it("renders persisted monitoring summary panels", async () => {
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);

    renderMonitoringRoute();

    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("7 chunks")).toBeInTheDocument();
    expect(screen.getByText("5 files")).toBeInTheDocument();
    expect(screen.getByText("45")).toBeInTheDocument();
    expect(screen.getByText("$0.036000")).toBeInTheDocument();
    expect(screen.getByText("1 useful, 2 not useful")).toBeInTheDocument();
    expect(screen.getAllByText("ResearchBudgetExceeded").length).toBeGreaterThan(0);
    expect(await screen.findByText("Recent runs")).toBeInTheDocument();
    expect(screen.getByText("repo_deep_research")).toBeInTheDocument();
    expect(screen.getByText("12 / 5")).toBeInTheDocument();
  });

  it("loads run detail when a recent run is selected", async () => {
    const user = userEvent.setup();
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);

    renderMonitoringRoute();

    await user.click(await screen.findByText("repo_deep_research"));

    expect(await screen.findByText("Grounded enough.")).toBeInTheDocument();
    expect(screen.getByText("req-1")).toBeInTheDocument();
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("sends selected filters to the monitoring run list endpoint", async () => {
    const user = userEvent.setup();
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);

    renderMonitoringRoute();

    await user.selectOptions(await screen.findByLabelText("Kind"), "agentic");
    await user.selectOptions(screen.getByLabelText("Status"), "ok");
    await user.selectOptions(screen.getByLabelText("Feedback"), "useful");

    expect(getMonitoringRuns).toHaveBeenLastCalledWith(
      "/api",
      expect.objectContaining({
        run_kind: "agentic",
        has_error: false,
        feedback: "useful",
      }),
      expect.any(AbortSignal),
    );
  });

  it("renders an honest empty state before persisted runs exist", async () => {
    vi.mocked(getMonitoringSummary).mockResolvedValue({
      ...summary,
      total_runs: 0,
      runs_by_kind: [],
      average_latency_by_kind: [],
      retrieval_volume: { retrieved_chunk_count: 0, unique_file_count: 0 },
      model_usage_by_model: [],
      feedback: { useful: 0, not_useful: 0 },
      errors_by_type: [],
    });

    renderMonitoringRoute();

    expect(
      await screen.findByText(
        "No persisted monitoring rows are available. Run a direct or agentic query first.",
      ),
    ).toBeInTheDocument();
  });
});
