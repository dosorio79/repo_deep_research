import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode, ComponentType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./index";
import { loadLatestRagRun, saveLatestRagRun } from "@/lib/latest-rag-run";
import {
  getBackendHealth,
  ingestRepository,
  runAgenticResearch,
  runRagQuery,
  submitFeedback,
} from "@/lib/rag-client";
import type { IngestSummary, RagRunResult, ResearchRunResult } from "@/lib/rag-types";

vi.mock("@/lib/rag-client", () => ({
  getBackendHealth: vi.fn(),
  ingestRepository: vi.fn(),
  runAgenticResearch: vi.fn(),
  runRagQuery: vi.fn(),
  submitFeedback: vi.fn(),
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
    evidence: [
      {
        evidence_id: "E1",
        path: "src/repo_research/config.py",
        start_line: 20,
        end_line: 36,
        symbol: "Settings",
        score: 0.92,
        reason: "Defines runtime configuration validation.",
        content: "class Settings(BaseSettings): ...",
      },
    ],
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
    session_id: "browser-session",
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

const budgetLimitedAgenticResult: ResearchRunResult = {
  ...agenticResult,
  answer: {
    ...agenticResult.answer!,
    summary: "Insufficient repository evidence to produce an agentic change plan.",
    evidence: [
      {
        evidence_id: "E1",
        path: "app/services/profiler.py",
        start_line: 1,
        end_line: 40,
        symbol: null,
        score: 0.9,
        reason: "Closest available repository evidence.",
      },
    ],
    confidence: 0,
    insufficient_evidence: true,
    risks: ["The answer is intentionally withheld because grounding failed."],
    unresolved_questions: ["maximum file reads exceeded"],
  },
  trace: {
    ...agenticResult.trace!,
    evidence_ids: ["E1"],
    retrieved_chunk_count: 8,
    unique_file_count: 1,
    tool_call_count: 7,
    insufficient_evidence: true,
    error_type: "ResearchBudgetExceeded",
    error_message: "maximum file reads exceeded",
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

async function ingestSampleRepository(user: ReturnType<typeof userEvent.setup>) {
  vi.mocked(ingestRepository).mockResolvedValue(ingestSummary);
  await user.type(screen.getByLabelText("Repository address"), "/tmp/sample-repo");
  await user.click(screen.getByRole("button", { name: "Ingest repository" }));
  await screen.findByText("sample-repo");
}

describe("Research route", () => {
  beforeEach(() => {
    vi.mocked(ingestRepository).mockReset();
    vi.mocked(getBackendHealth).mockReset();
    vi.mocked(getBackendHealth).mockResolvedValue({ status: "ok", qdrant: true });
    vi.mocked(runAgenticResearch).mockReset();
    vi.mocked(runRagQuery).mockReset();
    vi.mocked(submitFeedback).mockReset();
    vi.mocked(loadLatestRagRun).mockReset();
    vi.mocked(loadLatestRagRun).mockReturnValue(null);
    vi.mocked(saveLatestRagRun).mockReset();
    window.localStorage.clear();
    window.localStorage.setItem("repo-deep-research-session-id", "browser-session");
  });

  it("restores the latest successful result when returning to research", () => {
    vi.mocked(loadLatestRagRun).mockReturnValue(okResult);

    renderResearchRoute();

    expect(screen.getByText("Settings validates runtime config.")).toBeInTheDocument();
    expect(screen.getByLabelText("Question")).toHaveValue("Where is config validated?");
  });

  it("shows backend connection state before ingestion", async () => {
    vi.mocked(getBackendHealth).mockRejectedValue({
      title: "Network error",
      detail: "Could not reach the backend at /api/health.",
    });

    renderResearchRoute();

    await screen.findByText("API offline");
    expect(screen.getByRole("button", { name: "Check API connection" })).toBeInTheDocument();
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

    await ingestSampleRepository(user);
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

    await ingestSampleRepository(user);
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
    expect(ingestRepository).toHaveBeenCalledWith("/api", {
      repository_address: "/tmp/sample-repo",
    });
    await screen.findByText("sample-repo");
    await screen.findByText("12");
  });

  it("labels an unchanged repository revision as already indexed", async () => {
    vi.mocked(ingestRepository).mockResolvedValue({
      ...ingestSummary,
      index_updated: false,
    });
    const user = userEvent.setup();

    renderResearchRoute();

    await user.type(screen.getByLabelText("Repository address"), "/tmp/sample-repo");
    await user.click(screen.getByRole("button", { name: "Ingest repository" }));

    await screen.findByText("already indexed");
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
      name: "Connect the codebase.",
    });
    await within(repositoryRegion).findByText("Backend returned 400");
    expect(
      within(repositoryRegion).getByText("repository path is not a directory"),
    ).toBeInTheDocument();
  });

  it("does not run research before a repository is ingested", async () => {
    const user = userEvent.setup();

    renderResearchRoute();

    await user.type(screen.getByLabelText("Question"), "Where is config validated?");

    expect(screen.getByRole("button", { name: "Run query" })).toBeDisabled();
    expect(screen.getByText("Ingest a repository first")).toBeInTheDocument();
    expect(runRagQuery).not.toHaveBeenCalled();
    expect(runAgenticResearch).not.toHaveBeenCalled();
  });

  it("submits direct research to /rag with a limit field", async () => {
    vi.mocked(runRagQuery).mockResolvedValue(okResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await ingestSampleRepository(user);
    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => expect(runRagQuery).toHaveBeenCalled());
    expect(runRagQuery).toHaveBeenCalledWith(
      "/api",
      expect.objectContaining({
        question: "Where is config validated?",
        repository_path: "/tmp/sample-repo",
        limit: 8,
        session_id: "browser-session",
      }),
      expect.any(AbortSignal),
    );
    expect(runAgenticResearch).not.toHaveBeenCalled();
  });

  it("opens evidence details from a research evidence highlight", async () => {
    vi.mocked(runRagQuery).mockResolvedValue(okResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await ingestSampleRepository(user);
    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await user.click(await screen.findByRole("button", { name: "Open evidence E1" }));

    const dialog = screen.getByRole("dialog", { name: "Evidence detail" });
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("src/repo_research/config.py")).toBeInTheDocument();
    expect(within(dialog).getByText("class Settings(BaseSettings): ...")).toBeInTheDocument();
  });

  it("submits agentic research to /research with a retrieval_limit field", async () => {
    vi.mocked(runAgenticResearch).mockResolvedValue(agenticResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await ingestSampleRepository(user);
    await user.click(screen.getByRole("radio", { name: "agentic RAG" }));
    await user.type(screen.getByLabelText("Question"), "Which modules change for feedback?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await waitFor(() => expect(runAgenticResearch).toHaveBeenCalled());
    expect(runAgenticResearch).toHaveBeenCalledWith(
      "/api",
      expect.objectContaining({
        question: "Which modules change for feedback?",
        mode: "change",
        retrieval_limit: 8,
        session_id: "browser-session",
      }),
      expect.any(AbortSignal),
    );
    expect(runRagQuery).not.toHaveBeenCalled();
    await screen.findByText("Search repository evidence.");
  });

  it("explains bounded agentic partial results without treating them as request errors", async () => {
    vi.mocked(runAgenticResearch).mockResolvedValue(budgetLimitedAgenticResult);
    const user = userEvent.setup();

    renderResearchRoute();

    await ingestSampleRepository(user);
    await user.click(screen.getByRole("radio", { name: "agentic RAG" }));
    await user.type(
      screen.getByLabelText("Question"),
      "Which modules change for agentic analysis?",
    );
    await user.click(screen.getByRole("button", { name: "Run query" }));

    await screen.findByText("Bounded agent stopped at its tool budget");
    expect(screen.getByText("maximum file reads exceeded")).toBeInTheDocument();
    expect(screen.getByText("tool calls 7")).toBeInTheDocument();
    expect(screen.getByText("evidence 1")).toBeInTheDocument();
    expect(screen.queryByText("Network error")).not.toBeInTheDocument();
    expect(screen.queryByText(/Backend returned/)).not.toBeInTheDocument();
  });

  it("submits persisted feedback for the latest result", async () => {
    vi.mocked(loadLatestRagRun).mockReturnValue(okResult);
    vi.mocked(submitFeedback).mockResolvedValue({
      feedback_id: "feedback-1",
      session_id: "browser-session",
      request_id: "req-1",
      run_kind: "direct",
      useful: true,
      comment: "Grounded enough.",
      submitted_at: "2026-08-07T12:00:00Z",
    });
    const user = userEvent.setup();

    renderResearchRoute();

    await user.click(screen.getByRole("button", { name: "Useful" }));
    await user.type(screen.getByLabelText("Comment"), "Grounded enough.");
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));

    await waitFor(() => expect(submitFeedback).toHaveBeenCalled());
    expect(submitFeedback).toHaveBeenCalledWith("/api", {
      session_id: "browser-session",
      request_id: "req-1",
      run_kind: "direct",
      useful: true,
      comment: "Grounded enough.",
    });
    await screen.findByText("submitted");
    expect(screen.getByRole("button", { name: "Feedback recorded" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Useful" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Not useful" })).toBeDisabled();
    expect(screen.getByLabelText("Comment")).toBeDisabled();
  });
});
