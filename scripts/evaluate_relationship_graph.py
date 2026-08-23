"""Run relationship-aware graph evaluation checks.

The default mode is offline: it ingests a repository, validates the graph
artifact, and writes a compact summary. Pass --run-answers to run the existing
LLM judge-backed answer evaluation and include those metrics in the same output
directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path("artifacts/eval/relationship-aware")
DEFAULT_DATASET = Path("eval/development.json")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    repository_path = args.path or _prepare_default_fixture(output_dir)

    ingest = _run_json(["uv", "run", "repo-research", "ingest", str(repository_path)])
    graph_summary = _run_json(
        ["uv", "run", "repo-research", "graph-summary", "--path", str(repository_path)]
    )
    _write_json(output_dir / "ingest-summary.json", ingest)
    _write_json(output_dir / "graph-summary.json", graph_summary)

    checks = _graph_checks(graph_summary)
    answer_report_path: Path | None = None
    answer_summary: dict[str, Any] | None = None
    if args.run_answers:
        if not os.environ.get("OPENAI_API_KEY"):
            raise SystemExit("--run-answers requires OPENAI_API_KEY")
        answer_report_path = output_dir / "answer-agentic-hybrid.json"
        answer_results = _run_json(
            [
                "uv",
                "run",
                "repo-research",
                "evaluate-answers",
                "--source",
                "dataset",
                "--dataset",
                str(args.dataset),
                "--path",
                str(repository_path),
                "--approach",
                "agentic",
                "--retrieval-mode",
                "hybrid",
                "--workers",
                str(args.workers),
                "--output",
                str(answer_report_path),
            ]
        )
        if not isinstance(answer_results, list):
            raise SystemExit("evaluate-answers did not return a JSON list")
        answer_summary = summarize_answer_results(answer_results)
        _write_json(output_dir / "answer-summary.json", answer_summary)

    comparison: dict[str, Any] | None = None
    if args.baseline_report and answer_report_path:
        comparison = compare_answer_reports(
            _read_json_list(args.baseline_report),
            _read_json_list(answer_report_path),
        )
        _write_json(output_dir / "answer-comparison.json", comparison)

    run_summary = {
        "path": str(repository_path),
        "output_dir": str(output_dir),
        "graph_checks": checks,
        "graph_summary": graph_summary,
        "answer_report": str(answer_report_path) if answer_report_path else None,
        "answer_summary": answer_summary,
        "comparison": comparison,
    }
    _write_json(output_dir / "summary.json", run_summary)
    print(json.dumps(run_summary, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate relationship-aware graph research readiness."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="repository to evaluate; defaults to a generated fixture repository",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument(
        "--run-answers",
        action="store_true",
        help="run paid/LLM answer evaluation with the existing judge pipeline",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=None,
        help="optional previous evaluate-answers JSON report for A/B comparison",
    )
    return parser


def _prepare_default_fixture(output_dir: Path) -> Path:
    root = output_dir / "fixture-repo"
    if root.exists():
        shutil.rmtree(root)
    _write_text(root / "src/acme/config.py", 'TIMEOUT_ENV = "ACME_TIMEOUT"\n')
    _write_text(
        root / "src/acme/service.py",
        """
from acme.config import TIMEOUT_ENV


def traced(func):
    return func


class BaseService:
    pass


class SearchService(BaseService):
    @traced
    def run(self) -> str:
        return helper(TIMEOUT_ENV)


def helper(value: str) -> str:
    return value
""".strip()
        + "\n",
    )
    _write_text(
        root / "tests/test_service.py",
        """
from acme.service import SearchService


def test_service_reads_config() -> None:
    assert SearchService().run() == "ACME_TIMEOUT"
