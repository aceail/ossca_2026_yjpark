# Agent Trace Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the "내일의 너" agentic loop (LLM call, tool dispatch, memory ops, reflection, briefing) with OpenTelemetry and ship a self-hosted Arize Phoenix container in docker compose, so every chat round produces a structured trace consumable as a future eval-harness dataset row.

**Architecture:** Hybrid OpenTelemetry instrumentation — auto via `opentelemetry-instrumentation-fastapi` for HTTP routes, manual `@trace_subsystem` / `@trace_tool` / `@trace_llm` decorators on pipeline entry points, and one sparse context-manager span inside the ReAct loop body. Spans go over OTLP/HTTP to a Phoenix container on the compose network. UI is bound to `127.0.0.1:6006` only. Tracing toggles via `TOMORROW_YOU_TRACING_ENABLED=true|false`; when off, the OTel SDK uses its built-in `NoOpTracerProvider` and all decorators become near-zero overhead.

**Tech Stack:** Python 3.12 · FastAPI · uvicorn · OpenTelemetry SDK (`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`) · Arize Phoenix (`arizephoenix/phoenix:latest`) · unittest/pytest · docker compose.

**Spec deviation (recorded):** Spec §5 assumed Ollama LLM calls would be picked up by OpenInference auto-instrumentation. In practice `pipeline/chat.py:_call_ollama_chat` (line 415) uses `urllib.request` directly, not the openai Python SDK, so the OpenInference patch never fires. This plan replaces that auto-instrumentation with a manual `@trace_llm` decorator applied to `_call_ollama_chat`. Span attributes (`model`, `prompt_chars`, `response_chars`, `latency_ms`) are still recorded. Spec acceptance criteria (§11) remain unchanged.

---

## File Structure

**New files**

| Path | Responsibility |
|---|---|
| `agent/tracing.py` | Single import surface: `init_tracing()`, `is_enabled()`, decorators `@trace_subsystem`, `@trace_tool`, `@trace_llm`. NoOp fallback. |
| `tests/test_tracing.py` | Unit tests (init, each decorator) + integration test (span tree from chat flow). |
| `.claude/skills/tomorrow-you-tracing/SKILL.md` | Post-implementation convention guide for future contributors. |

**Modified files**

| Path | Change |
|---|---|
| `docker/Dockerfile.backend` | Append OpenTelemetry packages to inline `pip install`. |
| `docker/local.compose.yml` | Add `phoenix` service, `phoenix-data` volume, OTLP env vars on backend. |
| `backend/main.py` | Call `init_tracing()` first thing in lifespan; instrument FastAPI app. |
| `pipeline/memory.py` | `@trace_subsystem("memory")` on `upsert_memory`, `top_memories`, `recall`. |
| `pipeline/tools.py` | `@trace_tool` on `dispatch`. |
| `pipeline/chat.py` | `@trace_subsystem("chat")` on `post_user_message`; `@trace_llm` on `_call_ollama_chat`; `with span("react.round")` around tool-call loop body. |
| `pipeline/reflection.py` | `@trace_subsystem("reflection")` on `run_reflection`, `run_reflection_for_all`. |
| `pipeline/briefing.py` | `@trace_subsystem("briefing")` on `generate_briefing`. |
| `agent/integrations.py` | `@trace_subsystem("agent")` on `save_integration`, `get_integration`, `revoke_integration`. |
| `.env.example` | Document `TOMORROW_YOU_TRACING_ENABLED`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME`. |
| `backend/run.sh` | Export the env vars for local dev. |
| `docs/DEPLOY.md` | Add "Tracing" section (UI access, wipe procedure, toggle). |

---

## Task 1: Tracing module skeleton + dependency install

**Files:**
- Create: `agent/tracing.py`
- Create: `tests/test_tracing.py`
- Modify: `docker/Dockerfile.backend`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tracing.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'opentelemetry'` (or `agent.tracing`).

- [ ] **Step 3: Install OpenTelemetry deps for local dev**

Run:
```bash
pip install 'opentelemetry-api>=1.27' \
            'opentelemetry-sdk>=1.27' \
            'opentelemetry-exporter-otlp-proto-http>=1.27' \
            'opentelemetry-instrumentation-fastapi>=0.48b0'
```

Expected: all 4 packages install cleanly.

- [ ] **Step 4: Update `docker/Dockerfile.backend`**

Edit `docker/Dockerfile.backend`, replace the existing `RUN pip install` block (lines 13-19) with:

