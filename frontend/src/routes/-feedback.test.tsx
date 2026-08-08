import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./feedback";
import { getMonitoringSummary } from "@/lib/rag-client";

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/rag-client", () => ({
  getMonitoringSummary: vi.fn(),
}));

function renderFeedbackRoute() {
  const FeedbackComponent = Route.options.component as ComponentType;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <FeedbackComponent />
    </QueryClientProvider>,
  );
}

describe("Feedback route", () => {
  beforeEach(() => {
    vi.mocked(getMonitoringSummary).mockReset();
  });

  it("renders persisted useful and not-useful counts", async () => {
    vi.mocked(getMonitoringSummary).mockResolvedValue({
      total_runs: 2,
      runs_by_kind: [],
      average_latency_by_kind: [],
      retrieval_volume: { retrieved_chunk_count: 0, unique_file_count: 0 },
      model_usage_by_model: [],
      feedback: { useful: 3, not_useful: 1 },
      errors_by_type: [],
    });

    renderFeedbackRoute();

    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getAllByText("3")).toHaveLength(2);
    expect(screen.getAllByText("1")).toHaveLength(2);
  });

  it("renders an empty state before feedback exists", async () => {
    vi.mocked(getMonitoringSummary).mockResolvedValue({
      total_runs: 0,
      runs_by_kind: [],
      average_latency_by_kind: [],
      retrieval_volume: { retrieved_chunk_count: 0, unique_file_count: 0 },
      model_usage_by_model: [],
      feedback: { useful: 0, not_useful: 0 },
      errors_by_type: [],
    });

    renderFeedbackRoute();

    expect(
      await screen.findByText(
        "No persisted feedback is available. Submit feedback from a returned answer first.",
      ),
    ).toBeInTheDocument();
  });
});
