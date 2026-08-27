import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronRight,
  DatabaseZap,
  FileCode2,
  GitBranch,
  Loader2,
  Play,
  RefreshCw,
  Send,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiError } from "@/components/ApiError";
import { EvidenceReferences } from "@/components/EvidenceReferences";
import { ResearchStepsPanel } from "@/components/ResearchStepsPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { AppShell } from "@/components/AppShell";
import { loadLatestRagRun, saveLatestRagRun } from "@/lib/latest-rag-run";
import {
  getActiveRepositoryIngestionJob,
  getBackendHealth,
  getMonitoringRunDetail,
  getRepositoryIngestionJob,
  runAgenticResearch,
  runRagQuery,
  startRepositoryIngestionJob,
  submitFeedback,
} from "@/lib/rag-client";
import { getBrowserSessionId } from "@/lib/session-id";
import type {
  ApiErrorShape,
  BackendHealth,
  ChangeTarget,
  EvidenceItem,
  IngestionJob,
  IngestionJobStatus,
  IngestSummary,
  QuestionMode,
  RagRequest,
  ResearchKind,
  ResearchRequest,
  ResearchResult,
  RetrievalMode,
} from "@/lib/rag-types";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  {
    label: "Find configuration",
    question: "Where is repository configuration validated before the app starts?",
    mode: "locate" as QuestionMode,
    kind: "direct" as ResearchKind,
  },
  {
    label: "Explain the flow",
    question: "How does repository ingestion reach the vector store?",
    mode: "flow" as QuestionMode,
    kind: "direct" as ResearchKind,
  },
  {
    label: "Plan a change",
    question: "Which modules must change to add feedback persistence?",
    mode: "change" as QuestionMode,
    kind: "agentic" as ResearchKind,
  },
];

const QUESTION_MODES: QuestionMode[] = ["auto", "locate", "flow", "change"];
const RETRIEVAL_MODES: RetrievalMode[] = ["dense", "sparse", "hybrid"];
const DEFAULT_API_BASE_URL = (import.meta.env["VITE_API_BASE_URL"] as string | undefined) ?? "/api";
const ACTIVE_INGESTION_STATUSES = new Set<IngestionJobStatus>([
  "queued",
  "discovering",
  "indexing",
]);
type RecordedFeedback = {
  useful: boolean;
  duplicate?: boolean;
};
export const RESEARCH_HEAD = {
  meta: [
    { title: "Repo Deep Research" },
    {
      name: "description",
      content:
        "Local-first repository research with ingestion, direct RAG, agentic RAG, grounded answers, and evidence.",
    },
    { property: "og:title", content: "Repo Deep Research" },
    {
      property: "og:description",
      content: "Ingest a Python repository and ask grounded RAG questions with citations.",
    },
  ],
};

export const Route = createFileRoute("/")({
  head: () => RESEARCH_HEAD,
  component: ResearchView,
});