```dockerfile
# 우리 backend는 표준 stdlib·fastapi·pydantic·cryptography·pywebpush(옵션)만 필요.
# requirements.txt 없는 환경 — 명시 install.
# Sprint 27: OpenTelemetry stack for Phoenix tracing.
RUN pip install --no-cache-dir \
    'fastapi>=0.110' \
    'uvicorn[standard]>=0.27' \
    'pydantic>=2.6' \
    'cryptography>=42' \
    'pywebpush>=2.0' \
    'opentelemetry-api>=1.27' \
    'opentelemetry-sdk>=1.27' \
    'opentelemetry-exporter-otlp-proto-http>=1.27' \
    'opentelemetry-instrumentation-fastapi>=0.48b0'
```

- [ ] **Step 5: Create `agent/tracing.py`**

```python
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

logger = logging.getLogger(__name__)

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
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py -v`
Expected: 3 passed in `TestTracingInit`.

- [ ] **Step 7: Commit**

```bash
cd /dataset/yjpark/ossca_yjpark
git add agent/tracing.py tests/test_tracing.py docker/Dockerfile.backend
git commit -m "feat(tracing): Sprint 27 — tracing module skeleton + OTel deps

Add agent/tracing.py exposing init_tracing() / is_enabled() with NoOp
fallback when TOMORROW_YOU_TRACING_ENABLED != 'true'. Append OpenTelemetry
packages to docker/Dockerfile.backend. Unit tests cover disabled / enabled
/ idempotent init paths."
```

---

## Task 2: @trace_subsystem decorator

**Files:**
- Modify: `agent/tracing.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tracing.py`:

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry import trace as _otel_trace


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
        from opentelemetry.trace import StatusCode

        @trace_subsystem("memory")
        def bad_func():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            bad_func()

        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].status.status_code, StatusCode.ERROR)
        self.assertTrue(any("exception" in e.name for e in spans[0].events))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestTraceSubsystem -v`
Expected: FAIL with `ImportError: cannot import name 'trace_subsystem'`.

- [ ] **Step 3: Implement `@trace_subsystem`**

Append to `agent/tracing.py`:

```python
from functools import wraps
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable)


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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestTraceSubsystem -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add agent/tracing.py tests/test_tracing.py
git commit -m "feat(tracing): Sprint 27 — @trace_subsystem decorator"
```

---

## Task 3: @trace_tool decorator

**Files:**
- Modify: `agent/tracing.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tracing.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestTraceTool -v`
Expected: FAIL with `ImportError: cannot import name 'trace_tool'`.

- [ ] **Step 3: Implement `@trace_tool`**

Append to `agent/tracing.py`:

```python
def trace_tool(func: F) -> F:
    """Decorator for the Hermes tool dispatcher. Reads `name` kwarg at
    call time to label the span as 'tool.{name}'. Records the result
    dict's 'ok' field as tomorrow_you.tool_ok."""
    from opentelemetry import trace as _trace
    tracer = _trace.get_tracer(__name__)

    @wraps(func)
    def wrapper(*args, **kwargs):
        tool_name = kwargs.get("name") or "unknown"
        with tracer.start_as_current_span(f"tool.{tool_name}") as span:
            try:
                span.set_attribute("tomorrow_you.tool_name", tool_name)
            except Exception:
                pass
            try:
                result = func(*args, **kwargs)
                try:
                    if isinstance(result, dict) and "ok" in result:
                        span.set_attribute(
                            "tomorrow_you.tool_ok", bool(result.get("ok"))
                        )
                        if not result.get("ok"):
                            err = str(result.get("error") or "")[:200]
                            if err:
                                span.set_attribute("tomorrow_you.tool_error", err)
                except Exception:
                    pass
                return result
            except Exception as exc:
                try:
                    from opentelemetry.trace import Status, StatusCode
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                except Exception:
                    pass
                raise

    return wrapper  # type: ignore[return-value]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestTraceTool -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add agent/tracing.py tests/test_tracing.py
git commit -m "feat(tracing): Sprint 27 — @trace_tool decorator with ok/error capture"
```

---

## Task 4: @trace_llm decorator

**Files:**
- Modify: `agent/tracing.py`
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tracing.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestTraceLLM -v`
Expected: FAIL — `ImportError: cannot import name 'trace_llm'`.

- [ ] **Step 3: Implement `@trace_llm`**

Append to `agent/tracing.py`:

