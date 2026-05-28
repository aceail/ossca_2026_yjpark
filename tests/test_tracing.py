"""Sprint 27 — Agent Trace Console: tracing module unit tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
