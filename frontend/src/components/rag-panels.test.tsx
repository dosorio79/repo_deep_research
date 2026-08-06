import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnswerPanel } from "./AnswerPanel";
import { ResearchStepsPanel } from "./ResearchStepsPanel";
import { TracePanel } from "./TracePanel";
import type { RagAnswer, RagTrace } from "@/lib/rag-types";

describe("RAG result panels", () => {
  it("renders backend-shaped change targets", () => {
    const answer: RagAnswer = {
      question: "What should change?",
      mode: "change",
      summary: "Update the API contract.",
      implementation_flow: ["Inspect the API route."],
      evidence: [],
      relevant_files: ["src/repo_research/api.py"],
      relevant_symbols: ["create_app"],
      change_targets: [
        {
          path: "src/repo_research/api.py",
          symbol: "create_app",
          reason: "The API route is the browser integration boundary.",
          evidence_ids: ["E1"],
        },
      ],
      risks: [],
      confidence: 0.72,
      unresolved_questions: [],
      insufficient_evidence: false,
    };

    render(<AnswerPanel answer={answer} />);

    expect(screen.getByText("Update the API contract.")).toBeInTheDocument();
    expect(screen.getByText("src/repo_research/api.py::create_app")).toBeInTheDocument();
    expect(
      screen.getByText("The API route is the browser integration boundary."),
    ).toBeInTheDocument();
    expect(screen.getByText("evidence: E1")).toBeInTheDocument();
  });

  it("renders multiple model usage entries and string decimal costs", () => {
    const trace: RagTrace = {
      request_id: "req-1",
      repository_name: "repo_deep_research",
      branch: "dev",
      commit_hash: "abc123",
      question_mode: "locate",
      retrieval_mode: "hybrid",
      retrieval_limit: 5,
      retrieved_chunk_count: 2,
      unique_file_count: 1,
      latency_ms_total: 30,
      latency_ms_retrieval: 10,
      latency_ms_model: 20,
      model_usage: [
        {
          provider: "openai",
          model: "gpt-5-mini",
          input_tokens: 1000,
          output_tokens: 200,
          total_tokens: 1200,
          cached_input_tokens: 100,
          reasoning_tokens: 20,
          estimated_cost_usd: "0.0017",
          pricing_source: "configured",
          pricing_version: "test",
        },
        {
          provider: "openai",
          model: "gpt-5-mini",
          input_tokens: 500,
          output_tokens: 100,
          total_tokens: 600,
          estimated_cost_usd: null,
        },
      ],
      total_estimated_cost_usd: "0.0017",
      insufficient_evidence: false,
      error_type: null,
      error_message: null,
      tool_call_count: 0,
    };

    render(<TracePanel trace={trace} />);

    expect(screen.getByText("model_usage[0].provider")).toBeInTheDocument();
    expect(screen.getAllByText("gpt-5-mini")).toHaveLength(2);
    expect(screen.getAllByText("$0.001700")).toHaveLength(2);
    expect(screen.getByText("model_usage[1].estimated_cost_usd")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("renders agentic research steps", () => {
    render(
      <ResearchStepsPanel
        steps={[
          {
            sequence: 1,
            action: "Search repository evidence.",
            rationale: "Find modules related to feedback persistence.",
            evidence_ids: ["E1", "E2"],
          },
        ]}
      />,
    );

    expect(screen.getByText("Search repository evidence.")).toBeInTheDocument();
    expect(screen.getByText("Find modules related to feedback persistence.")).toBeInTheDocument();
    expect(screen.getByText("evidence: E1, E2")).toBeInTheDocument();
  });
});