function ResearchView() {
  const baseUrl = DEFAULT_API_BASE_URL;
  const [repositoryAddress, setRepositoryAddress] = useState("");
  const [ingestSummary, setIngestSummary] = useState<IngestSummary | null>(null);
  const [question, setQuestion] = useState("");
  const [researchKind, setResearchKind] = useState<ResearchKind>("direct");
  const [questionMode, setQuestionMode] = useState<QuestionMode>("auto");
  const [retrievalMode, setRetrievalMode] = useState<RetrievalMode>("hybrid");
  const [limit, setLimit] = useState(8);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [resultKind, setResultKind] = useState<ResearchKind>("direct");
  const [sessionId] = useState(() => getBrowserSessionId());
  const [ingestError, setIngestError] = useState<ApiErrorShape | null>(null);
  const [queryError, setQueryError] = useState<ApiErrorShape | null>(null);
  const [activeIngestionJobId, setActiveIngestionJobId] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const activeRequestId = result?.trace?.request_id ?? null;

  useEffect(() => () => activeRequest.current?.abort(), []);

  useEffect(() => {
    const latestRun = loadLatestRagRun();
    if (!latestRun) return;
    setResult(latestRun);
    if (latestRun.answer?.question) {
      setQuestion(latestRun.answer.question);
    }
    if (latestRun.answer?.mode) {
      setQuestionMode(latestRun.answer.mode);
    }
    setResultKind(latestRun.answer?.research_steps?.length ? "agentic" : "direct");
  }, []);

  const healthQuery = useQuery({
    queryKey: ["backend-health", baseUrl],
    queryFn: ({ signal }) => getBackendHealth(baseUrl, signal),
    enabled: baseUrl.trim().length > 0,
    retry: false,
    staleTime: 5_000,
  });

  const activeIngestionJobQuery = useQuery({
    queryKey: ["active-ingestion-job", baseUrl],
    queryFn: ({ signal }) => getActiveRepositoryIngestionJob(baseUrl, signal),
    enabled: baseUrl.trim().length > 0,
    retry: false,
    staleTime: 5_000,
  });

  const ingestJobQuery = useQuery({
    queryKey: ["ingestion-job", baseUrl, activeIngestionJobId],
    queryFn: ({ signal }) => getRepositoryIngestionJob(baseUrl, activeIngestionJobId ?? "", signal),
    enabled: Boolean(activeIngestionJobId),
    retry: false,
    refetchInterval: 2_000,
  });

  const ingestMutation = useMutation({
    mutationFn: (payload: { baseUrl: string; repositoryAddress: string }) =>
      startRepositoryIngestionJob(payload.baseUrl, {
        repository_address: payload.repositoryAddress,
      }),
    onSuccess: (data) => {
      setActiveIngestionJobId(data.job_id);
      setIngestError(null);
    },
    onError: (err: unknown) => {
      const shape = err as Partial<ApiErrorShape>;
      setIngestError({
        title: shape?.title ?? "Ingestion failed",
        detail: shape?.detail ?? "The backend could not ingest this repository.",
        ...(typeof shape?.status === "number" ? { status: shape.status } : {}),
      });
    },
  });

  useEffect(() => {
    const job = activeIngestionJobQuery.data;
    if (!job || !ACTIVE_INGESTION_STATUSES.has(job.status)) return;
    setActiveIngestionJobId(job.job_id);
    setRepositoryAddress(job.repository_address);
  }, [activeIngestionJobQuery.data]);

  const currentIngestionJob = activeIngestionJobId
    ? (ingestJobQuery.data ?? ingestMutation.data ?? activeIngestionJobQuery.data ?? null)
    : null;
  const ingestionActive =
    ingestMutation.isPending ||
    (currentIngestionJob !== null && ACTIVE_INGESTION_STATUSES.has(currentIngestionJob.status));

  useEffect(() => {
    if (!ingestJobQuery.data) return;
    const job = ingestJobQuery.data;
    if (job.status === "completed" && job.summary) {
      setIngestSummary(job.summary);
      setIngestError(null);
      setActiveIngestionJobId(null);
      return;
    }
    if (job.status === "failed" || job.status === "interrupted" || job.status === "cancelled") {
      setIngestError({
        title: job.status === "cancelled" ? "Ingestion cancelled" : "Ingestion failed",
        detail: job.error_detail ?? "The backend could not ingest this repository.",
      });
      setActiveIngestionJobId(null);
    }
  }, [ingestJobQuery.data]);

  useEffect(() => {
    if (!ingestionActive) return undefined;
    const preventUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", preventUnload);
    return () => window.removeEventListener("beforeunload", preventUnload);
  }, [ingestionActive]);

  const queryMutation = useMutation({
    mutationFn: (payload: {
      kind: ResearchKind;
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
      setQueryError(null);
    },
    onError: (err: unknown) => {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const shape = err as Partial<ApiErrorShape>;
      setQueryError({
        title: shape?.title ?? "Request failed",
        detail: shape?.detail ?? "An unexpected error occurred while calling the backend.",
        ...(typeof shape?.status === "number" ? { status: shape.status } : {}),
      });
    },
  });

  const feedbackMutation = useMutation({
    mutationFn: (payload: {
      useful: boolean;
      comment?: string;
      requestId?: string;
      runKind: ResearchKind;
    }) =>
      submitFeedback(baseUrl, {
        session_id: sessionId,
        run_kind: payload.runKind,
        useful: payload.useful,
        ...(payload.requestId ? { request_id: payload.requestId } : {}),
        ...(payload.comment ? { comment: payload.comment } : {}),
      }),
  });
  const monitoringDetailQuery = useQuery({
    queryKey: ["answer-feedback-detail", baseUrl, activeRequestId],
    queryFn: ({ signal }) => getMonitoringRunDetail(baseUrl, activeRequestId ?? "", signal),
    enabled: Boolean(activeRequestId),
    retry: false,
    staleTime: 5_000,
  });

  useEffect(() => {
    feedbackMutation.reset();
  }, [activeRequestId]);

  const ingest = () => {
    setIngestError(null);
    setIngestSummary(null);
    ingestMutation.mutate({
      baseUrl,
      repositoryAddress: repositoryAddress.trim(),
    });
  };

  const submit = () => {
    activeRequest.current?.abort();
    setQueryError(null);
    const controller = new AbortController();
    activeRequest.current = controller;
    const queryRepositoryPath = ingestSummary?.repository.root_path ?? repositoryAddress.trim();
    const common = {
      question: question.trim(),
      mode: questionMode,
      retrieval_mode: retrievalMode,
      session_id: sessionId,
      ...(queryRepositoryPath ? { repository_path: queryRepositoryPath } : {}),
    };
    const body =
      researchKind === "agentic"
        ? ({
            ...common,
            retrieval_limit: limit,
          } satisfies ResearchRequest)
        : ({
            ...common,
            limit,
          } satisfies RagRequest);
    queryMutation.mutate({
      kind: researchKind,
      baseUrl,
      body,
      signal: controller.signal,
    });
    setResultKind(researchKind);
  };

  const submitRunFeedback = (payload: { useful: boolean; comment?: string }) => {
    feedbackMutation.mutate({
      useful: payload.useful,
      runKind: resultKind,
      ...(result?.trace?.request_id ? { requestId: result.trace.request_id } : {}),
      ...(payload.comment ? { comment: payload.comment } : {}),
    });
  };

  const canIngest = repositoryAddress.trim().length > 0 && !ingestionActive;
  const hasRepository = ingestSummary !== null;
  const canAsk = hasRepository && question.trim().length > 0 && !queryMutation.isPending;
  const ingestStatusLabel = ingestSummary?.index_updated ? "indexed" : "already indexed";

  return (
    <AppShell
      navigationLocked={ingestionActive}
      navigationLockReason="Repository ingestion is still running."
    >
      <div className="space-y-3">
        <header className="border-b border-border pb-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-5xl">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="gap-1.5 border-primary/30 bg-primary/5">
                  <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden />
                  Repository research assistant
                </Badge>
                <Badge variant="secondary">Python repositories</Badge>
              </div>
              <h1 className="mt-3 max-w-4xl text-3xl font-semibold tracking-tight text-foreground md:text-4xl">
                Research a codebase with grounded RAG evidence.
              </h1>
              <p className="mt-2 max-w-3xl text-[14px] leading-6 text-muted-foreground">
                Ingest a repository, ask a codebase question, and inspect an answer that cites
                files, symbols, line ranges, and change targets.
              </p>
            </div>
            <ApiStatusLight
              health={healthQuery.data}
              error={healthQuery.error as ApiErrorShape | null}
              isChecking={healthQuery.isFetching}
              onRetry={() => void healthQuery.refetch()}
            />
          </div>
        </header>

        <section className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
          <div className="grid lg:grid-cols-[380px_minmax(0,1fr)]">
            <section
              aria-labelledby="repository-source-title"
              className="border-b border-border bg-secondary/20 lg:border-b-0 lg:border-r"
            >
              <div className="space-y-3 p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-[12px] font-medium uppercase tracking-wide text-primary">
                      Repository source
                    </p>
                    <h2
                      id="repository-source-title"
                      className="text-lg font-semibold tracking-tight"
                    >
                      Connect the codebase.
                    </h2>
                  </div>
                  {ingestSummary ? (
                    <Badge variant="secondary" className="gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
                      {ingestStatusLabel}
                    </Badge>
                  ) : null}
                </div>
                <div className="grid gap-3">
                  <div>
                    <Label
                      htmlFor="repositoryAddress"
                      className="text-[11px] uppercase tracking-wide text-muted-foreground"
                    >
                      Repository address
                    </Label>
                    <Input
                      id="repositoryAddress"
                      value={repositoryAddress}
                      spellCheck={false}
                      placeholder="/path/to/repo or https://github.com/owner/repo"
                      onChange={(event) => {
                        setRepositoryAddress(event.target.value);
                        setIngestSummary(null);
                        setIngestError(null);
                      }}
                      className="mt-1.5 h-10 mono text-[12px]"
                    />
                  </div>
                  <Button
                    type="button"
                    disabled={!canIngest}
                    onClick={ingest}
                    className="w-full gap-1.5"
                  >
                    {ingestionActive ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <DatabaseZap className="h-4 w-4" aria-hidden />
                    )}
                    {ingestionActive ? "Ingesting..." : "Ingest repository"}
                  </Button>
                </div>
                {ingestError ? <ApiError error={ingestError} /> : null}
                {ingestionActive ? <IngestionProgress job={currentIngestionJob} /> : null}
                {ingestSummary ? <RepositoryReceipt summary={ingestSummary} /> : null}
              </div>
            </section>

            <form
              className="p-4"
              onSubmit={(event) => {
                event.preventDefault();
                if (canAsk) submit();
              }}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-[12px] font-medium uppercase tracking-wide text-primary">
                    Research question
                  </p>
                  <h2 className="text-xl font-semibold tracking-tight">
                    Ask what you need to understand.
                  </h2>
                </div>
                <div className="flex flex-wrap items-end gap-3">
                  <div className="min-w-[220px]">
                    <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
                      Research mode
                    </span>
                    <Segmented
                      label="research type"
                      value={researchKind}
                      options={["direct", "agentic"]}
                      format={(value) => (value === "agentic" ? "agentic RAG" : "direct RAG")}
                      onChange={(value) => {
                        setResearchKind(value);
                        if (value === "agentic" && questionMode === "auto") {
                          setQuestionMode("change");
                        }
                      }}
                    />
                  </div>
                  <SearchSettingsPopover
                    limit={limit}
                    questionMode={questionMode}
                    retrievalMode={retrievalMode}
                    onLimitChange={setLimit}
                    onQuestionModeChange={setQuestionMode}
                    onRetrievalModeChange={setRetrievalMode}
                  />
                </div>
              </div>

              <div className="mt-3 space-y-3">
                <div className="flex flex-wrap gap-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example.label}
                      type="button"
                      onClick={() => {
                        setQuestion(example.question);
                        setQuestionMode(example.mode);
                        setResearchKind(example.kind);
                      }}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[12px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                    >
                      {example.label}
                      <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  ))}
                </div>

                <div>
                  <Label
                    htmlFor="question"
                    className="text-[11px] uppercase tracking-wide text-muted-foreground"
                  >
                    Question
                  </Label>
                  <Textarea
                    id="question"
                    value={question}
                    rows={4}
                    spellCheck={false}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.metaKey || event.ctrlKey) && event.key === "Enter" && canAsk) {
                        event.preventDefault();
                        submit();
                      }
                    }}
                    placeholder="e.g. Which modules must change to add feedback persistence?"
                    className="mt-1.5 min-h-[116px] resize-y text-[15px] leading-6"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
                  <Button type="submit" disabled={!canAsk} className="gap-1.5">
                    {queryMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <Play className="h-4 w-4" aria-hidden />
                    )}
                    {queryMutation.isPending ? "Running..." : "Run query"}
                  </Button>
                  <span className="mono text-[11px] text-muted-foreground">
                    {hasRepository ? "Cmd/Ctrl + Enter" : "Ingest a repository first"}
                  </span>
                </div>
                {queryError ? <ApiError error={queryError} /> : null}
              </div>
            </form>
          </div>
        </section>

        <section>
          {queryMutation.isPending ? (
            <div className="mb-3 rounded-lg border border-border bg-secondary/60 px-4 py-2 text-[13px] text-muted-foreground">
              Running {researchKind === "agentic" ? "agentic RAG" : "direct RAG"} against repository
              evidence. Last successful result remains visible.
            </div>
          ) : null}
          {result ? (
            <ReviewerResult
              result={result}
              runKind={resultKind}
              feedbackPending={feedbackMutation.isPending}
              recordedFeedback={
                feedbackMutation.data ?? monitoringDetailQuery.data?.feedback_events[0] ?? null
              }
              feedbackError={(feedbackMutation.error as ApiErrorShape | null) ?? null}
              onSubmitFeedback={submitRunFeedback}
            />
          ) : (
            <EmptyResult endpoint={researchKind === "agentic" ? "/research" : "/rag"} />
          )}
        </section>
      </div>
    </AppShell>
  );
}

