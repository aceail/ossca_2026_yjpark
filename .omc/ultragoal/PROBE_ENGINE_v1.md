# HITL Probe Engine v1 — G004

**연계**: FINAL_GOAL.md v2.3 §5 HITL 3-Phase · §8 OSSCA 기여 2번
**구현**: `probe/engine.py` · `probe/__init__.py` · `db/migrations/002_seed_probe_questions.sql` · `tests/test_probe_engine.py` (10/10 green)

## 핵심
- **Phase Router**: completion_percent + session_count → Phase 1/2/3
  - Phase 1: session_count < 4 (G005가 처리)
  - Phase 2: 4 ≤ session_count < 15 또는 completion_percent < 80%
  - Phase 3: completion_percent ≥ 80%
- **휴리스틱 점수**: `1.0×missing + 0.7×low_confidence + 0.5×expected_ig − 1.0×fatigue_penalty`
- **Cooldown**: `__skip__` 응답 24h 후 재시도
- **페르소나-aware**: `select_active_prompt(conn, user_id)` → 활성 페르소나의 system_prompt 반환
- **질문 뱅크 v1**: 12개 (time/regret/recovery/fear/post-emotion/micro-action/deadline/forbidden 슬롯)

## API
```python
from probe import ProbeEngine, PhaseRouter, select_active_prompt
engine = ProbeEngine(conn)
best = engine.best_question(user_id=...)  # Phase 2만 반환, 아니면 None
engine.record_answer(user_id=..., question_id=..., avoidance_session_id=..., answer_text=..., extracted_slot_updates={...})
engine.skip_today(user_id, question_id)  # cooldown 진입
pid, prompt = select_active_prompt(conn, user_id)
```

## 다음 의존
- G006 Pipeline에서 회피 입력 직전 호출
- G009 v3 페르소나 회귀에 active prompt 라우터 사용
