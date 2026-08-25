import { fireEvent, render, screen } from "@testing-library/react";
import type { MouseEventHandler, ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { Navigation } from "./AppShell";

vi.mock("@tanstack/react-router", () => ({
  Link: ({
    to,
    children,
    onClick,
    ...props
  }: {
    to: string;
    children: ReactNode;
    onClick?: MouseEventHandler<HTMLAnchorElement>;
  }) => (
    <a href={to} onClick={onClick} {...props}>
      {children}
    </a>
  ),
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

  it("blocks navigation clicks while a long operation is locked", () => {
    render(<Navigation locked lockedReason="Repository ingestion is still running." />);

    const monitoringLink = screen.getByRole("link", { name: /admin monitoring/i });
    const clickResult = fireEvent.click(monitoringLink);

    expect(clickResult).toBe(false);
    expect(monitoringLink).toHaveAttribute("aria-disabled", "true");
    expect(monitoringLink).toHaveAttribute("title", "Repository ingestion is still running.");
  });
});
