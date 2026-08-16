"""Tests for deterministic retrieval-evaluation records and metrics."""

import json
from datetime import UTC, datetime
from pathlib import Path

from repo_research.answer_evaluation import audit_evaluation_records
from repo_research.evaluation import (
    evaluate_records,
    load_records,
    summarize_retrieval_results,
    write_report,
)
from repo_research.models import (
    EvaluationRecord,
    EvaluationResult,
    ParsedChunk,
    RepositoryIdentity,
    RetrievalMode,
    SearchResult,
)


class FakeDatabase:
    """Return a fixed result so metrics do not depend on models or Qdrant."""

    def __init__(self, result: SearchResult) -> None:
        self._result = result

    def search(self, query: object) -> list[SearchResult]:
        return [self._result]


def test_evaluation_calculates_metrics_and_writes_stable_report(tmp_path: Path) -> None:
    repository = RepositoryIdentity(
        name="sample",
        root_path=tmp_path,
        branch="main",
        commit_hash="abc123",
    )
    chunk = ParsedChunk(
        chunk_id="chunk",
        repository_id=repository.repository_id,
        commit_hash=repository.commit_hash,
        path="src/example.py",
        language="python",
        chunk_type="function",
        symbol="target",
        start_line=1,
        end_line=2,
        content="def target():\n    return None\n",
        content_hash="hash",
    )
    records_path = tmp_path / "records.json"
    records_path.write_text(
        json.dumps(
            [
                EvaluationRecord(
                    id="locate_001",
                    question="Where is target?",
                    question_type="locate",
                    relevant_files=["src/example.py"],
                    relevant_symbols=["target"],
                ).model_dump()
            ]
        ),
        encoding="utf-8",
    )

    results = evaluate_records(
        database=FakeDatabase(SearchResult(chunk=chunk, score=1.0)),
        repository=repository,
        records=load_records(records_path),
        dataset="development",
        limit=5,
    )
    report_path = tmp_path / "report.json"
    write_report(results, report_path)

    assert len(results) == 3
    assert all(result.file_hit_rate == 1.0 for result in results)
    assert all(result.file_mrr == 1.0 for result in results)
    assert all(result.symbol_hit_rate == 1.0 for result in results)
    assert (
        json.loads(report_path.read_text(encoding="utf-8"))[0]["dataset"]
        == "development"
    )


def test_summarize_retrieval_results_adds_persistence_context() -> None:
    measured_at = datetime(2026, 8, 16, tzinfo=UTC)
    results = [
        EvaluationResult(
            dataset="eval/held_out.json",
            mode=RetrievalMode.DENSE,
            limit=5,
            record_count=15,
            file_hit_rate=0.5,
            file_mrr=0.4,
            file_recall=0.3,
            file_precision=0.2,
            symbol_hit_rate=0.1,
        ),
        EvaluationResult(
            dataset="eval/held_out.json",
            mode=RetrievalMode.HYBRID,
            limit=5,
            record_count=15,
            file_hit_rate=0.7,
            file_mrr=0.6,
            file_recall=0.5,
            file_precision=0.4,
            symbol_hit_rate=0.3,
        ),
    ]

    summaries = summarize_retrieval_results(
        results,
        source_label="datapeek held-out",
        selected_mode=RetrievalMode.HYBRID,
        measured_at=measured_at,
    )

    assert [summary.source_label for summary in summaries] == [
        "datapeek held-out",
        "datapeek held-out",
    ]
    assert [summary.selected for summary in summaries] == [False, True]
    assert [summary.measured_at for summary in summaries] == [measured_at, measured_at]


def test_versioned_ground_truth_sets_are_complete_disjoint_and_current() -> None:
    root = Path(__file__).parents[1]
    datapeek_root = root.parent / "datapeek"
    development = load_records(root / "eval/development.json")
    held_out = load_records(root / "eval/held_out.json")

    assert len(development) == 15
    assert len(held_out) == 15
    assert {record.id for record in development}.isdisjoint(
        record.id for record in held_out
    )
    audit = audit_evaluation_records({"development": development, "held_out": held_out})
    assert audit.record_count == 30
    assert audit.question_type_counts == {"change": 10, "flow": 10, "locate": 10}

    _assert_record_files_exist(development, root)
    _assert_external_record_files_exist_if_available(held_out, datapeek_root)


def test_external_ground_truth_file_check_allows_missing_repository(
    tmp_path: Path,
) -> None:
    records = [
        EvaluationRecord(
            id="external_locate_001",
            question="Where is the route?",
            question_type="locate",
            relevant_files=["app/main.py"],
        )
    ]

    _assert_external_record_files_exist_if_available(records, tmp_path / "missing")


def _assert_record_files_exist(
    records: list[EvaluationRecord], repository_root: Path
) -> None:
    missing = [
        f"{record.id}: {path}"
        for record in records
        for path in record.relevant_files
        if not (repository_root / path).exists()
    ]
    assert missing == []


def _assert_external_record_files_exist_if_available(
    records: list[EvaluationRecord], repository_root: Path
) -> None:
    if repository_root.exists():
        _assert_record_files_exist(records, repository_root)
        return

    assert all(record.relevant_files for record in records)
