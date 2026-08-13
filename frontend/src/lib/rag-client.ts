import type {
  ApiErrorShape,
  BackendHealth,
  EvaluationDashboardSummary,
  EvaluationResultList,
  EvaluationResultListParams,
  EvaluationRunList,
  EvaluationRunListParams,
  FeedbackEvent,
  FeedbackRequest,
  IngestSummary,
  MonitoringRunDetail,
  MonitoringRunList,
  MonitoringRunListParams,
  MonitoringSummary,
  RagRequest,
  RagRunResult,
  RepositoryIngestRequest,
  ResearchRequest,
  ResearchRunResult,
  RetrievalEvaluationList,
} from "./rag-types";

const ERROR_BODY_PREVIEW_LIMIT = 1200;

function extractDetail(body: unknown): string | null {
  if (!body || typeof body !== "object") return null;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (d && typeof d === "object") {
          const loc = Array.isArray((d as { loc?: unknown }).loc)
            ? (d as { loc: unknown[] }).loc.join(".")
            : "";
          const msg = (d as { msg?: unknown }).msg;
          return [loc, typeof msg === "string" ? msg : JSON.stringify(d)]
            .filter(Boolean)
            .join(": ");
        }
        return String(d);
      })
      .join("\n");
  }
  return null;
}

async function postJson<TPayload, TResult>(
  baseUrl: string,
  path: "/rag" | "/research" | "/repositories/ingest" | "/feedback",
  payload: TPayload,
  signal?: AbortSignal,
): Promise<TResult> {
  const url = `${baseUrl.replace(/\/+$/, "")}${path}`;
  let response: Response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: signal ?? null,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw {
      title: "Network error",
      detail: `Could not reach the backend at ${url}. Check that the API is running and the base URL is correct.`,
    } satisfies ApiErrorShape;
  }

  const text = await response.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }

  if (!response.ok) {
    throw {
      title: `Backend returned ${response.status} ${response.statusText}`.trim(),
      detail:
        extractDetail(parsed) ??
        (text ? text.slice(0, ERROR_BODY_PREVIEW_LIMIT) : "The backend returned no response body."),
      status: response.status,
    } satisfies ApiErrorShape;
  }

  if (!parsed || typeof parsed !== "object") {
    throw {
      title: "Unexpected response",
      detail: "The backend response was not valid JSON matching the expected research result.",
    } satisfies ApiErrorShape;
  }

  return parsed as TResult;
}

async function getJson<TResult>(
  baseUrl: string,
  path: string,
  signal?: AbortSignal,
): Promise<TResult> {
  const url = `${baseUrl.replace(/\/+$/, "")}${path}`;
  let response: Response;

  try {
    response = await fetch(url, { signal: signal ?? null });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw {
      title: "Network error",
      detail: `Could not reach the backend at ${url}. Check that the API is running and the base URL is correct.`,
    } satisfies ApiErrorShape;
  }

  const text = await response.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }

  if (!response.ok) {
    throw {
      title: `Backend returned ${response.status} ${response.statusText}`.trim(),
      detail:
        extractDetail(parsed) ??
        (text ? text.slice(0, ERROR_BODY_PREVIEW_LIMIT) : "The backend returned no response body."),
      status: response.status,
    } satisfies ApiErrorShape;
  }

  if (!parsed || typeof parsed !== "object") {
    throw {
      title: "Unexpected response",
      detail: "The backend response was not valid JSON.",
    } satisfies ApiErrorShape;
  }

  return parsed as TResult;
}

export async function getBackendHealth(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<BackendHealth> {
  return getJson<BackendHealth>(baseUrl, "/health", signal);
}

export async function runRagQuery(
  baseUrl: string,
  payload: RagRequest,
  signal?: AbortSignal,
): Promise<RagRunResult> {
  return postJson<RagRequest, RagRunResult>(baseUrl, "/rag", payload, signal);
}

export async function runAgenticResearch(
  baseUrl: string,
  payload: ResearchRequest,
  signal?: AbortSignal,
): Promise<ResearchRunResult> {
  return postJson<ResearchRequest, ResearchRunResult>(baseUrl, "/research", payload, signal);
}

export async function submitFeedback(
  baseUrl: string,
  payload: FeedbackRequest,
  signal?: AbortSignal,
): Promise<FeedbackEvent> {
  return postJson<FeedbackRequest, FeedbackEvent>(baseUrl, "/feedback", payload, signal);
}

export async function getMonitoringSummary(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<MonitoringSummary> {
  return getJson<MonitoringSummary>(baseUrl, "/monitoring/summary", signal);
}

export async function getMonitoringRuns(
  baseUrl: string,
  params: MonitoringRunListParams = {},
  signal?: AbortSignal,
): Promise<MonitoringRunList> {
  return getJson<MonitoringRunList>(baseUrl, `/monitoring/runs${queryString(params)}`, signal);
}

export async function getMonitoringRunDetail(
  baseUrl: string,
  requestId: string,
  signal?: AbortSignal,
): Promise<MonitoringRunDetail> {
  return getJson<MonitoringRunDetail>(
    baseUrl,
    `/monitoring/runs/${encodeURIComponent(requestId)}`,
    signal,
  );
}

export async function getEvaluationSummary(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<EvaluationDashboardSummary> {
  return getJson<EvaluationDashboardSummary>(baseUrl, "/evaluations/summary", signal);
}

export async function getEvaluationRuns(
  baseUrl: string,
  params: EvaluationRunListParams = {},
  signal?: AbortSignal,
): Promise<EvaluationRunList> {
  return getJson<EvaluationRunList>(baseUrl, `/evaluations/runs${queryString(params)}`, signal);
}

export async function getEvaluationResults(
  baseUrl: string,
  params: EvaluationResultListParams = {},
  signal?: AbortSignal,
): Promise<EvaluationResultList> {
  return getJson<EvaluationResultList>(
    baseUrl,
    `/evaluations/results${queryString(params)}`,
    signal,
  );
}

export async function getRetrievalEvaluationResults(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<RetrievalEvaluationList> {
  return getJson<RetrievalEvaluationList>(baseUrl, "/evaluations/retrieval", signal);
}

export async function ingestRepository(
  baseUrl: string,
  payload: RepositoryIngestRequest,
  signal?: AbortSignal,
): Promise<IngestSummary> {
  return postJson<RepositoryIngestRequest, IngestSummary>(
    baseUrl,
    "/repositories/ingest",
    payload,
    signal,
  );
}

function queryString(
  params: MonitoringRunListParams & EvaluationRunListParams & EvaluationResultListParams,
) {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.run_kind) search.set("run_kind", params.run_kind);
  if (params.repository_name) search.set("repository_name", params.repository_name);
  if (typeof params.has_error === "boolean") search.set("has_error", String(params.has_error));
  if (params.feedback && params.feedback !== "all") search.set("feedback", params.feedback);
  if (params.source_type) search.set("source_type", params.source_type);
  if (params.status) search.set("status", params.status);
  if (params.context_label) search.set("context_label", params.context_label);
  const value = search.toString();
  return value ? `?${value}` : "";
}
