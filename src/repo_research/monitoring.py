"""Optional Logfire instrumentation for API and agent execution."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

from repo_research.config import Settings

_logfire_configured = False
_pydantic_ai_instrumented = False


def configure_logfire(settings: Settings) -> None:
    """Configure Logfire once when explicitly enabled."""
    global _logfire_configured
    if not settings.logfire_enabled or _logfire_configured:
        return
    import logfire

    logfire.configure(
        send_to_logfire=settings.logfire_send_to_logfire,
        service_name="repo-deep-research",
        service_version=_service_version(),
        environment=settings.environment,
        inspect_arguments=False,
    )
    _logfire_configured = True


def instrument_fastapi(app: FastAPI, settings: Settings) -> None:
    """Instrument FastAPI without capturing request or response payloads."""
    if not settings.logfire_enabled:
        return
    configure_logfire(settings)
    import logfire

    logfire.instrument_fastapi(
        app,
        capture_headers=False,
        record_send_receive=False,
        extra_spans=False,
    )


def instrument_pydantic_ai(settings: Settings) -> None:
    """Instrument PydanticAI without recording prompts or binary content."""
    global _pydantic_ai_instrumented
    if not settings.logfire_enabled or _pydantic_ai_instrumented:
        return
    configure_logfire(settings)
    import logfire

    logfire.instrument_pydantic_ai(
        include_content=False,
        include_binary_content=False,
    )
    _pydantic_ai_instrumented = True


def _service_version() -> str:
    try:
        return version("repo-deep-research")
    except PackageNotFoundError:
        return "0.0.0"