function IngestionProgress({ job }: { job: IngestionJob | null }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const status = job?.status ?? "queued";
  const elapsedLabel =
    job && job.elapsed_seconds > 0
      ? `${job.elapsed_seconds.toLocaleString()}s elapsed`
      : "starting";
  const statusLabel = formatIngestionStatus(status);
  return (
    <Collapsible
      role="status"
      aria-live="polite"
      open={detailsOpen}
      onOpenChange={setDetailsOpen}
      className="rounded-md border border-primary/25 bg-primary/5 px-3 py-2 text-[12px]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-foreground">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-primary" aria-hidden />
          <span className="font-medium">Ingesting repository</span>
          <span className="rounded-sm bg-background px-1.5 py-0.5 text-[11px] text-muted-foreground">
            {statusLabel}
          </span>
          <span className="mono text-[11px] text-muted-foreground">{elapsedLabel}</span>
        </div>
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          >
            <ChevronRight
              className={cn(
                "h-3.5 w-3.5 transition-transform",
                detailsOpen ? "rotate-90" : "rotate-0",
              )}
              aria-hidden
            />
            {detailsOpen ? "Hide ingestion details" : "Show ingestion details"}
          </button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="mt-2 grid gap-1 text-muted-foreground">
        <span>{job?.repository_address ?? "Repository job has started."}</span>
        <span>Status: {statusLabel}</span>
        <span className="mono text-[11px]">Navigation is locked until ingestion finishes.</span>
      </CollapsibleContent>
    </Collapsible>
  );
}

