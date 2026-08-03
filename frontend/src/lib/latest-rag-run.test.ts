import { describe, expect, it } from "vitest";
import { loadLatestRagRun, saveLatestRagRun } from "./latest-rag-run";
import type { RagRunResult } from "./rag-types";

const result: RagRunResult = {
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

describe("latest RAG run storage", () => {
  it("round-trips the latest successful RAG response", () => {
    window.localStorage.clear();

    saveLatestRagRun(result);

    expect(loadLatestRagRun()).toEqual(result);
  });

  it("returns null for invalid stored JSON", () => {
    window.localStorage.setItem("repo-deep-research.latest-rag-run", "{");

    expect(loadLatestRagRun()).toBeNull();
  });
});
