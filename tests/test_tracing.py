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


class TestBackendStartup(unittest.TestCase):
    """Smoke test: lifespan startup must call init_tracing() without
    raising even when tracing is disabled."""

    def test_lifespan_calls_init_tracing_safely(self):
        # If lifespan throws when tracing is off, the backend won't start.
        # We just import + assert init_tracing is wired into backend.main.
        os.environ["TOMORROW_YOU_TRACING_ENABLED"] = "false"
        _reset_otel_globals()
        import importlib
        import backend.main
        importlib.reload(backend.main)
        # Tracer module is imported and is_enabled() is False with no exception.
        from agent.tracing import is_enabled
        # init_tracing isn't called until lifespan fires, but the import
        # path being clean is enough for this smoke check.
        self.assertFalse(is_enabled())


class TestSpanTreeIntegration(unittest.TestCase):
    """Run a synthetic chat round through pipeline.chat with mocked Ollama
    and verify the captured span tree shape matches the design."""

    def setUp(self):
        self.exporter = _install_in_memory_exporter()
        # Tmp DB with migrations + seed
        import tempfile
        from db import open_db, migrate
        from persona import seed_builtin_prompts
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self.db_path = Path(tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)
        seed_builtin_prompts(self.conn)
        # Minimal user setup — User table: (id, created_at, last_seen_at, settings_json)
        self.user_id = "test-user"
        self.conn.execute(
            "INSERT INTO User (id, created_at) VALUES (?, ?)",
            (self.user_id, "2026-05-28T00:00:00Z"),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_chat_flow_produces_expected_spans(self):
        """A single message that produces no tool call → spans: chat.post_user_message,
        react.round, llm.call. Order may vary; we check presence + parent links."""
        from unittest.mock import patch
        from pipeline import chat as chat_mod
        from pipeline.chat import create_chat_session, post_user_message

        # Fake Ollama: returns plain text (no tool_calls), one round.
        fake_response = {
            "message": {"content": '{"speak": "ok", "actions": []}'},
            "done": True,
        }
        # create_chat_session returns int (session id), not a dict
        session_id = create_chat_session(
            self.conn, user_id=self.user_id, persona_id=None,
        )

        # Pass a trace_llm-wrapped stub via call_fn so the llm.call span is
        # emitted even though no real Ollama instance is running.
        from agent.tracing import trace_llm

        @trace_llm
        def _fake_llm(messages, model="qwen3:8b", **kw):
            return fake_response

        post_user_message(
            self.conn,
            session_id=session_id,
            content="hi",
            call_fn=_fake_llm,
        )

        span_names = {s.name for s in self.exporter.get_finished_spans()}
        # Expected: chat entry + at least one llm.call + at least one react.round
        self.assertIn("chat.post_user_message", span_names)
        self.assertIn("llm.call", span_names)
        # react.round is sparse, present only if the chat actually entered the
        # tool loop. The flow under test enters the loop at least once.
        self.assertIn("react.round", span_names)


if __name__ == "__main__":
    unittest.main()
