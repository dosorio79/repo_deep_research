import { render, screen } from "@testing-library/react";
import type { ComponentType, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./monitoring";
import { loadLatestRagRun } from "@/lib/latest-rag-run";
import type { RagRunResult } from "@/lib/rag-types";

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/lib/latest-rag-run", () => ({
  loadLatestRagRun: vi.fn(),
}));

const result: RagRunResult = {
  answer: {
    question: "Where to add a rag agentic mode?",
    mode: "change",
    summary: "Add a repository-level agentic research mode.",
    implementation_flow: ["Update RagMode."],
    evidence: [
      {
        evidence_id: "E1",
        path: "src/repo_research/models.py",
        start_line: 63,
        end_line: 69,
        symbol: "RagMode",
        score: 0.33,
        reason: "RagMode defines the supported modes.",
      },
    ],
    relevant_files: ["src/repo_research/models.py"],
    relevant_symbols: ["RagMode"],
    change_targets: [
      {
        path: "src/repo_research/models.py",
        symbol: "RagMode",
        reason: "Add the new mode.",
        evidence_ids: ["E1"],
      },
    ],
    risks: ["Avoid starting M4 too early."],
    confidence: 0.75,
    unresolved_questions: ["research or agentic?"],
    insufficient_evidence: false,
  },
  trace: {
    request_id: "req-1",
    started_at: "2026-08-03T21:46:45.712100Z",
    completed_at: "2026-08-03T21:47:25.178039Z",
    repository_name: "repo_deep_research",
    branch: "feat/m3-6-frontend-harness",
    commit_hash: "abc123",
    question_mode: "change",
    retrieval_mode: "hybrid",
    retrieval_limit: 8,
    retrieved_chunk_count: 8,
    unique_file_count: 7,
    latency_ms_total: 39469,
    latency_ms_retrieval: 32,
    latency_ms_model: 39436,
    model_usage: [
      {
        provider: "openai",
        model: "gpt-5-mini",
        input_tokens: 2363,
        output_tokens: 2922,
        total_tokens: 5285,
        reasoning_tokens: 1600,
        estimated_cost_usd: "0.00643475",
        pricing_version: "openai-api-pricing-snapshot",
      },
    ],
    total_estimated_cost_usd: "0.00643475",
    insufficient_evidence: false,
    error_type: null,
    error_message: null,
    tool_call_count: 0,
  },
};

function renderMonitoringRoute() {
  const MonitoringComponent = Route.options.component as ComponentType;
  return render(<MonitoringComponent />);
}

describe("Monitoring route", () => {
  beforeEach(() => {
    vi.mocked(loadLatestRagRun).mockReset();
  });

  it("renders the latest RAG response outcome and usage metrics", async () => {
    vi.mocked(loadLatestRagRun).mockReturnValue(result);

    renderMonitoringRoute();

    expect(await screen.findByText("Grounded")).toBeInTheDocument();
    expect(screen.getByText("8 chunks, 7 files")).toBeInTheDocument();
    expect(screen.getAllByText("$0.006435")).toHaveLength(2);
    expect(screen.getByText("5,285 tokens")).toBeInTheDocument();
    expect(screen.getByText("openai-api-pricing-snapshot")).toBeInTheDocument();
  });

  it("renders an empty state before any successful run", async () => {
    vi.mocked(loadLatestRagRun).mockReturnValue(null);

    renderMonitoringRoute();

    expect(
      await screen.findByText(
        "Run a research query first. The latest successful response appears here.",
      ),
    ).toBeInTheDocument();
  });
});
