import { ChevronRight } from "lucide-react";
import { useState } from "react";
import { CopyButton } from "@/components/primitives";
import { cn } from "@/lib/utils";

export function RawJsonPanel({ data, title = "Raw JSON" }: { data: unknown; title?: string }) {
  const [open, setOpen] = useState(false);
  const json = JSON.stringify(data, null, 2);

  return (
    <section className="panel">
      <header className="flex h-9 items-center justify-between gap-2 px-3">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
        >
          <ChevronRight
            className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-90")}
            aria-hidden
          />
          {title}
        </button>
        <CopyButton value={json} label="Copy JSON" />
      </header>
      {open ? (
        <pre className="max-h-[480px] overflow-auto border-t border-border bg-secondary/40 p-3 mono text-[12px] leading-relaxed">
          {json}
        </pre>
      ) : null}
    </section>
  );
}