```python
import time


def trace_llm(func: F) -> F:
    """Decorator for an Ollama HTTP call. Captures model + latency_ms +
    rough prompt/response sizes. We do this manually because the project
    uses urllib (not the openai SDK), so OpenInference auto-instrumentation
    does not apply."""
    from opentelemetry import trace as _trace
    tracer = _trace.get_tracer(__name__)

    @wraps(func)
    def wrapper(*args, **kwargs):
        model = kwargs.get("model") or "unknown"
        with tracer.start_as_current_span("llm.call") as span:
            try:
                span.set_attribute("llm.model", model)
                msgs = args[0] if args else kwargs.get("messages") or []
                if isinstance(msgs, list):
                    span.set_attribute("llm.prompt_chars",
                                       sum(len(str(m.get("content", "")))
                                           for m in msgs if isinstance(m, dict)))
            except Exception:
                pass
            t0 = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                try:
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    span.set_attribute("llm.latency_ms", int(elapsed_ms))
                    if isinstance(result, dict):
                        content = (result.get("message") or {}).get("content")
                        if isinstance(content, str):
                            span.set_attribute(
                                "llm.response_chars", len(content)
                            )
                except Exception:
                    pass
                return result
            except Exception as exc:
                try:
                    from opentelemetry.trace import Status, StatusCode
                    span.record_exception(exc)
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                except Exception:
                    pass
                raise

    return wrapper  # type: ignore[return-value]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestTraceLLM -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add agent/tracing.py tests/test_tracing.py
git commit -m "feat(tracing): Sprint 27 — @trace_llm decorator for urllib-based Ollama calls"
```

---

## Task 5: Backend lifespan wiring + FastAPI instrumentation

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tracing.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails (or passes trivially before wiring)**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestBackendStartup -v`
Expected: PASS trivially (the assertion is permissive). The real verification is via existing 420-test regression in Task 14.

- [ ] **Step 3: Wire `init_tracing()` into `backend/main.py` lifespan**

Edit `backend/main.py`. Add this import near the top (after the other pipeline imports, around line 24):

```python
from agent.tracing import init_tracing
```

Then inside the `lifespan` function, immediately after `seed_builtin_prompts(conn)` (currently line 83) and before the `conn.close()`, insert:

```python
    # Sprint 27: tracing — boot once before any task spawns.
    try:
        init_tracing()
    except Exception:
        # Defensive: tracing init failures must not block app startup.
        pass

    # FastAPI auto-instrumentation (registers middleware on the existing app).
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass
```

The resulting lifespan opening (lines 79-90 region) should read:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """시작 시 DB migrate + seed_builtin_prompts + folder watch task."""
    conn = open_db(DB_PATH)
    migrate(conn)
    seed_builtin_prompts(conn)
    conn.close()

    # Sprint 27: tracing — boot once before any task spawns.
    try:
        init_tracing()
    except Exception:
        pass
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass

    watch_task = None
    ...
```

