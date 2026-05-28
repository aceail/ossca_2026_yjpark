# Agent Trace Console — Design

- **Date:** 2026-05-28
- **Owner:** yjpark
- **Status:** Draft → awaiting user review
- **Sprint slot:** Sprint 27 (first of a 5-sub-project roadmap)
- **Roadmap position:** ① of ① Tracing → ② Eval Harness → ③ RAG Memory → ④ Adaptive Reflection → ⑤ Smart Briefing 2.0

## 1. Summary

Instrument the "내일의 너" agentic loop end-to-end with OpenTelemetry and ship a self-hosted Arize Phoenix container in `docker/local.compose.yml` so that every chat round, tool call, memory operation, reflection cycle, and daily briefing is captured as a structured trace. The console serves two roles: (a) forensic debugging — "왜 이 답변이 나왔지" — and (b) raw material for the next sub-project, an LLM evaluation harness that will consume these traces as a dataset.

## 2. Motivation & Context

After 26 sprints the assistant now has: a Hermes-style ReAct loop (`pipeline/chat.py`), a tool registry (`pipeline/tools.py`), user memory with recall/remember/forget (`pipeline/memory.py`), a weekly reflection loop (`pipeline/reflection.py`), and a daily briefing (`pipeline/briefing.py`). Existing observability is limited to ad-hoc `print` and module-level logging — there is no way to reconstruct *why* a given response was produced, which tool was called with which arguments, or which memory entry was injected into the system prompt.

Recent bugs (Sprint 24 empty-reply rescue, Sprint 25 qwen3 date hallucination) were diagnosed only because the user happened to notice the symptom and ask. Without structured traces, the next ambiguous behavior will be diagnosed the same slow way. And the upcoming Eval Harness sub-project needs structured inputs to score the model against — those inputs are exactly what a trace captures.

## 3. Goals & Non-Goals

**Goals**

- Every Ollama LLM call, tool invocation, memory operation, reflection run, and briefing generation produces a span in Phoenix.
- Phoenix runs as a docker compose service alongside backend/frontend, with traces persisted in a named volume across restarts.
- Tracing can be turned off via a single env var with zero runtime overhead when disabled.
- Trace data never leaves the host machine. Phoenix UI bound to `127.0.0.1` only.
- The trace schema is shaped such that exporting a span tree to a dataset row for the future Eval Harness is straightforward (one trace ≈ one eval example).

**Non-goals**

- No custom UI in the Next.js frontend. Developers use the Phoenix UI at `localhost:6006`.
- No sampling logic in v1 — always-on full capture, single user, low volume.
- No PII redaction toggle in v1. Single-user, local-only deployment, so the user's data tracing itself is acceptable. A toggle can be added later.
- No alerting/monitoring dashboards. This is forensic + dataset infrastructure, not live ops.
- No multi-tenant separation. Single-user app.
- No Phoenix UI authentication. Mitigation is binding to loopback only.

## 4. Architecture

```
┌─────────────────── docker compose network ───────────────────┐
│                                                              │
│  ┌────────────┐    ┌────────────┐                            │
│  │ frontend   │───▶│  backend   │                            │
│  │ Next.js    │    │  FastAPI   │                            │
│  └────────────┘    └─────┬──────┘                            │
│                          │ OTLP/HTTP                         │
│                          │ POST /v1/traces                   │
│                          ▼                                   │
│                   ┌──────────────┐    ┌─────────────────┐    │
│                   │  phoenix     │◀───│ phoenix-data    │    │
│                   │  arizephoenix│    │ named volume    │    │
│                   │  /phoenix    │    │ (SQLite)        │    │
│                   └──────┬───────┘    └─────────────────┘    │
│                          │ :6006 (UI + OTLP)                 │
└──────────────────────────┼───────────────────────────────────┘
                           ▼
              127.0.0.1:6006  ←─ developer's browser
```

**Topology decisions**

| Concern | Decision |
|---|---|
| Phoenix image | `arizephoenix/phoenix:latest` pinned to a specific tag in compose |
| Persistence | Named volume `phoenix-data` mounted at the Phoenix data dir |
| OTLP endpoint (backend → phoenix) | `http://phoenix:6006/v1/traces` (docker DNS) |
| External port | `127.0.0.1:6006:6006` — UI reachable only from the host loopback |
| OTLP standard | OpenTelemetry over HTTP/JSON (no extra gRPC dependency) |
| Vendor lock-in | None — OTLP is portable; future swap to Jaeger/Tempo/LangSmith touches only `agent/tracing.py` |

## 5. Instrumentation Pattern (Hybrid)

