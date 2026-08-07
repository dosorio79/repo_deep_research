"""Shared telemetry helpers for run traces and model usage."""

from __future__ import annotations

import time
from decimal import Decimal

from repo_research.models import ModelUsage


def elapsed_ms(start: float) -> int:
    """Return elapsed milliseconds since a perf-counter start time."""
    return max(0, round((time.perf_counter() - start) * 1000))


def total_estimated_cost(model_usage: list[ModelUsage]) -> Decimal | None:
    """Return the total estimated cost when every usage item has a known cost."""
    if not model_usage:
        return None
    total = Decimal("0")
    for usage in model_usage:
        if usage.estimated_cost_usd is None:
            return None
        total += usage.estimated_cost_usd
    return total


def usage_int(usage: object, field_name: str) -> int | None:
    """Read one integer usage field from provider-specific usage objects."""
    value = getattr(usage, field_name, None)
    return value if isinstance(value, int) else None
