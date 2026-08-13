import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ClipboardCheck, Gauge, MessageSquare, TriangleAlert } from "lucide-react";
import { ApiError } from "@/components/ApiError";
import { AppShell } from "@/components/AppShell";
import { EvidenceReferences } from "@/components/EvidenceReferences";
import { EmptyLine, Field, Panel } from "@/components/primitives";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import {
  getEvaluationResults,
  getEvaluationRuns,
  getEvaluationSummary,
  getRetrievalEvaluationResults,
} from "@/lib/rag-client";
import type {
  ApiErrorShape,
  EvaluationDashboardSummary,
  EvaluationResultSummary,
  EvaluationRunSummary,
  RetrievalEvaluationSummary,
} from "@/lib/rag-types";

const DEFAULT_API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "/api";

export const Route = createFileRoute("/evaluations")({
  head: () => ({
    meta: [
      { title: "Evaluations - Repo Deep Research" },
      {
        name: "description",
        content: "PostgreSQL-backed answer-evaluation dashboard.",
      },
      { property: "og:title", content: "Evaluations - Repo Deep Research" },
      {
        property: "og:description",
        content: "Persisted answer quality scores and evaluation run history.",
      },
    ],
  }),
  component: EvaluationsView,
});

function EvaluationsView() {
  const [contextLabel, setContextLabel] = useState("all");
  const summaryQuery = useQuery({
    queryKey: ["evaluation-summary", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getEvaluationSummary(DEFAULT_API_BASE_URL, signal),
    retry: false,
    staleTime: 5_000,
  });
  const runsQuery = useQuery({
    queryKey: ["evaluation-runs", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getEvaluationRuns(DEFAULT_API_BASE_URL, { limit: 25 }, signal),
    retry: false,
    staleTime: 5_000,
  });
  const resultsQuery = useQuery({
    queryKey: ["evaluation-results", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getEvaluationResults(DEFAULT_API_BASE_URL, { limit: 50 }, signal),
    retry: false,
    staleTime: 5_000,
  });
  const retrievalQuery = useQuery({
    queryKey: ["retrieval-evaluation-results", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getRetrievalEvaluationResults(DEFAULT_API_BASE_URL, signal),
    retry: false,
    staleTime: 30_000,
  });

  return (
    <AppShell>
      <h1 className="sr-only">Repo Deep Research evaluations</h1>
      {summaryQuery.error ? (
        <ApiError error={summaryQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {runsQuery.error ? <ApiError error={runsQuery.error as unknown as ApiErrorShape} /> : null}
      {resultsQuery.error ? (
        <ApiError error={resultsQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {retrievalQuery.error ? (
        <ApiError error={retrievalQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {summaryQuery.error ? null : summaryQuery.data ? (
        <EvaluationDashboard
          summary={summaryQuery.data}
          runs={runsQuery.data?.runs ?? []}
          results={resultsQuery.data?.results ?? []}
          retrievalResults={retrievalQuery.data?.results ?? []}
          loadingRuns={runsQuery.isLoading}
          loadingResults={resultsQuery.isLoading}
          loadingRetrievalResults={retrievalQuery.isLoading}
          selectedContext={contextLabel}
          onContextChange={setContextLabel}
        />
      ) : summaryQuery.isLoading ? (
        <Panel title="Evaluations">
          <EmptyLine>Loading persisted evaluation results.</EmptyLine>
        </Panel>
      ) : (
        <div className="space-y-3">
          <SearchEvaluationHighlights
            results={retrievalQuery.data?.results ?? []}
            loading={retrievalQuery.isLoading}
          />
          <EmptyEvaluations />
        </div>
      )}
    </AppShell>
  );
}

function EmptyEvaluations() {
  return (
    <Panel title="Evaluations">
      <EmptyLine>
        No persisted evaluation results are available. Run evaluate-answers with --persist first.
      </EmptyLine>
    </Panel>
  );
}

function EvaluationDashboard({
  summary,
  runs,
  results,
  retrievalResults,
  loadingRuns,
  loadingResults,
  loadingRetrievalResults,
  selectedContext,
  onContextChange,
}: {
  summary: EvaluationDashboardSummary;
  runs: EvaluationRunSummary[];
  results: EvaluationResultSummary[];
  retrievalResults: RetrievalEvaluationSummary[];
  loadingRuns: boolean;
  loadingResults: boolean;
  loadingRetrievalResults: boolean;
  selectedContext: string;
  onContextChange: (value: string) => void;
}) {
  const contextOptions = useMemo(() => evaluationContextOptions(results), [results]);
  if (summary.total_results === 0)
    return (
      <div className="space-y-3">
        <SearchEvaluationHighlights results={retrievalResults} loading={loadingRetrievalResults} />
        <EmptyEvaluations />
      </div>
    );

  const visibleResults =
    selectedContext === "all"
      ? results
      : results.filter((result) => result.context_label === selectedContext);
  const visibleAverage = averageResultScore(visibleResults);
  const visibleUnsupportedRate =
    visibleResults.length === 0
      ? 0
      : visibleResults.filter((result) => result.unsupported_claim_count > 0).length /
        visibleResults.length;
  const worstResults = [...visibleResults]
    .sort((left, right) => left.average_score - right.average_score)
    .slice(0, 8);

  return (
    <div className="space-y-3">
      <SearchEvaluationHighlights results={retrievalResults} loading={loadingRetrievalResults} />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={ClipboardCheck}
          label="Evaluated answers"
          value={visibleResults.length.toLocaleString()}
          detail={
            selectedContext === "all"
              ? `${summary.completed_runs} completed runs, ${summary.failed_runs} failed`
              : `filtered to ${selectedContext}`
          }
        />
        <MetricCard
          icon={Gauge}
          label="Average score"
          value={formatScore(visibleAverage)}
          detail="mean for selected context"
        />
        <MetricCard
          icon={TriangleAlert}
          label="Unsupported claims"
          value={`${Math.round(visibleUnsupportedRate * 100)}%`}
          detail="selected results with unsupported claims"
        />
        <MetricCard
          icon={MessageSquare}
          label="Loaded feedback-linked"
          value={countFeedbackLinked(visibleResults).toLocaleString()}
          detail="selected loaded results with feedback"
        />
      </div>

      <Panel title="Evaluation context">
        <div className="grid gap-2 md:grid-cols-[minmax(220px,320px)_1fr] md:items-end">
          <SelectField
            label="Repository or dataset"
            value={selectedContext}
            onChange={onContextChange}
            options={[
              ["all", "All contexts"],
              ...contextOptions.map((value): [string, string] => [value, value]),
            ]}
          />
          <p className="text-[12px] text-muted-foreground">
            Scores are only comparable within the repository or dataset used to create the questions
            and answers.
          </p>
        </div>
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartPanel title="Average score by approach">
          <ChartContainer
            config={{ score: { label: "Average score", color: "var(--color-chart-1)" } }}
            className="h-[220px] w-full min-w-0 aspect-auto"
          >
            <BarChart accessibilityLayer data={runKindChartData(visibleResults)}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis domain={[0, 5]} tickLine={false} axisLine={false} width={30} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="score" fill="var(--color-score)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </ChartPanel>

        <ChartPanel title="Score distribution by metric">
          <ChartContainer
            config={{ score: { label: "Average score", color: "var(--color-chart-2)" } }}
            className="h-[220px] w-full min-w-0 aspect-auto"
          >
            <BarChart accessibilityLayer data={metricChartData(visibleResults)}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="metric" tickLine={false} axisLine={false} minTickGap={8} />
              <YAxis domain={[0, 5]} tickLine={false} axisLine={false} width={30} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="score" fill="var(--color-score)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </ChartPanel>

        <ChartPanel title="Recent feedback versus judge scores">
          <ChartContainer
            config={{ score: { label: "Average score", color: "var(--color-chart-3)" } }}
            className="h-[220px] w-full min-w-0 aspect-auto"
          >
            <BarChart accessibilityLayer data={feedbackChartData(visibleResults)}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="label" tickLine={false} axisLine={false} />
              <YAxis domain={[0, 5]} tickLine={false} axisLine={false} width={30} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="score" fill="var(--color-score)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </ChartPanel>

        <ChartPanel title="Recent quality compared with latency and cost">
          <div className="grid gap-2">
            <Field label="Loaded average latency">
              {formatLatency(averageLatency(visibleResults))}
            </Field>
            <Field label="Loaded estimated cost">{formatCost(totalCost(visibleResults))}</Field>
            <Field label="Selected average score">{formatScore(visibleAverage)}</Field>
          </div>
        </ChartPanel>
      </div>

      <Panel title="Recent evaluation runs">
        <EvaluationRunTable runs={runs} loading={loadingRuns} />
      </Panel>

      <Panel title="Lowest-scoring loaded answers">
        <EvaluationResultTable results={worstResults} loading={loadingResults} />
      </Panel>
    </div>
  );
}

function SearchEvaluationHighlights({
  results,
  loading,
}: {
  results: RetrievalEvaluationSummary[];
  loading: boolean;
}) {
  const heldOutResults = results.filter((item) => item.dataset.toLowerCase() === "held-out");
  const visibleResults = heldOutResults.length ? heldOutResults : results;
  const selected = visibleResults.find((item) => item.selected) ?? visibleResults[0];
  return (
    <Panel title="Search evaluation highlights">
      {loading ? <EmptyLine>Loading retrieval evaluation metrics.</EmptyLine> : null}
      {!loading && visibleResults.length === 0 ? (
        <EmptyLine>No persisted retrieval evaluation metrics are available.</EmptyLine>
      ) : null}
      {!loading && visibleResults.length > 0 ? (
        <>
          <div className="grid gap-3 lg:grid-cols-[260px_1fr]">
            <div className="grid gap-2">
              <Field label="Selected retrieval mode">{selected?.mode ?? "dense"}</Field>
              <Field label="Held-out file hit rate">
                {formatPercent(selected?.file_hit_rate ?? null)}
              </Field>
              <Field label="Held-out symbol hit rate">
                {formatPercent(selected?.symbol_hit_rate ?? null)}
              </Field>
            </div>
            <div className="grid gap-2 md:hidden">
              {visibleResults.map((item) => (
                <div key={item.mode} className="border-t border-border pt-2 first:border-t-0">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <span className="font-medium">{item.mode}</span>
                    {item.selected ? (
                      <span className="rounded-sm bg-secondary px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                        default
                      </span>
                    ) : null}
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                    <Field label="File hit">{formatPercent(item.file_hit_rate)}</Field>
                    <Field label="File MRR">{item.file_mrr.toFixed(3)}</Field>
                    <Field label="Recall">{formatPercent(item.file_recall)}</Field>
                    <Field label="Precision">{formatPercent(item.file_precision)}</Field>
                    <Field label="Symbol hit">{formatPercent(item.symbol_hit_rate)}</Field>
                  </div>
                </div>
              ))}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[640px] text-left text-[12px]">
                <thead className="border-b border-border text-muted-foreground">
                  <tr>
                    <th className="py-2 pr-3 font-medium">Dataset</th>
                    <th className="py-2 pr-3 font-medium">Mode</th>
                    <th className="py-2 pr-3 font-medium">File hit</th>
                    <th className="py-2 pr-3 font-medium">File MRR</th>
                    <th className="py-2 pr-3 font-medium">Recall</th>
                    <th className="py-2 pr-3 font-medium">Precision</th>
                    <th className="py-2 pr-3 font-medium">Symbol hit</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleResults.map((item) => (
                    <tr key={item.mode} className="border-b border-border/60">
                      <td className="py-2 pr-3">{item.dataset}</td>
                      <td className="py-2 pr-3">
                        {item.mode}
                        {item.selected ? (
                          <span className="ml-2 rounded-sm bg-secondary px-1.5 py-0.5 text-[10px] uppercase tracking-wide">
                            default
                          </span>
                        ) : null}
                      </td>
                      <td className="py-2 pr-3 mono">{formatPercent(item.file_hit_rate)}</td>
                      <td className="py-2 pr-3 mono">{item.file_mrr.toFixed(3)}</td>
                      <td className="py-2 pr-3 mono">{formatPercent(item.file_recall)}</td>
                      <td className="py-2 pr-3 mono">{formatPercent(item.file_precision)}</td>
                      <td className="py-2 pr-3 mono">{formatPercent(item.symbol_hit_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <p className="mt-2 text-[12px] text-muted-foreground">
            Search evaluation is loaded from persisted retrieval metrics produced from versioned
            repository question datasets.
          </p>
        </>
      ) : null}
    </Panel>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof ClipboardCheck;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <Panel title={label}>
      <div className="flex items-start gap-2">
        <Icon className="mt-0.5 h-4 w-4 text-muted-foreground" aria-hidden />
        <div>
          <div className="mono text-[20px] font-semibold leading-tight">{value}</div>
          <p className="text-[12px] text-muted-foreground">{detail}</p>
        </div>
      </div>
    </Panel>
  );
}

function ChartPanel({ title, children }: { title: string; children: ReactNode }) {
  return <Panel title={title}>{children}</Panel>;
}

function EvaluationRunTable({ runs, loading }: { runs: EvaluationRunSummary[]; loading: boolean }) {
  if (loading) return <EmptyLine>Loading evaluation runs.</EmptyLine>;
  if (runs.length === 0) return <EmptyLine>No persisted evaluation runs.</EmptyLine>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-[12px]">
        <thead className="border-b border-border text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">Started</th>
            <th className="py-2 pr-3 font-medium">Source</th>
            <th className="py-2 pr-3 font-medium">Context</th>
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Results</th>
            <th className="py-2 pr-3 font-medium">Average</th>
            <th className="py-2 pr-3 font-medium">Unsupported</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.evaluation_run_id} className="border-b border-border/60">
              <td className="py-2 pr-3 mono">{formatDate(run.started_at)}</td>
              <td className="py-2 pr-3">{sourceLabel(run.source_type)}</td>
              <td className="max-w-[240px] py-2 pr-3">{run.context_labels.join(", ")}</td>
              <td className="py-2 pr-3">{run.status}</td>
              <td className="py-2 pr-3 mono">{run.result_count}</td>
              <td className="py-2 pr-3 mono">{formatScore(run.average_score)}</td>
              <td className="py-2 pr-3 mono">{run.unsupported_claim_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvaluationResultTable({
  results,
  loading,
}: {
  results: EvaluationResultSummary[];
  loading: boolean;
}) {
  if (loading) return <EmptyLine>Loading evaluated answers.</EmptyLine>;
  if (results.length === 0)
    return <EmptyLine>No evaluated answers match the current view.</EmptyLine>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[1280px] text-left text-[12px]">
        <thead className="border-b border-border text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">Question</th>
            <th className="py-2 pr-3 font-medium">Source</th>
            <th className="py-2 pr-3 font-medium">Context</th>
            <th className="py-2 pr-3 font-medium">Approach</th>
            <th className="py-2 pr-3 font-medium">Average</th>
            <th className="py-2 pr-3 font-medium">Correct</th>
            <th className="py-2 pr-3 font-medium">Faithful</th>
            <th className="py-2 pr-3 font-medium">Citations</th>
            <th className="py-2 pr-3 font-medium">Coverage</th>
            <th className="py-2 pr-3 font-medium">Relevant</th>
            <th className="py-2 pr-3 font-medium">Presentation</th>
            <th className="py-2 pr-3 font-medium">Unsupported</th>
            <th className="py-2 pr-3 font-medium">Evidence</th>
            <th className="py-2 pr-3 font-medium">Feedback</th>
            <th className="py-2 pr-3 font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr key={result.result_id} className="border-b border-border/60">
              <td className="max-w-[360px] break-words py-2 pr-3">{result.question}</td>
              <td className="py-2 pr-3">{sourceLabel(result.source_type)}</td>
              <td className="max-w-[220px] break-words py-2 pr-3">{result.context_label}</td>
              <td className="py-2 pr-3">{result.run_kind ?? "unknown"}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.average_score)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.answer_correctness)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.faithfulness)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.citation_precision)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.reference_coverage)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.answer_relevance)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.presentation_quality)}</td>
              <td className="py-2 pr-3 mono">{result.unsupported_claim_count}</td>
              <td className="max-w-[180px] py-2 pr-3">
                {result.answer_evidence?.length ? (
                  <EvidenceReferences
                    evidenceIds={result.answer_evidence.map((item) => item.evidence_id)}
                    evidence={result.answer_evidence}
                    prefix=""
                  />
                ) : (
                  <span className="text-muted-foreground">n/a</span>
                )}
              </td>
              <td className="py-2 pr-3 mono">
                {result.feedback_useful}/{result.feedback_not_useful}
              </td>
              <td className="py-2 pr-3 mono">{formatCost(result.total_estimated_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function runKindChartData(results: EvaluationResultSummary[]) {
  return groupAverage(results, (result) => result.run_kind ?? "unknown");
}

function metricChartData(results: EvaluationResultSummary[]) {
  return [
    ["answer_correctness", results.map((result) => result.answer_correctness)],
    ["faithfulness", results.map((result) => result.faithfulness)],
    ["citation_precision", results.map((result) => result.citation_precision)],
    ["reference_coverage", results.map((result) => result.reference_coverage)],
    ["answer_relevance", results.map((result) => result.answer_relevance)],
    ["presentation_quality", results.map((result) => result.presentation_quality)],
  ]
    .map(([metric, values]) => ({
      metric: metricLabel(metric as string),
      score: averageNumbers(values as Array<number | null>),
    }))
    .filter((item): item is { metric: string; score: number } => item.score !== null);
}

function feedbackChartData(results: EvaluationResultSummary[]) {
  const useful = results.filter((result) => result.feedback_useful > 0);
  const notUseful = results.filter((result) => result.feedback_not_useful > 0);
  return [
    { label: "useful", score: averageResultScore(useful) ?? 0 },
    { label: "not useful", score: averageResultScore(notUseful) ?? 0 },
  ];
}

function averageResultScore(results: EvaluationResultSummary[]) {
  if (results.length === 0) return null;
  return roundScore(
    results.reduce((total, result) => total + result.average_score, 0) / results.length,
  );
}

function averageNumbers(values: Array<number | null>) {
  const numbers = values.filter((value): value is number => typeof value === "number");
  if (numbers.length === 0) return null;
  return roundScore(numbers.reduce((total, value) => total + value, 0) / numbers.length);
}

function groupAverage(
  results: EvaluationResultSummary[],
  getLabel: (result: EvaluationResultSummary) => string,
) {
  const groups = new Map<string, EvaluationResultSummary[]>();
  for (const result of results) {
    const label = getLabel(result);
    groups.set(label, [...(groups.get(label) ?? []), result]);
  }
  return [...groups.entries()].map(([label, group]) => ({
    label,
    score: averageResultScore(group) ?? 0,
  }));
}

function evaluationContextOptions(results: EvaluationResultSummary[]) {
  return [...new Set(results.map((result) => result.context_label))].sort((left, right) =>
    left.localeCompare(right),
  );
}

function countFeedbackLinked(results: EvaluationResultSummary[]) {
  return results.filter((result) => result.feedback_useful + result.feedback_not_useful > 0).length;
}

function averageLatency(results: EvaluationResultSummary[]) {
  const latencies = results
    .map((result) => result.latency_ms_total)
    .filter((value): value is number => typeof value === "number");
  if (latencies.length === 0) return null;
  return latencies.reduce((total, value) => total + value, 0) / latencies.length;
}

function totalCost(results: EvaluationResultSummary[]) {
  return results.reduce((total, result) => total + Number(result.total_estimated_cost_usd ?? 0), 0);
}

function formatScore(value: number | null) {
  if (value === null || Number.isNaN(value)) return "n/a";
  return value.toFixed(1);
}

function formatPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) return "n/a";
  return `${Math.round(value * 100)}%`;
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
      {label}
      <select
        className="h-8 rounded-md border border-input bg-background px-2 text-[13px] normal-case tracking-normal text-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function roundScore(value: number) {
  return Math.round(value * 10) / 10;
}

function formatLatency(value: number | null) {
  if (value === null) return "n/a";
  return `${Math.round(value).toLocaleString()} ms`;
}

function formatCost(value: number | string | null) {
  if (value === null) return "n/a";
  return `$${Number(value).toFixed(6)}`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function sourceLabel(value: string) {
  if (value === "dataset") return "Ground Truth";
  if (value === "monitored_runs") return "Evidence Audit";
  return value;
}

function metricLabel(value: string) {
  const labels: Record<string, string> = {
    answer_correctness: "correctness",
    faithfulness: "faithfulness",
    citation_precision: "citations",
    reference_coverage: "coverage",
    answer_relevance: "relevance",
    presentation_quality: "presentation",
    unsupported_claim_count: "unsupported",
  };
  return labels[value] ?? value.replaceAll("_", " ");
}
