import { FileCode2 } from "lucide-react";
import { useMemo, useState } from "react";
import { EmptyLine, Field } from "@/components/primitives";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { EvidenceItem } from "@/lib/rag-types";

function evidenceById(evidence: EvidenceItem[] | null | undefined) {
  return new Map((evidence ?? []).map((item) => [item.evidence_id, item]));
}

function formatLines(item: EvidenceItem) {
  if (item.start_line === null && item.end_line === null) return "n/a";
  if (item.start_line !== null && item.end_line !== null) {
    return `${item.start_line}-${item.end_line}`;
  }
  return String(item.start_line ?? item.end_line);
}

function EvidenceDetailDialog({
  item,
  open,
  onOpenChange,
  contentUnavailableLabel,
}: {
  item: EvidenceItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  contentUnavailableLabel: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader className="pr-8 text-left">
          <DialogTitle>Evidence detail</DialogTitle>
        </DialogHeader>
        {item ? (
          <div className="space-y-3">
            <div className="grid gap-1 rounded-md border border-border p-3">
              <Field label="Evidence ID">{item.evidence_id}</Field>
              <Field label="Path">{item.path || "n/a"}</Field>
              <Field label="Symbol">{item.symbol || "n/a"}</Field>
              <Field label="Lines">{formatLines(item)}</Field>
              <Field label="Reason">{item.reason || "n/a"}</Field>
            </div>
            <div>
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                Content
              </p>
              {item.content ? (
                <pre className="max-h-[360px] overflow-auto rounded-md border border-border bg-secondary/30 p-3 text-[12px] leading-5 whitespace-pre-wrap">
                  {item.content}
                </pre>
              ) : (
                <EmptyLine>{contentUnavailableLabel}</EmptyLine>
              )}
            </div>
          </div>
        ) : (
          <EmptyLine>No evidence item selected.</EmptyLine>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function EvidenceReferences({
  evidenceIds,
  evidence,
  prefix = "evidence:",
  contentUnavailableLabel = "No content snippet returned by this response.",
}: {
  evidenceIds: string[];
  evidence?: EvidenceItem[] | null | undefined;
  prefix?: string;
  contentUnavailableLabel?: string;
}) {
  const lookup = useMemo(() => evidenceById(evidence), [evidence]);
  const [selected, setSelected] = useState<EvidenceItem | null>(null);
  const ids = evidenceIds.filter(Boolean);

  if (ids.length === 0) return null;

  return (
    <>
      <span className="inline-flex flex-wrap items-center gap-1 mono text-[11px] text-muted-foreground">
        {prefix}
        {ids.map((id) => {
          const item = lookup.get(id);
          return item ? (
            <button
              key={id}
              type="button"
              onClick={() => setSelected(item)}
              className="inline-flex items-center gap-1 rounded-sm border border-border bg-background px-1 py-0.5 text-primary underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Open evidence ${id}`}
            >
              <FileCode2 className="h-3 w-3" aria-hidden />
              {id}
            </button>
          ) : (
            <span key={id}>{id}</span>
          );
        })}
      </span>
      <EvidenceDetailDialog
        item={selected}
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) setSelected(null);
        }}
        contentUnavailableLabel={contentUnavailableLabel}
      />
    </>
  );
}