""".strip()
        + "\n",
    )
    _run(
        [
            "git",
            "-C",
            str(root),
            "init",
        ]
    )
    _run(["git", "-C", str(root), "add", "."])
    _run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=eval@example.com",
            "-c",
            "user.name=Eval Runner",
            "commit",
            "-m",
            "fixture",
        ]
    )
    return root


def summarize_answer_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Return compact metrics from persisted answer-evaluation JSON rows."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[str(row.get("run_kind", "unknown"))].append(row)

    return {
        "overall": _summarize_rows(results),
        "by_run_kind": {
            run_kind: _summarize_rows(rows)
            for run_kind, rows in sorted(grouped.items())
        },
        "graph_usage": {
            "available_count": sum(1 for row in results if row.get("graph_available")),
            "expanded_count": sum(
                1 for row in results if int(row.get("graph_expansion_count") or 0) > 0
            ),
            "total_expansions": sum(
                int(row.get("graph_expansion_count") or 0) for row in results
            ),
            "total_nodes_visited": sum(
                int(row.get("graph_nodes_visited") or 0) for row in results
            ),
            "relationship_counts": _sum_relationship_counts(results),
        },
    }


def compare_answer_reports(
    baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]
) -> dict[str, Any]:
    """Compare reports with candidate-minus-baseline deltas."""
    baseline_summary = summarize_answer_results(baseline)["overall"]
    candidate_summary = summarize_answer_results(candidate)["overall"]
    metric_names = [
        "answer_correctness",
        "faithfulness",
        "citation_precision",
        "reference_coverage",
        "answer_relevance",
        "presentation_quality",
        "unsupported_claim_count",
    ]
    return {
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "delta": {
            metric: _delta(candidate_summary.get(metric), baseline_summary.get(metric))
            for metric in metric_names
        },
    }


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": len(rows),
        "answer_correctness": _average(rows, "answer_correctness"),
        "faithfulness": _average(rows, "faithfulness"),
        "citation_precision": _average(rows, "citation_precision"),
        "reference_coverage": _average(rows, "reference_coverage"),
        "answer_relevance": _average(rows, "answer_relevance"),
        "presentation_quality": _average(rows, "presentation_quality"),
        "unsupported_claim_count": _average(rows, "unsupported_claim_count"),
        "latency_ms_total": _average(rows, "latency_ms_total"),
    }


def _average(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(value) for row in rows if (value := row.get(key)) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _delta(candidate: object, baseline: object) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(float(candidate) - float(baseline), 3)


def _sum_relationship_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        relationships = row.get("graph_relationship_counts") or {}
        if isinstance(relationships, dict):
            for name, count in relationships.items():
                counts[str(name)] += int(count)
    return dict(sorted(counts.items()))


def _graph_checks(graph_summary: dict[str, Any]) -> dict[str, Any]:
    node_count = int(graph_summary.get("node_count") or 0)
    edge_count = int(graph_summary.get("edge_count") or 0)
    edge_counts = graph_summary.get("edge_counts_by_type") or {}
    checks = {
        "has_nodes": node_count > 0,
        "has_edges": edge_count > 0,
        "has_relationship_counts": bool(edge_counts),
    }
    if not all(checks.values()):
        raise SystemExit(f"graph artifact failed readiness checks: {checks}")
    return checks


def _run_json(command: list[str]) -> Any:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        message = [
            f"command failed with exit code {completed.returncode}: {' '.join(command)}"
        ]
        if completed.stdout.strip():
            message.extend(["stdout:", completed.stdout.strip()])
        if completed.stderr.strip():
            message.extend(["stderr:", completed.stderr.strip()])
        raise SystemExit("\n".join(message))
    return _parse_json_stdout(completed.stdout)


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        message = [
            f"command failed with exit code {completed.returncode}: {' '.join(command)}"
        ]
        if completed.stdout.strip():
            message.extend(["stdout:", completed.stdout.strip()])
        if completed.stderr.strip():
            message.extend(["stderr:", completed.stderr.strip()])
        raise SystemExit("\n".join(message))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _parse_json_stdout(stdout: str) -> Any:
    stripped = stdout.strip()
    if not stripped:
        raise ValueError("command returned empty stdout")
    for index, character in enumerate(stripped):
        if character in "[{":
            return json.loads(stripped[index:])
    raise ValueError("command stdout did not contain JSON")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"{path} does not contain a JSON list")
    return [dict(row) for row in value]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    sys.exit(main())