Three patterns, role-divided:

| Target | Pattern | Mechanism |
|---|---|---|
| Ollama LLM calls | **Auto** | `OpenAIInstrumentor().instrument()` once at startup (Ollama is OpenAI-API-compatible) |
| FastAPI HTTP routes | **Auto** | `FastAPIInstrumentor.instrument_app(app)` once at startup |
| Tool dispatchers | **Decorator** | `@trace_tool("create_task")` etc., applied to functions in `pipeline/tools.py` |
| Subsystem entry points (chat / memory / reflection / briefing / agent) | **Decorator** | `@trace_subsystem("memory")` etc. |
| ReAct loop rounds, "interesting decision points" inside long functions | **Context-manager** | `with tracer.start_as_current_span("react.round") as span: span.set_attribute(...)` — used sparingly |

**Why hybrid:** auto-instrumentation absorbs the work for the noisiest part (LLM calls). Decorators give consistency for the well-defined entry points. Context-managers stay rare and reserved for places where mid-function state matters (e.g. "ReAct round 0 selected 2 tools, round 1 produced final answer"). The convention will be codified in `.claude/skills/tomorrow-you-tracing/SKILL.md` as a post-implementation deliverable so future contributors (and Claude in future sessions) follow the same rules.

## 6. Components & File Changes

**New files**

| Path | Purpose |
|---|---|
| `agent/tracing.py` | Single module exposing `init_tracing()`, the three decorators, span attribute helpers, NoOp fallback |
| `tests/test_tracing.py` | Unit + integration tests using `InMemorySpanExporter` |
| `.claude/skills/tomorrow-you-tracing/SKILL.md` | Convention guide (post-implementation, written from the resulting code) |

**Modified files**

| Path | Change |
|---|---|
| `docker/local.compose.yml` | New `phoenix` service, `phoenix-data` volume, OTLP env var injection on backend |
| `backend/main.py` | Call `init_tracing()` inside the FastAPI lifespan startup hook; wrap in try/except |
| `pipeline/chat.py` | `@trace_subsystem("chat")` on entry; `with span("react.round", round=i)` per loop iteration |
| `pipeline/tools.py` | `@trace_tool(name)` on each tool dispatcher |
| `pipeline/memory.py` | `@trace_subsystem("memory")` on `recall`, `remember`, `forget`, `upsert` |
| `pipeline/reflection.py` | `@trace_subsystem("reflection")` on cycle; `with span("reflection.gather_evidence")` |
| `pipeline/briefing.py` | `@trace_subsystem("briefing")` on `generate` |
| `agent/router.py`, `agent/integrations.py` | `@trace_subsystem("agent")` on top-level dispatchers |
| `requirements.txt` (or pyproject) | Add `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`, `openinference-instrumentation-openai`, `arize-phoenix-otel` |
| `backend/run.sh` | Export `OTEL_EXPORTER_OTLP_ENDPOINT`, `TOMORROW_YOU_TRACING_ENABLED` |
| `.env.example` | Document new env vars |
| `docs/DEPLOY.md` | Section on how to access Phoenix UI, how to wipe trace data, retention notes |

## 7. Data Model — Span Hierarchy

**Per chat request:**

```
HTTP POST /chat                                  (FastAPI auto)
└── chat.process_message                         [user_id, session_id, message_len]
    ├── memory.recall                            [query, hit_count, salience_max]
    └── react.round (round=0)                    [round_index]
        ├── llm.call                             (auto: model, input_tokens, output_tokens, latency_ms)
        ├── tool.create_task                     [args, result, error?]
        └── react.round (round=1)
            └── llm.call                         (auto)
```

**Per reflection cycle:**

```
reflection.cycle                                 [user_id, trigger]
├── reflection.gather_evidence                   [chat_count, memory_count]
├── llm.call                                     (auto)
└── memory.upsert × N                            [salience, source=reflection]
```

**Per daily briefing:**

```
briefing.generate                                [user_id, mode=deterministic|llm]
├── briefing.collect_context                     [tasks_due, recent_memories]
└── llm.call                                     (auto, only if mode=llm)
```

**Common attributes on every span**

- `tomorrow_you.user_id`
- `tomorrow_you.session_id` (when applicable)
- `tomorrow_you.app_version` (git SHA from build env var)
- `tomorrow_you.environment` (`dev` | `prod`)

**Sensitive content**

User message text, model responses, and memory contents are captured in full. Justification: single-user app, local-only Phoenix, traces never leave the host. A `TOMORROW_YOU_TRACE_REDACT_PII` toggle is explicitly **deferred to a later sub-project** if/when multi-user becomes a concern.

