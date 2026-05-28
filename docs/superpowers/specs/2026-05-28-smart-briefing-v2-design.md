# Smart Briefing 2.0 — Design Spec (Sprint 31)

**Date:** 2026-05-28
**Status:** Approved (brainstorm)
**Sub-project:** ⑤ of the 5-sub-project roadmap

## Goal

Daily Briefing(`pipeline/briefing.py`)을 Hermes-style memory-aware briefing으로 격상.
- ③ RAG retriever (`rag.retriever.recall_semantic`)로 episodic 회상
- ⑥ adaptive tendencies (`pipeline.tendencies.load_from_memory`)로 톤·타이밍 개인화
- 새 momentum 지표 (streak / stagnation)로 행동 신호 제공

## Non-Goals
- 기존 `should_brief` cooldown 정책 변경 안 함 (KST 1일 1회)
- briefing을 별도 모듈로 분리하지 않음 (단일 파일 384줄 이내 유지)
- chat path는 손대지 않음

## Architecture

`pipeline/briefing.py` 단일 파일 확장:

```python
# 신규 헬퍼
def _compute_momentum(conn, user_id, *, now) -> dict
#   → {streak_days: int, last_active_date: str, stagnant_tasks: list[dict]}

# 신규 헬퍼 — RAG 회상 query 구성
def _build_rag_query(open_titles: list[str], recent_user_msgs: list[str]) -> str

# 신규 헬퍼 — fallback rendering
def _render_brief_lines(data: dict) -> list[str]

# 확장
collect_briefing_data() — 신규 키: momentum / tendencies / rag_recalls
_fallback_brief() — adaptive 3-7 lines (data 있는 차원만 emit)
build_briefing_prompt() — 신규 신호 전달 + tone 강제
```

## Signal Definitions

| 신호 | 출처 | 계산 |
|---|---|---|
| `momentum.streak_days` | Task / FolderSnapshot / ChatMessage | 오늘 기준 KST 연속 활성 일수. "활성" = (그날 Task closed) OR (FolderSnapshot taken_at) OR (ChatMessage role='user' count ≥ 3) |
| `momentum.stagnant_tasks` | Task | status='open' AND updated_at older than 5 days, top 3 by oldest |
| `tendencies` | UserMemory['adaptive_tendencies'] | `load_from_memory()` 그대로 |
| `rag_recalls` | rag.retriever.recall_semantic | query = open task titles 합치기 + 최근 user msg, kinds=("chat","memory","task"), k=3 |

## Adaptive Output Rules (3-7 lines)

| 라인 | 조건 | 내용 |
|---|---|---|
| L1 | 항상 | `📅 오늘 <date>. 진행 중 N개.` |
| L2 | overdue ≥ 1 | `⏰ 마감 지남: <titles>` |
| L3 | imminent ≥ 1 | `🔔 마감 임박(3일 내): <titles + deadline>` |
| L4 | streak ≥ 2 | `🔥 N일 연속 뭐든 진행 중` |
| L4-alt | streak = 0 AND stagnant ≥ 1 | `⏳ "<title>"은 N일째 멈춰있어` |
| L5 | rag_recalls ≥ 1 AND 의미 매칭 | `💭 <kind>에서 비슷한 맥락: <snippet>` |
| L6 | 항상 (tendencies.tone_preference에 따라 어조 변형) | 행동 추천 한 줄 |

## Tone Mapping (tendencies.tone_preference → L6)

| tone | L6 예시 |
|---|---|
| quiet | "오늘 하나만 가볍게 시작해볼까?" |
| witty | "오늘 한 놈만 패자." |
| sharp | "오늘 가장 미루던 거 먼저 손대." |
| savage | "변명 그만, 마감 임박부터." |

기본값(tendencies 미존재): quiet.

## LLM Prompt Strategy

`build_briefing_prompt()` 변경:
1. 신호 전체를 구조화 JSON으로 system context에 넣고
2. "위 신호 중 *있는 것만* 사용. 데이터 없는 차원 만들어내지 마라" 명시
3. "tone_preference=<X> → 어조 <X>로" 직접 지시
4. max 6 lines 제약

## Testing Strategy

`tests/test_briefing_v2.py` — 신규 10-12개:
- `_compute_momentum` — streak 계산 4 cases (연속/중단/0일/오늘만)
- `_compute_momentum` — stagnant_tasks 1 case (>5일 미수정)
- `collect_briefing_data` — 신규 키 3개 모두 채워짐 1 case
- `_fallback_brief` — overdue+streak 모두 있을 때 라인 emit 1 case
- `_fallback_brief` — rag_recalls=0이면 L5 skip 1 case
- `_fallback_brief` — tendencies.tone="savage" → L6에 적용 1 case
- `generate_briefing` — 통합 (mock LLM + RAG + tendencies + momentum) 1 case

기존 `tests/test_briefing.py` 12개는 100% 보존.

## Error Handling
- `_compute_momentum` SQL error → 빈 dict 반환, brief는 진행
- `tendencies.load_from_memory` None → fallback tone=quiet
- `recall_semantic` Exception → 빈 list (이미 fail-soft)

## Migration / Rollout
- 마이그레이션 없음 (DB schema 변경 없음)
- backend 재시작 즉시 적용
- 기존 `_last_briefing_at` cooldown 키 그대로 사용

## Dependencies
- `feature/sprint-30-rag-code` 머지 필요 (rag.retriever.recall_semantic)
- Sprint 28 산출물 `pipeline/tendencies.load_from_memory` 이미 main에 있음

## Future Work
- briefing.py 단일 파일이 400줄 초과하면 `pipeline/briefing/` 패키지로 분리 (data.py / render.py / prompt.py)
- momentum 신호를 chat path에도 expose (Hermes context의 한 부분)
