import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
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
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const runListParams = useMemo<MonitoringRunListParams>(() => {
    const params: MonitoringRunListParams = { limit, feedback };
    if (runKind !== "all") params.run_kind = runKind;
    if (status !== "all") params.has_error = status === "error";
    return params;
  }, [feedback, limit, runKind, status]);
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
          filters={{ runKind, status, feedback, limit }}
          onSelectRun={setSelectedRequestId}
          onRunKindChange={setRunKind}
          onStatusChange={setStatus}
          onFeedbackChange={setFeedback}
          onLimitChange={setLimit}
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
  onRunKindChange,
  onStatusChange,
  onFeedbackChange,
  onLimitChange,
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
  };
  onSelectRun: (requestId: string) => void;
  onRunKindChange: (value: ResearchKind | "all") => void;
  onStatusChange: (value: "all" | "error" | "ok") => void;
  onFeedbackChange: (value: MonitoringFeedbackFilter) => void;
  onLimitChange: (value: (typeof LIMIT_OPTIONS)[number]) => void;
}) {
  if (summary.total_runs === 0) return <EmptyMonitoring />;

  const feedbackTotal = summary.feedback.useful + summary.feedback.not_useful;
  const modelCost = summary.model_usage_by_model.reduce(
    (total, item) => total + numericCost(item.estimated_cost_usd),
    0,
  );
  const totalTokens = summary.model_usage_by_model.reduce(
    (total, item) => total + item.total_tokens,
    0,
  );
  const totalErrors = summary.errors_by_type.reduce((total, item) => total + item.count, 0);

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
        <MetricCard
          icon={Activity}
          label="Runs"
          value={summary.total_runs.toLocaleString()}
          detail={summary.runs_by_kind.map((item) => `${item.run_kind} ${item.count}`).join(", ")}
        />
        <MetricCard
          icon={Clock3}
          label="Latency"
          value={formatLatency(summary.average_latency_by_kind[0]?.average_latency_ms)}
          detail={summary.average_latency_by_kind
            .map((item) => `${item.run_kind} ${formatLatency(item.average_latency_ms)}`)
            .join(", ")}
        />
        <MetricCard
          icon={FileSearch}
          label="Retrieval"
          value={`${summary.retrieval_volume.retrieved_chunk_count.toLocaleString()} chunks`}
          detail={`${summary.retrieval_volume.unique_file_count.toLocaleString()} files`}
        />
        <MetricCard
          icon={CircleDollarSign}
          label="Tokens"
          value={totalTokens.toLocaleString()}
          detail={modelCost > 0 ? `$${modelCost.toFixed(6)}` : "cost unavailable"}
        />
        <MetricCard
          icon={MessageSquare}
          label="Feedback"
          value={feedbackTotal.toLocaleString()}
          detail={`${summary.feedback.useful} useful, ${summary.feedback.not_useful} not useful`}
        />
        <MetricCard
          icon={TriangleAlert}
          label="Errors"
          value={totalErrors.toLocaleString()}
          detail={summary.errors_by_type[0]?.error_type ?? "none"}
        />
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

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
        <Panel title="Recent runs">
          <RunFilters
            filters={filters}
            onRunKindChange={onRunKindChange}
            onStatusChange={onStatusChange}
            onFeedbackChange={onFeedbackChange}
            onLimitChange={onLimitChange}
          />
          <RunTable
            runs={runs}
            loading={runsLoading}
            selectedRequestId={selectedRequestId}
            onSelectRun={onSelectRun}
          />
        </Panel>
        <Panel title="Run detail">
          <RunDetail detail={selectedDetail} loading={detailLoading} />
        </Panel>
      </div>
    </div>
  );
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
    <div className="overflow-x-auto">
      <table className="w-full table-fixed border-collapse text-left text-[13px]">
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
