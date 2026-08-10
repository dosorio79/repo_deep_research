import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import {
  Activity,
  CircleDollarSign,
  Clock3,
  FileSearch,
  MessageSquare,
  TriangleAlert,
} from "lucide-react";
import { ApiError } from "@/components/ApiError";
import { AppShell } from "@/components/AppShell";
import { EmptyLine, Field, Panel } from "@/components/primitives";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { getMonitoringRunDetail, getMonitoringRuns, getMonitoringSummary } from "@/lib/rag-client";
import type {
  ApiErrorShape,
  MonitoringFeedbackFilter,
  MonitoringRunListParams,
  MonitoringRunDetail,
  MonitoringRunSummary,
  MonitoringSummary,
  ResearchKind,
} from "@/lib/rag-types";

const DEFAULT_API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "/api";
const LIMIT_OPTIONS = [25, 50, 100] as const;
const DATE_RANGE_OPTIONS = [
  ["all", "All loaded"],
  ["24h", "Newest 24h"],
  ["7d", "Newest 7d"],
  ["30d", "Newest 30d"],
] as const;
type DateRangeFilter = (typeof DATE_RANGE_OPTIONS)[number][0];
const RUN_KIND_CHART_CONFIG = {
  direct: { label: "Direct", color: "var(--color-chart-1)" },
  agentic: { label: "Agentic", color: "var(--color-chart-2)" },
};

export const Route = createFileRoute("/monitoring")({
  head: () => ({
    meta: [
      { title: "Monitoring - Repo Deep Research" },
      {
        name: "description",
        content: "PostgreSQL-backed run monitoring and feedback summary.",
      },
      { property: "og:title", content: "Monitoring - Repo Deep Research" },
      {
        property: "og:description",
        content: "Persisted monitoring panels for repository research runs.",
      },
    ],
  }),
  component: MonitoringView,
});

