import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { PlannedBackofficePanel } from "@/components/PlannedBackofficePanel";

export const Route = createFileRoute("/monitoring")({
  head: () => ({
    meta: [
      { title: "Monitoring (planned) — Repo Deep Research M3.6" },
      {
        name: "description",
        content: "Placeholder for the planned monitoring surface. Not implemented in M3.6.",
      },
      { property: "og:title", content: "Monitoring (planned) — Repo Deep Research M3.6" },
      {
        property: "og:description",
        content: "Planned monitoring surface for the Repo Deep Research harness.",
      },
    ],
  }),
  component: () => (
    <AppShell>
      <PlannedBackofficePanel
        title="Monitoring"
        description="Operational telemetry is not exposed to this frontend. Per-request latency and usage are visible in the Trace panel of a Research run."
        scope={[
          "Aggregated latency and cost over time",
          "Error-rate and failure breakdowns",
          "Request history and search",
        ]}
      />
    </AppShell>
  ),
});