function formatIngestionStatus(status: IngestionJobStatus) {
  if (status === "queued") return "queued";
  if (status === "discovering") return "discovering";
  if (status === "indexing") return "indexing";
  return status;
}

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  format,
}: {
  label: string;
  value: T;
  options: readonly T[];
  onChange: (value: T) => void;
  format?: (value: T) => string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="mt-1.5 flex flex-wrap gap-1 rounded-md border border-border bg-secondary p-1"
    >
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={option === value}
          onClick={() => onChange(option)}
          className={cn(
            "rounded-[4px] px-2.5 py-1.5 mono text-[12px] transition-colors",
            option === value
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {format ? format(option) : option}
        </button>
      ))}
    </div>
  );
}

function SearchSettingsPopover({
  limit,
  questionMode,
  retrievalMode,
  onLimitChange,
  onQuestionModeChange,
  onRetrievalModeChange,
}: {
  limit: number;
  questionMode: QuestionMode;
  retrievalMode: RetrievalMode;
  onLimitChange: (value: number) => void;
  onQuestionModeChange: (value: QuestionMode) => void;
  onRetrievalModeChange: (value: RetrievalMode) => void;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" className="gap-1.5">
          <SlidersHorizontal className="h-4 w-4" aria-hidden />
          Search settings
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(360px,calc(100vw-2rem))]">
        <div className="space-y-4">
          <div>
            <Label
              htmlFor="limit"
              className="text-[11px] uppercase tracking-wide text-muted-foreground"
            >
              Evidence limit: <span className="mono">{limit}</span>
            </Label>
            <Slider
              id="limit"
              className="mt-3"
              min={1}
              max={20}
              step={1}
              value={[limit]}
              onValueChange={(value) => onLimitChange(value[0] ?? limit)}
            />
          </div>

          <div>
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Question intent
            </span>
            <Segmented
              label="question mode"
              value={questionMode}
              options={QUESTION_MODES}
              onChange={onQuestionModeChange}
            />
          </div>

          <div>
            <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
              Retrieval
            </span>
            <Segmented
              label="retrieval mode"
              value={retrievalMode}
              options={RETRIEVAL_MODES}
              onChange={onRetrievalModeChange}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function ApiStatusLight({
  health,
  error,
  isChecking,
  onRetry,
}: {
  health: BackendHealth | undefined;
  error: ApiErrorShape | null;
  isChecking: boolean;
  onRetry: () => void;
}) {
  const isReachable = Boolean(health) && !error;
  const isReady = isReachable && health?.qdrant;
  const statusLabel = isChecking
    ? "checking"
    : isReady
      ? "API ready"
      : isReachable
        ? "API online, storage unavailable"
        : "API offline";

  return (
    <div className="flex items-center gap-2">
      <Badge
        variant={isReady ? "secondary" : "outline"}
        className={cn(
          "gap-1.5",
          isReady
            ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
            : error
              ? "border-destructive/40 text-destructive"
              : "border-warning/50 text-warning-foreground",
        )}
      >
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            isReady ? "bg-emerald-500" : error ? "bg-destructive" : "bg-warning",
          )}
          aria-hidden
        />
        {isChecking ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : null}
        {statusLabel}
      </Badge>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onRetry}
        disabled={isChecking}
        aria-label="Check API connection"
      >
        <RefreshCw className={cn("h-3.5 w-3.5", isChecking && "animate-spin")} aria-hidden />
      </Button>
      {error ? <span className="sr-only">{error.detail}</span> : null}
    </div>
  );
}

