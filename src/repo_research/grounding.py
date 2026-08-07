"""Shared grounding helpers for canonical evidence-derived output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

from repo_research.models import ChangeTarget, EvidenceItem


class ChangeTargetLike(Protocol):
    """Minimal shape needed to canonicalize a proposed change target."""

    reason: str
    evidence_ids: list[str]


def canonical_change_targets(
    targets: Iterable[ChangeTargetLike],
    evidence_by_id: Mapping[str, EvidenceItem],
) -> list[ChangeTarget]:
    """Return change targets pinned to the first cited canonical evidence item."""
    canonical: list[ChangeTarget] = []
    for target in targets:
        evidence_ids = [
            evidence_id
            for evidence_id in target.evidence_ids
            if evidence_id in evidence_by_id
        ]
        if not evidence_ids:
            continue
        first_evidence = evidence_by_id[evidence_ids[0]]
        canonical.append(
            ChangeTarget(
                path=first_evidence.path,
                symbol=first_evidence.symbol,
                reason=target.reason,
                evidence_ids=evidence_ids,
            )
        )
    return canonical
