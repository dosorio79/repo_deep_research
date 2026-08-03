import {
  AlertTriangle,
  FileCode2,
  GitPullRequestArrow,
  HelpCircle,
  ListOrdered,
} from "lucide-react";
import { CopyButton, EmptyLine, Panel } from "@/components/primitives";
import type { ChangeTarget, RagAnswer } from "@/lib/rag-types";

function List({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1">
      {items.map((item, i) => (
        <li key={i} className="flex gap-2 text-[13px]">
          <span className="mono text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function Chips({ items, copyable }: { items: string[]; copyable?: boolean }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item, i) => (
        <span
          key={i}
          className="group inline-flex max-w-full items-center gap-1 rounded-sm border border-border bg-secondary/60 px-1.5 py-0.5 mono text-[12px]"
        >
          <span className="path-text truncate" title={item}>
            {item}
          </span>
          {copyable ? <CopyButton value={item} label="" className="border-0 px-0.5" /> : null}
        </span>
      ))}
    </div>
  );
}

function ChangeTargetList({ items }: { items: ChangeTarget[] }) {
  return (
    <ul className="space-y-2">
      {items.map((item, i) => {
        const target = item.symbol ? `${item.path}::${item.symbol}` : item.path;
        return (
          <li
            key={`${target}-${i}`}
            className="rounded-sm border border-border/70 bg-secondary/30 p-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="path-text text-[12px]" title={target}>
                  {target}
                </p>
                <p className="mt-1 text-[12px] text-muted-foreground">{item.reason}</p>
              </div>
              <CopyButton value={target} label="" className="shrink-0" />
            </div>
            {item.evidence_ids.length > 0 ? (
              <p className="mt-1 mono text-[11px] text-muted-foreground">
                evidence: {item.evidence_ids.join(", ")}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function confidenceLabel(c: RagAnswer["confidence"]) {
  if (c === null || c === undefined) return "Unknown";
  if (typeof c === "number") return c.toFixed(2);
  return c;
}

export function AnswerPanel({ answer }: { answer: RagAnswer | null }) {
  if (!answer) {
    return (
      <Panel title="Answer">
        <EmptyLine>No answer object in the response.</EmptyLine>
      </Panel>
    );
  }

  const hasItems = <T,>(a: T[] | null | undefined) => Array.isArray(a) && a.length > 0;

  return (
    <div className="space-y-3">
      {answer.insufficient_evidence ? (
        <div className="flex items-start gap-2 rounded-md border border-warning/50 bg-warning/10 p-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning-foreground" aria-hidden />
          <p className="text-[13px] text-warning-foreground">
            Insufficient evidence — the backend reported it could not ground an answer in retrieved
            code.
          </p>
        </div>
      ) : null}

      <Panel
        title="Summary"
        right={
          <span className="mono text-[11px] text-muted-foreground">
            confidence: {confidenceLabel(answer.confidence)}
          </span>
        }
      >
        {answer.summary ? (
          <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{answer.summary}</p>
        ) : (
          <EmptyLine>No summary returned.</EmptyLine>
        )}
      </Panel>

      <Panel
        title="Implementation flow"
        right={<ListOrdered className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
      >
        {hasItems(answer.implementation_flow) ? (
          <List items={answer.implementation_flow!} />
        ) : (
          <EmptyLine>No implementation flow returned.</EmptyLine>
        )}
      </Panel>

      <div className="grid gap-3 md:grid-cols-2">
        <Panel
          title="Relevant files"
          right={<FileCode2 className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
        >
          {hasItems(answer.relevant_files) ? (
            <Chips items={answer.relevant_files!} copyable />
          ) : (
            <EmptyLine>None returned.</EmptyLine>
          )}
        </Panel>
        <Panel title="Relevant symbols">
          {hasItems(answer.relevant_symbols) ? (
            <Chips items={answer.relevant_symbols!} />
          ) : (
            <EmptyLine>None returned.</EmptyLine>
          )}
        </Panel>
      </div>

      {hasItems(answer.change_targets) ? (
        <Panel
          title="Change targets"
          right={<GitPullRequestArrow className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
        >
          <ChangeTargetList items={answer.change_targets!} />
        </Panel>
      ) : null}

      <div className="grid gap-3 md:grid-cols-2">
        <Panel
          title="Risks"
          right={<AlertTriangle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
        >
          {hasItems(answer.risks) ? (
            <List items={answer.risks!} />
          ) : (
            <EmptyLine>None returned.</EmptyLine>
          )}
        </Panel>
        <Panel
          title="Unresolved questions"
          right={<HelpCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />}
        >
          {hasItems(answer.unresolved_questions) ? (
            <List items={answer.unresolved_questions!} />
          ) : (
            <EmptyLine>None returned.</EmptyLine>
          )}
        </Panel>
      </div>
    </div>
  );
}
