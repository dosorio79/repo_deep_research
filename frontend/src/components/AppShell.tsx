import { Link } from "@tanstack/react-router";
import { Activity, ClipboardCheck, Lock, Search, Terminal } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Research", icon: Search },
  { to: "/monitoring", label: "Admin Monitoring", icon: Activity, admin: true },
  { to: "/evaluations", label: "Admin Evaluations", icon: ClipboardCheck, admin: true },
] as const;

export function Navigation() {
  return (
    <nav className="flex min-w-0 items-center gap-0.5 overflow-x-auto">
      {NAV.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          activeOptions={{ exact: item.to === "/" }}
          className={cn(
            "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          )}
          activeProps={{ className: "bg-secondary text-foreground font-medium" }}
        >
          <item.icon className="h-3.5 w-3.5" aria-hidden />
          <span>{item.label}</span>
          {"admin" in item ? <Lock className="h-3 w-3" aria-hidden /> : null}
        </Link>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-2 px-4 py-2 lg:h-12 lg:flex-row lg:items-center lg:gap-4 lg:py-0">
          <div className="flex shrink-0 items-center gap-2">
            <Terminal className="h-4 w-4 text-primary" aria-hidden />
            <span className="whitespace-nowrap mono text-[13px] font-semibold tracking-tight">
              Repo Deep Research
            </span>
          </div>
          <Navigation />
          <div className="hidden whitespace-nowrap mono text-[11px] text-muted-foreground xl:ml-auto xl:block">
            evidence-grounded repository research
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-4">{children}</main>
    </div>
  );
}
