import type { ApiErrorShape, RagRequest, RagRunResult } from "./rag-types";

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

export async function runRagQuery(
  baseUrl: string,
  payload: RagRequest,
  signal?: AbortSignal,
): Promise<RagRunResult> {
  const url = `${baseUrl.replace(/\/+$/, "")}/rag`;
  let response: Response;

  try {
    response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: signal ?? null,
    });
  } catch {
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
        (text ? text.slice(0, 1200) : "The backend returned no response body."),
      status: response.status,
    } satisfies ApiErrorShape;
  }

  if (!parsed || typeof parsed !== "object") {
    throw {
      title: "Unexpected response",
      detail: "The backend response was not valid JSON matching RagRunResult.",
    } satisfies ApiErrorShape;
  }

  return parsed as RagRunResult;
}
