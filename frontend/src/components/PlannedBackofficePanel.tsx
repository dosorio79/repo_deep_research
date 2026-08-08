import { Construction } from "lucide-react";

export function PlannedBackofficePanel({
  title,
  description,
  scope,
}: {
  title: string;
  description: string;
  scope: string[];
}) {
  return (
    <div className="panel mx-auto max-w-2xl p-5">
      <div className="flex items-center gap-2">
        <Construction className="h-4 w-4 text-muted-foreground" aria-hidden />
        <h1 className="text-[15px] font-semibold">{title}</h1>
        <span className="rounded-sm border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
          planned
        </span>
      </div>
      <p className="mt-2 text-[13px] text-muted-foreground">{description}</p>
      <p className="mt-4 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Not implemented yet
      </p>
      <ul className="mt-2 space-y-1">
        {scope.map((s) => (
          <li key={s} className="flex gap-2 text-[13px] text-muted-foreground">
            <span aria-hidden className="text-border">
              —
            </span>
            <span>{s}</span>
          </li>
        ))}
      </ul>
      <p className="mt-4 border-t border-border pt-3 mono text-[11px] text-muted-foreground">
        This panel intentionally shows no data. No metrics, evaluations, or charts are available
        from the backend for this surface.
      </p>
    </div>
  );
}
