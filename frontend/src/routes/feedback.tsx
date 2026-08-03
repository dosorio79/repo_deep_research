import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { PlannedBackofficePanel } from "@/components/PlannedBackofficePanel";

export const Route = createFileRoute("/feedback")({
  head: () => ({
    meta: [
      { title: "Feedback (planned) — Repo Deep Research M3.6" },
      {
        name: "description",
        content: "Placeholder for the planned feedback surface. Not implemented in M3.6.",
      },
      { property: "og:title", content: "Feedback (planned) — Repo Deep Research M3.6" },
      {
        property: "og:description",
        content: "Planned reviewer feedback surface for the Repo Deep Research harness.",
      },
    ],
  }),
  component: () => (
    <AppShell>
      <PlannedBackofficePanel
        title="Feedback"
        description="Reviewer feedback capture has no backend endpoint in this milestone, so nothing is collected or stored here."
        scope={[
          "Per-answer accept / reject signals",
          "Evidence-level correctness marking",
          "Feedback export for dataset building",
        ]}
      />
    </AppShell>
  ),
});
