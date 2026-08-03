import type { RagRunResult } from "./rag-types";

const LATEST_RAG_RUN_STORAGE_KEY = "repo-deep-research.latest-rag-run";

export function saveLatestRagRun(result: RagRunResult) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(LATEST_RAG_RUN_STORAGE_KEY, JSON.stringify(result));
}

export function loadLatestRagRun(): RagRunResult | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(LATEST_RAG_RUN_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return null;
    return parsed as RagRunResult;
  } catch {
    return null;
  }
}
