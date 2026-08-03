import { EmptyLine, Field, Panel } from "@/components/primitives";
import type { RagTrace } from "@/lib/rag-types";

function num(v: number | null | undefined, suffix = "") {
  return typeof v === "number" ? `${v}${suffix}` : "Unknown";
}

function cost(v: number | string | null | undefined) {
  if (typeof v === "number") return `$${v.toFixed(6)}`;
  if (typeof v === "string" && v.trim().length > 0) {
    const parsed = Number(v);
    return Number.isFinite(parsed) ? `$${parsed.toFixed(6)}` : v;
  }
  return "Unavailable";
}

function text(v: string | null | undefined) {
  return v && v.length > 0 ? v : "Unknown";
}

export function TracePanel({ trace }: { trace: RagTrace | null }) {
  if (!trace) {
    return (
      <Panel title="Trace">
        <EmptyLine>No trace object in the response.</EmptyLine>
      </Panel>
    );
  }

  const usageEntries = trace.model_usage ?? [];

  return (
    <div className="space-y-3">
      {trace.error_type || trace.error_message ? (
        <Panel title="Backend-reported error">
          <p className="mono text-[12px] text-destructive">{text(trace.error_type)}</p>
          <p className="mt-1 whitespace-pre-wrap break-words text-[12px] text-muted-foreground">
            {text(trace.error_message)}
          </p>
        </Panel>
      ) : null}

      <Panel title="Run context">
        <Field label="request_id">{text(trace.request_id)}</Field>
        <Field label="repository_name">{text(trace.repository_name)}</Field>
        <Field label="branch">{text(trace.branch)}</Field>
        <Field label="commit_hash">{text(trace.commit_hash)}</Field>
        <Field label="question_mode">{text(trace.question_mode)}</Field>
        <Field label="retrieval_mode">{text(trace.retrieval_mode)}</Field>
        <Field label="retrieval_limit">{num(trace.retrieval_limit)}</Field>
        <Field label="insufficient_evidence">
          {trace.insufficient_evidence === null || trace.insufficient_evidence === undefined
            ? "Unknown"
            : String(trace.insufficient_evidence)}
        </Field>
      </Panel>

      <Panel title="Retrieval & latency">
        <Field label="retrieved_chunk_count">{num(trace.retrieved_chunk_count)}</Field>
        <Field label="unique_file_count">{num(trace.unique_file_count)}</Field>
        <Field label="tool_call_count">{num(trace.tool_call_count)}</Field>
        <Field label="latency_ms_retrieval">{num(trace.latency_ms_retrieval, " ms")}</Field>
        <Field label="latency_ms_model">{num(trace.latency_ms_model, " ms")}</Field>
        <Field label="latency_ms_total">{num(trace.latency_ms_total, " ms")}</Field>
      </Panel>

      <Panel
        title="Model usage & cost"
        right={
          <span className="mono text-[10px] uppercase tracking-wide text-muted-foreground">
            telemetry only
          </span>
        }
      >
        {usageEntries.length === 0 ? (
          <EmptyLine>Model usage unavailable.</EmptyLine>
        ) : (
          usageEntries.map((usage, i) => (
            <div
              key={`${usage.provider ?? "provider"}-${usage.model ?? "model"}-${i}`}
              className="mb-2 border-b border-border/60 pb-2 last:mb-0 last:border-0 last:pb-0"
            >
              <Field label={`model_usage[${i}].provider`}>{text(usage.provider)}</Field>
              <Field label={`model_usage[${i}].model`}>{text(usage.model)}</Field>
              <Field label={`model_usage[${i}].input_tokens`}>{num(usage.input_tokens)}</Field>
              <Field label={`model_usage[${i}].output_tokens`}>{num(usage.output_tokens)}</Field>
              <Field label={`model_usage[${i}].total_tokens`}>{num(usage.total_tokens)}</Field>
              <Field label={`model_usage[${i}].cached_input_tokens`}>
                {num(usage.cached_input_tokens)}
              </Field>
              <Field label={`model_usage[${i}].reasoning_tokens`}>
                {num(usage.reasoning_tokens)}
              </Field>
              <Field label={`model_usage[${i}].pricing_source`}>{text(usage.pricing_source)}</Field>
              <Field label={`model_usage[${i}].pricing_version`}>
                {text(usage.pricing_version)}
              </Field>
              <Field label={`model_usage[${i}].estimated_cost_usd`}>
                {cost(usage.estimated_cost_usd)}
              </Field>
            </div>
          ))
        )}
        <Field label="total_estimated_cost_usd">{cost(trace.total_estimated_cost_usd)}</Field>
      </Panel>
    </div>
  );
}
