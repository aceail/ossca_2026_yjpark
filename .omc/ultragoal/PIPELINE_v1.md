# Pipeline v1 — G006 AvoidanceSessionPipeline

**버전**: v1
**작성일**: 2026-05-26
**연계**: FINAL_GOAL.md v2.3 §5·§6·§6.5·§12·§15 · DATA_MODEL_v1.md · PROBE_ENGINE_v1.md · PERSONA_SYSTEM_v1.md

---

## 핵심 결정

- `SessionOrchestrator` 단일 클래스로 회피 입력 → 프로브 → 시나리오 → 결정 전 파이프라인 캡슐화
- LLM 호출은 `urllib.request` 표준 라이브러리 (외부 의존 최소화), timeout 60s
- Safety 키워드 감지 시 LLM 호출 없이 즉시 `soft_stop` 카드 반환
- 절대 금지어(`FORBIDDEN_GROUPS`) 출력 포함 시 `soft_stop` 폴백

## 아키텍처 흐름

```
사용자 입력
  └─► start_session()          → AvoidanceSession INSERT
  └─► maybe_probe()            → ProbeEngine.best_question() (Phase 2만)
  └─► record_probe_answer()    → ProbeAnswer INSERT + UserProfile.slots 갱신
  └─► generate_scenario()
        ├─ Safety 검사          → soft_stop 즉시 반환 (LLM 호출 X)
        ├─ select_active_prompt → 활성 페르소나 system_prompt
        ├─ _call_ollama()       → exaone3.5:7.8b (OLLAMA 127.0.0.1:11434)
        ├─ JSON 파싱 + 금지어 검사
        └─ ScenarioCard INSERT
  └─► record_decision()        → AvoidanceSession.user_decision 갱신
```

## 모듈 구조

| 경로 | 역할 |
|---|---|
| `pipeline/__init__.py` | SessionOrchestrator export |
| `pipeline/orchestrator.py` | 전 파이프라인 로직 |
| `ui/__init__.py` | render_card export |
| `ui/tui.py` | ANSI 52컬럼 박스 카드 렌더러 |
| `scripts/cli.py` | 사용자 실행 TUI MVP CLI |
| `db/migrations/003_pipeline_session_indexes.sql` | 세션·카드 성능 인덱스 |

## 실행 방법

```bash
# 기본 실행
python3 scripts/cli.py

# 특정 사용자 ID
python3 scripts/cli.py --user-id my-user-id

# ollama 실제 호출 테스트
OLLAMA_AVAILABLE=1 python3 -m unittest tests/test_pipeline.py -v

# 단위 테스트 (ollama 불필요)
python3 -m unittest tests/test_pipeline.py tests/test_tui_card.py -v
```

## Safety 정책 (§6.5 F)

- 자해·자살·"진짜 죽고 싶다"·약통 명시 → `soft_stop` 즉시 반환
- 한국어 자조 관용구("현타", "멘탈 나갔다", "존나 하기 싫다") → 위기 분류 제외
- LLM 출력에 절대 금지어 포함 시 → `soft_stop` 폴백

## 테스트 커버리지

- `tests/test_pipeline.py`: 17개 (1 skipped=OLLAMA 실제 호출)
- `tests/test_tui_card.py`: 19개
- 총 36개 / 36 통과 (ollama skip 제외)
