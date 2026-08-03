import { createFileRoute } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { AnswerPanel } from "@/components/AnswerPanel";
import { ApiError } from "@/components/ApiError";
import { EvidencePanel } from "@/components/EvidencePanel";
import { RagQueryForm, type QueryFormState } from "@/components/RagQueryForm";
import { RawJsonPanel } from "@/components/RawJsonPanel";
import { TracePanel } from "@/components/TracePanel";
import { runRagQuery } from "@/lib/rag-client";
import type { ApiErrorShape, RagRequest, RagRunResult } from "@/lib/rag-types";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Research — Repo Deep Research M3.6" },
      {
        name: "description",
        content:
          "Developer testing harness for the Repo Deep Research RAG backend: run /rag queries and inspect answers, evidence and traces.",
      },
      { property: "og:title", content: "Research — Repo Deep Research M3.6" },
      {
        property: "og:description",
        content:
          "Run /rag queries against the FastAPI backend and inspect answer, evidence and trace output.",
      },
    ],
  }),
  component: ResearchView,
});

function ResearchView() {
  const [form, setForm] = useState<QueryFormState>({
    question: "",
    mode: "auto",
    retrievalMode: "hybrid",
    limit: 8,
    baseUrl: "http://localhost:8000",
    repositoryPath: "",
  });
  const [result, setResult] = useState<RagRunResult | null>(null);
  const [error, setError] = useState<ApiErrorShape | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const mutation = useMutation({
    mutationFn: (payload: { baseUrl: string; body: RagRequest; signal: AbortSignal }) =>
      runRagQuery(payload.baseUrl, payload.body, payload.signal),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const shape = err as Partial<ApiErrorShape>;
      setError({
        title: shape?.title ?? "Request failed",
        detail: shape?.detail ?? "An unexpected error occurred while calling the backend.",
        ...(typeof shape?.status === "number" ? { status: shape.status } : {}),
      });
    },
  });

  const submit = () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const body: RagRequest = {
      question: form.question.trim(),
      mode: form.mode,
      retrieval_mode: form.retrievalMode,
      limit: form.limit,
      ...(form.repositoryPath.trim() ? { repository_path: form.repositoryPath.trim() } : {}),
    };
    mutation.mutate({ baseUrl: form.baseUrl, body, signal: controller.signal });
  };

  return (
    <AppShell>
      <h1 className="sr-only">Repo Deep Research — RAG query harness</h1>
      <div className="grid gap-3 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-3 lg:sticky lg:top-16 lg:self-start">
          <RagQueryForm
            state={form}
            onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
            onSubmit={submit}
            loading={mutation.isPending}
          />
          {error ? <ApiError error={error} /> : null}
        </div>

        <div className="min-w-0">
          {mutation.isPending ? (
            <div className="mb-3 rounded-md border border-border bg-secondary/60 px-3 py-1.5 mono text-[12px] text-muted-foreground">
              Running query… showing last successful result below.
            </div>
          ) : null}

          {result ? (
            <Tabs defaultValue="answer">
              <TabsList className="h-8 rounded-md">
                <TabsTrigger value="answer" className="text-[12px]">
                  Answer
                </TabsTrigger>
                <TabsTrigger value="evidence" className="text-[12px]">
                  Evidence
                </TabsTrigger>
                <TabsTrigger value="trace" className="text-[12px]">
                  Trace
                </TabsTrigger>
              </TabsList>
              <TabsContent value="answer" className="mt-3 space-y-3">
                <AnswerPanel answer={result.answer} />
                <EvidencePanel evidence={result.answer?.evidence ?? null} />
              </TabsContent>
              <TabsContent value="evidence" className="mt-3">
                <EvidencePanel evidence={result.answer?.evidence ?? null} />
              </TabsContent>
              <TabsContent value="trace" className="mt-3">
                <TracePanel trace={result.trace ?? null} />
              </TabsContent>
              <div className="mt-3">
                <RawJsonPanel data={result} title="Raw RagRunResult JSON" />
              </div>
            </Tabs>
          ) : (
            <div className="panel flex min-h-[320px] items-center justify-center p-6">
              <p className="max-w-md text-center text-[13px] text-muted-foreground">
                No result yet. Enter a question and run a query against{" "}
                <span className="mono">{form.baseUrl.replace(/\/+$/, "")}/rag</span> to inspect the
                answer, evidence and trace.
              </p>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
