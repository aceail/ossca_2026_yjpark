# Chat Cards + Time Hygiene (Sprint 40) — Design Spec

**Date:** 2026-05-29
**Status:** Approved (brainstorm + designer feedback 반영)
**Goal:** 사용자가 보고한 2가지 실제 문제 fix + chat 카드를 정적 텍스트에서 *인터랙티브 행동 시작점*으로 격상

## Problems addressed
1. **LLM 시간 환각:** "오늘 18시까지 보고서" → backend deadline=23:59, "30분 남았다"가 LLM 환각 (실제 5h+ 남음)
2. **Recovery card JSON 노출:** `{"card_type":"recovery", "sentences":{...}}`가 raw text로 chat에 표시됨
3. **Chat 카드가 정적:** 정보만 표시, 행동 surface 없음 → 행동 전환율 ceiling

## Non-Goals
- 새 LLM 모델 도입 (qwen3:8b 그대로)
- chat scenario card 전체 리팩토링 (scope creep)
- 다국어 시간 표현 (한국어만)

## Architecture

### A. Deterministic time parsing (T1)
신규 `pipeline/time_parse.py`:
```python
def parse_natural_deadline(text: str, now: datetime) -> Optional[str]:
    """한국어 자연어에서 deadline ISO timestamp 추출. 못 잡으면 None."""
```

지원 패턴 (확장 우선순위):
- `\d+시` (24h) + optional `분`
- `오전/오후 + \d+시` + optional `분`
- `오늘 (저녁|밤|오전|오후|새벽)` — 기본 시각 매핑
- `내일`, `모레`, `다음주`
- `\d+:\d+` (24h colon)
- 이미 ISO 형식이면 그대로

Backend가 task 등록 hook에서 LLM의 deadline_at을 정규식 결과로 *덮어쓰기*. 정규식이 None일 때만 LLM 값 유지.

### B. Recovery card prefix-line emission (T2)
`pipeline/chat.py` 후처리:
LLM이 chat reply에 `{"card_type":"recovery","sentences":{"fact":..,"feeling":..,"micro_action":..}}` 토하면 가로채:
```
🪞 fact: <시간 backend 재계산>. <원본 fact 본문>
🫧 feeling: <원본 feeling>
👣 micro: <원본 micro> :: deeplink=/tasks?focus={taskId}
```
시간 부분 재계산: `_build_temporal_hints` 활용해 현재 KST + 남은 시간 계산.
`:: deeplink=...` syntax는 frontend의 RecoveryCardCluster에서 파싱.

### C. RecoveryCardCluster component (T3) — designer 권고
`frontend/components/RecoveryCardCluster.tsx`:
- 좌측 6px 세로 띠 (`--color-recovery-border`)
- 3 섹션, 같은 카드 내 divider:
  - **fact** (`--color-bg-card`) — 무채색, 중립
  - **feeling** (`--color-recovery-bg` 황토) — 부드러움
  - **micro** (`--color-action-bg` 흑) — filled, 행동 catalyst
- `card-enter` stagger animationDelay 0/60/120ms
- fact/feeling tap → router.push(deepLink) + 우측 `→` affordance opacity 40→80
- micro 내부 3 버튼:
  - Primary full-width: `▶ 시작` (deepLink 이동)
  - Secondary row 2개: `✓ 완료` (task PATCH done) / `⏰ 30분후` (snooze)
- 모든 button `active:scale-[0.97] transition-transform duration-100`

`CARD_PREFIXES` 확장: `🪞🫧👣` 추가. parseAssistantContent에서 cluster 감지 → 별도 component 렌더.

### D. Prompt 시간 verbatim (T4)
`_build_temporal_hints` 강화:
```
[시간 hint — 절대 직접 계산하지 마, 아래 값만 verbatim 사용]
- 현재: 2026-05-29 12:18 KST (Friday)
- open task 마감 임박:
  - "보고서": 2026-05-29 18:00 KST (남은 시간 5h 42min)
- 답변에 시간/남은 시간을 언급할 땐 위 값을 그대로 복사.
```

scenario prompt (`pipeline/orchestrator.py`)에도 동일 hint inject.

### E. Interactive action cards (T5)
기존 `✅📁✓📅✏⚠` 카드도 동일 패턴:
- 카드 전체 `<button>` wrap → 해당 페이지 deep link
- 우측 `→` affordance
- `active:scale-[0.97] transition-transform duration-100`

| Prefix | Deep link |
|---|---|
| ✅ task | `/tasks?focus={id}` |
| 📅 schedule | `/calendar` |
| 📁 folder | `/tasks?focus={id}` (with folder hint) |
| ✏ edit | `/tasks?focus={id}` |

### F. Motion (T6) — designer 권고
- `card-enter` keyframe globals.css (이미 있으면 reuse, 없으면 추가)
- stagger via `animationDelay` inline
- tap response `active:scale-[0.97] duration-100`
- `prefers-reduced-motion` → fade-in 200ms fallback

## Schema
변경 없음.

## Testing
- T1: 12+ time parsing 케이스 (18시, 오후 6시, 내일 정오, 다음주 월요일, 23:59, 이미 ISO 등)
- T2: JSON 입력 → prefix-line 변환 단위 테스트 (3 cases)
- T3: 컴포넌트는 unit test 생략, 통합 검증으로 대체
- T7: 전체 회귀 + 컨테이너 + 「보고서」 task patch

## Migration
- 신규 모듈 1개 (time_parse.py)
- 신규 컴포넌트 1개 (RecoveryCardCluster)
- 기존 파일 수정: pipeline/chat.py, pipeline/orchestrator.py, frontend/app/chat/page.tsx, frontend/app/globals.css

## Dependencies
- 기존 wire 모두 활용 (chat path, scenario flow, CARD_PREFIXES)
- 신규 lib 0개

## Future Work
- 영어 시간 표현 추가
- voice input → time parse
- card 클릭률 추적 (NotificationLog와 통합)
