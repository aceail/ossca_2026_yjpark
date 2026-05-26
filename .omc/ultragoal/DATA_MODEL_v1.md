# Data Model v1 — G003 (17 테이블)

**버전**: v1 (G003 산출)
**작성일**: 2026-05-26
**연계**: FINAL_GOAL.md v2.3 §6 (16→17 테이블) · §6.5 Safety Policy · §12 Persona · §15 Agent Architecture
**Migration**: `db/migrations/001_initial.sql` (인덱스 + 5 default 페르소나 seed 포함)
**구현**: `db/__init__.py` · `db/schema.py` · `tests/test_data_model.py` (13/13 green)

---

## 0. 핵심 결정 (v2.3 반영)

- 로컬 SQLite (WAL 모드), 백엔드 X
- `PRAGMA foreign_keys = ON` 강제
- 사용자 데이터 영구 저장 위치: `tomorrow_you.db` (프로젝트 루트, .gitignore)
- 마이그레이션 시스템: `SchemaMigration` 테이블 + SHA256 checksum
- 5 default 페르소나는 마이그레이션 seed로 자동 삽입

## 1. 17 테이블 그룹 매트릭스

```
사용자 상태 (5)         LLM 운영 (7)              Safety (1)         Agent (3)               Persona (1)
─────────────────       ─────────────────         ──────────────     ────────────────        ────────────
User                    ScenarioCard ────┐        SafetyHarm         ExternalIntegration     Persona
UserProfile ───────┐    ProbeQuestion   │         TimeSeries         AgentTool ─────┐         (5 seed)
AvoidanceSession ──┼──> ProbeAnswer      │                            ToolInvocation
RegretScore         │   ModelRun ────────┤
FingerprintSnapshot │   PromptVersion ───┤
                    │   EvaluationResult │
                    │   SchemaMigration  │
                    └────────────────────┘
```

## 2. 테이블별 핵심 필드

### A. 사용자 상태

| 테이블 | 핵심 컬럼 |
|---|---|
| `User` | id(TEXT, device uuid) · created_at · last_seen_at · settings_json |
| `UserProfile` | user_id(FK,unique) · slots_json · completion_percent · forbidden_topics_json · **active_persona_id(FK)** |
| `AvoidanceSession` | user_id · avoidance_input · scenario_card_id(FK) · user_decision · created_at |
| `RegretScore` | avoidance_session_id · intensity(0-10 CHECK) · free_text · recorded_at  (관계 지표) |
| `FingerprintSnapshot` | user_id · embedding_json · stats_json · embedding_model+version |

### B. LLM 운영·평가

| 테이블 | 핵심 컬럼 |
|---|---|
| `ScenarioCard` | avoidance_session_id · card_type · persona_id(FK) · fact · feeling · micro_action · safety_message · model_run_id · prompt_version_id |
| `ProbeQuestion` | text · target_slot · expected_information_gain · enabled · version |
| `ProbeAnswer` | user_id · avoidance_session_id · probe_question_id · answer_text · extracted_slot_updates_json |
| `ModelRun` | model_name · quantization · temperature · top_p · latency_ms · input_tokens · output_tokens · error |
| `PromptVersion` | name+version(unique) · system_prompt · notes |
| `EvaluationResult` | sample_id · model_run_id · scenario_card_id · pass · issues_json · metrics_json |
| `SchemaMigration` | version(unique) · applied_at · checksum(SHA256) |

### C. Safety

| 테이블 | 핵심 컬럼 |
|---|---|
| `SafetyHarmTimeSeries` | user_id · week_start(unique with user) · self_blame_word_count · failure_imagery_ratio · identity_failure_phrases_count · pre_card_tension_self_report |

### D. Agent

| 테이블 | 핵심 컬럼 |
|---|---|
| `ExternalIntegration` | user_id · provider(unique with user) · oauth_token_encrypted(BLOB) · refresh_token_encrypted(BLOB) · scopes · expires_at |
| `AgentTool` | name(unique) · type · enabled · config_json |
| `ToolInvocation` | user_id · avoidance_session_id · persona_id · agent_tool_id · input_json · output_json · latency_ms · error |

