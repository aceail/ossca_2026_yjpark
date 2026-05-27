# Contributing to 내일의 너 (Tomorrow's You)

OSSCA 2026 멘티 산출물입니다. 외부 기여를 환영하되, **윤리 라이선스(Ethical Use Restriction)** 조건을 반드시 확인해 주세요.

## 시작하기

1. Fork → `git clone` → `cd ossca_2026_yjpark`
2. `cp .env.example .env` + `cp frontend/.env.example frontend/.env.local`
3. 의존성:
   ```bash
   pip install --user fastapi uvicorn pydantic cryptography
   cd frontend && npm install && cd ..
   ```
4. DB + 5 페르소나 seed:
   ```bash
   python3 -c "from db import open_db, migrate; migrate(open_db('tomorrow_you.db'))"
   ```
5. 테스트:
   ```bash
   python3 -m unittest discover tests
   cd frontend && npm run build
   ```

## 기여 영역

### 환영
1. **HITL 질문 뱅크 확장** (`db/migrations/00X_*.sql`, `probe/`)
2. **페르소나 라이브러리 확장** (`persona/builder.py` `BUILTIN_PERSONAS`)
3. **EvaluationHarness 차원 추가** (`scripts/eval_harness.py`)
4. **한국어 시나리오 프롬프트 v3+** (`scenario_prompt_v3.md`)
5. **Slow Harm 시계열 알람 강화** (`regret/slow_harm.py`)
6. **UI 컴포넌트** (`frontend/components/`)
7. **Agent tool adapter** — 실제 OAuth 플로우 (`agent/tools/`)

### 신중 (윤리 라이선스 검토 필수)
- 새 카드 모드·새 페르소나 — 절대 한계선(`persona/builder.py::FORBIDDEN_GROUPS`) 준수
- Probe 질문 추가 — sensitive 키워드 자동 audit 가이드 따르기
- 알림·게이미피케이션 — `streak`·`badge`·`confetti` 절대 X (FINAL_GOAL.md §11)

### 거절
- 사용자 취약성을 설득 무기로 변환하는 기여
- 클라우드 백엔드/회원가입 서버 추가
- 자동 외부 액션 (write 액션)
- 수치심 기반 동기 메커니즘

## 코드 스타일

- **Python**: 3.10+, type hints, snake_case, immutable 우선
- **TypeScript**: Next.js 16 App Router, 함수형 컴포넌트, 명시적 type
- **CSS**: Tailwind v4 `@theme`, 디자인 토큰만 사용, 빨간 경고 UI X
- **한국어 주석/메시지**: 일반 사용자 노출 텍스트
- **불필요한 주석 금지** — 코드로 의도 표현

## 테스트

- 새 모듈은 `tests/test_<module>.py` 필수
- 회귀 임계 — `python3 -m unittest discover tests` 모두 통과
- 절대 한계선 회귀 — `tests/test_release_artifacts.py` + `tests/test_persona_system.py` 절대 깨면 안 됨
- frontend — `cd frontend && npm run build` (typecheck 포함)

## Commit 메시지 (Conventional Commits)

```
<type>(<scope>): <description>

type: feat | fix | docs | style | refactor | perf | test | build | ci | chore | revert
scope: persona | probe | pipeline | regret | agent | backend | frontend | ultragoal | ...
```

예시:
- `feat(persona): add 6th default '큰누나' persona`
- `fix(pipeline): handle Ollama timeout gracefully`

## PR 가이드

1. issue 먼저 (큰 변경)
2. 윤리 라이선스 영향 명시 (있다면)
3. 테스트 추가 + 통과 캡처
4. 한국어 README/문서 영향 시 함께 업데이트
5. 디자인 변경 — `UI_UX_DIRECTION_v1.md` 원칙 준수

## 보안 취약성

`SECURITY.md` 참조.

## 라이선스

MIT + Ethical Use Restriction. `LICENSE` 전문 필수 확인.

## 멘토·메인테이너

- yjpark (claude@jlkgroup.com) — OSSCA 2026 멘티
