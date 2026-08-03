import { createFileRoute } from "@tanstack/react-router";
import { Activity, CircleDollarSign, Clock3, FileSearch, Gauge } from "lucide-react";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { EmptyLine, Field, Panel } from "@/components/primitives";
import { loadLatestRagRun } from "@/lib/latest-rag-run";
import type { RagRunResult } from "@/lib/rag-types";

export const Route = createFileRoute("/monitoring")({
  head: () => ({
    meta: [
      { title: "Monitoring — Repo Deep Research M3.6" },
      {
        name: "description",
        content: "Latest RAG run outcome from the local frontend harness.",
      },
      { property: "og:title", content: "Monitoring — Repo Deep Research M3.6" },
      {
        property: "og:description",
        content: "Latest RAG run telemetry for the Repo Deep Research harness.",
      },
    ],
  }),
  component: MonitoringView,
});

function MonitoringView() {
  const [latestRun, setLatestRun] = useState<RagRunResult | null>(null);

  useEffect(() => {
    setLatestRun(loadLatestRagRun());
  }, []);

  return (
    <AppShell>
      <h1 className="sr-only">Repo Deep Research monitoring</h1>
      {latestRun ? <LatestRunMonitoring result={latestRun} /> : <EmptyMonitoring />}
    </AppShell>
  );
}

function EmptyMonitoring() {
  return (
    <Panel title="Latest run">
      <EmptyLine>
        Run a research query first. The latest successful response appears here.
      </EmptyLine>
    </Panel>
  );
}

function LatestRunMonitoring({ result }: { result: RagRunResult }) {
  const answer = result.answer;
  const trace = result.trace;
  const usage = trace?.model_usage ?? [];
  const totalTokens = usage.reduce((sum, entry) => sum + (entry.total_tokens ?? 0), 0);
  const inputTokens = usage.reduce((sum, entry) => sum + (entry.input_tokens ?? 0), 0);
  const outputTokens = usage.reduce((sum, entry) => sum + (entry.output_tokens ?? 0), 0);
  const reasoningTokens = usage.reduce((sum, entry) => sum + (entry.reasoning_tokens ?? 0), 0);
  const evidenceCount = answer?.evidence?.length ?? 0;
  const changeTargetCount = answer?.change_targets?.length ?? 0;
  const riskCount = answer?.risks?.length ?? 0;
  const unresolvedCount = answer?.unresolved_questions?.length ?? 0;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          icon={Gauge}
          label="Outcome"
          value={trace?.insufficient_evidence ? "Insufficient" : "Grounded"}
          detail={trace?.question_mode ?? answer?.mode ?? "Unknown"}
        />
        <MetricCard
          icon={FileSearch}
          label="Evidence"
          value={String(evidenceCount)}
          detail={`${trace?.retrieved_chunk_count ?? 0} chunks, ${trace?.unique_file_count ?? 0} files`}
        />
        <MetricCard
          icon={Clock3}
          label="Latency"
          value={formatMs(trace?.latency_ms_total)}
          detail={`model ${formatMs(trace?.latency_ms_model)}`}
        />
        <MetricCard
          icon={CircleDollarSign}
          label="Cost"
          value={formatCost(trace?.total_estimated_cost_usd)}
          detail={`${totalTokens.toLocaleString()} tokens`}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel
          title="Run outcome"
          right={
            <span className="mono text-[10px] uppercase tracking-wide text-muted-foreground">
              latest response
            </span>
          }
        >
          <Field label="request_id">{text(trace?.request_id)}</Field>
          <Field label="repository">{text(trace?.repository_name)}</Field>
          <Field label="branch">{text(trace?.branch)}</Field>
          <Field label="commit_hash">{text(trace?.commit_hash)}</Field>
          <Field label="question_mode">{text(trace?.question_mode)}</Field>
          <Field label="retrieval_mode">{text(trace?.retrieval_mode)}</Field>
          <Field label="confidence">{formatConfidence(answer?.confidence)}</Field>
          <Field label="insufficient_evidence">
            {String(Boolean(trace?.insufficient_evidence))}
          </Field>
        </Panel>

        <Panel title="Retrieval signal">
          <Field label="retrieval_limit">{num(trace?.retrieval_limit)}</Field>
          <Field label="retrieved_chunk_count">{num(trace?.retrieved_chunk_count)}</Field>
          <Field label="unique_file_count">{num(trace?.unique_file_count)}</Field>
          <Field label="evidence_count">{num(evidenceCount)}</Field>
          <Field label="change_target_count">{num(changeTargetCount)}</Field>
          <Field label="risk_count">{num(riskCount)}</Field>
          <Field label="unresolved_question_count">{num(unresolvedCount)}</Field>
        </Panel>

        <Panel title="Latency breakdown">
          <Field label="latency_ms_retrieval">{formatMs(trace?.latency_ms_retrieval)}</Field>
          <Field label="latency_ms_model">{formatMs(trace?.latency_ms_model)}</Field>
          <Field label="latency_ms_total">{formatMs(trace?.latency_ms_total)}</Field>
          <Field label="tool_call_count">{num(trace?.tool_call_count)}</Field>
          <Field label="started_at">{text(trace?.started_at)}</Field>
          <Field label="completed_at">{text(trace?.completed_at)}</Field>
        </Panel>

        <Panel title="Model usage & price">
          <Field label="model_calls">{num(usage.length)}</Field>
          <Field label="input_tokens">{num(inputTokens)}</Field>
          <Field label="output_tokens">{num(outputTokens)}</Field>
          <Field label="reasoning_tokens">{num(reasoningTokens)}</Field>
          <Field label="total_tokens">{num(totalTokens)}</Field>
          <Field label="total_estimated_cost_usd">
            {formatCost(trace?.total_estimated_cost_usd)}
          </Field>
          <Field label="pricing_version">{text(usage[0]?.pricing_version)}</Field>
        </Panel>
      </div>

      {trace?.error_type || trace?.error_message ? (
        <Panel title="Backend error">
          <Field label="error_type">{text(trace.error_type)}</Field>
          <p className="mt-2 whitespace-pre-wrap break-words text-[12px] text-muted-foreground">
            {text(trace.error_message)}
          </p>
        </Panel>
      ) : null}
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

function num(v: number | null | undefined) {
  return typeof v === "number" ? v.toLocaleString() : "Unknown";
}

function text(v: string | null | undefined) {
  return v && v.length > 0 ? v : "Unknown";
}

function formatMs(v: number | null | undefined) {
  return typeof v === "number" ? `${v.toLocaleString()} ms` : "Unknown";
}

function formatCost(v: number | string | null | undefined) {
  if (typeof v === "number") return `$${v.toFixed(6)}`;
  if (typeof v === "string" && v.trim().length > 0) {
    const parsed = Number(v);
    return Number.isFinite(parsed) ? `$${parsed.toFixed(6)}` : v;
  }
  return "Unavailable";
}

function formatConfidence(v: number | string | null | undefined) {
  if (typeof v === "number") return `${Math.round(v * 100)}%`;
  if (typeof v === "string" && v.trim().length > 0) return v;
  return "Unknown";
}
