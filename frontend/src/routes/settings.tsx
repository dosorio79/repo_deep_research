import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { PlannedBackofficePanel } from "@/components/PlannedBackofficePanel";

export const Route = createFileRoute("/settings")({
  head: () => ({
    meta: [
      { title: "Settings (planned) — Repo Deep Research M3.6" },
      {
        name: "description",
        content:
          "Settings are minimal in M3.6: the API base URL and repository path are configured per query in the Research view.",
      },
      { property: "og:title", content: "Settings (planned) — Repo Deep Research M3.6" },
      {
        property: "og:description",
        content: "Minimal settings surface for the Repo Deep Research harness.",
      },
    ],
  }),
  component: () => (
    <AppShell>
      <PlannedBackofficePanel
        title="Settings"
        description="Configuration is per-query and lives in the Research view: API base URL, and repository path under advanced settings. Nothing is persisted."
        scope={[
          "Persisted API base URL and defaults",
          "Named backend environments",
          "Request timeout and header overrides",
        ]}
      />
    </AppShell>
  ),
});
