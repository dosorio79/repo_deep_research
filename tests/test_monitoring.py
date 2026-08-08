"""Tests for optional Logfire instrumentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

import repo_research.monitoring as monitoring
from repo_research.config import Settings


def make_settings(**kwargs: Any) -> Settings:
    """Build settings with pydantic-settings private test overrides."""
    return Settings(**kwargs)


def test_logfire_instrumentation_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(monitoring, "_logfire_configured", False)
    monkeypatch.setattr(monitoring, "_pydantic_ai_instrumented", False)
    monkeypatch.setattr(
        "logfire.configure", lambda **_kwargs: calls.append("configure")
    )
    monkeypatch.setattr(
        "logfire.instrument_fastapi",
        lambda *_args, **_kwargs: calls.append("fastapi"),
    )
    monkeypatch.setattr(
        "logfire.instrument_pydantic_ai",
        lambda *_args, **_kwargs: calls.append("pydantic_ai"),
    )

    settings = make_settings(_env_file=None, repository_root=Path("."))

    monitoring.instrument_fastapi(FastAPI(), settings)
    monitoring.instrument_pydantic_ai(settings)

    assert calls == []


def test_logfire_instruments_fastapi_without_payload_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_kwargs: list[dict[str, Any]] = []
    fastapi_kwargs: list[dict[str, Any]] = []
    monkeypatch.setattr(monitoring, "_logfire_configured", False)
    monkeypatch.setattr(monitoring, "_pydantic_ai_instrumented", False)
    monkeypatch.setattr(
        "logfire.configure",
        lambda **kwargs: configure_kwargs.append(kwargs),
    )
    monkeypatch.setattr(
        "logfire.instrument_fastapi",
        lambda _app, **kwargs: fastapi_kwargs.append(kwargs),
    )

    settings = make_settings(
        _env_file=None,
        repository_root=Path("."),
        logfire_enabled=True,
        logfire_send_to_logfire=False,
    )

    monitoring.instrument_fastapi(FastAPI(), settings)

    assert configure_kwargs[0]["send_to_logfire"] is False
    assert configure_kwargs[0]["inspect_arguments"] is False
    assert fastapi_kwargs == [
        {
            "capture_headers": False,
            "record_send_receive": False,
            "extra_spans": False,
        }
    ]


def test_logfire_instruments_pydantic_ai_without_content_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_calls = 0
    pydantic_kwargs: list[dict[str, Any]] = []
    monkeypatch.setattr(monitoring, "_logfire_configured", False)
    monkeypatch.setattr(monitoring, "_pydantic_ai_instrumented", False)

    def configure(**_kwargs: Any) -> None:
        nonlocal configure_calls
        configure_calls += 1

    monkeypatch.setattr("logfire.configure", configure)
    monkeypatch.setattr(
        "logfire.instrument_pydantic_ai",
        lambda **kwargs: pydantic_kwargs.append(kwargs),
    )
    settings = make_settings(
        _env_file=None,
        repository_root=Path("."),
        logfire_enabled=True,
    )

    monitoring.instrument_pydantic_ai(settings)
    monitoring.instrument_pydantic_ai(settings)

    assert configure_calls == 1
    assert pydantic_kwargs == [
        {
            "include_content": False,
            "include_binary_content": False,
        }
    ]
