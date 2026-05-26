# Ultragoal Brief — "내일의 너" (Tomorrow's You) / AM(Anxiety Motivator)

## Mission

OSSCA 2026 멘티 프로젝트로, Ollama 기반 로컬 LLM을 활용한 **개인화 미루기 개입 도구**를 만들어 오픈소스로 공개한다.
사용자가 회피 행동을 하려는 순간, 그 사용자만의 과거 회피-후회 패턴을 근거로 미래 자아의 후회 시나리오를 2인칭으로 생성해 보여줌으로써 행동 전환을 유도한다.

## Problem We Solve

1. 기존 미루기 앱은 외재적 보상(타이머·게임화·명언)에 의존해 곧 내성이 생긴다.
2. "내일의 너에게 미안하지 않게"라는 정서는 강력하지만, 일반 문구로는 와닿지 않는다 — 사용자 본인 데이터로 구성된 시나리오여야 한다.
3. 순수 LLM은 콜드 스타트(개인 데이터 0)와 환각(없는 후회 지어내기) 위험이 크다 — HITL 능동 학습으로 해결한다.

## Solution Mechanism — HITL 3-Phase Cold Start

- **Phase 1 (Onboarding, 첫 60초)**: 두려움 앵커·미루기 유형·회복 패턴 기초 슬롯을 채우는 마이크로 인터뷰. "데이터 수집"이 아닌 "저를 길들이는 시간"으로 리프레이밍해 마찰 최소화.
- **Phase 2 (Adaptive Probing, 4-15세션)**: 회피 입력 가로채기 → 정보 이득 최대 질문 1개 → 시나리오 생성. 세션당 1개 질문 캡으로 피로 누적 방지.
- **Phase 3 (Passive Inference, 프로필 80%+)**: HITL 최소화, 누적 fingerprint 기반 수동 추론. 후회 점수 같은 비강제 신호만 수집.

핵심 통찰: 시스템이 자기 불확실성을 인정하고 가장 가치 있는 질문을 던질 때, 사용자는 개인화 깊이를 체감하고 데이터 제공에 동의한다 — "없는 메모리"가 약점이 아닌 온보딩의 강점이 된다.

## Core Data Model (5 Tables — Confirmed)

- **User**: 계정·인증·디바이스 식별
- **UserProfile**: 두려움 유형, 미루기 트리거 카테고리, 회복 전략, 슬롯 완성도(%)
- **AvoidanceSession**: 회피 입력 원문, 타임스탬프, 생성된 시나리오 ID, 사용자 선택(전환/지속/신고)
- **RegretScore**: 사후 회고 시점 후회 강도(0-10) + 자유 텍스트 — 시나리오 정확도 ground truth
- **FingerprintSnapshot**: 주기적 갱신되는 행동 지문(임베딩+통계) — 시나리오 생성 컨텍스트

## Tech Stack

- **LLM 호스팅**: Ollama (프라이버시 — 회피·후회 데이터는 민감)
- **모델 후보**: 한국어 지원 + 7-13B 범위 (개인 GPU 가용성)
- **저장소**: 로컬 SQLite 또는 단일 파일 JSON
- **UI**: TBD (CLI MVP → 웹/모바일)

## Development Tooling

- **CodeGraph** (https://github.com/colbymchenry/codegraph): 사전 인덱싱된 코드 지식 그래프(tree-sitter AST + SQLite + FTS5 + call graph)로 Claude Code의 파일 스캔을 대체. 토큰 57%·도구 호출 71% 절감 기대. G003(DataModel) 이후 모든 구현 스토리에서 활용.
  - 설치: `npm i -g @colbymchenry/codegraph`
  - 초기화: 프로젝트 루트에서 `codegraph init -i` → Claude Code 자동 구성
  - Auto-sync 활성화로 코드 변경 시 인덱스 자동 갱신
  - `.codegraph/` 디렉토리는 git ignore 처리

## OSSCA Contribution Surfaces

1. HITL 질문 뱅크 큐레이션 (공개 라이브러리)
2. 정보 이득 알고리즘 (메타데이터-주도형 슬롯 선택)
3. Ollama 한국어 어댑터 프롬프트 템플릿
4. 시나리오 정확도 평가용 후회 점수 데이터셋 스키마

## Locked Design Decisions (G001 — 2026-05-26)

### v1 결정
1. **온보딩 길이 = 5질문 ~120초** (v2에서 카드형 3 필수 + 2 보너스로 진화)
2. **HITL 수집 타이밍 = 회피 입력 직전 가로채기 (세션당 최대 1개)** (v2에서 cooldown + 연출형 마찰 추가)

### v2 노선 보강 (CCG_REVIEW_R1/R2 흡수)
> "양보다 깊이 · 자기선택 · 의도된 마찰"
> + **"관계의 장기 신뢰 · 행동 자본 보존 · 미래 자아의 두 얼굴"**

### v2 핵심 변경
- 시나리오 화법: 2인칭 → **1인칭 미래 자아 강제** ("나는 지금 ~")
- Safety: crisis-only → **Slow Harm 시계열 모니터링** 추가
- Soft-stop 감속 레이어 (1393 즉시 호출 금지)
- 절대 금지어 리스트 + "정확하지만 안 쓸 사실" 필터
- 시나리오 뒤 **30초 운동성 강제** (failure rehearsal 방지)
- 데이터 모델 5 → **13 테이블** (운영·평가·Safety 8개 추가)
- 로드맵 8 → **9 stories** (G002.5 EvaluationHarness 신설)
- DoD에 "다음에도 앱을 열 의향" + "자기비난 언어 증가율 ≤0" 추가
- UX 안전: 톤 조절 6선·Self-Destruct·역설적 의도 감지·사회적 노출 자동 보호

### v2.1 (UI/UX 격상)
- "인간친화 = 1급 설계 변수" 명시, CLI MVP → TUI MVP + 웹 SPA prototype
- §14 UI/UX Direction 신설 (designer 에이전트 산출: UI_UX_DIRECTION_v1.md)

### v2.2 (4 톤 모드 + Agent 격상)
- 4 톤 모드: Quiet/Sharp/Witty/Savage + Recovery sub-mode (모드 무관 절대 한계선)
- Agent 격상: GoogleCalendar(read-only) + LocalFiles + WebSearch + OAuth 로컬 토큰 암호화
- 16 테이블 (Persona·ExternalIntegration·AgentTool·ToolInvocation 추가)
- G010 AgentIntegrations 신설 (9→10 stories)
- §15 Agent Architecture 신설

### v2.3 (페르소나 시스템 = Character.AI 패러다임)
- 다중 페르소나가 상위 개념 — 5 default(내일의 나/1년 후 나/친한 친구/엄격한 코치/객관 옵저버) + Custom Builder
- 톤 모드 4개는 페르소나 attribute로 흡수
- 17 테이블 (Persona 테이블 추가)
- G011 PersonaSystem 신설 (10→11 stories)
- 권장 실행 순서: G009 → G005 → G003 → G011 → G010 → G004 → ...

## Definition of Done (Ultragoal Level)

- 5개 코어 테이블이 구현되고 통합 테스트 통과
- HITL Probe Engine이 Phase 1/2/3 라우팅을 자동 결정
- Ollama로 한국어 시나리오 카드가 일관된 톤으로 생성됨 (정확도 평가 통과)
- 최소 1명의 실제 사용자가 2주간 사용한 사용성 피드백 수집
- README + 기여 가이드 + 라이선스 + 데모 영상으로 OSSCA 멘토 리뷰 통과
- ai-slop-cleaner + verification + code-review 모든 게이트 클린