function RepositoryReceipt({ summary }: { summary: IngestSummary }) {
  const commit = summary.repository.commit_hash;
  return (
    <div className="grid gap-2 border-t border-border bg-secondary/20 px-4 py-3 text-[12px] sm:grid-cols-4">
      <ReceiptItem label="Repository" value={summary.repository.name} />
      <ReceiptItem label="Branch" value={summary.repository.branch} />
      <ReceiptItem label="Commit" value={commit.length > 12 ? commit.slice(0, 12) : commit} />
      <ReceiptItem label="Chunks" value={String(summary.indexed_chunks)} />
    </div>
  );
}

function ReceiptItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-muted-foreground">{label}</p>
      <p className="mono truncate font-medium text-foreground" title={value}>
        {value}
      </p>
    </div>
  );
}

function EmptyResult({ endpoint }: { endpoint: string }) {
  return (
    <div className="rounded-lg border border-dashed border-border bg-card p-8 text-center shadow-sm">
      <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-md bg-primary/10 text-primary">
        <FileCode2 className="h-5 w-5" aria-hidden />
      </div>
      <h2 className="mt-4 text-xl font-semibold tracking-tight">
        Run a query to see the evidence.
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-[14px] leading-6 text-muted-foreground">
        The answer will appear first, followed by cited files, symbols, change targets, and a
        compact run summary from <span className="mono">{endpoint}</span>.
      </p>
    </div>
  );
}

