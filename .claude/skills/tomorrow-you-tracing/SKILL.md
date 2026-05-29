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

## Sprint 29 Eval Harness

The trace schema is shaped so that one trace ≈ one eval-harness example. The
eval harness extracts traces via Phoenix REST API and converts them to scenario
JSON files for deterministic evaluation.

**Key implementation files**:
- `eval/cli.py` — Command-line interface with three subcommands:
  - `export-phoenix` — Extract traces from Phoenix and convert to scenarios
  - `run-scenarios` — Run chat agent against a scenario file
  - `score-only` — Score actual output against expected output
- `eval/phoenix_export.py` — Trace → scenarios converter
- `eval/runner_sprint29.py` — Chat agent orchestrator for evaluation
- `eval/metrics_hermes.py` — Deterministic scoring (no LLM)

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

## Eval Harness (Sprint 29)

The trace extractor (`eval/phoenix_export.py`) walks Phoenix span trees and
emits scenario rows for the chat-agent eval harness. Use the CLI:

```bash
# Export latest 100 traces from Phoenix
python -m eval.cli export-phoenix --url http://localhost:6006 --output eval/scenarios/phoenix.json

# Run curated 8 golden scenarios
python -m eval.cli run-scenarios eval/scenarios/sprint29.json --json-summary
```

If you change span names or attribute keys here, update the extractor
(`eval/phoenix_export.py`) and the eval scenarios so the metrics still bind.

## Sprint 30 — RAG Memory

새 `rag/` 모듈은 Phoenix에서 `trace_subsystem("rag")` 네임스페이스로 가시화됨:

- `rag.embedder.embed_text` — Ollama `/api/embeddings` 호출. latency·error_rate가 Phoenix 트레이스에 자동 기록됨.
- `rag.store.search` — sqlite-vec KNN. 벡터 차원/k 파라미터가 span attribute로 캡처.
- `rag.indexer.tick` — 60초 주기 backfill loop의 한 tick. `n_indexed`가 카운터로 노출.
- `rag.retriever.recall_semantic` — chat auto-inject 및 LLM tool 경로 공통 진입점. `query` 길이·`k`·반환 hit 개수가 attribute.

`chat.post_user_message` 트레이스에서 RAG hit이 system_prompt에 prefix되는 순간이 자식 span으로 보임. retriever fail-soft (Ollama 다운 등) 시 빈 list 반환하므로 chat span은 항상 정상 종료됨.
