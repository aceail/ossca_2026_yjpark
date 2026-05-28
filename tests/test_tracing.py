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


class TestTraceTool(unittest.TestCase):
    def setUp(self):
        self.exporter = _install_in_memory_exporter()

    def test_captures_tool_name_from_call(self):
        """@trace_tool reads `name` from kwargs at call time (since the
        Hermes tool registry dispatches by name argument)."""
        from agent.tracing import trace_tool

        @trace_tool
        def dispatch(conn, user_id, name, args):
            return {"ok": True, "called": name}

        result = dispatch(None, "u1", name="create_task", args={"title": "x"})
        self.assertEqual(result["called"], "create_task")

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "tool.create_task")
        self.assertEqual(
            spans[0].attributes.get("tomorrow_you.tool_name"), "create_task",
        )

    def test_records_tool_error_result(self):
        """A tool that returns {ok: False, error: ...} is recorded as
        non-exception ERROR (the tool didn't raise but reported failure)."""
        from agent.tracing import trace_tool

        @trace_tool
        def dispatch(conn, user_id, name, args):
            return {"ok": False, "error": "task not found"}

        dispatch(None, "u1", name="update_task", args={})

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(
            spans[0].attributes.get("tomorrow_you.tool_ok"), False,
        )


class TestTraceLLM(unittest.TestCase):
    def setUp(self):
        self.exporter = _install_in_memory_exporter()

    def test_records_model_and_latency(self):
        from agent.tracing import trace_llm

        @trace_llm
        def fake_ollama_call(messages, model, **kw):
            return {"message": {"content": "hello world"}}

        result = fake_ollama_call(
            [{"role": "user", "content": "hi"}], model="qwen3:8b",
        )
        self.assertEqual(result["message"]["content"], "hello world")

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].name, "llm.call")
        attrs = dict(spans[0].attributes)
        self.assertEqual(attrs.get("llm.model"), "qwen3:8b")
        # latency_ms is a number ≥ 0
        self.assertGreaterEqual(attrs.get("llm.latency_ms", -1), 0)


if __name__ == "__main__":
    unittest.main()
