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

## Adaptive Self-Learning Loop (Sprint 28)

New spans introduced for the typed-tendencies extractor:

- `tendencies.extract_features` — deterministic heuristic extractor
- `tendencies.llm_critic` — qwen3:8b call (visible only when reflection actually calls the LLM)

These spans always sit under `reflection.run_reflection`. If you add a new
behavioral output that reads `UserMemory["adaptive_tendencies"]`, wrap the
read site in your own span (or call `tendencies.load_from_memory` which is
already instrumented) so the trace shows the read-side dependency too.

Storage convention:

- Key in UserMemory is the literal string `"adaptive_tendencies"`.
- Value is the JSON shape defined in
  `docs/superpowers/specs/2026-05-28-adaptive-self-learning-loop-design.md` §5.
- Confidence threshold for *acting* on a dim is 0.3. Below that, behavior
  falls back to persona/static defaults.
