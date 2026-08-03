import { Link } from "@tanstack/react-router";
import { Search, FlaskConical, Activity, MessageSquare, Settings, Terminal } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Research", icon: Search, status: "active" },
  { to: "/evaluations", label: "Evaluations", icon: FlaskConical, status: "planned" },
  { to: "/monitoring", label: "Monitoring", icon: Activity, status: "active" },
  { to: "/feedback", label: "Feedback", icon: MessageSquare, status: "planned" },
  { to: "/settings", label: "Settings", icon: Settings, status: "planned" },
] as const;

export function Navigation() {
  return (
    <nav className="flex items-center gap-0.5">
      {NAV.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          activeOptions={{ exact: item.to === "/" }}
          className={cn(
            "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground",
          )}
          activeProps={{ className: "bg-secondary text-foreground font-medium" }}
        >
          <item.icon className="h-3.5 w-3.5" aria-hidden />
          <span>{item.label}</span>
          {item.status === "planned" ? (
            <span className="rounded-sm border border-border px-1 text-[10px] uppercase tracking-wide text-muted-foreground">
              planned
            </span>
          ) : null}
        </Link>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-card/95 backdrop-blur">
        <div className="mx-auto flex h-12 max-w-[1600px] items-center gap-4 px-4">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-primary" aria-hidden />
            <span className="mono text-[13px] font-semibold tracking-tight">
              Repo Deep Research
            </span>
            <span className="rounded-sm bg-secondary px-1.5 py-0.5 mono text-[10px] text-muted-foreground">
              M3.6
            </span>
          </div>
          <Navigation />
          <div className="ml-auto mono text-[11px] text-muted-foreground">
            backend testing harness
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] px-4 py-4">{children}</main>
    </div>
  );
}
