import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { Navigation } from "./AppShell";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={to}>{children}</a>,
}));

describe("Navigation", () => {
  it("separates user research from admin evidence destinations", () => {
    render(<Navigation />);

    expect(screen.getByRole("link", { name: /research/i })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: /admin monitoring/i })).toHaveAttribute(
      "href",
      "/monitoring",
    );
    expect(screen.getByRole("link", { name: /admin evaluations/i })).toHaveAttribute(
      "href",
      "/evaluations",
    );
  });
});
