"""OpenAI token price estimation for application telemetry."""

from __future__ import annotations

from decimal import Decimal
from typing import NotRequired, TypedDict

from pydantic import BaseModel, Field


class ModelPrice(TypedDict):
    """USD prices per one million tokens for a text model."""

    input: Decimal
    output: Decimal
    cached_input: NotRequired[Decimal]


PRICING_SOURCE = "https://developers.openai.com/api/docs/models"
PRICING_VERSION = "openai-api-pricing-snapshot"

MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-5-mini": {
        "input": Decimal("0.25"),
        "cached_input": Decimal("0.025"),
        "output": Decimal("2.00"),
    },
    "gpt-5.1": {
        "input": Decimal("1.25"),
        "cached_input": Decimal("0.125"),
        "output": Decimal("10.00"),
    },
    "gpt-5": {
        "input": Decimal("1.25"),
        "cached_input": Decimal("0.125"),
        "output": Decimal("10.00"),
    },
    "gpt-5.4-mini": {
        "input": Decimal("0.75"),
        "output": Decimal("4.50"),
    },
    "gpt-5.4-nano": {
        "input": Decimal("0.20"),
        "output": Decimal("1.25"),
    },
}


class PriceEstimate(BaseModel):
    """A non-fatal model cost estimate for one usage record."""

    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(ge=0)
    input_cost_usd: Decimal | None = Field(default=None, ge=0)
    cached_input_cost_usd: Decimal | None = Field(default=None, ge=0)
    output_cost_usd: Decimal | None = Field(default=None, ge=0)
    total_cost_usd: Decimal | None = Field(default=None, ge=0)
    pricing_source: str = Field(min_length=1)
    pricing_version: str = Field(min_length=1)


def estimate_openai_price(
    *,
    input_tokens: int,
    output_tokens: int,
    model: str,
    cached_input_tokens: int = 0,
    model_prices: dict[str, ModelPrice] | None = None,
) -> PriceEstimate:
    """Estimate OpenAI API cost without failing for unknown model pricing."""
    _validate_token_count("input_tokens", input_tokens)
    _validate_token_count("output_tokens", output_tokens)
    _validate_token_count("cached_input_tokens", cached_input_tokens)

    prices = MODEL_PRICES if model_prices is None else model_prices
    model_price = prices.get(model)
    if model_price is None:
        return PriceEstimate(
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            pricing_source="unknown",
            pricing_version="unknown",
        )
    if cached_input_tokens and "cached_input" not in model_price:
        return PriceEstimate(
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            pricing_source=PRICING_SOURCE,
            pricing_version=PRICING_VERSION,
        )

    billable_input_tokens = input_tokens - cached_input_tokens
    if billable_input_tokens < 0:
        msg = "cached_input_tokens cannot exceed input_tokens"
        raise ValueError(msg)

    input_cost = _token_cost(billable_input_tokens, model_price["input"])
    cached_input_cost = _token_cost(
        cached_input_tokens, model_price.get("cached_input", model_price["input"])
    )
    output_cost = _token_cost(output_tokens, model_price["output"])
    total_cost = input_cost + cached_input_cost + output_cost
    return PriceEstimate(
        model=model,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=total_cost,
        pricing_source=PRICING_SOURCE,
        pricing_version=PRICING_VERSION,
    )


def _token_cost(tokens: int, price_per_million: Decimal) -> Decimal:
    return (Decimal(tokens) / Decimal("1000000")) * price_per_million


def _validate_token_count(name: str, value: int) -> None:
    if value < 0:
        msg = f"{name} must be greater than or equal to 0"
        raise ValueError(msg)
