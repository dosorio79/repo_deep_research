import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode, ComponentType } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Route } from "./index";
import { runRagQuery } from "@/lib/rag-client";

vi.mock("@/lib/rag-client", () => ({
  runRagQuery: vi.fn(),
}));

vi.mock("@/components/AppShell", () => ({
  AppShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

function renderResearchRoute() {
  const ResearchComponent = Route.options.component as ComponentType;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ResearchComponent />
    </QueryClientProvider>,
  );
}

describe("Research route", () => {
  beforeEach(() => {
    vi.mocked(runRagQuery).mockReset();
  });

  it("aborts an in-flight RAG request when the route unmounts", async () => {
    vi.mocked(runRagQuery).mockImplementation(
      (_baseUrl, _body, signal) =>
        new Promise((resolve, reject) => {
          signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    const user = userEvent.setup();

    const view = renderResearchRoute();

    await user.type(screen.getByLabelText("Question"), "Where is config validated?");
    await user.click(screen.getByRole("button", { name: "Run query" }));

    const firstSignal = vi.mocked(runRagQuery).mock.calls[0]?.[2];
    expect(firstSignal?.aborted).toBe(false);

    view.unmount();

    await waitFor(() => expect(firstSignal?.aborted).toBe(true));
    expect(vi.mocked(runRagQuery)).toHaveBeenCalledTimes(1);
  });
});
