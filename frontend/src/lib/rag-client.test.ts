import { afterEach, describe, expect, it, vi } from "vitest";
import { getBackendHealth, ingestRepository, runAgenticResearch, runRagQuery } from "./rag-client";
import type { IngestSummary, RagRunResult, ResearchRunResult } from "./rag-types";

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
        rationale: "Find code that handles feedback.",
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

describe("runRagQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts a RAG request to the backend /rag endpoint", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(okResult), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      runRagQuery(
        "http://localhost:8000///",
        {
          question: "Where is config validated?",
          mode: "locate",
          retrieval_mode: "hybrid",
          limit: 5,
        },
        controller.signal,
      ),
    ).resolves.toEqual(okResult);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/rag",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "Where is config validated?",
          mode: "locate",
          retrieval_mode: "hybrid",
          limit: 5,
        }),
        signal: controller.signal,
      }),
    );
  });

  it("posts an agentic research request to the backend /research endpoint", async () => {
    const controller = new AbortController();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(agenticResult), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      runAgenticResearch(
        "http://localhost:8000///",
        {
          question: "Which modules must change for feedback?",
          mode: "change",
          retrieval_mode: "dense",
          retrieval_limit: 5,
        },
        controller.signal,
      ),
    ).resolves.toEqual(agenticResult);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/research",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: "Which modules must change for feedback?",
          mode: "change",
          retrieval_mode: "dense",
          retrieval_limit: 5,
        }),
        signal: controller.signal,
      }),
    );
  });

  it("posts a repository ingestion request to the backend ingest endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(ingestSummary), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      ingestRepository("http://localhost:8000///", {
        repository_address: "/tmp/sample-repo",
      }),
    ).resolves.toEqual(ingestSummary);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/repositories/ingest",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repository_address: "/tmp/sample-repo",
        }),
      }),
    );
  });

  it("checks backend health at the configured base URL", async () => {
    const health = { status: "ok", qdrant: true };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(health), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(getBackendHealth("http://localhost:8000///")).resolves.toEqual(health);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/health",
      expect.objectContaining({ signal: null }),
    );
  });

  it("surfaces FastAPI validation errors without exposing a stack trace", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: [
              {
                loc: ["body", "limit"],
                msg: "Input should be less than or equal to 20",
              },
            ],
          }),
          { status: 422, statusText: "Unprocessable Entity" },
        ),
      ),
    );

    await expect(
      runRagQuery("http://localhost:8000", {
        question: "Where is config validated?",
        mode: "locate",
        retrieval_mode: "hybrid",
        limit: 21,
      }),
    ).rejects.toMatchObject({
      title: "Backend returned 422 Unprocessable Entity",
      detail: "body.limit: Input should be less than or equal to 20",
      status: 422,
    });
  });

  it("reports network failures with the exact backend URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));

    await expect(
      runRagQuery("http://localhost:8000", {
        question: "Where is config validated?",
        mode: "locate",
        retrieval_mode: "hybrid",
        limit: 5,
      }),
    ).rejects.toMatchObject({
      title: "Network error",
      detail: expect.stringContaining("http://localhost:8000/rag"),
    });
  });
});