function ReviewerResult({
  result,
  runKind,
  feedbackPending,
  recordedFeedback,
  feedbackError,
  onSubmitFeedback,
}: {
  result: ResearchResult;
  runKind: ResearchKind;
  feedbackPending: boolean;
  recordedFeedback: RecordedFeedback | null;
  feedbackError: ApiErrorShape | null;
  onSubmitFeedback: (payload: { useful: boolean; comment?: string }) => void;
}) {
  const answer = result.answer;
  const evidence = answer?.evidence ?? [];
  const changeTargets = answer?.change_targets ?? [];

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border bg-card shadow-sm">
        <div className="border-b border-border bg-secondary/35 px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[12px] font-medium uppercase tracking-wide text-primary">Answer</p>
              <h2 className="text-2xl font-semibold tracking-tight">
                {answer?.mode === "change"
                  ? "Change-impact research"
                  : "Grounded repository answer"}
              </h2>
            </div>
            <Badge variant={answer?.insufficient_evidence ? "outline" : "secondary"}>
              confidence {formatConfidence(answer?.confidence)}
            </Badge>
          </div>
        </div>
        <div className="space-y-4 p-4">
          <ResultStatus result={result} />
          <p className="max-w-4xl whitespace-pre-wrap text-[15px] leading-7">
            {answer?.summary ?? "No summary returned."}
          </p>
          {answer?.implementation_flow?.length ? (
            <div className="grid gap-2 md:grid-cols-2">
              {answer.implementation_flow.slice(0, 4).map((item, index) => (
                <div key={`${item}-${index}`} className="rounded-md border border-border p-3">
                  <p className="mono text-[11px] text-muted-foreground">
                    step {String(index + 1).padStart(2, "0")}
                  </p>
                  <p className="mt-1 text-[13px] leading-5">{item}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {answer?.research_steps?.length ? (
        <ResearchStepsPanel steps={answer.research_steps} evidence={answer.evidence} />
      ) : null}

      {changeTargets.length > 0 ? (
        <ChangeTargetCards targets={changeTargets} evidence={answer?.evidence} />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <EvidenceHighlights evidence={evidence} />
        <RunTraceSummary result={result} />
      </div>
      {result.trace ? (
        <FeedbackControls
          runKind={runKind}
          requestId={result.trace.request_id}
          pending={feedbackPending}
          recordedFeedback={recordedFeedback}
          error={feedbackError}
          onSubmit={onSubmitFeedback}
        />
      ) : null}
    </div>
  );
}

function FeedbackControls({
  runKind,
  requestId,
  pending,
  recordedFeedback,
  error,
  onSubmit,
}: {
  runKind: ResearchKind;
  requestId: string;
  pending: boolean;
  recordedFeedback: RecordedFeedback | null;
  error: ApiErrorShape | null;
  onSubmit: (payload: { useful: boolean; comment?: string }) => void;
}) {
  const [useful, setUseful] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const submitted = recordedFeedback !== null;
  const canSubmit = useful !== null && !pending && !submitted;

  return (
    <div className="rounded-md border border-border bg-secondary/25 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-[12px] font-semibold uppercase tracking-wide text-muted-foreground">
            Run feedback
          </p>
          <p className="mt-1 mono text-[11px] text-muted-foreground">
            {runKind} - {requestId}
          </p>
        </div>
        {submitted ? (
          <Badge variant="secondary">
            {recordedFeedback.duplicate ? "already recorded" : "submitted"}
          </Badge>
        ) : null}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant={useful === true ? "default" : "outline"}
          size="sm"
          disabled={submitted || pending}
          onClick={() => setUseful(true)}
          className="gap-1.5"
        >
          <ThumbsUp className="h-4 w-4" aria-hidden />
          Useful
        </Button>
        <Button
          type="button"
          variant={useful === false ? "default" : "outline"}
          size="sm"
          disabled={submitted || pending}
          onClick={() => setUseful(false)}
          className="gap-1.5"
        >
          <ThumbsDown className="h-4 w-4" aria-hidden />
          Not useful
        </Button>
      </div>
      <Label
        htmlFor="feedbackComment"
        className="mt-3 block text-[11px] uppercase tracking-wide text-muted-foreground"
      >
        Comment
      </Label>
      <Textarea
        id="feedbackComment"
        value={comment}
        rows={2}
        maxLength={2000}
        disabled={submitted || pending}
        onChange={(event) => setComment(event.target.value)}
        className="mt-1.5 min-h-[68px] resize-y text-[13px] leading-5"
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!canSubmit}
          onClick={() =>
            useful !== null
              ? onSubmit({
                  useful,
                  ...(comment.trim() ? { comment: comment.trim() } : {}),
                })
              : undefined
          }
          className="gap-1.5"
        >
          {pending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          ) : (
            <Send className="h-4 w-4" aria-hidden />
          )}
          {submitted ? "Feedback recorded" : "Submit feedback"}
        </Button>
        {submitted ? (
          <span className="text-[12px] text-muted-foreground">
            Recorded as {recordedFeedback.useful ? "useful" : "not useful"}.
          </span>
        ) : null}
        {error ? <span className="text-[12px] text-destructive">{error.detail}</span> : null}
      </div>
    </div>
  );
}

function ResultStatus({ result }: { result: ResearchResult }) {
  const answer = result.answer;
  const trace = result.trace;
  if (!answer?.insufficient_evidence && !trace?.error_type) return null;

  const isBudgetExceeded = trace?.error_type === "ResearchBudgetExceeded";
  const title = isBudgetExceeded ? "Bounded agent stopped at its tool budget" : "Partial result";
  const detail = isBudgetExceeded
    ? "The agent returned the strongest grounded evidence it found before hitting its configured search or file-read limit."
    : "The backend could not fully ground this answer in retrieved repository evidence.";
  const evidenceCount = trace?.evidence_ids?.length ?? answer?.evidence?.length ?? 0;

  return (
    <div className="rounded-md border border-warning/50 bg-warning/10 p-3 text-warning-foreground">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[13px] font-semibold">{title}</p>
        {trace?.error_message ? (
          <Badge variant="outline" className="border-warning/50 bg-background/60 mono text-[11px]">
            {trace.error_message}
          </Badge>
        ) : null}
      </div>
      <p className="mt-1 text-[13px] leading-5">{detail}</p>
      <div className="mt-2 flex flex-wrap gap-2 text-[12px]">
        <span className="rounded-sm bg-background/70 px-2 py-1 mono">
          tool calls {trace?.tool_call_count ?? 0}
        </span>
        <span className="rounded-sm bg-background/70 px-2 py-1 mono">evidence {evidenceCount}</span>
        {trace?.error_type ? (
          <span className="rounded-sm bg-background/70 px-2 py-1 mono">{trace.error_type}</span>
        ) : null}
      </div>
    </div>
  );
}

function formatConfidence(value: unknown) {
  if (typeof value === "number") return value.toFixed(2);
  if (typeof value === "string" && value) return value;
  return "unknown";
}

function ChangeTargetCards({
  targets,
  evidence,
}: {
  targets: ChangeTarget[];
  evidence: EvidenceItem[] | null | undefined;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-primary" aria-hidden />
        <h2 className="text-[15px] font-semibold">Likely change targets</h2>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {targets.map((target, index) => {
          const name = target.symbol ? `${target.path}::${target.symbol}` : target.path;
          return (
            <div key={`${name}-${index}`} className="rounded-md border border-border p-3">
              <p className="path-text mono text-[12px] font-medium" title={name}>
                {name}
              </p>
              <p className="mt-2 text-[13px] leading-5 text-muted-foreground">{target.reason}</p>
              <div className="mt-2">
                <EvidenceReferences
                  evidenceIds={target.evidence_ids}
                  evidence={evidence}
                  prefix="evidence"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EvidenceHighlights({
  evidence,
}: {
  evidence: NonNullable<ResearchResult["answer"]>["evidence"];
}) {
  const items = evidence ?? [];
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FileCode2 className="h-4 w-4 text-primary" aria-hidden />
          <h2 className="text-[15px] font-semibold">Evidence highlights</h2>
        </div>
        <Badge variant="outline">{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p className="mt-3 text-[13px] text-muted-foreground">No evidence returned.</p>
      ) : (
        <div className="mt-3 space-y-2">
          {items.slice(0, 3).map((item) => (
            <div key={item.evidence_id} className="rounded-md border border-border p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="path-text mono text-[12px] font-medium">{item.path}</p>
                  <div className="mt-1">
                    <EvidenceReferences
                      evidenceIds={[item.evidence_id]}
                      evidence={items}
                      prefix=""
                    />
                  </div>
                </div>
                <span className="mono text-[11px] text-muted-foreground">
                  {item.start_line}-{item.end_line}
                </span>
              </div>
              <p className="mt-1 text-[12px] text-muted-foreground">{item.reason}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RunTraceSummary({ result }: { result: ResearchResult }) {
  const trace = result.trace;
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-primary" aria-hidden />
        <h2 className="text-[15px] font-semibold">Run summary</h2>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
        <ReceiptItem label="Repository" value={trace?.repository_name ?? "unknown"} />
        <ReceiptItem label="Mode" value={trace?.question_mode ?? "unknown"} />
        <ReceiptItem label="Retrieval" value={trace?.retrieval_mode ?? "unknown"} />
        <ReceiptItem label="Tool calls" value={String(trace?.tool_call_count ?? 0)} />
        <ReceiptItem label="Evidence" value={String(trace?.evidence_ids?.length ?? 0)} />
        <ReceiptItem label="Latency" value={`${trace?.latency_ms_total ?? 0} ms`} />
      </div>
    </div>
  );
}
