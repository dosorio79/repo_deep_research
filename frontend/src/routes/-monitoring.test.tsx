import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./monitoring";
import { getMonitoringSummary } from "@/lib/rag-client";
import type { MonitoringSummary } from "@/lib/rag-types";

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/rag-client", () => ({
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
    vi.mocked(getMonitoringSummary).mockReset();
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
