import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { AnswerPanel } from "@/components/AnswerPanel";
import { ApiError } from "@/components/ApiError";
import { EvidencePanel } from "@/components/EvidencePanel";
import { RagQueryForm, type QueryFormState } from "@/components/RagQueryForm";
import { RawJsonPanel } from "@/components/RawJsonPanel";
import { RepositoryIngestPanel } from "@/components/RepositoryIngestPanel";
import { ResearchStepsPanel } from "@/components/ResearchStepsPanel";
import { TracePanel } from "@/components/TracePanel";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { saveLatestRagRun } from "@/lib/latest-rag-run";
import { ingestRepository, runAgenticResearch, runRagQuery } from "@/lib/rag-client";
import type {
  ApiErrorShape,
  IngestSummary,
  RagRequest,
  ResearchRequest,
  ResearchResult,
} from "@/lib/rag-types";

const DEFAULT_API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "/api";

export function TechnicalResearchConsole() {
  const [form, setForm] = useState<QueryFormState>({
    researchKind: "direct",
    question: "",
    mode: "auto",
    retrievalMode: "hybrid",
    limit: 8,
  });
  const [baseUrl, setBaseUrl] = useState(DEFAULT_API_BASE_URL);
  const [repositoryAddress, setRepositoryAddress] = useState("");
  const [ingestSummary, setIngestSummary] = useState<IngestSummary | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [error, setError] = useState<ApiErrorShape | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const ingestMutation = useMutation({
    mutationFn: (payload: { baseUrl: string; repositoryPath: string }) =>
      ingestRepository(payload.baseUrl, { repository_address: payload.repositoryPath }),
    onSuccess: (data) => {
      setIngestSummary(data);
      setError(null);
    },
    onError: (err: unknown) => {
      const shape = err as Partial<ApiErrorShape>;
      setError({
        title: shape?.title ?? "Ingestion failed",
        detail: shape?.detail ?? "The backend could not ingest this repository.",
        ...(typeof shape?.status === "number" ? { status: shape.status } : {}),
      });
    },
  });

  const queryMutation = useMutation({
    mutationFn: (payload: {
      kind: QueryFormState["researchKind"];
      baseUrl: string;
      body: RagRequest | ResearchRequest;
      signal: AbortSignal;
    }) =>
      payload.kind === "agentic"
        ? runAgenticResearch(payload.baseUrl, payload.body as ResearchRequest, payload.signal)
        : runRagQuery(payload.baseUrl, payload.body as RagRequest, payload.signal),
    onSuccess: (data) => {
      saveLatestRagRun(data);
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
    const queryRepositoryPath = ingestSummary?.repository.root_path ?? repositoryAddress.trim();
    const common = {
      question: form.question.trim(),
      mode: form.mode,
      retrieval_mode: form.retrievalMode,
      ...(queryRepositoryPath ? { repository_path: queryRepositoryPath } : {}),
    };
    const body =
      form.researchKind === "agentic"
        ? ({
            ...common,
            retrieval_limit: form.limit,
          } satisfies ResearchRequest)
        : ({
            ...common,
            limit: form.limit,
          } satisfies RagRequest);
    queryMutation.mutate({
      kind: form.researchKind,
      baseUrl,
      body,
      signal: controller.signal,
    });
  };

  const ingest = () => {
    ingestMutation.mutate({
      baseUrl,
      repositoryPath: repositoryAddress.trim(),
    });
  };

  return (
    <>
      <div className="mb-4 grid gap-3 border-b border-border pb-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div>
          <p className="text-[12px] font-medium uppercase tracking-wide text-primary">
            Technical console
          </p>
          <h2 className="mt-1 max-w-3xl text-3xl font-semibold tracking-tight">
            Ingest a repository, then inspect every RAG detail.
          </h2>
          <p className="mt-2 max-w-3xl text-[14px] leading-relaxed text-muted-foreground">
            Backoffice view for API contracts, retrieval settings, trace metadata, evidence tables,
            and raw JSON.
          </p>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-md border border-border bg-card p-2">
            <p className="mono text-[16px] font-semibold">URL</p>
            <p className="text-[11px] text-muted-foreground">or path</p>
          </div>
          <div className="rounded-md border border-border bg-card p-2">
            <p className="mono text-[16px] font-semibold">2</p>
            <p className="text-[11px] text-muted-foreground">RAG modes</p>
          </div>
          <div className="rounded-md border border-border bg-card p-2">
            <p className="mono text-[16px] font-semibold">JSON</p>
            <p className="text-[11px] text-muted-foreground">trace</p>
          </div>
        </div>
      </div>

      <div className="mb-3">
        <RepositoryIngestPanel
          baseUrl={baseUrl}
          repositoryAddress={repositoryAddress}
          summary={ingestSummary}
          loading={ingestMutation.isPending}
          onAddressChange={(value) => {
            setRepositoryAddress(value);
            setIngestSummary(null);
          }}
          onBaseUrlChange={setBaseUrl}
          onIngest={ingest}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="space-y-3 lg:sticky lg:top-16 lg:self-start">
          <RagQueryForm
            state={form}
            onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
            onSubmit={submit}
            loading={queryMutation.isPending}
          />
          {error ? <ApiError error={error} /> : null}
        </div>

        <div className="min-w-0">
          {queryMutation.isPending ? (
            <div className="mb-3 rounded-md border border-border bg-secondary/60 px-3 py-1.5 mono text-[12px] text-muted-foreground">
              Running {form.researchKind === "agentic" ? "agentic research" : "direct research"}...
              showing last successful result below.
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
                <ResearchStepsPanel steps={result.answer?.research_steps} />
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
                <span className="mono">
                  {baseUrl.replace(/\/+$/, "")}
                  {form.researchKind === "agentic" ? "/research" : "/rag"}
                </span>{" "}
                to inspect the answer and evidence.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
