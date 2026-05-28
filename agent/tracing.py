"""Sprint 27 — Agent Trace Console: OpenTelemetry instrumentation surface.

This module is the SINGLE import surface for tracing across the codebase:
- init_tracing(): boot once at app startup
- is_enabled(): introspect whether export is on
- @trace_subsystem(name): decorator for subsystem entry points
- @trace_tool(name=None): decorator for tool dispatchers
- @trace_llm: decorator for LLM HTTP calls (manual since we use urllib, not openai SDK)
- span(name, **attrs): context-manager helper for sparse mid-function spans

Invariant: tracing failures NEVER break the app. Every public surface is
wrapped in defensive try/except; failures surface only as WARN logs.
"""

from __future__ import annotations

import logging
import os
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

_INITIALIZED = False
_ENABLED = False


def is_enabled() -> bool:
    """True iff init_tracing() succeeded with TOMORROW_YOU_TRACING_ENABLED=true."""
    return _ENABLED


def init_tracing(*, service_name: str = "tomorrow-you-backend") -> None:
    """Idempotent. Reads TOMORROW_YOU_TRACING_ENABLED. False or any
    exception → falls back to OTel's default NoOp tracer (zero overhead)."""
    global _INITIALIZED, _ENABLED
    if _INITIALIZED:
        return
    _INITIALIZED = True

    flag = os.environ.get("TOMORROW_YOU_TRACING_ENABLED", "false").lower()
    if flag != "true":
        logger.info("tracing disabled (TOMORROW_YOU_TRACING_ENABLED=%s)", flag)
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        endpoint = os.environ.get(
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "http://phoenix:6006/v1/traces",
        )
        resource = Resource.create({
            "service.name": service_name,
            "service.version": os.environ.get("TOMORROW_YOU_APP_VERSION", "dev"),
            "deployment.environment": os.environ.get("TOMORROW_YOU_ENV", "dev"),
        })
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)
        _ENABLED = True
        logger.info("tracing enabled, exporting to %s", endpoint)
    except Exception as exc:
        logger.warning("tracing init failed, falling back to NoOp: %s", exc)
        # _ENABLED stays False; OTel's NoOpTracerProvider is the default


def trace_subsystem(name: str) -> Callable[[F], F]:
    """Wrap a function in a span named '{name}.{func.__name__}' with
    attribute tomorrow_you.subsystem=name. Exceptions are recorded as
    ERROR-status span events, then re-raised."""
    def decorator(func: F) -> F:
        from opentelemetry import trace as _trace
        tracer = _trace.get_tracer(__name__)

        @wraps(func)
        def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(f"{name}.{func.__name__}") as span:
                try:
                    span.set_attribute("tomorrow_you.subsystem", name)
                except Exception:
                    pass
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    try:
                        from opentelemetry.trace import Status, StatusCode
                        span.record_exception(exc)
                        span.set_status(Status(StatusCode.ERROR, str(exc)))
                    except Exception:
                        pass
                    raise

        return wrapper  # type: ignore[return-value]

    return decorator
