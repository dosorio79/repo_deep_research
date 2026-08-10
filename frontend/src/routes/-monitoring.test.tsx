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
  total_runs: 4,
  runs_by_kind: [
    { run_kind: "agentic", count: 1 },
    { run_kind: "direct", count: 1 },
  ],
  average_latency_by_kind: [
    { run_kind: "agentic", average_latency_ms: 300 },
    { run_kind: "direct", average_latency_ms: 100 },
  ],
  retrieval_volume: { retrieved_chunk_count: 40, unique_file_count: 23 },
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
  runs: [
    runSummary,
    {
      ...runSummary,
      request_id: "req-2",
      session_id: "session-2",
      run_kind: "direct",
      completed_at: "2026-08-07T12:05:00Z",
      retrieval_mode: "dense",
      retrieved_chunk_count: 8,
      unique_file_count: 3,
      latency_ms_total: 1000,
      latency_ms_retrieval: 120,
      latency_ms_model: 700,
      tool_call_count: 0,
      has_error: true,
      feedback_useful: 0,
      feedback_not_useful: 1,
      total_estimated_cost_usd: "0.006",
    },
    {
      ...runSummary,
      request_id: "req-3",
      session_id: "session-3",
      completed_at: "2026-08-07T12:10:00Z",
      retrieved_chunk_count: 5,
      unique_file_count: 2,
      latency_ms_total: 3000,
      latency_ms_retrieval: 240,
      tool_call_count: 4,
      feedback_useful: 0,
    },
  ],
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

  it("renders scoped monitoring cards, runs, and aggregations", async () => {
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);

    renderMonitoringRoute();

    expect(await screen.findByText("Dashboard scope")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Cards and charts summarize the loaded runs that match these filters. Date ranges are anchored to the newest loaded run.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("3 / 3 loaded")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("25 chunks")).toBeInTheDocument();
    expect(screen.getByText("10 files")).toBeInTheDocument();
    expect(screen.getAllByText("$0.030000").length).toBeGreaterThan(0);
    expect(screen.getByText("1 useful, 1 not useful")).toBeInTheDocument();
    expect(screen.getByText("45 tokens")).toBeInTheDocument();
    expect(screen.getAllByText("ResearchBudgetExceeded").length).toBeGreaterThan(0);
    expect(await screen.findByText("Recent runs")).toBeInTheDocument();
    expect(screen.getAllByText("repo_deep_research").length).toBeGreaterThan(0);
    expect(screen.getByText("12 / 5")).toBeInTheDocument();
    expect(screen.getByText("Aggregations for current scope")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Charts summarize the runs currently shown above, including date and filter selections.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Runs over time")).toBeInTheDocument();
    expect(screen.getByText("3 recent runs in the current view")).toBeInTheDocument();
    expect(screen.getByText("Latency by mode")).toBeInTheDocument();
    expect(screen.getByText("Slowest average 2,500 ms")).toBeInTheDocument();
    expect(screen.getByText("Retrieval volume")).toBeInTheDocument();
    expect(
      screen.getByText("25 chunks, 10 files in the current view (40 chunks, 23 files total)"),
    ).toBeInTheDocument();
    expect(screen.getByText("Estimated cost by mode")).toBeInTheDocument();
    expect(screen.getByText("$0.030000 in the current view")).toBeInTheDocument();
    expect(screen.getByText("Feedback mix")).toBeInTheDocument();
    expect(screen.getByText("50% positive feedback rate")).toBeInTheDocument();
    expect(screen.getByText("Errors and tool calls")).toBeInTheDocument();
    expect(screen.getByText("1 errors, 3.5 avg agentic tool calls")).toBeInTheDocument();
    expect(screen.getByText("All-time persisted summary")).toBeInTheDocument();
    expect(
      screen.getByText(
        "These panels use the full persisted monitoring summary, independent of dashboard scope.",
      ),
    ).toBeInTheDocument();

    const recentRuns = screen.getByText("Recent runs");
    const aggregations = screen.getByText("Aggregations for current scope");
    expect(
      recentRuns.compareDocumentPosition(aggregations) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("opens run detail in a sheet when a recent run is selected", async () => {
    const user = userEvent.setup();
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);

    renderMonitoringRoute();

    const repositoryCells = await screen.findAllByText("repo_deep_research");
    await user.click(repositoryCells[0] as HTMLElement);

    expect(await screen.findByRole("dialog", { name: "Run detail" })).toBeInTheDocument();
    expect(await screen.findByText("Grounded enough.")).toBeInTheDocument();
    expect(screen.getByText("req-1")).toBeInTheDocument();
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("closes run detail from the sheet close button", async () => {
    const user = userEvent.setup();
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);

    renderMonitoringRoute();

    const repositoryCells = await screen.findAllByText("repo_deep_research");
    await user.click(repositoryCells[0] as HTMLElement);

    expect(await screen.findByRole("dialog", { name: "Run detail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Run detail" })).not.toBeInTheDocument();
  });

  it("filters loaded rows and aggregations with the date slicer", async () => {
    const user = userEvent.setup();
    vi.mocked(getMonitoringSummary).mockResolvedValue(summary);
    vi.mocked(getMonitoringRuns).mockResolvedValue({
      runs: [
        ...runList.runs,
        {
          ...runSummary,
          request_id: "req-old",
          session_id: "session-old",
          completed_at: "2026-07-01T12:00:00Z",
          repository_name: "old_repo",
          retrieved_chunk_count: 20,
          unique_file_count: 4,
          total_estimated_cost_usd: "0.010",
        },
      ],
    });

    renderMonitoringRoute();

    expect(await screen.findByText("old_repo")).toBeInTheDocument();
    expect(screen.getByText("4 / 4 loaded")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Newest 24h" }));

    expect(screen.queryByText("old_repo")).not.toBeInTheDocument();
    expect(screen.getByText("3 / 4 loaded")).toBeInTheDocument();
    expect(screen.getByText("25 chunks")).toBeInTheDocument();
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
