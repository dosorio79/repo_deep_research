"""Tests for the relationship-aware evaluation harness."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def test_summarize_answer_results_includes_graph_usage() -> None:
    module = _load_script()

    summary = module.summarize_answer_results(
        [
            {
                "run_kind": "agentic",
                "answer_correctness": 4,
                "faithfulness": 5,
                "citation_precision": 5,
                "reference_coverage": 4,
                "answer_relevance": 4,
                "presentation_quality": 5,
                "unsupported_claim_count": 0,
                "graph_available": True,
                "graph_expansion_count": 1,
                "graph_nodes_visited": 3,
                "graph_relationship_counts": {"CALLS": 2},
            },
            {
                "run_kind": "agentic",
                "answer_correctness": 2,
                "faithfulness": 3,
                "citation_precision": 4,
                "reference_coverage": 2,
                "answer_relevance": 3,
                "presentation_quality": 4,
                "unsupported_claim_count": 2,
                "graph_available": True,
                "graph_expansion_count": 0,
                "graph_nodes_visited": 0,
                "graph_relationship_counts": {},
            },
        ]
    )

    assert summary["overall"]["count"] == 2
    assert summary["overall"]["answer_correctness"] == 3.0
    assert summary["graph_usage"] == {
        "available_count": 2,
        "expanded_count": 1,
        "graph_expansion_rate": 0.5,
        "total_expansions": 1,
        "total_nodes_visited": 3,
        "relationship_counts": {"CALLS": 2},
    }


def test_require_graph_expansion_rejects_zero_expanded_rows() -> None:
    module = _load_script()

    try:
        module.require_graph_expansion(
            {
                "graph_usage": {
                    "available_count": 2,
                    "expanded_count": 0,
                    "graph_expansion_rate": 0.0,
                }
            }
        )
    except SystemExit as error:
        assert "graph expansion was required" in str(error)
    else:
        raise AssertionError("require_graph_expansion should reject zero expansions")


def test_require_graph_expansion_accepts_expanded_rows() -> None:
    module = _load_script()

    module.require_graph_expansion(
        {
            "graph_usage": {
                "available_count": 2,
                "expanded_count": 1,
                "graph_expansion_rate": 0.5,
            }
        }
    )


def test_select_records_filters_question_type_and_limits() -> None:
    module = _load_script()

    records = [
        {"id": "locate_001", "question_type": "locate"},
        {"id": "flow_001", "question_type": "flow"},
        {"id": "flow_002", "question_type": "flow"},
        {"id": "change_001", "question_type": "change"},
    ]

    selected = module._select_records(
        records,
        question_types=["flow", "change"],
        max_records=2,
    )

    assert [record["id"] for record in selected] == ["flow_001", "flow_002"]


def test_select_records_rejects_non_positive_limit() -> None:
    module = _load_script()

    try:
        module._select_records(
            [{"id": "flow_001", "question_type": "flow"}],
            question_types=[],
            max_records=0,
        )
    except ValueError as error:
        assert "greater than zero" in str(error)
    else:
        raise AssertionError("max_records=0 should be rejected")


def test_compare_answer_reports_returns_candidate_minus_baseline_delta() -> None:
    module = _load_script()

    comparison = module.compare_answer_reports(
        [
            {
                "answer_correctness": 3,
                "faithfulness": 4,
                "citation_precision": 4,
                "reference_coverage": 3,
                "answer_relevance": 3,
                "presentation_quality": 4,
                "unsupported_claim_count": 2,
            }
        ],
        [
            {
                "answer_correctness": 4,
                "faithfulness": 5,
                "citation_precision": 5,
                "reference_coverage": 4,
                "answer_relevance": 4,
                "presentation_quality": 5,
                "unsupported_claim_count": 1,
            }
        ],
    )

    assert comparison["delta"]["answer_correctness"] == 1.0
    assert comparison["delta"]["unsupported_claim_count"] == -1.0


def _load_script() -> ModuleType:
    path = Path("scripts/evaluate_relationship_graph.py")
    spec = importlib.util.spec_from_file_location("evaluate_relationship_graph", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
