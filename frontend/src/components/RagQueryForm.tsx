import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { QuestionMode, ResearchKind, RetrievalMode } from "@/lib/rag-types";

const MODES: QuestionMode[] = ["auto", "locate", "flow", "change"];
const RETRIEVAL_MODES: RetrievalMode[] = ["dense", "sparse", "hybrid"];
const RESEARCH_KINDS: ResearchKind[] = ["direct", "agentic"];

function researchKindLabel(kind: ResearchKind): string {
  return kind === "agentic" ? "agentic RAG" : "direct RAG";
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
  name,
}: {
  value: T;
  options: readonly T[];
  onChange: (v: T) => void;
  name: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={name}
      className="inline-flex rounded-md border border-border bg-secondary p-0.5"
    >
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          role="radio"
          aria-checked={value === opt}
          onClick={() => onChange(opt)}
          className={cn(
            "rounded-[4px] px-2.5 py-1 mono text-[12px] transition-colors",
            value === opt
              ? "bg-card text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {name === "research type" ? researchKindLabel(opt as ResearchKind) : opt}
        </button>
      ))}
    </div>
  );
}

export interface QueryFormState {
  researchKind: ResearchKind;
  question: string;
  mode: QuestionMode;
  retrievalMode: RetrievalMode;
  limit: number;
}

export function RagQueryForm({
  state,
  onChange,
  onSubmit,
  loading,
}: {
  state: QueryFormState;
  onChange: (patch: Partial<QueryFormState>) => void;
  onSubmit: () => void;
  loading: boolean;
}) {
  const disabled = loading || state.question.trim().length === 0;

  return (
    <form
      className="panel p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!disabled) onSubmit();
      }}
    >
      <div className="mb-3 rounded-md border border-border bg-secondary/40 p-2">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Research type
        </span>
        <div className="mt-1.5">
          <Segmented
            name="research type"
            value={state.researchKind}
            options={RESEARCH_KINDS}
            onChange={(researchKind) =>
              onChange({
                researchKind,
                mode: researchKind === "agentic" && state.mode === "auto" ? "change" : state.mode,
              })
            }
          />
        </div>
        <p className="mt-1.5 text-[12px] text-muted-foreground">
          {state.researchKind === "agentic"
            ? "Bounded tool-using research for change-impact questions."
            : "Grounded answer from retrieved repository evidence."}
        </p>
      </div>

      <Label
        htmlFor="question"
        className="text-[11px] uppercase tracking-wide text-muted-foreground"
      >
        Question
      </Label>
      <Textarea
        id="question"
        value={state.question}
        onChange={(e) => onChange({ question: e.target.value })}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !disabled) {
            e.preventDefault();
            onSubmit();
          }
        }}
        rows={5}
        spellCheck={false}
        placeholder={
          state.researchKind === "agentic"
            ? "e.g. Which modules must change to add feedback persistence?"
            : "e.g. Where is retrieval limit validated before the model call?"
        }
        className="mt-1.5 resize-y mono text-[13px]"
      />

      <div className="mt-3 space-y-3">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">Mode</span>
          <Segmented
            name="question mode"
            value={state.mode}
            options={MODES}
            onChange={(mode) => onChange({ mode })}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Retrieval mode
          </span>
          <Segmented
            name="retrieval mode"
            value={state.retrievalMode}
            options={RETRIEVAL_MODES}
            onChange={(retrievalMode) => onChange({ retrievalMode })}
          />
        </div>

        <div>
          <div className="flex items-center justify-between">
            <Label
              htmlFor="limit"
              className="text-[11px] uppercase tracking-wide text-muted-foreground"
            >
              {state.researchKind === "agentic" ? "Retrieval limit" : "Limit"}
            </Label>
            <div className="flex items-center gap-1">
              <button
                type="button"
                aria-label="Decrease limit"
                onClick={() => onChange({ limit: Math.max(1, state.limit - 1) })}
                className="h-6 w-6 rounded-sm border border-border text-muted-foreground hover:bg-secondary"
              >
                −
              </button>
              <span className="w-7 text-center mono text-[13px]">{state.limit}</span>
              <button
                type="button"
                aria-label="Increase limit"
                onClick={() => onChange({ limit: Math.min(20, state.limit + 1) })}
                className="h-6 w-6 rounded-sm border border-border text-muted-foreground hover:bg-secondary"
              >
                +
              </button>
            </div>
          </div>
          <Slider
            id="limit"
            className="mt-2"
            min={1}
            max={20}
            step={1}
            value={[state.limit]}
            onValueChange={(v) => onChange({ limit: v[0] ?? state.limit })}
          />
        </div>

        <div className="flex items-center gap-2 border-t border-border pt-3">
          <Button type="submit" size="sm" disabled={disabled} className="gap-1.5">
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            ) : (
              <Play className="h-3.5 w-3.5" aria-hidden />
            )}
            {loading ? "Running…" : "Run query"}
          </Button>
          <span className="mono text-[11px] text-muted-foreground">⌘/Ctrl + Enter</span>
        </div>
      </div>
    </form>
  );
}
