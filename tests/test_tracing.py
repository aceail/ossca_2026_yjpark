"""Sprint 27 — Agent Trace Console: tracing module unit tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

from opentelemetry import trace as _otel_trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import Status, StatusCode

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _reset_otel_globals():
    """OTel TracerProvider는 process-global이라 각 테스트마다 reset 필요."""
    from opentelemetry import trace
    trace._TRACER_PROVIDER = None
    trace._TRACER_PROVIDER_SET_ONCE = trace.Once()  # type: ignore[attr-defined]
    import agent.tracing as _t
    _t._INITIALIZED = False
    _t._ENABLED = False


class TestTracingInit(unittest.TestCase):
    def setUp(self):
        _reset_otel_globals()

    def test_noop_when_disabled(self):
        from agent.tracing import init_tracing, is_enabled

        os.environ["TOMORROW_YOU_TRACING_ENABLED"] = "false"
        init_tracing()
        self.assertFalse(is_enabled())

    def test_enabled_creates_tracer_provider(self):
        from agent.tracing import init_tracing, is_enabled

        os.environ["TOMORROW_YOU_TRACING_ENABLED"] = "true"
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:6006/v1/traces"
        init_tracing()
        self.assertTrue(is_enabled())

    def test_idempotent(self):
        from agent.tracing import init_tracing, is_enabled

        os.environ["TOMORROW_YOU_TRACING_ENABLED"] = "true"
        init_tracing()
        init_tracing()  # 두 번 호출해도 예외 없음
        self.assertTrue(is_enabled())


def _install_in_memory_exporter() -> InMemorySpanExporter:
    """Replace the global TracerProvider with one that exports to memory.
    Returns the exporter for assertions."""
    _reset_otel_globals()
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    _otel_trace.set_tracer_provider(provider)
    import agent.tracing as _t
    _t._INITIALIZED = True
    _t._ENABLED = True
    return exporter


class TestTraceSubsystem(unittest.TestCase):
    def setUp(self):
        self.exporter = _install_in_memory_exporter()

    def test_creates_span_with_attributes(self):
        from agent.tracing import trace_subsystem

        @trace_subsystem("memory")
        def my_func(user_id: str, x: int) -> int:
            return x * 2

        self.assertEqual(my_func("u1", 21), 42)

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "memory.my_func")
        self.assertEqual(
            spans[0].attributes.get("tomorrow_you.subsystem"), "memory",
        )

    def test_records_exception_and_reraises(self):
        from agent.tracing import trace_subsystem

        @trace_subsystem("memory")
        def bad_func():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            bad_func()

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertTrue(any("exception" in e.name for e in spans[0].events))


if __name__ == "__main__":
    unittest.main()
