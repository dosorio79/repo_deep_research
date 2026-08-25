import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { Fragment, useMemo, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";
import { ClipboardCheck, Gauge, MessageSquare, TriangleAlert } from "lucide-react";
import { ApiError } from "@/components/ApiError";
import { AppShell } from "@/components/AppShell";
import { EvidenceReferences } from "@/components/EvidenceReferences";
import { EmptyLine, Field, Panel } from "@/components/primitives";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getEvaluationResults,
  getEvaluationRuns,
  getEvaluationSummary,
  getGroundTruthEvaluationResults,
  getRetrievalEvaluationResults,
} from "@/lib/rag-client";
import type {
  ApiErrorShape,
  EvaluationDashboardSummary,
  EvaluationResultSummary,
  EvaluationRunSummary,
  GroundTruthEvaluationSummary,
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
    queryFn: ({ signal }) =>
      getEvaluationResults(
        DEFAULT_API_BASE_URL,
        { limit: 50, source_type: "monitored_runs" },
        signal,
      ),
    retry: false,
    staleTime: 5_000,
  });
  const groundTruthQuery = useQuery({
    queryKey: ["ground-truth-evaluation-results", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getGroundTruthEvaluationResults(DEFAULT_API_BASE_URL, signal),
    retry: false,
    staleTime: 30_000,
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
      {groundTruthQuery.error ? (
        <ApiError error={groundTruthQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {retrievalQuery.error ? (
        <ApiError error={retrievalQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {summaryQuery.error ? null : summaryQuery.data ? (
        <EvaluationDashboard
          summary={summaryQuery.data}
          runs={runsQuery.data?.runs ?? []}
          results={resultsQuery.data?.results ?? []}
          groundTruthResults={groundTruthQuery.data?.results ?? []}
          retrievalResults={retrievalQuery.data?.results ?? []}
          loadingRuns={runsQuery.isLoading}
          loadingResults={resultsQuery.isLoading}
          loadingGroundTruthResults={groundTruthQuery.isLoading}
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
    <Panel title="Output quality evaluation">
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
  groundTruthResults,
  retrievalResults,
  loadingRuns,
  loadingResults,
  loadingGroundTruthResults,
  loadingRetrievalResults,
  selectedContext,
  onContextChange,
}: {
  summary: EvaluationDashboardSummary;
  runs: EvaluationRunSummary[];
  results: EvaluationResultSummary[];
  groundTruthResults: GroundTruthEvaluationSummary[];
  retrievalResults: RetrievalEvaluationSummary[];
  loadingRuns: boolean;
  loadingResults: boolean;
  loadingGroundTruthResults: boolean;
  loadingRetrievalResults: boolean;
  selectedContext: string;
  onContextChange: (value: string) => void;
}) {
  const contextOptions = useMemo(() => evaluationContextOptions(results), [results]);
  if (summary.total_results === 0 && groundTruthResults.length === 0)
    return (
      <div className="space-y-3">
        <SearchEvaluationHighlights results={retrievalResults} loading={loadingRetrievalResults} />
        <Panel title="Recent evaluation runs">
          <EvaluationRunTable runs={runs} loading={loadingRuns} />
        </Panel>
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
  const postHocResults = visibleResults.filter((result) => result.source_type === "monitored_runs");
  const displayedPostHocResults = lowestScoringResults(postHocResults);

  return (
    <div className="space-y-3">
      <SearchEvaluationHighlights results={retrievalResults} loading={loadingRetrievalResults} />

      <SectionHeader
        title="Output quality evaluation"
        description="Answer scores below judge generated responses against their expected answer or returned evidence. These metrics are separate from the search retrieval checks above."
      />

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

      <Panel title="Answer reviews">
        <Tabs defaultValue="ground-truth" className="grid gap-3">
          <TabsList className="w-full justify-start overflow-x-auto sm:w-auto">
            <TabsTrigger value="ground-truth">
              Ground Truth Assessments ({groundTruthResults.length})
            </TabsTrigger>
            <TabsTrigger value="post-hoc">
              Post-hoc LLM Review (lowest {displayedPostHocResults.length} of{" "}
              {postHocResults.length})
            </TabsTrigger>
          </TabsList>
          <TabsContent value="ground-truth" className="mt-0">
            <GroundTruthAssessmentPanel
              results={groundTruthResults}
              loading={loadingGroundTruthResults}
            />
          </TabsContent>
          <TabsContent value="post-hoc" className="mt-0">
            <ReviewTabPanel
              title="Persisted live answers judged against their returned evidence."
              results={displayedPostHocResults}
              loading={loadingResults}
            />
          </TabsContent>
        </Tabs>
      </Panel>
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="border-t border-border pt-3">
      <h2 className="text-[14px] font-semibold">{title}</h2>
      <p className="mt-1 max-w-3xl text-[12px] text-muted-foreground">{description}</p>
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
  const visibleResults = curatedRetrievalHighlights(results);
  const heldOutResults = visibleResults.filter((item) =>
    item.source_label.toLowerCase().includes("datapeek held-out"),
  );
  const datasetGroups = groupRetrievalResultsByDataset(visibleResults);
  const selected =
    heldOutResults.find((item) => item.selected) ??
    visibleResults.find((item) => item.selected) ??
    heldOutResults[0] ??
    visibleResults[0];
  return (
    <Panel title="Search evaluation highlights">
      {loading ? <EmptyLine>Loading retrieval evaluation metrics.</EmptyLine> : null}
      {!loading && visibleResults.length === 0 ? (
        <EmptyLine>No persisted retrieval evaluation metrics are available.</EmptyLine>
      ) : null}
      {!loading && visibleResults.length > 0 ? (
        <>
          <div className="grid gap-3 xl:grid-cols-[280px_1fr]">
            <div className="rounded-md border border-border bg-secondary/20 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Production default
              </p>
              <div className="mt-2 grid gap-1">
                <Field label="Mode">{selected?.mode ?? "dense"}</Field>
                <Field label="Dataset">{selected?.dataset ?? "Not measured"}</Field>
                <Field label="File hit">{formatPercent(selected?.file_hit_rate ?? null)}</Field>
                <Field label="Symbol hit">{formatPercent(selected?.symbol_hit_rate ?? null)}</Field>
                <Field label="Records">{selected?.record_count ?? "0"}</Field>
                <Field label="Limit">{selected ? `top ${selected.limit}` : "top 0"}</Field>
              </div>
            </div>
            <div className="space-y-3">
              {datasetGroups.map(([dataset, datasetResults]) => (
                <div key={dataset} className="space-y-2">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-[13px] font-semibold">{dataset}</h3>
                    <span className="text-[11px] text-muted-foreground">
                      {datasetResults[0]?.record_count ?? 0} questions, top{" "}
                      {datasetResults[0]?.limit ?? 0} results
                    </span>
                  </div>
                  <div className="grid gap-2 md:grid-cols-3">
                    {datasetResults.map((item) => (
                      <RetrievalModeCard key={`${item.dataset}-${item.mode}`} item={item} />
                    ))}
                  </div>
                </div>
              ))}
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

function RetrievalModeCard({ item }: { item: RetrievalEvaluationSummary }) {
  return (
    <div className="rounded-md border border-border p-2">
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
  );
}

function ReviewTabPanel({
  title,
  results,
  loading,
}: {
  title: string;
  results: EvaluationResultSummary[];
  loading: boolean;
}) {
  return (
    <div className="grid gap-3">
      <div className="grid gap-2 md:grid-cols-3">
        <Field label="Loaded reviews">{results.length.toLocaleString()}</Field>
        <Field label="Average score">{formatScore(averageResultScore(results))}</Field>
        <Field label="Unsupported rate">{formatPercent(unsupportedClaimRate(results))}</Field>
      </div>
      <p className="text-[12px] text-muted-foreground">{title}</p>
      <EvaluationResultTable results={results} loading={loading} />
    </div>
  );
}

function GroundTruthAssessmentPanel({
  results,
  loading,
}: {
  results: GroundTruthEvaluationSummary[];
  loading: boolean;
}) {
  return (
    <div className="grid gap-3">
      <div className="grid gap-2 md:grid-cols-3">
        <Field label="Assessment rows">{results.length.toLocaleString()}</Field>
        <Field label="Best correctness">{formatScore(bestGroundTruthScore(results))}</Field>
        <Field label="Unsupported rows">
          {formatPercent(averageGroundTruthUnsupportedRate(results))}
        </Field>
      </div>
      <p className="text-[12px] text-muted-foreground">
        Offline dataset assessments summarize judged answers against versioned expected files and
        symbols.
      </p>
      <GroundTruthAssessmentTable results={results} loading={loading} />
    </div>
  );
}

function GroundTruthAssessmentTable({
  results,
  loading,
}: {
  results: GroundTruthEvaluationSummary[];
  loading: boolean;
}) {
  if (loading) return <EmptyLine>Loading ground-truth assessments.</EmptyLine>;
  if (results.length === 0)
    return <EmptyLine>No persisted ground-truth assessments are available.</EmptyLine>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[980px] text-left text-[12px]">
        <thead className="border-b border-border text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">Dataset</th>
            <th className="py-2 pr-3 font-medium">Approach</th>
            <th className="py-2 pr-3 font-medium">Records</th>
            <th className="py-2 pr-3 font-medium">Correct</th>
            <th className="py-2 pr-3 font-medium">Coverage</th>
            <th className="py-2 pr-3 font-medium">Faithful</th>
            <th className="py-2 pr-3 font-medium">Citations</th>
            <th className="py-2 pr-3 font-medium">Unsupported rows</th>
            <th className="py-2 pr-3 font-medium">Avg latency</th>
            <th className="py-2 pr-3 font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr key={`${result.dataset}-${result.run_kind}`} className="border-b border-border/60">
              <td className="max-w-[260px] break-words py-2 pr-3">{result.dataset}</td>
              <td className="py-2 pr-3">{result.run_kind}</td>
              <td className="py-2 pr-3 mono">{result.record_count}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.answer_correctness)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.reference_coverage)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.faithfulness)}</td>
              <td className="py-2 pr-3 mono">{formatScore(result.citation_precision)}</td>
              <td className="py-2 pr-3 mono">{formatPercent(result.unsupported_claim_rate)}</td>
              <td className="py-2 pr-3 mono">{formatLatency(result.average_latency_ms)}</td>
              <td className="py-2 pr-3 mono">{formatCost(result.total_estimated_cost_usd)}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
  const sections = [
    ["Completed", runs.filter((run) => run.status === "completed" && run.result_count > 0)],
    ["Zero-result", runs.filter((run) => run.status === "completed" && run.result_count === 0)],
    ["Failed", runs.filter((run) => run.status === "failed")],
    [
      "Running or pending",
      runs.filter((run) => run.status !== "completed" && run.status !== "failed"),
    ],
  ] as const;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[860px] text-left text-[12px]">
        <thead className="border-b border-border text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">Started</th>
            <th className="py-2 pr-3 font-medium">Source</th>
            <th className="py-2 pr-3 font-medium">Context</th>
            <th className="py-2 pr-3 font-medium">Eval version</th>
            <th className="py-2 pr-3 font-medium">Status</th>
            <th className="py-2 pr-3 font-medium">Results</th>
            <th className="py-2 pr-3 font-medium">Average</th>
            <th className="py-2 pr-3 font-medium">Unsupported</th>
          </tr>
        </thead>
        <tbody>
          {sections.map(([label, sectionRuns]) =>
            sectionRuns.length ? (
              <Fragment key={label}>
                <tr className="border-b border-border/60 bg-secondary/35">
                  <td
                    className="py-1.5 pr-3 text-[11px] uppercase tracking-wide text-muted-foreground"
                    colSpan={8}
                  >
                    {label}
                  </td>
                </tr>
                {sectionRuns.map((run) => (
                  <tr key={run.evaluation_run_id} className="border-b border-border/60">
                    <td className="py-2 pr-3 mono">{formatDate(run.started_at)}</td>
                    <td className="py-2 pr-3">{sourceLabel(run.source_type)}</td>
                    <td className="max-w-[240px] py-2 pr-3">{run.context_labels.join(", ")}</td>
                    <td className="py-2 pr-3 mono">
                      {formatVersion(
                        run.evaluation_app_version,
                        run.evaluation_version_provenance,
                      )}
                    </td>
                    <td className="py-2 pr-3">{run.status}</td>
                    <td className="py-2 pr-3 mono">{run.result_count}</td>
                    <td className="py-2 pr-3 mono">{formatScore(run.average_score)}</td>
                    <td className="py-2 pr-3 mono">{run.unsupported_claim_count}</td>
                  </tr>
                ))}
              </Fragment>
            ) : null,
          )}
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
      <table className="w-full min-w-[1420px] text-left text-[12px]">
        <thead className="border-b border-border text-muted-foreground">
          <tr>
            <th className="py-2 pr-3 font-medium">Question</th>
            <th className="py-2 pr-3 font-medium">Source</th>
            <th className="py-2 pr-3 font-medium">Context</th>
            <th className="py-2 pr-3 font-medium">Versions</th>
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
              <td className="py-2 pr-3 mono">
                <span className="block">
                  answer {formatVersion(result.answer_app_version, result.answer_version_provenance)}
                </span>
                <span className="block text-muted-foreground">
                  eval{" "}
                  {formatVersion(result.evaluation_app_version, result.evaluation_version_provenance)}
                </span>
              </td>
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
                  <div className="space-y-1">
                    <EvidenceReferences
                      evidenceIds={result.answer_evidence.map((item) => item.evidence_id)}
                      evidence={result.answer_evidence}
                      prefix=""
                      contentUnavailableLabel="No content snippet captured for this older recorded answer."
                    />
                    {result.answer_evidence.some((item) => !item.content) ? (
                      <span className="inline-flex rounded-sm border border-border bg-secondary/40 px-1.5 py-0.5 text-[11px] text-muted-foreground">
                        metadata only
                      </span>
                    ) : null}
                  </div>
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

function lowestScoringResults(results: EvaluationResultSummary[]) {
  return [...results].sort((left, right) => left.average_score - right.average_score).slice(0, 8);
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

function unsupportedClaimRate(results: EvaluationResultSummary[]) {
  if (results.length === 0) return null;
  return results.filter((result) => result.unsupported_claim_count > 0).length / results.length;
}

function bestGroundTruthScore(results: GroundTruthEvaluationSummary[]) {
  const scores = results
    .map((result) => result.answer_correctness)
    .filter((value): value is number => typeof value === "number");
  if (scores.length === 0) return null;
  return Math.max(...scores);
}

function averageGroundTruthUnsupportedRate(results: GroundTruthEvaluationSummary[]) {
  if (results.length === 0) return null;
  return (
    results.reduce((total, result) => total + result.unsupported_claim_rate, 0) / results.length
  );
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

function groupRetrievalResultsByDataset(results: RetrievalEvaluationSummary[]) {
  const groups = new Map<string, RetrievalEvaluationSummary[]>();
  for (const result of results) {
    groups.set(result.dataset, [...(groups.get(result.dataset) ?? []), result]);
  }
  return [...groups.entries()];
}

function curatedRetrievalHighlights(results: RetrievalEvaluationSummary[]) {
  return [
    ...latestRetrievalContext(results, (result) =>
      result.source_label.toLowerCase().includes("repo_deep_research development"),
    ),
    ...latestRetrievalContext(results, (result) =>
      result.source_label.toLowerCase().includes("datapeek held-out"),
    ),
  ];
}

function latestRetrievalContext(
  results: RetrievalEvaluationSummary[],
  matchesContext: (result: RetrievalEvaluationSummary) => boolean,
) {
  const contextResults = results.filter(matchesContext);
  const newest = [...contextResults].sort((left, right) => {
    return new Date(right.measured_at).getTime() - new Date(left.measured_at).getTime();
  })[0];
  if (!newest) return [];
  return contextResults.filter((result) => result.source_label === newest.source_label);
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

function formatVersion(version: string | null | undefined, provenance: string | null | undefined) {
  const value = version || "unknown";
  return provenance && provenance !== "exact" ? `${value} (${provenance})` : value;
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