## 8. Configuration & Toggle

| Env var | Default | Effect |
|---|---|---|
| `TOMORROW_YOU_TRACING_ENABLED` | `true` in dev compose, `false` in tests | If false, `init_tracing()` returns immediately and OTEL SDK uses `NoOpTracerProvider`; all decorators become near-zero-cost passthroughs |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://phoenix:6006/v1/traces` | Where backend ships spans |
| `OTEL_SERVICE_NAME` | `tomorrow-you-backend` | Service identifier in Phoenix UI |
| `OTEL_RESOURCE_ATTRIBUTES` | `deployment.environment=dev,service.version=<git-sha>` | Resource-level metadata |

The toggle is read **once at startup** — changing it requires a backend restart. This is intentional; we avoid runtime reconfiguration complexity.

## 9. Error Handling

**Invariant:** tracing failures NEVER break the app.

- `init_tracing()` is wrapped in try/except at the call site. On exception, log a warning and proceed with the SDK's default NoOp tracer.
- Domain exceptions raised inside an instrumented function: the span is finalized with `status=ERROR` plus an exception event, then the exception is **re-raised** unchanged.
- Tracing-layer exceptions (exporter timeout, serialization failure, etc.): caught and logged at WARN, **never** propagated to caller.
- Phoenix container unreachable: OTLP exporter buffers up to its default queue, then drops oldest spans. Backend keeps running normally.
- Double instrumentation guard: `OpenAIInstrumentor().instrument()` is called inside `init_tracing()`, which is itself idempotent (early-return on already-initialized).

## 10. Testing Strategy

**Unit tests** (`tests/test_tracing.py`)

- Decorators create the expected span name + kind.
- Specified attributes are recorded on the span.
- A function that raises records `status=ERROR` and an exception event.
- With `TOMORROW_YOU_TRACING_ENABLED=false`, no spans are exported and overhead is negligible.

**Integration test**

- Use `opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter`.
- Run a synthetic chat round through `pipeline.chat`'s public entry with a mocked Ollama client.
- Assert the resulting span tree shape: root `chat.process_message` → child `memory.recall`, `react.round`, `llm.call`, `tool.*` in the expected hierarchy.
- Assert common attributes (`tomorrow_you.user_id`, etc.) are present.

**Smoke test (manual)**

1. `docker compose up`
2. Send a chat message via the web UI.
3. Open `http://localhost:6006` in a browser.
4. Verify a trace appears under service `tomorrow-you-backend` with the expected structure.

**Regression target:** all 420 existing tests must still pass with tracing enabled and with it disabled.

**CI**

- No Phoenix container is started in CI. Tests use the in-memory exporter only.
- Adds ~10-15 new test cases.

## 11. Acceptance Criteria

The sub-project is "done" when:

1. `docker compose up` brings up Phoenix alongside backend and frontend, and `http://localhost:6006` shows the Phoenix UI.
2. A single chat round produces, at minimum, the span tree shown in §7.
3. A reflection cycle and a daily briefing each produce their respective span trees.
4. Toggling `TOMORROW_YOU_TRACING_ENABLED=false` and restarting the backend disables all trace export with no test failures.
5. `tests/test_tracing.py` covers the cases in §10 and all 420 prior tests still pass.
6. `.claude/skills/tomorrow-you-tracing/SKILL.md` is written, describing where to add new spans in this codebase.
7. `docs/DEPLOY.md` has a "Tracing" section explaining UI access, wiping data, and the toggle.

## 12. Future Work (explicitly out of scope here)

- PII redaction toggle (when multi-user happens).
- Sampling (when volume gets high).
- Span-to-eval-dataset export script (will be designed inside sub-project ② Eval Harness, but the schema in §7 is shaped to make it cheap).
- Cost dashboards beyond what Phoenix gives out of the box.
- Alerting on error rates.
- Custom in-app trace viewer in the Next.js frontend.

## 13. References

- Arize Phoenix — https://docs.arize.com/phoenix
- OpenInference instrumentation for OpenAI — https://github.com/Arize-ai/openinference
- OpenTelemetry Python SDK — https://opentelemetry.io/docs/languages/python/
- Local Claude Code skills leveraged during implementation: `langsmith`, `langsmith-fetch`, `phoenix`, `python-observability`
- Roadmap: `docs/superpowers/specs/2026-05-28-agent-trace-console-design.md` (this file) → planned follow-ups for ② Eval Harness, ③ RAG Memory, ④ Adaptive Reflection, ⑤ Smart Briefing 2.0
