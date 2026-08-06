import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode, ComponentType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./index";
import { loadLatestRagRun, saveLatestRagRun } from "@/lib/latest-rag-run";
import { ingestRepository, runAgenticResearch, runRagQuery } from "@/lib/rag-client";
import type { IngestSummary, RagRunResult, ResearchRunResult } from "@/lib/rag-types";

vi.mock("@/lib/rag-client", () => ({
  ingestRepository: vi.fn(),
  runAgenticResearch: vi.fn(),
  runRagQuery: vi.fn(),
}));

vi.mock("@/lib/latest-rag-run", () => ({
  loadLatestRagRun: vi.fn(),
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

const agenticResult: ResearchRunResult = {
  ...okResult,
  answer: {
    ...okResult.answer!,
    mode: "change",
    research_steps: [
      {
        sequence: 1,
        action: "Search repository evidence.",
        rationale: "Locate feedback and monitoring requirements.",
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
    vi.mocked(ingestRepository).mockReset();
    vi.mocked(runAgenticResearch).mockReset();
    vi.mocked(runRagQuery).mockReset();
    vi.mocked(loadLatestRagRun).mockReset();
    vi.mocked(loadLatestRagRun).mockReturnValue(null);
    vi.mocked(saveLatestRagRun).mockReset();
  });

  it("restores the latest successful result when returning to research", () => {
    vi.mocked(loadLatestRagRun).mockReturnValue(okResult);

    renderResearchRoute();

    expect(screen.getByText("Settings validates runtime config.")).toBeInTheDocument();
    expect(screen.getByLabelText("Question")).toHaveValue("Where is config validated?");
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

    await user.type(screen.getByLabelText("Repository address"), "/tmp/sample-repo");
    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => expect(saveLatestRagRun).toHaveBeenCalledWith(okResult));
  });

  it("ingests a repository address before research", async () => {
    vi.mocked(ingestRepository).mockResolvedValue(ingestSummary);
    const user = userEvent.setup();

    renderResearchRoute();

    await user.type(screen.getByLabelText("Repository address"), "/tmp/sample-repo");
    await user.click(screen.getByRole("button", { name: "Ingest repository" }));

    await waitFor(() => expect(ingestRepository).toHaveBeenCalled());
    expect(ingestRepository).toHaveBeenCalledWith("http://localhost:8000", {
      repository_address: "/tmp/sample-repo",
    });
    await screen.findByText("sample-repo");
    await screen.findByText("12");
  });

  it("shows repository ingest errors beside the repository controls", async () => {
    vi.mocked(ingestRepository).mockRejectedValue({
      title: "Backend returned 400",
      detail: "repository path is not a directory",
      status: 400,
    });
    const user = userEvent.setup();

    renderResearchRoute();

    await user.type(screen.getByLabelText("Repository address"), "/tmp/missing-repo");
    await user.click(screen.getByRole("button", { name: "Ingest repository" }));

    const repositoryRegion = screen.getByRole("region", {
      name: "Connect the codebase to research.",
    });
    await within(repositoryRegion).findByText("Backend returned 400");
    expect(
      within(repositoryRegion).getByText("repository path is not a directory"),
    ).toBeInTheDocument();
  });

  it("submits direct research to /rag with a limit field", async () => {
    vi.mocked(runRagQuery).mockResolvedValue(okResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await user.type(screen.getByLabelText("Repository address"), "/tmp/sample-repo");
    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => expect(runRagQuery).toHaveBeenCalled());
    expect(runRagQuery).toHaveBeenCalledWith(
      "http://localhost:8000",
      expect.objectContaining({
        question: "Where is config validated?",
        repository_path: "/tmp/sample-repo",
        limit: 8,
      }),
      expect.any(AbortSignal),
    );
    expect(runAgenticResearch).not.toHaveBeenCalled();
  });

  it("submits agentic research to /research with a retrieval_limit field", async () => {
    vi.mocked(runAgenticResearch).mockResolvedValue(agenticResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await user.click(screen.getByRole("radio", { name: "agentic RAG" }));
    await user.type(screen.getByLabelText("Question"), "Which modules change for feedback?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => expect(runAgenticResearch).toHaveBeenCalled());
    expect(runAgenticResearch).toHaveBeenCalledWith(
      "http://localhost:8000",
      expect.objectContaining({
        question: "Which modules change for feedback?",
        mode: "change",
        retrieval_limit: 8,
      }),
      expect.any(AbortSignal),
    );
    expect(runRagQuery).not.toHaveBeenCalled();
    await screen.findByText("Search repository evidence.");
  });
});