- [ ] **Step 4: Run all tracing tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/test_tracing.py
git commit -m "feat(tracing): Sprint 27 — wire init_tracing into FastAPI lifespan"
```

---

## Task 6: Apply decorators in `pipeline/memory.py`

**Files:**
- Modify: `pipeline/memory.py`

- [ ] **Step 1: Add import at top of `pipeline/memory.py`**

Add immediately after the existing `from __future__ import annotations` block:

```python
from agent.tracing import trace_subsystem
```

- [ ] **Step 2: Apply `@trace_subsystem("memory")` to `upsert_memory`, `top_memories`, `recall`**

Above each `def` line, add the decorator. The functions exist at lines 16, 48, 60 (approx). Result:

```python
@trace_subsystem("memory")
def upsert_memory(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    ...
```

```python
@trace_subsystem("memory")
def top_memories(
    conn: sqlite3.Connection, user_id: str, *, limit: int = 5,
) -> list[dict]:
    ...
```

```python
@trace_subsystem("memory")
def recall(
    ...
```

- [ ] **Step 3: Run the existing memory tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_user_memory.py tests/test_memory_fts.py -v`
Expected: 0 regressions (all existing memory tests pass).

- [ ] **Step 4: Commit**

```bash
git add pipeline/memory.py
git commit -m "feat(tracing): Sprint 27 — instrument memory subsystem"
```

---

## Task 7: Apply decorator on `pipeline/tools.py:dispatch`

**Files:**
- Modify: `pipeline/tools.py`

- [ ] **Step 1: Add import at top of `pipeline/tools.py`**

After the `from typing import ...` import block (around line 17):

```python
from agent.tracing import trace_tool
```

- [ ] **Step 2: Decorate `dispatch` at line 391**

Above the `def dispatch(` line:

```python
@trace_tool
def dispatch(
    ...
```

- [ ] **Step 3: Run existing tool / agent tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_agent_tools.py tests/test_agent_react_loop.py -v`
Expected: 0 regressions.

- [ ] **Step 4: Commit**

```bash
git add pipeline/tools.py
git commit -m "feat(tracing): Sprint 27 — instrument tool dispatch"
```

---

## Task 8: Apply decorators in `pipeline/chat.py` + ReAct round span

**Files:**
- Modify: `pipeline/chat.py`

- [ ] **Step 1: Add imports at top of `pipeline/chat.py`**

After the existing imports (around line 22):

```python
from agent.tracing import trace_subsystem, trace_llm
```

- [ ] **Step 2: Decorate `_call_ollama_chat` (line 415) with `@trace_llm`**

```python
@trace_llm
def _call_ollama_chat(
    ...
```

- [ ] **Step 3: Decorate `post_user_message` (line 518) with `@trace_subsystem("chat")`**

```python
@trace_subsystem("chat")
def post_user_message(
    ...
```

- [ ] **Step 4: Locate the ReAct tool-call loop body inside `post_user_message`**

Run: `grep -n "tool_calls\|tool_rounds\|AGENT_MAX_TOOL_ROUNDS" /dataset/yjpark/ossca_yjpark/pipeline/chat.py`

Expected: lines pointing to the ReAct loop body (likely uses a `for` or `while` over `AGENT_MAX_TOOL_ROUNDS`). Note the line numbers.

- [ ] **Step 5: Wrap each ReAct iteration in a `with span("react.round")`**

At the top of `pipeline/chat.py`, add a helper near the other imports:

```python
from contextlib import contextmanager

@contextmanager
def _react_round_span(round_index: int):
    """Sparse span around one ReAct iteration. Imported lazily so this
    file stays usable without tracing installed."""
    try:
        from opentelemetry import trace as _trace
        tracer = _trace.get_tracer(__name__)
        with tracer.start_as_current_span("react.round") as span:
            try:
                span.set_attribute("react.round_index", round_index)
            except Exception:
                pass
            yield span
    except Exception:
        yield None
```

Then in the ReAct loop body inside `post_user_message`, wrap one iteration. If the loop reads:

```python
for round_idx in range(AGENT_MAX_TOOL_ROUNDS):
    # ... build messages ...
    response = _call_ollama_chat(...)
    # ... process tool_calls ...
```

Change to:

```python
for round_idx in range(AGENT_MAX_TOOL_ROUNDS):
    with _react_round_span(round_idx):
        # ... build messages ...
        response = _call_ollama_chat(...)
        # ... process tool_calls ...
```

(If the actual loop variable name differs, use whatever exists; the round index attribute should be a numeric counter.)

- [ ] **Step 6: Run existing chat tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_chat_actions.py tests/test_chat_actions_v2.py tests/test_agent_react_loop.py tests/test_temporal_hints.py -v`
Expected: 0 regressions.

- [ ] **Step 7: Commit**

```bash
git add pipeline/chat.py
git commit -m "feat(tracing): Sprint 27 — instrument chat (entry + LLM + ReAct rounds)"
```

---

## Task 9: Apply decorators in `pipeline/reflection.py`

**Files:**
- Modify: `pipeline/reflection.py`

- [ ] **Step 1: Add import after existing imports (around line 20)**

```python
from agent.tracing import trace_subsystem
```

- [ ] **Step 2: Decorate `run_reflection` (line 137) and `run_reflection_for_all` (line 194)**

```python
@trace_subsystem("reflection")
def run_reflection(
    ...
```

```python
@trace_subsystem("reflection")
def run_reflection_for_all(
    ...
```

- [ ] **Step 3: Run existing reflection tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_reflection.py -v`
Expected: 0 regressions.

- [ ] **Step 4: Commit**

```bash
git add pipeline/reflection.py
git commit -m "feat(tracing): Sprint 27 — instrument reflection subsystem"
```

---

## Task 10: Apply decorator in `pipeline/briefing.py`

**Files:**
- Modify: `pipeline/briefing.py`

- [ ] **Step 1: Add import after existing imports (around line 17)**

```python
from agent.tracing import trace_subsystem
```

- [ ] **Step 2: Decorate `generate_briefing` (line 132)**

```python
@trace_subsystem("briefing")
def generate_briefing(
    ...
```

- [ ] **Step 3: Run existing briefing tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_briefing.py -v`
Expected: 0 regressions.

- [ ] **Step 4: Commit**

```bash
git add pipeline/briefing.py
git commit -m "feat(tracing): Sprint 27 — instrument briefing subsystem"
```

---

## Task 11: Apply decorators in `agent/integrations.py` and `agent/router.py`

**Files:**
- Modify: `agent/integrations.py`
- Modify: `agent/router.py`

`agent/router.py` exposes the `ToolRouter` class whose only public method is
`route()` (line 75). We decorate the method directly — `functools.wraps`
preserves `self`-binding correctly.

- [ ] **Step 1: Add import + decorate `agent/integrations.py`**

Add this import near the top of `agent/integrations.py` (after existing imports):

```python
from agent.tracing import trace_subsystem
```

Then add `@trace_subsystem("agent")` above each of these three function definitions:

- `save_integration` at line 115
- `get_integration` at line 152
- `revoke_integration` at line 183

Example for one:

```python
@trace_subsystem("agent")
def save_integration(
    ...
```

(Apply the identical decorator pattern to the other two.)

- [ ] **Step 2: Add import + decorate `agent/router.py`**

Add this import near the top of `agent/router.py` (after the existing
`from .consent import has_consent` line, around line 22):

```python
from agent.tracing import trace_subsystem
```

Then decorate the `route` method inside `class ToolRouter` (line 75). The
decorator goes between the method header and the surrounding class indent:

```python
class ToolRouter:
    """입력 컨텍스트를 분석하여 호출할 tool 목록 반환."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @trace_subsystem("agent")
    def route(
        self,
        input_context: str,
        ...
```

- [ ] **Step 3: Run existing consent/integration/router tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_agent_consent.py tests/test_fernet_key_derivation.py -v`
Expected: 0 regressions.

If a router-specific test file exists in the suite, run it as well; if not, the
integration test in Task 12 indirectly exercises router behavior through the
chat flow.

- [ ] **Step 4: Commit**

```bash
git add agent/integrations.py agent/router.py
git commit -m "feat(tracing): Sprint 27 — instrument agent integrations + tool router"
```

---

## Task 12: Integration test — full span tree from a chat flow

**Files:**
- Modify: `tests/test_tracing.py`

- [ ] **Step 1: Write the failing integration test**

Append to `tests/test_tracing.py`:

```python
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
        # Minimal user + session setup — adjust to project's bootstrap
        # if it exposes one. Otherwise insert directly:
        self.user_id = "test-user"
        self.conn.execute(
            "INSERT INTO User (id, created_at, updated_at) VALUES (?, ?, ?)",
            (self.user_id, "2026-05-28T00:00:00Z", "2026-05-28T00:00:00Z"),
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
        session = create_chat_session(
            self.conn, user_id=self.user_id, persona_id=None,
        )
        with patch.object(
            chat_mod, "_call_ollama_chat", return_value=fake_response,
        ):
            post_user_message(
                self.conn,
                session_id=session["id"],
                user_id=self.user_id,
                content="hi",
            )

        span_names = {s.name for s in self.exporter.get_finished_spans()}
        # Expected: chat entry + at least one llm.call + at least one react.round
        self.assertIn("chat.post_user_message", span_names)
        self.assertIn("llm.call", span_names)
        # react.round is sparse, present only if the chat actually entered the
        # tool loop. The flow under test enters the loop at least once.
        self.assertIn("react.round", span_names)
```

- [ ] **Step 2: Run the integration test**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tracing.py::TestSpanTreeIntegration -v`
Expected: PASS if the prior tasks 5-8 were applied correctly. If FAIL, the error message identifies which span is missing — fix the corresponding decorator placement.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tracing.py
git commit -m "test(tracing): Sprint 27 — integration test for chat span tree"
```

---

## Task 13: Add Phoenix service to docker compose

**Files:**
- Modify: `docker/local.compose.yml`
- Modify: `.env.example`
- Modify: `backend/run.sh`

- [ ] **Step 1: Replace `docker/local.compose.yml`**

Full updated file:

```yaml
# Local 모드 운영용 docker-compose.
# 같은 머신에 Ollama·SQLite·우리 backend·frontend + Sprint 27 Phoenix 한 번에 띄움.

version: "3.9"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: naeil-ollama
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]
      interval: 30s
      timeout: 5s
      retries: 5

  phoenix:
    # Sprint 27: Agent Trace Console. Self-hosted Arize Phoenix.
    image: arizephoenix/phoenix:latest
    container_name: naeil-phoenix
    restart: unless-stopped
    ports:
      # Loopback bind only — UI is for the developer on this host.
      - "127.0.0.1:6006:6006"
    volumes:
      - phoenix_data:/data
    environment:
      PHOENIX_WORKING_DIR: /data

  backend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    container_name: naeil-backend
    restart: unless-stopped
    depends_on:
      ollama:
        condition: service_healthy
      phoenix:
        condition: service_started
    environment:
      TOMORROW_YOU_DB: /data/tomorrow_you.db
      NAEIL_AGENT_MODEL: ${NAEIL_AGENT_MODEL:-qwen3:8b}
      NAEIL_AGENT_TOOLS: "1"
      NAEIL_WATCH_INTERVAL_MIN: ${NAEIL_WATCH_INTERVAL_MIN:-30}
      NAEIL_FOLLOWUP_INTERVAL_MIN: ${NAEIL_FOLLOWUP_INTERVAL_MIN:-60}
      NAEIL_REFLECTION_INTERVAL_HOURS: ${NAEIL_REFLECTION_INTERVAL_HOURS:-12}
      NAEIL_VAPID_PUBLIC_KEY: ${NAEIL_VAPID_PUBLIC_KEY:-}
      NAEIL_VAPID_PRIVATE_KEY: ${NAEIL_VAPID_PRIVATE_KEY:-}
      NAEIL_VAPID_SUBJECT: ${NAEIL_VAPID_SUBJECT:-mailto:admin@example.com}
      TOMORROW_YOU_FERNET_PASSPHRASE: ${TOMORROW_YOU_FERNET_PASSPHRASE:-}
      OLLAMA_HOST: http://ollama:11434
      # Sprint 27: tracing
      TOMORROW_YOU_TRACING_ENABLED: ${TOMORROW_YOU_TRACING_ENABLED:-true}
      OTEL_EXPORTER_OTLP_ENDPOINT: http://phoenix:6006/v1/traces
      OTEL_SERVICE_NAME: tomorrow-you-backend
      TOMORROW_YOU_ENV: ${TOMORROW_YOU_ENV:-dev}
    volumes:
      - naeil_data:/data
    ports:
      - "8001:8001"

  frontend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.frontend
      args:
        NEXT_PUBLIC_API_BASE: ${PUBLIC_API_BASE:-http://localhost:8001}
        NEXT_PUBLIC_VAPID_PUBLIC_KEY: ${NAEIL_VAPID_PUBLIC_KEY:-}
    container_name: naeil-frontend
    restart: unless-stopped
    depends_on:
      - backend
    ports:
      - "3000:3000"

volumes:
  ollama_data:
  naeil_data:
  phoenix_data:
```

- [ ] **Step 2: Update `.env.example`**

Append to `.env.example`:

```bash

# ─── Sprint 27: Tracing (Arize Phoenix) ──────────────────────────
# true to ship spans to Phoenix; false to disable (NoOp, zero overhead).
TOMORROW_YOU_TRACING_ENABLED=true
# dev | prod — recorded on every span for filtering in the Phoenix UI.
TOMORROW_YOU_ENV=dev
```

- [ ] **Step 3: Update `backend/run.sh` (local non-docker dev path)**

Read the current contents of `backend/run.sh`. Add the following two exports near the top, after the shebang and any existing exports:

```bash
export TOMORROW_YOU_TRACING_ENABLED="${TOMORROW_YOU_TRACING_ENABLED:-true}"
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:6006/v1/traces}"
export OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-tomorrow-you-backend}"
export TOMORROW_YOU_ENV="${TOMORROW_YOU_ENV:-dev}"
```

- [ ] **Step 4: Validate compose file**

Run: `cd /dataset/yjpark/ossca_yjpark && docker compose -f docker/local.compose.yml config > /dev/null && echo OK`
Expected: `OK` (no YAML parse errors).

- [ ] **Step 5: Commit**

```bash
git add docker/local.compose.yml .env.example backend/run.sh
git commit -m "feat(tracing): Sprint 27 — phoenix service in local.compose + env vars

127.0.0.1:6006:6006 binding to keep UI local-only. Backend wired to ship
OTLP to phoenix:6006/v1/traces. TOMORROW_YOU_TRACING_ENABLED default true
in compose; disabled by default in code path so tests stay quiet."
```

---

## Task 14: Regression + manual smoke test

**Files:**
- (no code changes)

- [ ] **Step 1: Run the full test suite**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/ -q`
Expected: all prior tests pass + new tracing tests pass. Zero regressions.

If failures appear, treat each as a real issue — investigate before continuing.

- [ ] **Step 2: Boot the full stack**

Run: `cd /dataset/yjpark/ossca_yjpark && docker compose -f docker/local.compose.yml --env-file .env up -d`
Expected: 4 containers running — `naeil-ollama`, `naeil-phoenix`, `naeil-backend`, `naeil-frontend`.

Verify with: `docker compose -f docker/local.compose.yml ps`

- [ ] **Step 3: Open Phoenix UI**

Open in browser: `http://localhost:6006`
Expected: Phoenix UI loads. Service `tomorrow-you-backend` may not appear yet (no traces sent).

- [ ] **Step 4: Send a chat message**

Open `http://localhost:3000`, navigate to chat, send a message like "발표자료 6월 1일까지 만들어야 해".

- [ ] **Step 5: Verify trace in Phoenix UI**

Refresh the Phoenix UI. Under traces, find a trace from service `tomorrow-you-backend`. Drill in.

Expected span tree includes (subset is acceptable, but at minimum):

- `chat.post_user_message` (root or child of HTTP span)
  - `memory.recall` (if recall is called in the pipeline path)
  - `react.round` (round_index attribute present)
    - `llm.call` (model attribute = `qwen3:8b` or whatever `NAEIL_AGENT_MODEL` is set to)
    - `tool.create_task` (with `tomorrow_you.tool_ok=true`)

If any expected span is missing, identify whether the corresponding decorator was applied in Tasks 6-11 and re-check.

- [ ] **Step 6: Verify the disable toggle**

Stop backend: `docker compose -f docker/local.compose.yml stop backend`
Edit `.env`: `TOMORROW_YOU_TRACING_ENABLED=false`
Restart: `docker compose -f docker/local.compose.yml up -d backend`
Send another chat message via the UI.
Refresh Phoenix: no new trace should appear for that message.
Revert `.env` to `true` and restart.

- [ ] **Step 7: Commit (no code changes — record a smoke-test note in a brief commit only if anything was tweaked)**

If any minor adjustments were made during smoke testing, commit them with:

```bash
git add -p   # selectively stage only the necessary files
git commit -m "fix(tracing): Sprint 27 — smoke-test adjustments"
```

Otherwise, skip the commit and move to Task 15.

---

## Task 15: Write `.claude/skills/tomorrow-you-tracing/SKILL.md`

**Files:**
- Create: `.claude/skills/tomorrow-you-tracing/SKILL.md`

- [ ] **Step 1: Create the directory**

Run: `mkdir -p /dataset/yjpark/ossca_yjpark/.claude/skills/tomorrow-you-tracing`

- [ ] **Step 2: Write the SKILL.md**

Create `.claude/skills/tomorrow-you-tracing/SKILL.md`:

```markdown
---
name: tomorrow-you-tracing
description: How to add or modify OpenTelemetry spans in the "내일의 너" codebase. Use whenever you instrument a new subsystem, debug a missing span, or extend the trace schema for the upcoming eval harness sub-project.
---

# 내일의 너 — Tracing Conventions (Sprint 27)

This codebase uses **hybrid OpenTelemetry instrumentation** exported via OTLP/HTTP
to a self-hosted Arize Phoenix container. Spans are toggled by
`TOMORROW_YOU_TRACING_ENABLED`. Single import surface is `agent/tracing.py`.

## When to use which pattern

| Target | Pattern | Decorator/Helper |
|---|---|---|
| Subsystem entry function (chat, memory, reflection, briefing, agent) | Decorator | `@trace_subsystem("subsystem_name")` |
| Hermes tool dispatcher | Decorator | `@trace_tool` (reads `name` kwarg at call time) |
| Ollama HTTP call | Decorator | `@trace_llm` (captures model + latency_ms + char counts) |
| Mid-function "interesting moment" (e.g. each ReAct round) | Context manager | Inline `with tracer.start_as_current_span(...)` |
| FastAPI HTTP routes | Auto | Done once in `backend/main.py` lifespan |

## Rules

1. **Never** swallow tracing-layer exceptions silently *outside* `agent/tracing.py`.
   The decorators already do this internally — don't add more `try/except` around
   them at call sites.
2. Span names are dot-delimited: `subsystem.func_name`, `tool.tool_name`, `llm.call`.
3. Every domain exception in an instrumented function is recorded with
   `status=ERROR` and re-raised. Don't catch and rewrap to suppress.
4. Sensitive content (chat messages, memory contents) is captured in full because
   this is a single-user local-only deployment. If multi-user happens, add a
   `TOMORROW_YOU_TRACE_REDACT_PII` toggle — don't hand-strip at call sites.

## Adding a new subsystem

1. Add `from agent.tracing import trace_subsystem` to the module.
2. Decorate the public entry function(s) with `@trace_subsystem("<name>")`.
3. If there's a noteworthy mid-function decision, wrap it in a sparse
   `with tracer.start_as_current_span("<subsystem>.<phase>") as span:` block and
   record useful attributes via `span.set_attribute(...)`.
4. Run the relevant subsystem's existing pytest suite — no regressions.
5. Run the integration test (`tests/test_tracing.py::TestSpanTreeIntegration`) if
   the new subsystem is reachable from a chat round.

## Phoenix UI

- URL: `http://localhost:6006` (host-only, loopback bind)
- Wipe traces: `docker compose -f docker/local.compose.yml down phoenix &&` 
  `docker volume rm <project>_phoenix_data && docker compose up -d phoenix`
- Disable tracing temporarily: set `TOMORROW_YOU_TRACING_ENABLED=false` and
  restart the backend.

## Future hook for sub-project ② Eval Harness

The trace schema is shaped so that one trace ≈ one eval-harness example. The
extractor (to be designed in sub-project ②) will:

1. Pull a trace from Phoenix via its REST API or local SQLite.
2. Walk the span tree to collect `chat.post_user_message` (input) → `llm.call` 
   (model invocation) → `tool.*` results → final response stored in DB.
3. Emit a JSONL row containing those four parts.

Do not change span names or attribute keys without updating that extractor and
the schema doc in this file.
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/tomorrow-you-tracing/
git commit -m "docs(skill): Sprint 27 — tracing conventions SKILL.md"
```

---

## Task 16: Update `docs/DEPLOY.md`

**Files:**
- Modify: `docs/DEPLOY.md`

- [ ] **Step 1: Read current DEPLOY.md**

Run: `cat /dataset/yjpark/ossca_yjpark/docs/DEPLOY.md | tail -20`

This shows the current trailing content so you can append cleanly.

- [ ] **Step 2: Append a new "Tracing" section**

At the end of `docs/DEPLOY.md`, append:

```markdown

## Tracing (Sprint 27)

The compose stack now includes a self-hosted Arize Phoenix container for
observability of the agent loop.

### Accessing the UI

After `docker compose -f docker/local.compose.yml up -d`:

- Phoenix UI: <http://localhost:6006> (bound to loopback only)
- Service identifier: `tomorrow-you-backend`

### Toggling tracing on/off

Set in `.env`:

```bash
TOMORROW_YOU_TRACING_ENABLED=true   # or false
```

Then restart backend: `docker compose -f docker/local.compose.yml up -d backend`.
Disabled mode incurs near-zero overhead (NoOpTracerProvider).

### Wiping trace history

```bash
docker compose -f docker/local.compose.yml down phoenix
docker volume rm $(docker volume ls -q | grep phoenix_data)
docker compose -f docker/local.compose.yml up -d phoenix
```

### What gets traced

Every chat round, tool dispatch, memory operation (recall/upsert/top_memories),
reflection cycle, daily briefing, and Ollama LLM call produces a span. See
`.claude/skills/tomorrow-you-tracing/SKILL.md` for the schema and conventions.

### Privacy note

Spans contain full user message text, model responses, and memory contents.
The Phoenix container holds this data on a local volume (`phoenix_data`) and
the UI is bound to `127.0.0.1` only — nothing leaves this host. If you share
this machine or deploy beyond local, add a redaction layer before relaxing
the bind.
```

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOY.md
git commit -m "docs(deploy): Sprint 27 — tracing section with toggle/wipe/privacy notes"
```

---

## Final verification checklist

After all 16 tasks complete, verify the spec §11 acceptance criteria one by one:

- [ ] **AC1:** `docker compose -f docker/local.compose.yml up -d` brings up Phoenix; `http://localhost:6006` shows the UI.
- [ ] **AC2:** A single chat round produces (minimum) `chat.post_user_message` + `react.round` + `llm.call` spans.
- [ ] **AC3:** A reflection cycle produces `reflection.run_reflection_for_all` + `reflection.run_reflection` + `llm.call` spans. A daily briefing produces `briefing.generate_briefing` + (optionally) `llm.call`.
- [ ] **AC4:** Setting `TOMORROW_YOU_TRACING_ENABLED=false` and restarting backend stops trace export, all existing tests pass.
- [ ] **AC5:** `tests/test_tracing.py` covers init / each decorator / span-tree integration. Prior tests all pass.
- [ ] **AC6:** `.claude/skills/tomorrow-you-tracing/SKILL.md` exists and describes where to add new spans.
- [ ] **AC7:** `docs/DEPLOY.md` has a Tracing section.

If all 7 are green, Sprint 27 is shipped.
