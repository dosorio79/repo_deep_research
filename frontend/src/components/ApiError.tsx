import { AlertTriangle } from "lucide-react";
import type { ApiErrorShape } from "@/lib/rag-types";

export function ApiError({ error }: { error: ApiErrorShape }) {
  return (
    <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 p-3">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden />
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-destructive">{error.title}</p>
          <p className="mt-1 whitespace-pre-wrap break-words mono text-[12px] text-muted-foreground">
            {error.detail}
          </p>
        </div>
      </div>
    </div>
  );
}
