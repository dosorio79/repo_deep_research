import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare, ThumbsDown, ThumbsUp } from "lucide-react";
import { ApiError } from "@/components/ApiError";
import { AppShell } from "@/components/AppShell";
import { EmptyLine, Field, Panel } from "@/components/primitives";
import { getMonitoringSummary } from "@/lib/rag-client";
import type { ApiErrorShape } from "@/lib/rag-types";

const DEFAULT_API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "/api";

export const Route = createFileRoute("/feedback")({
  head: () => ({
    meta: [
      { title: "Feedback - Repo Deep Research" },
      {
        name: "description",
        content: "Persisted user feedback summary for repository research runs.",
      },
      { property: "og:title", content: "Feedback - Repo Deep Research" },
      {
        property: "og:description",
        content: "Reviewer feedback counts from the PostgreSQL-backed API.",
      },
    ],
  }),
  component: FeedbackView,
});

function FeedbackView() {
  const summaryQuery = useQuery({
    queryKey: ["feedback-summary", DEFAULT_API_BASE_URL],
    queryFn: ({ signal }) => getMonitoringSummary(DEFAULT_API_BASE_URL, signal),
    retry: false,
    staleTime: 5_000,
  });

  const feedback = summaryQuery.data?.feedback;
  const total = (feedback?.useful ?? 0) + (feedback?.not_useful ?? 0);

  return (
    <AppShell>
      <h1 className="sr-only">Repo Deep Research feedback</h1>
      {summaryQuery.error ? (
        <ApiError error={summaryQuery.error as unknown as ApiErrorShape} />
      ) : null}
      <div className="grid gap-3 md:grid-cols-3">
        <Metric icon={MessageSquare} label="Feedback" value={total.toLocaleString()} />
        <Metric icon={ThumbsUp} label="Useful" value={(feedback?.useful ?? 0).toLocaleString()} />
        <Metric
          icon={ThumbsDown}
          label="Not useful"
          value={(feedback?.not_useful ?? 0).toLocaleString()}
        />
      </div>
      <div className="mt-3">
        <Panel title="Persisted feedback">
          {summaryQuery.isLoading ? (
            <EmptyLine>Loading persisted feedback counts.</EmptyLine>
          ) : total > 0 ? (
            <>
              <Field label="useful">{feedback?.useful.toLocaleString()}</Field>
              <Field label="not_useful">{feedback?.not_useful.toLocaleString()}</Field>
            </>
          ) : (
            <EmptyLine>
              No persisted feedback is available. Submit feedback from a returned answer first.
            </EmptyLine>
          )}
        </Panel>
      </div>
    </AppShell>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof MessageSquare;
  label: string;
  value: string;
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
    </section>
  );
}
