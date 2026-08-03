"""Tests for model price estimation telemetry."""

from decimal import Decimal

import pytest

from repo_research.pricing import estimate_openai_price


def test_estimate_openai_price_for_known_model() -> None:
    estimate = estimate_openai_price(
        model="gpt-5-mini",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )

    assert estimate.input_cost_usd == Decimal("0.25")
    assert estimate.output_cost_usd == Decimal("1.000")
    assert estimate.total_cost_usd == Decimal("1.250")
    assert estimate.pricing_source != "unknown"


def test_estimate_openai_price_uses_cached_input_price() -> None:
    estimate = estimate_openai_price(
        model="gpt-5-mini",
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=0,
    )

    assert estimate.input_cost_usd == Decimal("0.1875")
    assert estimate.cached_input_cost_usd == Decimal("0.00625")
    assert estimate.total_cost_usd == Decimal("0.19375")


def test_estimate_openai_price_unknown_model_is_non_fatal() -> None:
    estimate = estimate_openai_price(
        model="unknown-model",
        input_tokens=1_000,
        output_tokens=500,
    )

    assert estimate.total_cost_usd is None
    assert estimate.pricing_source == "unknown"


def test_estimate_openai_price_respects_empty_override_table() -> None:
    estimate = estimate_openai_price(
        model="gpt-5-mini",
        input_tokens=1_000,
        output_tokens=500,
        model_prices={},
    )

    assert estimate.total_cost_usd is None
    assert estimate.pricing_source == "unknown"


def test_estimate_openai_price_rejects_invalid_token_counts() -> None:
    with pytest.raises(ValueError, match="input_tokens"):
        estimate_openai_price(
            model="gpt-5-mini",
            input_tokens=-1,
            output_tokens=0,
        )
