"""Deterministic retrieval evaluation for manually verified repository evidence."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import TypeAdapter

from repo_research.models import (
    EvaluationRecord,
    EvaluationResult,
    RepositoryIdentity,
    RetrievalEvaluationSummary,
    RetrievalMode,
    SearchQuery,
)
from repo_research.protocols import RepositorySearcher


def load_records(path: Path) -> list[EvaluationRecord]:
    """Load and validate a versioned JSON ground-truth dataset."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return TypeAdapter(list[EvaluationRecord]).validate_python(data)


def evaluate_records(
    *,
    database: RepositorySearcher,
    repository: RepositoryIdentity,
    records: list[EvaluationRecord],
    dataset: str,
    limit: int,
) -> list[EvaluationResult]:
    """Evaluate each baseline retrieval mode against verified evidence records."""
    return [
        _evaluate_mode(
            database=database,
            repository=repository,
            records=records,
            dataset=dataset,
            limit=limit,
            mode=mode,
        )
        for mode in RetrievalMode
    ]


def write_report(results: list[EvaluationResult], path: Path) -> None:
    """Write a stable JSON report suitable for review and comparison."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([result.model_dump(mode="json") for result in results], indent=2)
        + "\n",
        encoding="utf-8",
    )


def summarize_retrieval_results(
    results: list[EvaluationResult],
    *,
    source_label: str,
    selected_mode: RetrievalMode | None,
    measured_at: datetime,
) -> list[RetrievalEvaluationSummary]:
    """Convert JSON retrieval metrics into persisted dashboard rows."""
    return [
        RetrievalEvaluationSummary(
            **result.model_dump(),
            source_label=source_label,
            selected=result.mode is selected_mode,
            measured_at=measured_at,
        )
        for result in results
    ]


def _evaluate_mode(
    *,
    database: RepositorySearcher,
    repository: RepositoryIdentity,
    records: list[EvaluationRecord],
    dataset: str,
    limit: int,
    mode: RetrievalMode,
) -> EvaluationResult:
    file_hits = 0
    file_reciprocal_ranks = 0.0
    file_recalls = 0.0
    file_precisions = 0.0
    symbol_hits = 0
    for record in records:
        results = database.search(
            SearchQuery(
                text=record.question,
                repository_id=repository.repository_id,
                commit_hash=repository.commit_hash,
                limit=limit,
                mode=mode,
            )
        )
        result_files = [result.chunk.path for result in results]
        relevant_files = set(record.relevant_files)
        matched_files = relevant_files.intersection(result_files)
        file_hits += int(bool(matched_files))
        file_recalls += len(matched_files) / len(relevant_files)
        file_precisions += (
            len(matched_files) / len(set(result_files)) if results else 0.0
        )
        file_reciprocal_ranks += _reciprocal_rank(result_files, relevant_files)
        if record.relevant_symbols:
            result_symbols = {result.chunk.symbol for result in results}
            symbol_hits += int(
                bool(set(record.relevant_symbols).intersection(result_symbols))
            )

    count = len(records)
    denominator = float(count) if count else 1.0
    symbol_record_count = sum(bool(record.relevant_symbols) for record in records)
    symbol_denominator = float(symbol_record_count) if symbol_record_count else 1.0
    return EvaluationResult(
        dataset=dataset,
        mode=mode,
        limit=limit,
        record_count=count,
        file_hit_rate=file_hits / denominator,
        file_mrr=file_reciprocal_ranks / denominator,
        file_recall=file_recalls / denominator,
        file_precision=file_precisions / denominator,
        symbol_hit_rate=symbol_hits / symbol_denominator,
    )


def _reciprocal_rank(result_files: list[str], relevant_files: set[str]) -> float:
    for position, path in enumerate(result_files, start=1):
        if path in relevant_files:
            return 1.0 / position
    return 0.0
