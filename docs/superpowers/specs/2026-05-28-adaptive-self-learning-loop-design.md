# Adaptive Self-Learning Loop — Design

- **Date:** 2026-05-28
- **Owner:** yjpark
- **Status:** Draft → awaiting user review
- **Sprint slot:** Sprint 28 (sub-project ⑥ of the 6-track roadmap)
- **Roadmap position:** ⑥ Adaptive Self-Learning Loop. Replaces the originally-scoped "Work Artifact Upload" after the user redirected the project's North Star back to Hermes-style self-learning.
- **Builds on:** Sprint 18 Hermes agent loop, Sprint 20 UserMemory, Sprint 21 self-reflection, Sprint 27 tracing.

## 1. Summary

Close the agent's behavioral feedback loop: extract typed per-user *tendencies* from existing signals (chat history, task lifecycle, folder snapshots, followup reactions), persist them as JSON under `UserMemory["adaptive_tendencies"]`, and have the followup loop read them when deciding tone and timing. First delivery personalizes two behaviors — **followup tone** (gentle vs sharp vs balanced) and **followup timing** (when to start nudging based on the user's typical deadline buffer). Hybrid implementation: deterministic heuristic feature extractor + qwen3:8b critic, with the heuristic acting as a safety net when the LLM produces unusable output.

## 2. Motivation & Context

"내일의 너" already collects rich signals (ChatMessage, Task, FolderSnapshot, RegretScore). It also already has a reflection loop (Sprint 21) that extracts free-text patterns into UserMemory. What's missing is the *behavioral output* side: nothing reads those patterns and changes the assistant's actual behavior. The followup loop still applies a uniform tone-escalation rule regardless of whether a given user thrives under sharp messages or shuts down. This sub-project closes that loop for the two most user-perceived behaviors first.

The user explicitly framed this as the reason Hermes was adopted in the first place: "각 개별사용자의 성향을 좀 파악하면 좋을거 같아 자가학습으로" — grasp each individual user's tendencies through self-learning. So the design has to feel like self-learning, not rule engineering.

## 3. Goals & Non-Goals

**Goals**

- Heuristic feature extractor produces a stable, typed set of measurements from existing tables every 12h.
- LLM critic enriches the typed set with qualitative dimensions (tone preference, reaction-to-sharp) using qwen3:8b.
- A merged typed JSON is persisted under `UserMemory["adaptive_tendencies"]` per user, with a `version_at` timestamp.
- `pipeline/followup.py:decide_followup` reads from the JSON to (a) pick tone and (b) decide *when* to start nudging (deadline buffer).
- Failure modes never break the existing followup loop. Heuristic and LLM each degrade independently.
- Every tendencies extraction is visible as a span (`tendencies.extract`, `tendencies.llm_critic`) in the Sprint 27 Phoenix trace.

**Non-goals**

- No new tables. UserMemory + JSON value is enough for v1.
- No A/B testing framework — that's sub-project ② Eval Harness when it lands.
- No personalization of briefing or task-creation prompts in this sprint (only followup tone + timing).
- No upload feature in this sub-project. The originally-scoped "Work Artifact Upload" is dropped from the roadmap; if needed later it joins as input-signal flavor under this same loop.
- No vector embeddings or RAG over the tendencies — single small JSON per user.

## 4. Architecture

```
┌── 12h reflection_loop (existing, backend lifespan task) ───────────────┐
│                                                                        │
│  ① Heuristic Feature Extractor — pipeline/tendencies.py                │
│     scans ChatMessage / Task / FolderSnapshot / Task.last_followup_at  │
│     ⤷ raw_features (typed):                                            │
│        chat_count_7d            : int                                   │
│        avg_deadline_buffer_days : float                                 │
│        peak_hour_histogram      : list[int] (24-bucket)                 │
│        sharp_then_progress_ratio : float (0..1)                         │
│        gentle_then_progress_ratio: float (0..1)                         │
│        snapshot_growth_pattern  : 'late_spike' | 'steady' | 'flat'      │
│                                                                        │
│  ② LLM Critic — qwen3:8b, think=false                                  │
│     prompt(raw_features + last_N chat samples) → JSON:                  │
│        tone_preference         : gentle | sharp | balanced              │
│        reaction_to_sharp       : improves | shuts_down | neutral        │
│        typical_deadline_buffer_days : int                               │
│        peak_work_hours         : list[int]                              │
│        confidence              : dict[dim → 0..1]                       │
│                                                                        │
│  ③ Merge — heuristic-first for numeric dims, LLM-only for qualitative  │
│                                                                        │
│  ④ Save to UserMemory["adaptive_tendencies"]                           │
│     value = json.dumps(merged), source="adaptive", version_at = now    │
└────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
        ┌── 60min followup_loop reads on every dispatch ──┐
        │  pipeline/followup.py:decide_followup           │
        │   - tone = pick_tone(tendencies, base_persona_tone) │
        │   - kick_in_days = tendencies.typical_deadline_buffer_days + 2 │
        │     (start nudging early for late-starters)     │
        │   - fall back to existing logic if tendencies absent/invalid    │
        └─────────────────────────────────────────────────┘
```

