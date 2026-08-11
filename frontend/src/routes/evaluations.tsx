import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ClipboardCheck, Gauge, MessageSquare, TriangleAlert } from "lucide-react";
import { ApiError } from "@/components/ApiError";
import { AppShell } from "@/components/AppShell";
import { EmptyLine, Field, Panel } from "@/components/primitives";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { getEvaluationResults, getEvaluationRuns, getEvaluationSummary } from "@/lib/rag-client";
import type {
  ApiErrorShape,
  EvaluationDashboardSummary,
  EvaluationResultSummary,
  EvaluationRunSummary,
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
      {summaryQuery.error ? null : summaryQuery.data ? (
        <EvaluationDashboard
          summary={summaryQuery.data}
          runs={runsQuery.data?.runs ?? []}
          results={resultsQuery.data?.results ?? []}
          loadingRuns={runsQuery.isLoading}
          loadingResults={resultsQuery.isLoading}
        />
      ) : summaryQuery.isLoading ? (
        <Panel title="Evaluations">
          <EmptyLine>Loading persisted evaluation results.</EmptyLine>
        </Panel>
      ) : (
        <EmptyEvaluations />
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
  loadingRuns,
  loadingResults,
}: {
  summary: EvaluationDashboardSummary;
  runs: EvaluationRunSummary[];
  results: EvaluationResultSummary[];
  loadingRuns: boolean;
  loadingResults: boolean;
}) {
  if (summary.total_results === 0) return <EmptyEvaluations />;

  const worstResults = [...results]
    .sort((left, right) => left.average_score - right.average_score)
    .slice(0, 8);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={ClipboardCheck}
          label="Evaluated answers"
          value={summary.total_results.toLocaleString()}
          detail={`${summary.completed_runs} completed runs, ${summary.failed_runs} failed`}
        />
        <MetricCard
          icon={Gauge}
          label="Average score"
          value={formatScore(summary.average_score)}
          detail="mean across judged metrics"
        />
        <MetricCard
          icon={TriangleAlert}
          label="Unsupported claims"
          value={`${Math.round(summary.unsupported_claim_rate * 100)}%`}
          detail="results with unsupported claims"
        />
        <MetricCard
          icon={MessageSquare}
          label="Loaded feedback-linked"
          value={countFeedbackLinked(results).toLocaleString()}
          detail="latest loaded results with feedback"
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <ChartPanel title="Average score by approach">
          <ChartContainer
            config={{ score: { label: "Average score", color: "var(--color-chart-1)" } }}
            className="h-[220px] w-full min-w-0 aspect-auto"
          >
            <BarChart accessibilityLayer data={runKindChartData(summary)}>
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
            <BarChart accessibilityLayer data={metricChartData(summary)}>
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
            <BarChart accessibilityLayer data={feedbackChartData(results)}>
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
            <Field label="Loaded average latency">{formatLatency(averageLatency(results))}</Field>
            <Field label="Loaded estimated cost">{formatCost(totalCost(results))}</Field>
            <Field label="All-results average score">{formatScore(summary.average_score)}</Field>
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
      <table className="w-full min-w-[920px] text-left text-[12px]">
        <thead className="border-b border-border text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">Question</th>
            <th className="py-2 pr-3 font-medium">Approach</th>
            <th className="py-2 pr-3 font-medium">Average</th>
            <th className="py-2 pr-3 font-medium">Grounded</th>
            <th className="py-2 pr-3 font-medium">Citations</th>
            <th className="py-2 pr-3 font-medium">Unsupported</th>
            <th className="py-2 pr-3 font-medium">Feedback</th>
            <th className="py-2 pr-3 font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr key={result.result_id} className="border-b border-border/60">
              <td className="max-w-[360px] break-words py-2 pr-3">{result.question}</td>
              <td className="py-2 pr-3">{result.run_kind ?? "unknown"}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.average_score)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.groundedness)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.citation_accuracy)}</td>
              <td className="py-2 pr-3 mono">{result.unsupported_claim_count}</td>
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

function runKindChartData(summary: EvaluationDashboardSummary) {
  return summary.average_by_run_kind.map((item) => ({
    label: item.run_kind ?? "unknown",
    score: roundScore(item.average_score),
  }));
}

function metricChartData(summary: EvaluationDashboardSummary) {
  return summary.metric_averages.map((item) => ({
    metric: item.metric.replace("_", " "),
    score: roundScore(item.average_score),
  }));
}

function feedbackChartData(results: EvaluationResultSummary[]) {
  const useful = results.filter((result) => result.feedback_useful > 0);
  const notUseful = results.filter((result) => result.feedback_not_useful > 0);
  return [
    { label: "useful", score: averageResultScore(useful) },
    { label: "not useful", score: averageResultScore(notUseful) },
  ];
}

function averageResultScore(results: EvaluationResultSummary[]) {
  if (results.length === 0) return 0;
  return roundScore(
    results.reduce((total, result) => total + result.average_score, 0) / results.length,
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
  return value === "monitored_runs" ? "monitored runs" : value;
}
