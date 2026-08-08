import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { PlannedBackofficePanel } from "@/components/PlannedBackofficePanel";

export const Route = createFileRoute("/evaluations")({
  head: () => ({
    meta: [
      { title: "Evaluations (planned) - Repo Deep Research" },
      {
        name: "description",
        content: "Placeholder for the planned evaluation surface.",
      },
      { property: "og:title", content: "Evaluations (planned) - Repo Deep Research" },
      {
        property: "og:description",
        content: "Planned evaluation surface for the Repo Deep Research harness.",
      },
    ],
  }),
  component: () => (
    <AppShell>
      <PlannedBackofficePanel
        title="Evaluations"
        description="Evaluation runs are executed outside this frontend. No evaluation execution or results UI exists in this milestone."
        scope={[
          "Dataset and eval-suite browsing",
          "Triggering evaluation runs",
          "Per-case scoring and regression comparison",
        ]}
      />
    </AppShell>
  ),
});