## 5. Data Model — `adaptive_tendencies` JSON schema

Stored as the `value` column of UserMemory where `key = "adaptive_tendencies"`.

```json
{
  "version_at": "2026-05-28T12:00:00+00:00",
  "raw_features": {
    "chat_count_7d": 23,
    "avg_deadline_buffer_days": 1.4,
    "peak_hour_histogram": [0,0,0,0,0,0,0,0,0,0,1,2,3,4,5,4,3,2,1,0,0,0,0,0],
    "sharp_then_progress_ratio": 0.62,
    "gentle_then_progress_ratio": 0.31,
    "snapshot_growth_pattern": "late_spike"
  },
  "qualitative": {
    "tone_preference": "sharp",
    "reaction_to_sharp": "improves",
    "typical_deadline_buffer_days": 1,
    "peak_work_hours": [13, 14, 15]
  },
  "confidence": {
    "tone_preference": 0.78,
    "reaction_to_sharp": 0.55,
    "typical_deadline_buffer_days": 0.92,
    "peak_work_hours": 0.7
  }
}
```

Notes:
- `version_at` lets downstream code know how fresh the tendencies are; below a threshold (e.g., older than 24h) the system can still use them but a fresher extraction is requested next cycle.
- Each qualitative dim has a `confidence`. If confidence < 0.3, followup ignores that dim and uses the persona default.
- The shape is forward-compatible: new dims can be added without DB migrations.

## 6. Components & File Changes

**New files**

| Path | Responsibility |
|---|---|
| `pipeline/tendencies.py` | `extract_features(conn, user_id, now) -> dict`, `llm_critic(features, chat_samples) -> dict`, `merge(features, critic) -> dict`, `save_to_memory(conn, user_id, merged)`, `load_from_memory(conn, user_id) -> dict | None` |
| `tests/test_tendencies.py` | Feature extractor unit tests + critic schema tests (mocked LLM) + followup integration |

**Modified files**

| Path | Change |
|---|---|
| `pipeline/reflection.py` | `run_reflection` now also invokes `tendencies.extract_features` → `llm_critic` → `save_to_memory` after the existing free-text reflection. New steps wrapped in try/except so existing flow unaffected on failure. |
| `pipeline/followup.py` | `decide_followup` consults `tendencies.load_from_memory()` first; uses `tone_preference` (if confidence ≥ 0.3) and `typical_deadline_buffer_days` (if confidence ≥ 0.3) to set tone and kick-in threshold. Falls back to existing persona tone / static D-2 default if tendencies absent or low-confidence. |

No DB migration — UserMemory already accepts arbitrary string `key` and `value`. We just write `key="adaptive_tendencies"`.

## 7. Heuristic Feature Extractor — Definitions

Definitions are chosen to be computable from current schema only.

- `chat_count_7d`: count of `ChatMessage` rows for the user where `created_at >= now - 7d`.
- `avg_deadline_buffer_days`: for completed/abandoned tasks, mean of `(min(updated_at, deadline_at) - last_followup_at).days`. If the user has fewer than 3 closed tasks, value is `null` (caller handles).
- `peak_hour_histogram`: 24 ints, hour-of-day count of user's `ChatMessage` over the last 30d, KST.
- `sharp_then_progress_ratio` / `gentle_then_progress_ratio`: of all followup events with tone X, fraction where the next FolderSnapshot for that task showed file_count or total_bytes increase. Requires at least 5 prior followup events; else `null`.
- `snapshot_growth_pattern`: classify last 30d of FolderSnapshot deltas per task into `'late_spike'` (>60% growth in last 20% of time window), `'steady'`, `'flat'` (no growth). Aggregate across user's tasks by majority vote.

All extractors return `None` (or `null` in JSON) when insufficient data. Merge step preserves `null` and the LLM critic is told which dims are unmeasured so it can be more cautious.

## 8. LLM Critic Prompt (verbatim shape)

```
[시스템]
당신은 사용자 행동을 분석하는 평가자입니다. 사용자의 통계와 최근 채팅
샘플을 보고 아래 JSON schema를 정확히 채워 응답하세요. 다른 텍스트
일체 금지. 통계가 null인 차원은 'confidence'를 낮게 설정해야 합니다.

[사용자 측정값]
{raw_features}

[최근 채팅 샘플 (N=10)]
{recent_chat_samples}

[출력 schema]
{
  "tone_preference": "gentle" | "sharp" | "balanced",
  "reaction_to_sharp": "improves" | "shuts_down" | "neutral",
  "typical_deadline_buffer_days": <int>,
  "peak_work_hours": <list[int]>,
  "confidence": {
    "tone_preference": <0..1>,
    "reaction_to_sharp": <0..1>,
    "typical_deadline_buffer_days": <0..1>,
    "peak_work_hours": <0..1>
  }
}
```

The prompt is sent with `think=false` so qwen3:8b returns the JSON directly. Response parsed with `json.loads(first_brace_to_last_brace)`; if invalid, critic returns `{}` and merge step uses heuristics only.

