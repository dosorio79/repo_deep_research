import { CopyButton, EmptyLine, Panel } from "@/components/primitives";
import type { EvidenceItem } from "@/lib/rag-types";

function lineRange(e: EvidenceItem) {
  if (e.start_line === null && e.end_line === null) return "—";
  if (e.start_line !== null && e.end_line !== null) return `${e.start_line}–${e.end_line}`;
  return String(e.start_line ?? e.end_line);
}

export function EvidencePanel({ evidence }: { evidence: EvidenceItem[] | null }) {
  const items = evidence ?? [];
  const allPaths = items
    .map((e) => (e.path ? `${e.path}${e.start_line !== null ? `:${e.start_line}` : ""}` : null))
    .filter(Boolean)
    .join("\n");

  return (
    <Panel
      title={`Evidence (${items.length})`}
      right={items.length > 0 ? <CopyButton value={allPaths} label="Copy paths" /> : undefined}
      className="overflow-hidden"
    >
      {items.length === 0 ? (
        <EmptyLine>No evidence returned for this query.</EmptyLine>
      ) : (
        <div className="-m-3 overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-border text-[11px] uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-1.5 font-medium">ID</th>
                <th className="px-3 py-1.5 font-medium">Path</th>
                <th className="px-3 py-1.5 font-medium">Lines</th>
                <th className="px-3 py-1.5 font-medium">Symbol</th>
                <th className="px-3 py-1.5 font-medium">Score</th>
                <th className="px-3 py-1.5 font-medium">Reason</th>
                <th className="px-3 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {items.map((e, i) => (
                <tr
                  key={e.evidence_id ?? i}
                  className="border-b border-border/60 align-top last:border-0 hover:bg-secondary/50"
                >
                  <td className="px-3 py-1.5 mono text-[12px] text-muted-foreground">
                    {e.evidence_id ?? i + 1}
                  </td>
                  <td className="max-w-[320px] px-3 py-1.5">
                    <span className="path-text block text-[12px]" title={e.path ?? undefined}>
                      {e.path ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 mono text-[12px] whitespace-nowrap">{lineRange(e)}</td>
                  <td className="max-w-[200px] px-3 py-1.5 mono text-[12px] break-all">
                    {e.symbol ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 mono text-[12px]">
                    {typeof e.score === "number" ? e.score.toFixed(3) : "—"}
                  </td>
                  <td className="max-w-[380px] px-3 py-1.5 text-[12px] text-muted-foreground">
                    {e.reason ?? "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    {e.path ? (
                      <CopyButton
                        value={`${e.path}${e.start_line !== null ? `:${e.start_line}` : ""}`}
                        label=""
                      />
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
