import { afterEach, describe, expect, it, vi } from "vitest";
import { getBrowserSessionId } from "./session-id";

describe("getBrowserSessionId", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("reuses the persisted browser session id", () => {
    window.localStorage.setItem("repo-deep-research-session-id", "browser-session");

    expect(getBrowserSessionId()).toBe("browser-session");
  });

  it("creates and persists a new browser session id", () => {
    const sessionId = getBrowserSessionId();

    expect(sessionId).toMatch(/[0-9a-f-]{36}|session-/);
    expect(window.localStorage.getItem("repo-deep-research-session-id")).toBe(sessionId);
  });

  it("does not require window during server rendering", () => {
    vi.stubGlobal("window", undefined);

    expect(getBrowserSessionId()).toMatch(/[0-9a-f-]{36}|^session-/);
  });
});