## 9. Followup Integration

`pipeline/followup.py:decide_followup` gets one new dependency: `tendencies = load_from_memory(conn, user_id)`.

**Tone selection**

```
if tendencies and tendencies['confidence'].get('tone_preference', 0) >= 0.3:
    base_tone = tendencies['qualitative']['tone_preference']
else:
    base_tone = persona_tone or 'balanced'

if tendencies and tendencies['confidence'].get('reaction_to_sharp', 0) >= 0.3:
    if tendencies['qualitative']['reaction_to_sharp'] == 'shuts_down' and base_tone == 'sharp':
        base_tone = 'balanced'  # demote — sharp shuts this user down
```

**Timing (kick-in)**

```
default_kick_in = 2
if tendencies and tendencies['confidence'].get('typical_deadline_buffer_days', 0) >= 0.3:
    buf = tendencies['qualitative']['typical_deadline_buffer_days']
    # User who starts at D-1 needs nudges D-3; user who starts at D-7 only needs D-2.
    kick_in = max(default_kick_in, buf + 2)
else:
    kick_in = default_kick_in

days = _days_until(task.deadline_at, now)
if days is None or days > kick_in:
    decision.should_send = False
```

Existing escalation logic (frequency cap, progressed gate) is unchanged.

## 10. Error Handling

Invariant: **tendencies extraction failure never breaks reflection or followup**.

- `extract_features()` exceptions logged at WARN, return `{}`.
- `llm_critic()` exceptions logged at WARN, return `{}`.
- `merge()` with both empty → still writes a minimal record with version_at, so downstream knows the cycle ran.
- `load_from_memory()` returns `None` on JSON parse error; `decide_followup` then uses pre-existing logic.
- Schema validation: unknown keys in LLM JSON are dropped (whitelist), values outside enum/range are dropped.
- Multi-user: extraction runs per user; one user's failure doesn't stop others.

## 11. Testing Strategy

**Unit (`tests/test_tendencies.py`)**

- `extract_features` returns stable output for a constructed in-memory DB (frozen `now`).
- Null handling: insufficient-data cases return None for the corresponding feature.
- `merge` prefers heuristic numeric dims when both heuristic and critic provide them; uses critic only for qualitative dims.
- `load_from_memory` returns None on missing key, on invalid JSON, on schema violation; returns parsed dict otherwise.
- Mocked-LLM critic: feed canned response, assert correct merge output and confidence preserved.

**Integration**

- `decide_followup` with no tendencies → identical decision to current behavior (regression).
- `decide_followup` with `tone_preference=sharp, confidence=0.9` → tone='sharp' regardless of persona.
- `decide_followup` with `reaction_to_sharp=shuts_down, confidence=0.9, tone=sharp` → demoted to 'balanced'.
- `decide_followup` with `typical_deadline_buffer_days=5, confidence=0.9, task deadline 6 days away` → fires (kick_in = 7).
- `decide_followup` with same buffer but task 8 days away → does NOT fire.

**Regression target:** all 438 prior tests still pass; ~15 new ones land us at ~453.

**Tracing verification:** synthetic reflection run produces `reflection.run_reflection`, `tendencies.extract_features`, `tendencies.llm_critic`, `memory.upsert_memory` spans in Phoenix (Sprint 27 instrumentation reused).

## 12. Acceptance Criteria

1. ✅ `pipeline/tendencies.py` exists with the 5 functions in §6 and they are importable.
2. ✅ Running `pipeline/reflection.py:run_reflection_for_all` triggers tendencies extraction for users with sufficient data; users without data don't crash the cycle.
3. ✅ `UserMemory["adaptive_tendencies"]` is populated for at least one test user with valid JSON matching the §5 schema.
4. ✅ `decide_followup` consults tendencies; verified via integration tests covering all 5 cases in §11.
5. ✅ LLM critic disabled (or unreachable) → tendencies still saved with heuristic fields + empty qualitative; followup still works.
6. ✅ All 438 prior tests pass; new unit + integration tests in `test_tendencies.py` all pass.
7. ✅ Phoenix trace shows new `tendencies.extract_features` and `tendencies.llm_critic` spans during a reflection cycle.

## 13. Future Work (out of scope)

- Personalize briefing time-of-day from `peak_work_hours`.
- Personalize task-creation prompts (auto-suggest deadline buffer based on `avg_deadline_buffer_days`).
- A/B test tone overrides — needs sub-project ② Eval Harness.
- Vector-embedding-based tendency clustering across users.
- Surfacing tendencies back to the user ("나는 너의 패턴을 이렇게 봤어 — 맞아?").

## 14. References

- Sprint 18 Hermes agent loop: `pipeline/chat.py`
- Sprint 20 UserMemory: `pipeline/memory.py`, `db/migrations/016_user_memory.sql`
- Sprint 21 self-reflection: `pipeline/reflection.py`
- Sprint 27 tracing: `agent/tracing.py`, `.claude/skills/tomorrow-you-tracing/SKILL.md`
- Roadmap context: this file replaces the original Work Artifact Upload sub-project ⑥ after user redirected scope.
