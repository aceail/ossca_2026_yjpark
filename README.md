# 내일의 너 (Tomorrow's You)

> 미루기 직전, 미래 자아가 1인칭 시점으로 말하는 시나리오를 LLM이 생성해 행동을 멈추게 하는 **개인화 윤리적 행동 변화 도구**.
> OSSCA 2026 멘티 산출물 · Ollama 로컬 LLM · 17 테이블 SQLite · 5 페르소나 · 4 톤 모드 · Slow Harm 안전 시계열 · Agent 통합.

```
오늘도 미뤘다.
내일의 너는 알고 있다.
```

---

## 핵심 차별점

- **다중 페르소나 (Character.AI 패러다임)** — 5 default + Custom Builder. 각 페르소나는 자체 `perspective`(1st/2nd/3rd) + 톤(Quiet/Sharp/Witty/Savage) + 절대 한계선.
- **팩트폭격 + 유쾌 톤** — 위로 X 비난 X. 시간·결과를 직시하되 1인칭 자기 풍자로 가벼움 유지.
- **로컬 우선** — Ollama로 모든 LLM 호출이 디바이스 안. OAuth 토큰도 로컬 암호화. 클라우드 백엔드 없음.
- **Slow Harm 안전 시계열** — 급성 위기뿐 아니라 저강도 만성 손상(자기 비난 누적·정체성 결함 표현·실패 이미지 디폴트화) 주별 추적.
- **윤리 디자인** — "잔소리하는 부모의 디지털 투사체"가 되지 않도록 16개 메커니즘 (Self-Destruct 즉시 삭제·Soft-stop 감속·역설적 의도 감지·사회적 노출 자동 블러).
- **TUI MVP + 웹 SPA prototype** — 카드 비주얼이 1급 자산.

## Quickstart

```bash
# 1. Ollama 서버 + 모델 준비
ollama serve &
ollama pull exaone3.5:7.8b

# 2. DB 마이그레이션
python3 -c "from db import open_db, migrate; migrate(open_db('tomorrow_you.db'))"

# 3. CLI MVP 실행
python3 scripts/cli.py

# (옵션) 웹 prototype 보기
python3 -m http.server -d web 8000
```

## 첫 사용 흐름

1. **Onboarding** — 카드형 5질문(3 필수 + 2 보너스). 60초 또는 120초 ESCape. 페르소나 선택 카드에서 5 default 중 1 또는 Custom Builder.
2. **회피 입력** — "내일 발표인데 슬라이드 0장. 새벽 1시야."
3. **Probe (선택)** — Phase 2이면 정보이득 최대 1개 질문 (skip 가능, 24h cooldown).
4. **시나리오 카드 생성** — 페르소나별 화법으로 fact + feeling + 30초 micro_action.
5. **결정** — [t]시작 / [c]계속 / [r]리포트 / [d]삭제 (Self-Destruct).
6. **사후 회고** — 24h 후 RegretScore + 카드 정확도 + 다음 사용 의향.

## 프로젝트 구조

```
.
├── db/                    # 17 테이블 SQLite + 마이그레이션 시스템 (G003)
│   ├── schema.py
│   └── migrations/
│       ├── 001_initial.sql            # 17 테이블 + 5 페르소나 seed
│       ├── 002_seed_probe_questions.sql
│       ├── 003_pipeline_session_indexes.sql
│       └── 004_seed_agent_tools.sql
├── persona/               # 5 default + Builder 안전 audit (G011)
├── probe/                 # HITL Phase 1/2/3 + 휴리스틱 (G004)
├── pipeline/              # SessionOrchestrator (G006)
├── ui/                    # TUI 카드 렌더링
├── regret/                # RegretScore + Fingerprint + Slow Harm + 정확도 (G007)
├── agent/                 # Calendar/Files/Search tool 통합 (G010)
├── scripts/               # CLI + 평가 파이프라인 + 시뮬레이터
├── web/                   # 웹 SPA prototype + 디자인 토큰 v1
├── tests/                 # unittest (130+)
└── .omc/ultragoal/        # v2.3 설계 문서 (17+ 산출물)
```

## OSSCA 기여 표면 (재사용 가능 라이브러리)

1. HITL 질문 뱅크 + 휴리스틱 정보 이득 알고리즘
2. Ollama 한국어 시나리오 카드 프롬프트 (v2 팩트폭격 + 유쾌)
3. 후회 점수 데이터셋 스키마 + Slow Harm 시계열 패턴
4. 카드 디자인 시스템 + 5 페르소나 시각 토큰
5. 톤 모드 시스템 (Quiet/Sharp/Witty/Savage + Recovery)
6. Agent Tool Library (Calendar/Files/Search + OAuth 로컬 암호화)
7. 윤리적 페르소나 시스템 + 안전 audit 게이트

## 윤리 가이드라인

MIT + **dual-use 제한**: 사용자 취약성을 설득 무기로 변환하는 파생 금지. 자세한 조건은 `LICENSE` 참조.

비목표 (명시):
- 클라우드 백엔드 · 회원가입 서버
- 네이티브 모바일 (TUI + 웹 prototype까지만)
- 자동 외부 액션 (read-only first)
- 게이미피케이션 (streak·뱃지·confetti)
- 수치심 기반 동기 의존

## 테스트

```bash
python3 -m unittest discover tests -v
```

130+ unittest (data model · persona · probe · pipeline · tui · agent · regret · eval harness · release artifacts).

## 설계 문서

`.omc/ultragoal/` 폴더:
- `FINAL_GOAL.md` — 17 섹션 마스터 명세 (v2.3)
- `UI_UX_DIRECTION_v1.md` — 788줄 디자인 가이드
- `CCG_REVIEW_R2.md` — 블라인드스팟 리뷰 합성
- `PERSONA_SYSTEM_v1.md` · `PIPELINE_v1.md` · `EVAL_HARNESS_DESIGN_v1.md` · `REGRET_FINGERPRINT_v1.md` · `AGENT_INTEGRATIONS_v1.md` · `DATA_MODEL_v1.md` · `ONBOARDING_FLOW_v1.md`

## 라이선스

MIT + Ethical Use Restriction. `LICENSE`.

## 만든 사람

OSSCA 2026 멘티 — Yeonjae Park (claude@jlkgroup.com)
