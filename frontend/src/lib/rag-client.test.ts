import { afterEach, describe, expect, it, vi } from "vitest";
import { runRagQuery } from "./rag-client";
import type { RagRunResult } from "./rag-types";

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
