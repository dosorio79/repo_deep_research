import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
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
import { getMonitoringSummary } from "@/lib/rag-client";
import type { ApiErrorShape, MonitoringSummary } from "@/lib/rag-types";

const DEFAULT_API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "/api";

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
  const summaryQuery = useQuery({
    queryKey: ["monitoring-summary", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getMonitoringSummary(DEFAULT_API_BASE_URL, signal),
    retry: false,
    staleTime: 5_000,
  });

  return (
    <AppShell>
      <h1 className="sr-only">Repo Deep Research monitoring</h1>
      {summaryQuery.error ? (
        <ApiError error={summaryQuery.error as unknown as ApiErrorShape} />
      ) : null}
      {summaryQuery.data ? (
        <MonitoringDashboard summary={summaryQuery.data} />
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

function MonitoringDashboard({ summary }: { summary: MonitoringSummary }) {
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

function numericCost(value: number | string | null) {
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}
