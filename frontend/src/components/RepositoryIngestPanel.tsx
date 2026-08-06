import { CheckCircle2, DatabaseZap, FolderGit2, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { IngestSummary } from "@/lib/rag-types";

export function RepositoryIngestPanel({
  baseUrl,
  repositoryAddress,
  summary,
  loading,
  onAddressChange,
  onBaseUrlChange,
  onIngest,
}: {
  baseUrl: string;
  repositoryAddress: string;
  summary: IngestSummary | null;
  loading: boolean;
  onAddressChange: (value: string) => void;
  onBaseUrlChange: (value: string) => void;
  onIngest: () => void;
}) {
  const endpoint = `${baseUrl.replace(/\/+$/, "")}/repositories/ingest`;
  const canIngest = repositoryAddress.trim().length > 0 && !loading;

  return (
    <section className="panel p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <FolderGit2 className="h-4 w-4 text-primary" aria-hidden />
            <h2 className="text-[15px] font-semibold">Repository</h2>
          </div>
          <p className="mt-1 text-[12px] leading-relaxed text-muted-foreground">
            Add a local path or public GitHub URL, ingest it, then ask direct RAG or agentic RAG
            questions against that indexed revision.
          </p>
        </div>
        {summary ? (
          <Badge variant="secondary" className="gap-1 whitespace-nowrap">
            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden />
            indexed
          </Badge>
        ) : null}
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <div>
          <Label
            htmlFor="repositoryAddress"
            className="text-[11px] uppercase tracking-wide text-muted-foreground"
          >
            Repository address
          </Label>
          <Input
            id="repositoryAddress"
            value={repositoryAddress}
            spellCheck={false}
            placeholder="/path/to/python-repository or https://github.com/owner/repo"
            onChange={(event) => onAddressChange(event.target.value)}
            className="mt-1.5 mono text-[12px]"
          />
        </div>
        <div>
          <Label
            htmlFor="baseUrl"
            className="text-[11px] uppercase tracking-wide text-muted-foreground"
          >
            API base URL
          </Label>
          <Input
            id="baseUrl"
            value={baseUrl}
            spellCheck={false}
            onChange={(event) => onBaseUrlChange(event.target.value)}
            className="mt-1.5 mono text-[12px]"
          />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          size="sm"
          disabled={!canIngest}
          onClick={onIngest}
          className="gap-1.5"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
          ) : (
            <DatabaseZap className="h-3.5 w-3.5" aria-hidden />
          )}
          {loading ? "Ingesting..." : "Ingest repository"}
        </Button>
        <span className="mono text-[11px] text-muted-foreground">POST {endpoint}</span>
      </div>

      {summary ? (
        <div className="mt-3 grid gap-2 border-t border-border pt-3 text-[12px] sm:grid-cols-4">
          <div>
            <p className="text-muted-foreground">Name</p>
            <p className="mono truncate text-foreground">{summary.repository.name}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Branch</p>
            <p className="mono truncate text-foreground">{summary.repository.branch}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Commit</p>
            <p className="mono truncate text-foreground">{summary.repository.commit_hash}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Chunks</p>
            <p className="mono text-foreground">{summary.indexed_chunks}</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
