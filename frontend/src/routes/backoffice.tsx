import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/AppShell";
import { TechnicalResearchConsole } from "@/components/TechnicalResearchConsole";

export const Route = createFileRoute("/backoffice")({
  head: () => ({
    meta: [
      { title: "Backoffice — Repo Deep Research" },
      {
        name: "description",
        content:
          "Technical repository research console with ingestion, retrieval settings, evidence, trace, and raw JSON.",
      },
    ],
  }),
  component: BackofficeView,
});

function BackofficeView() {
  return (
    <AppShell>
      <TechnicalResearchConsole />
    </AppShell>
  );
}