### E. Persona

| 테이블 | 핵심 컬럼 |
|---|---|
| `Persona` | name · perspective(CHECK 1st/2nd/3rd) · tone_mode(CHECK Quiet/Sharp/Witty/Savage) · voice_style · greeting · forbidden_topics_json · system_prompt_override · avatar_color · avatar_icon · is_builtin · created_by_user(FK) |

**Partial Unique Index**:
- `idx_persona_builtin_name` ON Persona(name) WHERE created_by_user IS NULL
- `idx_persona_user_name` ON Persona(name, created_by_user) WHERE created_by_user IS NOT NULL

## 3. Foreign Key Cascade 정책

| Relationship | ON DELETE |
|---|---|
| AvoidanceSession.user_id → User | CASCADE |
| RegretScore.avoidance_session_id → AvoidanceSession | CASCADE |
| ScenarioCard.avoidance_session_id → AvoidanceSession | CASCADE |
| ScenarioCard.persona_id → Persona | SET NULL (히스토리 보존) |
| ToolInvocation.user_id → User | CASCADE |
| UserProfile.active_persona_id → Persona | SET NULL |

사용자 삭제(Self-Destruct cascade) 시 모든 child rows 자동 정리, 단 Persona·PromptVersion 같은 공유 리소스는 SET NULL로 보존.

## 4. 5 Default Persona Seed

마이그레이션 001_initial 끝에서 자동 삽입:

| name | perspective | tone | icon | color |
|---|---|---|---|---|
| 내일의 나 | 1st | Sharp | 🌙 | #3B6B9A |
| 1년 후의 나 | 1st | Quiet | 🌅 | #5A7080 |
| 친한 친구 ㅈㅅ | 2nd | Witty | 🤝 | #C4935A |
| 엄격한 코치 | 2nd | Sharp | 🎯 | #3B6B9A |
| 객관 옵저버 | 3rd | Quiet | 👁️ | #5A7080 |

## 5. 사용법

```python
from db import open_db, migrate, list_personas, get_persona

conn = open_db("tomorrow_you.db")       # WAL + foreign_keys ON
applied = migrate(conn)                  # 마이그레이션 적용
print(applied)                           # ['001_initial']

personas = list_personas(conn, builtin_only=True)
morning = get_persona(conn, "내일의 나")
```

## 6. 테스트 커버리지 (tests/test_data_model.py)

13개 테스트 / 13 통과 / 0 실패 / runtime ~1.7s:
- TestMigration (4): 적용·idempotent·17 테이블·SchemaMigration 기록
- TestPersonaSeed (3): 5 builtin seed · perspective 분포 · get_persona
- TestCRUDFlow (6): User+Profile+Persona FK · Session→Card join · RegretScore CHECK · cascade delete · SafetyHarm · ToolInvocation audit

## 7. 다음 스토리 의존

- **G011 PersonaSystem** — 페르소나별 system_prompt_override·voice_style 채우기 + Persona Builder UI에서 안전 audit 후 INSERT
- **G004 HITLProbeEngine** — ProbeQuestion seed 데이터 + ProbeAnswer 작성
- **G010 AgentIntegrations** — ExternalIntegration OAuth + ToolInvocation 로그
- **G006 Pipeline** — 입력 → ProbeAnswer → ScenarioCard → AvoidanceSession 결정 → RegretScore 흐름
- **G007 Regret/Fingerprint** — RegretScore 시계열 + FingerprintSnapshot + SafetyHarmTimeSeries 주기 업데이트
- **G009 EvaluationHarness v3** — Persona 차원 추가 시 ScenarioCard.persona_id 기반 회귀

## 8. v2 확장 후보 (이번 v1 범위 외)

- 임베딩 컬럼 — FingerprintSnapshot.embedding_json을 sqlite-vec 확장으로 native vector column으로
- 전문 검색 — ScenarioCard.fact/feeling/micro_action에 FTS5 인덱스
- 백업 — SQLite VACUUM INTO 자동 일일 백업
