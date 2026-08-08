import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { Navigation } from "./AppShell";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children }: { to: string; children: ReactNode }) => (
    <a href={to}>{children}</a>
  ),
}));

describe("Navigation", () => {
  it("exposes persisted monitoring as a first-class destination", () => {
    render(<Navigation />);

    expect(screen.getByRole("link", { name: /research/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /monitoring/i })).toHaveAttribute(
      "href",
      "/monitoring",
    );
  });
});
