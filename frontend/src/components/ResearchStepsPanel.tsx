import { Route } from "lucide-react";
import { EmptyLine, Panel } from "@/components/primitives";
import type { ResearchStep } from "@/lib/rag-types";

export function ResearchStepsPanel({ steps }: { steps: ResearchStep[] | null | undefined }) {
  if (!Array.isArray(steps) || steps.length === 0) {
    return null;
  }

  return (
    <Panel
      title="Agentic research steps"
      right={<Route className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
    >
      <ol className="space-y-2">
        {steps.map((step) => (
          <li
            key={step.sequence}
            className="rounded-sm border border-border/70 bg-secondary/30 p-2"
          >
            <div className="flex gap-2">
              <span className="mono text-[12px] text-muted-foreground">
                {String(step.sequence).padStart(2, "0")}
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium">{step.action}</p>
                <p className="mt-1 text-[12px] text-muted-foreground">{step.rationale}</p>
                {step.evidence_ids.length > 0 ? (
                  <p className="mt-1 mono text-[11px] text-muted-foreground">
                    evidence: {step.evidence_ids.join(", ")}
                  </p>
                ) : (
                  <EmptyLine>No cited evidence for this step.</EmptyLine>
                )}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