function MonitoringView() {
  const [runKind, setRunKind] = useState<ResearchKind | "all">("all");
  const [status, setStatus] = useState<"all" | "error" | "ok">("all");
  const [feedback, setFeedback] = useState<MonitoringFeedbackFilter>("all");
  const [limit, setLimit] = useState<(typeof LIMIT_OPTIONS)[number]>(50);
  const [dateRange, setDateRange] = useState<DateRangeFilter>("all");
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const runListParams = useMemo<MonitoringRunListParams>(() => {
    const params: MonitoringRunListParams = { limit, feedback };
    if (runKind !== "all") params.run_kind = runKind;
    if (status !== "all") params.has_error = status === "error";
    return params;
  }, [feedback, limit, runKind, status]);

  useEffect(() => {
    setSelectedRequestId(null);
  }, [dateRange, feedback, limit, runKind, status]);

  const summaryQuery = useQuery({
    queryKey: ["monitoring-summary", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getMonitoringSummary(DEFAULT_API_BASE_URL, signal),
    retry: false,
    staleTime: 5_000,
  });
  const runsQuery = useQuery({
    queryKey: ["monitoring-runs", DEFAULT_API_BASE_URL, runListParams],
    queryFn: ({ signal }) => getMonitoringRuns(DEFAULT_API_BASE_URL, runListParams, signal),
    retry: false,
    staleTime: 5_000,
  });
  const detailQuery = useQuery({
    queryKey: ["monitoring-run-detail", DEFAULT_API_BASE_URL, selectedRequestId],
    queryFn: ({ signal }) =>
      getMonitoringRunDetail(DEFAULT_API_BASE_URL, selectedRequestId ?? "", signal),
    enabled: selectedRequestId !== null,
    retry: false,
    staleTime: 5_000,
  });

  return (
    <AppShell>
      <h1 className="sr-only">Repo Deep Research monitoring</h1>
      {summaryQuery.error ? (
        <ApiError error={summaryQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {runsQuery.error ? <ApiError error={runsQuery.error as unknown as ApiErrorShape} /> : null}
      {detailQuery.error ? (
        <ApiError error={detailQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {summaryQuery.data ? (
        <MonitoringDashboard
          summary={summaryQuery.data}
          runs={runsQuery.data?.runs ?? []}
          runsLoading={runsQuery.isLoading}
          selectedRequestId={selectedRequestId}
          selectedDetail={detailQuery.data ?? null}
          detailLoading={detailQuery.isLoading}
          filters={{ runKind, status, feedback, limit, dateRange }}
          onSelectRun={setSelectedRequestId}
          onCloseRunDetail={() => setSelectedRequestId(null)}
          onRunKindChange={setRunKind}
          onStatusChange={setStatus}
          onFeedbackChange={setFeedback}
          onLimitChange={setLimit}
          onDateRangeChange={setDateRange}
        />
      ) : summaryQuery.isLoading ? (
        <Panel title="Monitoring">
          <EmptyLine>Loading persisted run metrics.</EmptyLine>
        </Panel>
      ) : (
        <EmptyMonitoring />
      )}
    </AppShell>
  );
}

function EmptyMonitoring() {
  return (
    <Panel title="Monitoring">
      <EmptyLine>
        No persisted monitoring rows are available. Run a direct or agentic query first.
      </EmptyLine>
    </Panel>
  );
}

function MonitoringDashboard({
  summary,
  runs,
  runsLoading,
  selectedRequestId,
  selectedDetail,
  detailLoading,
  filters,
  onSelectRun,
  onCloseRunDetail,
  onRunKindChange,
  onStatusChange,
  onFeedbackChange,
  onLimitChange,
  onDateRangeChange,
}: {
  summary: MonitoringSummary;
  runs: MonitoringRunSummary[];
  runsLoading: boolean;
  selectedRequestId: string | null;
  selectedDetail: MonitoringRunDetail | null;
  detailLoading: boolean;
  filters: {
    runKind: ResearchKind | "all";
    status: "all" | "error" | "ok";
    feedback: MonitoringFeedbackFilter;
    limit: (typeof LIMIT_OPTIONS)[number];
    dateRange: DateRangeFilter;
  };
  onSelectRun: (requestId: string) => void;
  onCloseRunDetail: () => void;
  onRunKindChange: (value: ResearchKind | "all") => void;
  onStatusChange: (value: "all" | "error" | "ok") => void;
  onFeedbackChange: (value: MonitoringFeedbackFilter) => void;
  onLimitChange: (value: (typeof LIMIT_OPTIONS)[number]) => void;
  onDateRangeChange: (value: DateRangeFilter) => void;
}) {
  const scopedRuns = useMemo(
    () => filterRunsByDateRange(runs, filters.dateRange),
    [filters.dateRange, runs],
  );
  const scopeSummary = useMemo(() => buildRunScopeSummary(scopedRuns), [scopedRuns]);

  useEffect(() => {
    if (
      selectedRequestId !== null &&
      !runsLoading &&
      !scopedRuns.some((run) => run.request_id === selectedRequestId)
    ) {
      onCloseRunDetail();
    }
  }, [onCloseRunDetail, runsLoading, scopedRuns, selectedRequestId]);

  if (summary.total_runs === 0) return <EmptyMonitoring />;

  return (
    <div className="space-y-3">
      <DashboardScopeToolbar
        filters={filters}
        displayedRunCount={scopedRuns.length}
        loadedRunCount={runs.length}
        onDateRangeChange={onDateRangeChange}
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard
          icon={Activity}
          label="Runs"
          value={scopeSummary.totalRuns.toLocaleString()}
          detail={`${scopeSummary.directRuns.toLocaleString()} direct, ${scopeSummary.agenticRuns.toLocaleString()} agentic`}
        />
        <MetricCard
          icon={Clock3}
          label="Latency"
          value={formatLatency(scopeSummary.averageLatencyMs)}
          detail={`retrieval avg ${formatLatency(scopeSummary.averageRetrievalLatencyMs)}`}
        />
        <MetricCard
          icon={FileSearch}
          label="Retrieval"
          value={`${scopeSummary.retrievedChunkCount.toLocaleString()} chunks`}
          detail={`${scopeSummary.uniqueFileCount.toLocaleString()} files`}
        />
        <MetricCard
          icon={CircleDollarSign}
          label="Cost"
          value={formatCost(scopeSummary.estimatedCostUsd) ?? "$0.000000"}
          detail="estimated for current scope"
        />
        <MetricCard
          icon={MessageSquare}
          label="Feedback"
          value={scopeSummary.feedbackTotal.toLocaleString()}
          detail={`${scopeSummary.feedbackUseful} useful, ${scopeSummary.feedbackNotUseful} not useful`}
        />
        <MetricCard
          icon={TriangleAlert}
          label="Errors"
          value={scopeSummary.errorCount.toLocaleString()}
          detail="in current scope"
        />
      </div>

      <Panel title="Recent runs">
        <RunFilters
          filters={filters}
          onRunKindChange={onRunKindChange}
          onStatusChange={onStatusChange}
          onFeedbackChange={onFeedbackChange}
          onLimitChange={onLimitChange}
        />
        <RunTable
          runs={scopedRuns}
          loading={runsLoading}
          selectedRequestId={selectedRequestId}
          onSelectRun={onSelectRun}
        />
      </Panel>

      <section className="space-y-2">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-[15px] font-semibold">Aggregations for current scope</h2>
            <p className="text-[12px] text-muted-foreground">
              Charts summarize the runs currently shown above, including date and filter selections.
            </p>
          </div>
          <span className="mono text-[11px] text-muted-foreground">
            {scopedRuns.length.toLocaleString()} of {runs.length.toLocaleString()} loaded runs
          </span>
        </div>
        <MonitoringCharts summary={summary} runs={scopedRuns} loading={runsLoading} />
      </section>

      <section className="space-y-2">
        <div>
          <h2 className="text-[15px] font-semibold">All-time persisted summary</h2>
          <p className="text-[12px] text-muted-foreground">
            These panels use the full persisted monitoring summary, independent of dashboard scope.
          </p>
        </div>
        <div className="grid gap-3 lg:grid-cols-2">
          <Panel title="Runs by kind">
            {summary.runs_by_kind.map((item) => (
              <Field key={item.run_kind} label={item.run_kind}>
                {item.count.toLocaleString()}
              </Field>
            ))}
          </Panel>
          <Panel title="Average latency">
            {summary.average_latency_by_kind.map((item) => (
              <Field key={item.run_kind} label={item.run_kind}>
                {formatLatency(item.average_latency_ms)}
              </Field>
            ))}
          </Panel>
          <Panel title="Model usage">
            {summary.model_usage_by_model.length ? (
              summary.model_usage_by_model.map((item) => (
                <Field key={`${item.provider}-${item.model}`} label={item.model}>
                  {item.total_tokens.toLocaleString()} tokens
                </Field>
              ))
            ) : (
              <EmptyLine>No model usage rows with token totals yet.</EmptyLine>
            )}
          </Panel>
          <Panel title="Errors by type">
            {summary.errors_by_type.length ? (
              summary.errors_by_type.map((item) => (
                <Field key={item.error_type} label={item.error_type}>
                  {item.count.toLocaleString()}
                </Field>
              ))
            ) : (
              <EmptyLine>No persisted run errors.</EmptyLine>
            )}
          </Panel>
        </div>
      </section>

      <RunDetailSheet
        open={selectedRequestId !== null}
        detail={selectedDetail}
        loading={detailLoading}
        onOpenChange={(open) => {
          if (!open) onCloseRunDetail();
        }}
      />
    </div>
  );
}

function MonitoringCharts({
  summary,
  runs,
  loading,
}: {
  summary: MonitoringSummary;
  runs: MonitoringRunSummary[];
  loading: boolean;
}) {
  const chartData = useMemo(() => buildMonitoringChartData(runs), [runs]);

  if (loading) {
    return (
      <Panel title="Monitoring charts">
        <EmptyLine>Loading chart data from persisted runs.</EmptyLine>
      </Panel>
    );
  }

  if (runs.length === 0) {
    return (
      <Panel title="Monitoring charts">
        <EmptyLine>No chart data matches the selected filters.</EmptyLine>
      </Panel>
    );
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
      <ChartPanel
        title="Runs over time"
        detail={`${chartData.totalDisplayedRuns.toLocaleString()} recent runs in the current view`}
      >
        <ChartContainer
          config={RUN_KIND_CHART_CONFIG}
          className="h-[220px] w-full min-w-0 aspect-auto"
        >
          <LineChart accessibilityLayer data={chartData.runsOverTime}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="bucket" tickLine={false} axisLine={false} minTickGap={16} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={30} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Line
              type="monotone"
              dataKey="direct"
              stroke="var(--color-direct)"
              strokeWidth={2}
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="agentic"
              stroke="var(--color-agentic)"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ChartContainer>
      </ChartPanel>

      <ChartPanel
        title="Latency by mode"
        detail={`Slowest average ${formatLatency(chartData.maxAverageLatency)}`}
      >
        <ChartContainer
          config={{
            total: { label: "Total latency", color: "var(--color-chart-1)" },
            retrieval: { label: "Retrieval latency", color: "var(--color-chart-2)" },
          }}
          className="h-[220px] w-full min-w-0 aspect-auto"
        >
          <BarChart accessibilityLayer data={chartData.latencyByKind}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="run_kind" tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} width={44} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="total" fill="var(--color-total)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="retrieval" fill="var(--color-retrieval)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartPanel>

      <ChartPanel
        title="Retrieval volume"
        detail={`${chartData.visibleRetrievedChunks.toLocaleString()} chunks, ${chartData.visibleUniqueFiles.toLocaleString()} files in the current view (${summary.retrieval_volume.retrieved_chunk_count.toLocaleString()} chunks, ${summary.retrieval_volume.unique_file_count.toLocaleString()} files total)`}
      >
        <ChartContainer
          config={{
            chunks: { label: "Chunks", color: "var(--color-chart-3)" },
            files: { label: "Files", color: "var(--color-chart-4)" },
          }}
          className="h-[220px] w-full min-w-0 aspect-auto"
        >
          <BarChart accessibilityLayer data={chartData.retrievalByRun}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={10} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={34} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="chunks" fill="var(--color-chunks)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="files" fill="var(--color-files)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartPanel>

      <ChartPanel
        title="Estimated cost by mode"
        detail={`${formatCost(chartData.totalVisibleCost) ?? "cost unavailable"} in the current view`}
      >
        {chartData.costByKind.some((item) => item.cost > 0) ? (
          <ChartContainer
            config={{
              cost: { label: "Estimated cost", color: "var(--color-chart-1)" },
            }}
            className="h-[220px] w-full min-w-0 aspect-auto"
          >
            <BarChart accessibilityLayer data={chartData.costByKind}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="run_kind" tickLine={false} axisLine={false} />
              <YAxis tickLine={false} axisLine={false} width={54} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <Bar dataKey="cost" fill="var(--color-cost)" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ChartContainer>
        ) : (
          <EmptyLine>No estimated cost is available for the selected runs.</EmptyLine>
        )}
      </ChartPanel>

      <ChartPanel
        title="Feedback mix"
        detail={`${chartData.visiblePositiveFeedbackRate}% positive feedback rate`}
      >
        <ChartContainer
          config={{
            count: { label: "Feedback", color: "var(--color-chart-5)" },
          }}
          className="h-[220px] w-full min-w-0 aspect-auto"
        >
          <BarChart accessibilityLayer data={chartData.feedbackMix}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={30} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="count" fill="var(--color-count)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartPanel>

      <ChartPanel
        title="Errors and tool calls"
        detail={`${chartData.visibleErrors.toLocaleString()} errors, ${chartData.averageAgenticToolCalls.toFixed(1)} avg agentic tool calls`}
      >
        <ChartContainer
          config={{
            errors: { label: "Errors", color: "var(--color-chart-1)" },
            toolCalls: { label: "Avg tool calls", color: "var(--color-chart-2)" },
          }}
          className="h-[220px] w-full min-w-0 aspect-auto"
        >
          <BarChart accessibilityLayer data={chartData.errorsAndToolCalls}>
            <CartesianGrid vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={34} />
            <ChartTooltip content={<ChartTooltipContent />} />
            <Bar dataKey="errors" fill="var(--color-errors)" radius={[3, 3, 0, 0]} />
            <Bar dataKey="toolCalls" fill="var(--color-toolCalls)" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </ChartPanel>
    </div>
  );
}

function ChartPanel({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children: ReactNode;
}) {
  return (
    <Panel
      title={title}
      right={
        <span className="max-w-[190px] truncate text-right mono text-[11px] text-muted-foreground sm:max-w-[320px]">
          {detail}
        </span>
      }
    >
      {children}
    </Panel>
  );
}

function DashboardScopeToolbar({
  filters,
  displayedRunCount,
  loadedRunCount,
  onDateRangeChange,
}: {
  filters: {
    runKind: ResearchKind | "all";
    status: "all" | "error" | "ok";
    feedback: MonitoringFeedbackFilter;
    limit: (typeof LIMIT_OPTIONS)[number];
    dateRange: DateRangeFilter;
  };
  displayedRunCount: number;
  loadedRunCount: number;
  onDateRangeChange: (value: DateRangeFilter) => void;
}) {
  return (
    <Panel
      title="Dashboard scope"
      right={
        <span className="mono text-[11px] text-muted-foreground">
          {displayedRunCount.toLocaleString()} / {loadedRunCount.toLocaleString()} loaded
        </span>
      }
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="text-[12px] text-muted-foreground">
            Cards and charts summarize the loaded runs that match these filters. Date ranges are
            anchored to the newest loaded run.
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <ScopeChip label="Kind" value={scopeKindLabel(filters.runKind)} />
            <ScopeChip label="Status" value={scopeStatusLabel(filters.status)} />
            <ScopeChip label="Feedback" value={scopeFeedbackLabel(filters.feedback)} />
            <ScopeChip label="Limit" value={filters.limit.toLocaleString()} />
            <ScopeChip label="Date" value={scopeDateLabel(filters.dateRange)} />
          </div>
        </div>
        <div
          className="inline-flex w-full rounded-md border border-border bg-secondary/50 p-1 sm:w-auto"
          aria-label="Date range"
        >
          {DATE_RANGE_OPTIONS.map(([value, label]) => (
            <button
              key={value}
              type="button"
              className="h-8 flex-1 rounded px-2 text-[12px] font-medium text-muted-foreground transition hover:text-foreground data-[active=true]:bg-background data-[active=true]:text-foreground data-[active=true]:shadow-sm sm:flex-none"
              data-active={filters.dateRange === value}
              aria-pressed={filters.dateRange === value}
              onClick={() => onDateRangeChange(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </Panel>
  );
}

function ScopeChip({ label, value }: { label: string; value: string }) {
  return (
    <span className="rounded-md border border-border bg-background px-2 py-1 text-[11px] text-muted-foreground">
      <span className="font-semibold text-foreground">{label}</span>: {value}
    </span>
  );
}

function scopeKindLabel(value: ResearchKind | "all") {
  if (value === "all") return "All";
  return value === "agentic" ? "Agentic" : "Direct";
}

function scopeStatusLabel(value: "all" | "error" | "ok") {
  if (value === "all") return "All";
  return value === "error" ? "Error" : "No error";
}

function scopeFeedbackLabel(value: MonitoringFeedbackFilter) {
  if (value === "not_useful") return "Not useful";
  return value === "all" ? "All" : value.charAt(0).toUpperCase() + value.slice(1);
}

function scopeDateLabel(value: DateRangeFilter) {
  return DATE_RANGE_OPTIONS.find(([optionValue]) => optionValue === value)?.[1] ?? "All loaded";
}

function buildMonitoringChartData(runs: MonitoringRunSummary[]) {
  const runsAscending = [...runs].sort(
    (left, right) => new Date(left.completed_at).getTime() - new Date(right.completed_at).getTime(),
  );
  const buckets = new Map<string, { bucket: string; direct: number; agentic: number }>();
  for (const run of runsAscending) {
    const bucket = formatDateTime(run.completed_at);
    const current = buckets.get(bucket) ?? { bucket, direct: 0, agentic: 0 };
    current[run.run_kind] += 1;
    buckets.set(bucket, current);
  }

  const latencyByKind = (["direct", "agentic"] as const).map((runKind) => {
    const matching = runs.filter((run) => run.run_kind === runKind);
    return {
      run_kind: runKind,
      total: average(matching.map((run) => run.latency_ms_total)),
      retrieval: average(matching.map((run) => run.latency_ms_retrieval)),
    };
  });
  const costByKind = (["direct", "agentic"] as const).map((runKind) => ({
    run_kind: runKind,
    cost: sum(
      runs
        .filter((run) => run.run_kind === runKind)
        .map((run) => numericCost(run.total_estimated_cost_usd)),
    ),
  }));
  const visibleFeedback = runs.reduce(
    (total, run) => ({
      useful: total.useful + run.feedback_useful,
      notUseful: total.notUseful + run.feedback_not_useful,
    }),
    { useful: 0, notUseful: 0 },
  );
  const visibleFeedbackTotal = visibleFeedback.useful + visibleFeedback.notUseful;
  const agenticRuns = runs.filter((run) => run.run_kind === "agentic");

  return {
    runsOverTime: [...buckets.values()],
    latencyByKind,
    retrievalByRun: runsAscending.slice(-12).map((run) => ({
      label: `${run.run_kind} ${shortCommit(run.request_id)}`,
      chunks: run.retrieved_chunk_count,
      files: run.unique_file_count,
    })),
    costByKind,
    feedbackMix: [
      { label: "Useful", count: visibleFeedback.useful },
      { label: "Not useful", count: visibleFeedback.notUseful },
    ],
    errorsAndToolCalls: [
      {
        label: "Current view",
        errors: runs.filter((run) => run.has_error).length,
        toolCalls: average(agenticRuns.map((run) => run.tool_call_count)),
      },
    ],
    totalDisplayedRuns: runs.length,
    visibleRetrievedChunks: sum(runs.map((run) => run.retrieved_chunk_count)),
    visibleUniqueFiles: sum(runs.map((run) => run.unique_file_count)),
    maxAverageLatency: Math.max(...latencyByKind.map((item) => item.total), 0),
    totalVisibleCost: sum(costByKind.map((item) => item.cost)),
    visiblePositiveFeedbackRate: visibleFeedbackTotal
      ? Math.round((visibleFeedback.useful / visibleFeedbackTotal) * 100)
      : 0,
    visibleErrors: runs.filter((run) => run.has_error).length,
    averageAgenticToolCalls: average(agenticRuns.map((run) => run.tool_call_count)),
  };
}

function filterRunsByDateRange(runs: MonitoringRunSummary[], dateRange: DateRangeFilter) {
  if (dateRange === "all" || runs.length === 0) return runs;

  const windowMsByRange: Record<Exclude<DateRangeFilter, "all">, number> = {
    "24h": 24 * 60 * 60 * 1_000,
    "7d": 7 * 24 * 60 * 60 * 1_000,
    "30d": 30 * 24 * 60 * 60 * 1_000,
  };
  const anchorTime = Math.max(...runs.map((run) => new Date(run.completed_at).getTime()));
  const cutoffTime = anchorTime - windowMsByRange[dateRange];
  return runs.filter((run) => new Date(run.completed_at).getTime() >= cutoffTime);
}

function buildRunScopeSummary(runs: MonitoringRunSummary[]) {
  const feedbackUseful = sum(runs.map((run) => run.feedback_useful));
  const feedbackNotUseful = sum(runs.map((run) => run.feedback_not_useful));

  return {
    totalRuns: runs.length,
    directRuns: runs.filter((run) => run.run_kind === "direct").length,
    agenticRuns: runs.filter((run) => run.run_kind === "agentic").length,
    averageLatencyMs: average(runs.map((run) => run.latency_ms_total)),
    averageRetrievalLatencyMs: average(runs.map((run) => run.latency_ms_retrieval)),
    retrievedChunkCount: sum(runs.map((run) => run.retrieved_chunk_count)),
    uniqueFileCount: sum(runs.map((run) => run.unique_file_count)),
    estimatedCostUsd: sum(runs.map((run) => numericCost(run.total_estimated_cost_usd))),
    feedbackUseful,
    feedbackNotUseful,
    feedbackTotal: feedbackUseful + feedbackNotUseful,
    errorCount: runs.filter((run) => run.has_error).length,
  };
}

function average(values: number[]) {
  const validValues = values.filter((value) => Number.isFinite(value));
  if (validValues.length === 0) return 0;
  return validValues.reduce((total, value) => total + value, 0) / validValues.length;
}

function sum(values: number[]) {
  return values.reduce((total, value) => total + value, 0);
}

function RunFilters({
  filters,
  onRunKindChange,
  onStatusChange,
  onFeedbackChange,
  onLimitChange,
}: {
  filters: {
    runKind: ResearchKind | "all";
    status: "all" | "error" | "ok";
    feedback: MonitoringFeedbackFilter;
    limit: (typeof LIMIT_OPTIONS)[number];
  };
  onRunKindChange: (value: ResearchKind | "all") => void;
  onStatusChange: (value: "all" | "error" | "ok") => void;
  onFeedbackChange: (value: MonitoringFeedbackFilter) => void;
  onLimitChange: (value: (typeof LIMIT_OPTIONS)[number]) => void;
}) {
  return (
    <div className="mb-3 grid gap-2 md:grid-cols-4">
      <SelectField
        label="Kind"
        value={filters.runKind}
        onChange={(value) => onRunKindChange(value as ResearchKind | "all")}
        options={[
          ["all", "All"],
          ["direct", "Direct"],
          ["agentic", "Agentic"],
        ]}
      />
      <SelectField
        label="Status"
        value={filters.status}
        onChange={(value) => onStatusChange(value as "all" | "error" | "ok")}
        options={[
          ["all", "All"],
          ["ok", "No error"],
          ["error", "Error"],
        ]}
      />
      <SelectField
        label="Feedback"
        value={filters.feedback}
        onChange={(value) => onFeedbackChange(value as MonitoringFeedbackFilter)}
        options={[
          ["all", "All"],
          ["useful", "Useful"],
          ["not_useful", "Not useful"],
          ["none", "None"],
        ]}
      />
      <SelectField
        label="Limit"
        value={String(filters.limit)}
        onChange={(value) => onLimitChange(Number(value) as (typeof LIMIT_OPTIONS)[number])}
        options={LIMIT_OPTIONS.map((value) => [String(value), String(value)])}
      />
    </div>
  );
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

function RunTable({
  runs,
  loading,
  selectedRequestId,
  onSelectRun,
}: {
  runs: MonitoringRunSummary[];
  loading: boolean;
  selectedRequestId: string | null;
  onSelectRun: (requestId: string) => void;
}) {
  if (loading) return <EmptyLine>Loading recent runs.</EmptyLine>;
  if (runs.length === 0) return <EmptyLine>No runs match the selected filters.</EmptyLine>;

  return (
    <div className="max-w-full overflow-x-auto">
      <table className="min-w-[820px] table-fixed border-collapse text-left text-[13px]">
        <thead>
          <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
            <th className="w-[126px] py-2 pr-3 font-semibold">Time</th>
            <th className="w-[82px] py-2 pr-3 font-semibold">Kind</th>
            <th className="w-[190px] py-2 pr-3 font-semibold">Repository</th>
            <th className="w-[82px] py-2 pr-3 font-semibold">Mode</th>
            <th className="w-[96px] py-2 pr-3 text-right font-semibold">Retrieval</th>
            <th className="w-[96px] py-2 pr-3 text-right font-semibold">Latency</th>
            <th className="w-[92px] py-2 pr-3 text-right font-semibold">Feedback</th>
            <th className="w-[74px] py-2 text-right font-semibold">Status</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr
              key={run.request_id}
              className="cursor-pointer border-b border-border/70 hover:bg-secondary data-[selected=true]:bg-secondary"
              data-selected={run.request_id === selectedRequestId}
              onClick={() => onSelectRun(run.request_id)}
            >
              <td className="truncate py-2 pr-3 mono text-[11px]">
                {formatDateTime(run.completed_at)}
              </td>
              <td className="py-2 pr-3">{run.run_kind}</td>
              <td className="truncate py-2 pr-3" title={run.repository_name}>
                {run.repository_name}
                <span className="block truncate mono text-[11px] text-muted-foreground">
                  {shortCommit(run.commit_hash)}
                </span>
              </td>
              <td className="py-2 pr-3">{run.retrieval_mode}</td>
              <td className="py-2 pr-3 text-right mono text-[11px]">
                {run.retrieved_chunk_count} / {run.unique_file_count}
              </td>
              <td className="py-2 pr-3 text-right mono text-[11px]">
                {formatLatency(run.latency_ms_total)}
              </td>
              <td className="py-2 pr-3 text-right mono text-[11px]">
                {run.feedback_useful} / {run.feedback_not_useful}
              </td>
              <td className="py-2 text-right">
                <span className={run.has_error ? "text-destructive" : "text-muted-foreground"}>
                  {run.has_error ? "error" : "ok"}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunDetailSheet({
  open,
  detail,
  loading,
  onOpenChange,
}: {
  open: boolean;
  detail: MonitoringRunDetail | null;
  loading: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex w-full flex-col overflow-y-auto p-4 sm:max-w-md">
        <SheetHeader className="pr-8 text-left">
          <SheetTitle>Run detail</SheetTitle>
          <SheetDescription>Persisted metadata and feedback for the selected run.</SheetDescription>
        </SheetHeader>
        <div className="mt-3">
          <RunDetail detail={detail} loading={loading} />
        </div>
      </SheetContent>
    </Sheet>
  );
}

function RunDetail({ detail, loading }: { detail: MonitoringRunDetail | null; loading: boolean }) {
  if (loading) return <EmptyLine>Loading run detail.</EmptyLine>;
  if (!detail) return <EmptyLine>Select a recent run to inspect persisted detail.</EmptyLine>;

  const totalTokens = detail.model_usage.reduce(
    (total, item) => total + Number(item.total_tokens ?? 0),
    0,
  );

  return (
    <div className="space-y-3">
      <div className="grid gap-1">
        <div className="truncate text-[15px] font-semibold">{detail.repository_name}</div>
        <div className="mono text-[11px] text-muted-foreground">
          {detail.branch} @ {shortCommit(detail.commit_hash)}
        </div>
      </div>
      <div className="grid gap-1">
        <Field label="Request">{detail.request_id}</Field>
        <Field label="Kind">{detail.run_kind}</Field>
        <Field label="Mode">{detail.question_mode}</Field>
        <Field label="Retrieval">
          {detail.retrieval_mode}, limit {detail.retrieval_limit}
        </Field>
        <Field label="Evidence">{detail.evidence_count.toLocaleString()}</Field>
        <Field label="Tool calls">{detail.tool_call_count.toLocaleString()}</Field>
        <Field label="Latency">{formatLatency(detail.latency_ms_total)}</Field>
        <Field label="Tokens">{totalTokens.toLocaleString()}</Field>
        <Field label="Cost">
          {formatCost(detail.total_estimated_cost_usd) ?? "cost unavailable"}
        </Field>
        <Field label="Insufficient evidence">{detail.insufficient_evidence ? "yes" : "no"}</Field>
      </div>
      {detail.error_type ? (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 p-2">
          <div className="text-[12px] font-semibold text-destructive">{detail.error_type}</div>
          <div className="mt-1 break-words mono text-[11px] text-muted-foreground">
            {detail.error_message ?? "No error message persisted."}
          </div>
        </div>
      ) : null}
      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          Feedback
        </div>
        {detail.feedback_events.length ? (
          <div className="space-y-1">
            {detail.feedback_events.map((event) => (
              <div key={event.feedback_id} className="rounded-md border border-border p-2">
                <div className="text-[12px] font-medium">
                  {event.useful ? "Useful" : "Not useful"}
                </div>
                {event.comment ? (
                  <div className="mt-1 break-words text-[12px] text-muted-foreground">
                    {event.comment}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <EmptyLine>No linked feedback for this run.</EmptyLine>
        )}
      </div>
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  detail,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <section className="panel p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <Icon className="h-3.5 w-3.5 text-primary" aria-hidden />
      </div>
      <div className="mt-2 truncate text-[20px] font-semibold leading-tight">{value}</div>
      <div className="mt-1 truncate mono text-[11px] text-muted-foreground">{detail}</div>
    </section>
  );
}

function formatLatency(value: number | null | undefined) {
  return typeof value === "number" ? `${Math.round(value).toLocaleString()} ms` : "unknown";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function shortCommit(value: string) {
  return value.slice(0, 7);
}

function formatCost(value: number | string | null) {
  const cost = numericCost(value);
  return cost > 0 ? `$${cost.toFixed(6)}` : null;
}

function numericCost(value: number | string | null) {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}
