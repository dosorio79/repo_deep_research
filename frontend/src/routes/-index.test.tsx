import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode, ComponentType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./index";
import { saveLatestRagRun } from "@/lib/latest-rag-run";
import { runRagQuery } from "@/lib/rag-client";
import type { RagRunResult } from "@/lib/rag-types";

vi.mock("@/lib/rag-client", () => ({
  runRagQuery: vi.fn(),
}));

vi.mock("@/lib/latest-rag-run", () => ({
  saveLatestRagRun: vi.fn(),
}));

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

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

function renderResearchRoute() {
  const ResearchComponent = Route.options.component as ComponentType;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ResearchComponent />
    </QueryClientProvider>,
  );
}

describe("Research route", () => {
  beforeEach(() => {
    vi.mocked(runRagQuery).mockReset();
    vi.mocked(saveLatestRagRun).mockReset();
  });

  it("aborts an in-flight RAG request when the route unmounts", async () => {
    vi.mocked(runRagQuery).mockImplementation(
      (_baseUrl, _body, signal) =>
        new Promise((resolve, reject) => {
          signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    const user = userEvent.setup();

    const view = renderResearchRoute();

    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    const firstSignal = vi.mocked(runRagQuery).mock.calls[0]?.[2];
    expect(firstSignal?.aborted).toBe(false);

    view.unmount();

    await waitFor(() => expect(firstSignal?.aborted).toBe(true));
    expect(vi.mocked(runRagQuery)).toHaveBeenCalledTimes(1);
  });

  it("stores the latest successful RAG response for monitoring", async () => {
    vi.mocked(runRagQuery).mockResolvedValue(okResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => expect(saveLatestRagRun).toHaveBeenCalledWith(okResult));
  });
});
