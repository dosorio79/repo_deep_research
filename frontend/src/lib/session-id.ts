const SESSION_STORAGE_KEY = "repo-deep-research-session-id";

export function getBrowserSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;
  const generated = globalThis.crypto?.randomUUID?.() ?? fallbackSessionId();
  window.localStorage.setItem(SESSION_STORAGE_KEY, generated);
  return generated;
}

function fallbackSessionId(): string {
  return `session-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}
