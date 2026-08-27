"""Background repository ingestion job orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Thread
from typing import Protocol

from qdrant_client.http.exceptions import ResponseHandlingException

from repo_research.models import (
    IngestionJob,
    IngestionJobStatus,
    IngestSummary,
    RepositoryIngestRequest,
)


class IngestionJobStore(Protocol):
    """Persistence operations needed by background ingestion jobs."""

    def create_ingestion_job(self, job: IngestionJob) -> IngestionJob:
        """Persist a new ingestion job."""

    def get_ingestion_job(self, job_id: str) -> IngestionJob | None:
        """Return one ingestion job if it exists."""

    def latest_active_ingestion_job(self) -> IngestionJob | None:
        """Return the newest active ingestion job if one exists."""

    def update_ingestion_job(self, job: IngestionJob) -> IngestionJob:
        """Persist mutable ingestion job fields."""

    def interrupt_active_ingestion_jobs(self) -> int:
        """Mark active jobs from a previous process as interrupted."""


WorkerStarter = Callable[[Callable[[], None]], None]
IngestRunner = Callable[[RepositoryIngestRequest], IngestSummary]


def start_daemon_thread(work: Callable[[], None]) -> None:
    """Run ingestion work after the API response can be returned."""
    thread = Thread(target=work, daemon=True)
    thread.start()


class IngestionJobService:
    """Create, run, and recover background repository ingestion jobs."""

    def __init__(
        self,
        *,
        store: IngestionJobStore,
        run_ingest: IngestRunner,
        worker_starter: WorkerStarter = start_daemon_thread,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._run_ingest = run_ingest
        self._worker_starter = worker_starter
        self._clock = clock or (lambda: datetime.now(UTC))

    def start(self, request: RepositoryIngestRequest) -> IngestionJob:
        """Persist a queued job and start ingestion in the background."""
        now = self._clock()
        job = self._store.create_ingestion_job(
            IngestionJob(
                repository_address=request.repository_address,
                status=IngestionJobStatus.QUEUED,
                created_at=now,
                updated_at=now,
            )
        )
        self._worker_starter(lambda: self._run(job.job_id, request))
        return self._with_elapsed(job)

    def get(self, job_id: str) -> IngestionJob | None:
        """Return one job with current elapsed time for active states."""
        job = self._store.get_ingestion_job(job_id)
        return self._with_elapsed(job) if job else None

    def latest_active(self) -> IngestionJob | None:
        """Return the newest active job with current elapsed time."""
        job = self._store.latest_active_ingestion_job()
        return self._with_elapsed(job) if job else None

    def cancel(self, job_id: str) -> IngestionJob | None:
        """Cancel a queued job when possible."""
        job = self._store.get_ingestion_job(job_id)
        if not job:
            return None
        if job.status != IngestionJobStatus.QUEUED:
            return self._with_elapsed(job)
        now = self._clock()
        cancelled = job.model_copy(
            update={
                "status": IngestionJobStatus.CANCELLED,
                "updated_at": now,
                "completed_at": now,
                "elapsed_seconds": self._elapsed_seconds(job, now),
            }
        )
        return self._store.update_ingestion_job(cancelled)

    def interrupt_abandoned(self) -> int:
        """Mark jobs left active by a previous API process as interrupted."""
        return self._store.interrupt_active_ingestion_jobs()

    def _run(self, job_id: str, request: RepositoryIngestRequest) -> None:
        job = self._store.get_ingestion_job(job_id)
        if job is None or job.status == IngestionJobStatus.CANCELLED:
            return
        now = self._clock()
        running = self._store.update_ingestion_job(
            job.model_copy(
                update={
                    "status": IngestionJobStatus.INDEXING,
                    "started_at": job.started_at or now,
                    "updated_at": now,
                    "elapsed_seconds": self._elapsed_seconds(job, now),
                }
            )
        )
        try:
            summary = self._run_ingest(request)
        except Exception as error:
            self._store.update_ingestion_job(
                running.model_copy(
                    update={
                        "status": IngestionJobStatus.FAILED,
                        "updated_at": self._clock(),
                        "completed_at": self._clock(),
                        "elapsed_seconds": self._elapsed_seconds(
                            running, self._clock()
                        ),
                        "error_type": type(error).__name__,
                        "error_detail": _safe_error_detail(error),
                    }
                )
            )
            return
        now = self._clock()
        self._store.update_ingestion_job(
            running.model_copy(
                update={
                    "status": IngestionJobStatus.COMPLETED,
                    "updated_at": now,
                    "completed_at": now,
                    "elapsed_seconds": self._elapsed_seconds(running, now),
                    "repository": summary.repository,
                    "summary": summary,
                    "error_type": None,
                    "error_detail": None,
                }
            )
        )

    def _with_elapsed(self, job: IngestionJob) -> IngestionJob:
        now = self._clock()
        return job.model_copy(
            update={"elapsed_seconds": self._elapsed_seconds(job, now)}
        )

    @staticmethod
    def _elapsed_seconds(job: IngestionJob, now: datetime) -> int:
        anchor = job.started_at or job.created_at
        return max(0, int((now - anchor).total_seconds()))


def _safe_error_detail(error: Exception) -> str:
    if isinstance(error, ValueError):
        return str(error)
    if isinstance(error, ResponseHandlingException):
        return (
            "Repository vector store is unavailable; start Qdrant and retry ingestion."
        )
    return "Repository ingestion failed; check API logs and retry."
