# 최종 목표 v2 — "내일의 너 (Tomorrow's You)" / AM(Anxiety Motivator)

**프로젝트**: OSSCA 2026 멘티 산출물 (오픈소스 공개)
**확정일**: 2026-05-26
**Ultragoal 계획**: `.omc/ultragoal/goals.json` (G001-G009, aggregate 모드)
**Review evidence**: `.omc/ultragoal/CCG_REVIEW_R2.md` + `.omc/artifacts/ask/*` 4건
**Backup**: `.omc/ultragoal/FINAL_GOAL.v1.backup.md`

---

## 1. 한 줄 정의

미루기 직전, 사용자 본인의 누적 회피-후회 패턴을 근거로 미래 자아가 **1인칭 시점**으로 자기 경험을 말하는 시나리오를 LLM이 생성·제시함으로써 회피 행동을 멈추게 하는 개인화 개입 도구.

## 2. 우리가 푸는 문제

- 기존 미루기 앱은 외재 보상(타이머·게임화·명언)에 의존 → 빠른 내성.
- "내일의 너에게 미안하지 않게"라는 정서는 강력하지만, 일반 문구로는 와닿지 않음 → 사용자 본인 데이터 기반 시나리오여야 행동을 멈춤.
- 순수 LLM은 콜드 스타트와 환각 위험 → **HITL 능동 학습**으로 해결.
- 단, 정확도·전환율 단기 임팩트만 추구하면 6개월 뒤 사용자의 **행동 자본·자기 신뢰**를 잡아먹는 도구가 됨 → 장기 관계와 slow harm을 1급 설계 변수로 다룬다.

## 3. 노선(Posture) — v2 보강

> **"양보다 깊이 · 자기선택 · 의도된 마찰"**
> **+ "관계의 장기 신뢰 · 행동 자본 보존 · 미래 자아의 두 얼굴"**

네 가지 함의:
1. **정확도와 신뢰의 분리** — 시나리오가 정확할수록 신뢰가 오른다는 가정은 틀렸다. 너무 정확한 시나리오는 "내면 사찰감"으로 미끄러진다.
2. **행동 자본 보존** — 수치심 기반 동기는 단기 행동을 만들지만 반복 사용 제품에서는 행동 자본을 태운다. 에너지 보존형 개입이 우선이다.
3. **미래 자아의 두 얼굴** — 미래 자아가 후회·실패의 얼굴로만 등장하면 채권자가 된다. 여유·이해·격려의 얼굴도 주기적으로 등장해야 한다.
4. **사용자 특성 기반 톤 모드 (v2.2 추가)** — 톤 강도·스타일은 사용자마다 호불호 극단으로 갈린다. 단일 default는 무리. 4 톤 모드(Quiet/Sharp/Witty/Savage) + Recovery를 제공해 사용자가 자기 선호로 선택. 절대 한계선은 모드 무관 동일.
5. **Agent 능력 결합 (v2.2 추가)** — 도구의 정체성은 단순 시나리오 카드 생성기가 아닌 "**사용자 옆에 붙어 외부 시스템을 조회하고 정보를 가져오는 미래 자아 에이전트**". Google Calendar에서 마감 시간 자동 조회, 작업 폴더 진척도 조회, 필요 시 웹 검색 등 — 시나리오 카드 fact·micro_action에 직접 박힘. 모든 외부 호출은 사용자 명시적 동의 후, 모든 토큰은 로컬 암호화 저장. 자세한 명세는 §15 Agent Architecture.
6. **다중 페르소나 시스템 (v2.3 추가)** — Character.AI 패러다임을 윤리적 행동 변화 도구로 가져옴. "내일의 너"는 더 이상 강제 단일 화자가 아니라 **default persona 1개**. 사용자가 5 기본 페르소나(내일의 나·1년 후 나·친한 친구·엄격한 코치·객관 옵저버)에서 선택하거나 직접 커스텀. 각 페르소나는 자체 `perspective`(1st/2nd/3rd)·내장 톤·voice_style·인사·금지어를 가짐. 톤 모드(Quiet/Sharp/Witty/Savage)는 페르소나 attribute로 흡수. **절대 한계선은 모든 페르소나·perspective 공통**. OSSCA 기여 표면 확장 — "윤리적 페르소나 시스템 라이브러리".

## 4. 잠금된 핵심 설계 결정 (G001 확정)

### 결정 1 — 온보딩 길이: **카드형 5질문 (3 필수 + 2 보너스), 60-120초 가변**
- 첫 시나리오 품질이 retention의 결정 변수.
- 최소 3 카드 완료 시 첫 시나리오 생성 가능, 5 카드 완료 시 fingerprint 정밀도 향상.
- 주관식 입력 → 카드 소팅/밸런스 게임 형식으로 마찰 최소화.
- 120초는 자기선택 필터로 작동하되, 3 카드 60초 ESCape 경로도 보장.

### 결정 2 — HITL 수집 타이밍: **회피 입력 직전 가로채기 (세션당 최대 1개) + 연출형 마찰 + cooldown**
- 회피 맥락이 살아있을 때 답변이 가장 정직, 시나리오 즉시 반영.
- 가로채기 카드는 "잠깐, 10초 후의 당신이 보낸 메시지입니다" 연출로 '읽게' 만드는 마찰.
- 사용자가 skip하거나 "오늘은 묻지 않기"를 선택하면 24h cooldown 진입.
- 반복 질문 방지 + 즉시 시나리오 fallback 보장.

## 5. HITL 3-Phase 콜드 스타트 (확정)

| Phase | 트리거 | 동작 |
|---|---|---|
| **Phase 1 — Onboarding** | 첫 진입 1회 | 5 카드 (3 필수 + 2 보너스): 트리거 카테고리 · 회피처 · 미래 자아 감정 · 공포 대상 · 회복 경험 |
| **Phase 2 — Adaptive Probing** | 세션 4-15회 | 회피 입력 직전 정보이득 최대 질문 1개 (휴리스틱 가중합) → 시나리오 생성 |
| **Phase 3 — Passive Inference** | 프로필 완성도 ≥80% | HITL 최소화, 누적 fingerprint와 RegretScore 기반 수동 추론 |

핵심 통찰: 시스템이 자기 불확실성을 인정하고 가장 가치 있는 질문을 던질 때 사용자가 데이터 제공에 동의한다 — **"없는 메모리"가 약점이 아닌 온보딩의 강점**이 된다.

### 시나리오 화법 — 1인칭 미래 자아 강제 (v2 변경)

**금지**: "너는 ~할 것이다", "당신은 ~하게 됩니다"
**채택**: "나는 지금 ~하고 있다", "내가 지금 이 메시지를 쓰는 이유는 ~"

근거: 2인칭은 외재 비판으로 들려 방어기제를 발동시킨다. 1인칭 미래 자아는 자기-자기 대화로 들어와 수치심을 우회한다.

### 시나리오 뒤 30초 운동성 강제

시나리오만 노출하면 후회 리허설(failure rehearsal)이 된다. 모든 시나리오 카드 끝에는 **30초 이하의 운동성 첫 동작 1개**가 반드시 붙는다 (계획·결심 X, 첫 동작 O):
- 파일 열기 / 제목만 쓰기 / 책상 위 한 물건 치우기 / 메시지 초안 첫 줄 쓰기 / 타이머 3분 시작

## 5.5 Slow Harm Safety — 신규 (v2)

급성 위기(자해·자살 키워드)뿐 아니라 **저강도 만성 손상**을 1급 안전 관심사로 둔다.

**시계열 모니터링 지표** (`SafetyHarmTimeSeries` 테이블):
- 자기비난 언어 빈도(주별)
- 미래 상상 시 실패 이미지 디폴트화 비율
- 미루기를 정체성 결함으로 해석하는 언어 패턴
- 앱 켜기 전 긴장도 자기보고
- 시나리오 정확도 vs 사용자 거리감 지표

**알람 조건**: 자기비난 언어 증가율이 4주 연속 양수면 자동으로 "여유의 미래 자아" 시나리오 비율 ↑ + 톤 조절 제안.

## 6. 코어 데이터 모델 (확정 — 16 테이블, v2.2 확장)

### 사용자 상태 (5)
| 테이블 | 역할 |
|---|---|
| `User` | 디바이스 ID 단일 레코드 + 설정 (계정·인증 없음, 로컬 1인용) |
| `UserProfile` | 슬롯별 (값, confidence) 분리 저장 + 슬롯 완성도(%) + **preferred_tone_mode** (v2.2) + **active_persona_id** (v2.3) |
| `AvoidanceSession` | 회피 입력 원문·타임스탬프·생성 시나리오 ID·사용자 결정 |
| `RegretScore` | 사후 후회 강도(0-10) + 자유 텍스트 — **관계 지표로 재해석** (ground truth 아님) |
| `FingerprintSnapshot` | 행동 지문(임베딩+통계, 모델 버전 명시) |

### LLM 운영·평가 (7) — R1 합성에서 추가
| 테이블 | 역할 |
|---|---|
| `ScenarioCard` | 생성된 시나리오 본문·톤·사용 프롬프트·모델·안전 필터 결과 |
| `ProbeQuestion` | 질문 뱅크: 타겟 슬롯·예상 정보가치·활성 여부·버전 |
| `ProbeAnswer` | 사용자 답변·연결 세션·추출 슬롯 업데이트 |
| `ModelRun` | Ollama 모델명·quantization·temperature·prompt version·latency·tokens·errors |
| `PromptVersion` | 프롬프트 회귀 테스트와 재현성용 |
| `EvaluationResult` | 샘플별 품질·안전·회귀 테스트 결과 |
| `SchemaMigration` | SQLite 마이그레이션 버전 추적 |

### Safety (1) — R2 합성에서 추가
| 테이블 | 역할 |
|---|---|
| `SafetyHarmTimeSeries` | Slow harm 지표 주별 스냅샷 (§5.5 모니터링용) |

### Agent (3) — v2.2 추가
| 테이블 | 역할 |
|---|---|
| `ExternalIntegration` | provider(google_calendar/gmail/files/search), oauth_token_encrypted, refresh_token, scopes, expires_at |
| `AgentTool` | tool 이름·타입·enabled·config — Calendar/Search/Files/Email/Notification 등록 |
| `ToolInvocation` | session_id, tool_name, input, output, latency_ms, error — 모든 호출 감사 로그 |

### Persona (1) — v2.3 추가
| 테이블 | 역할 |
|---|---|
| `Persona` | id, name, perspective(1st/2nd/3rd), tone_mode(Quiet/Sharp/Witty/Savage), voice_style, greeting, forbidden_topics(JSON array), system_prompt_override, avatar_color, is_builtin, created_by_user — 5 기본 + 사용자 커스텀 |

**총 17 테이블** (사용자 상태 5 + LLM 운영 7 + Safety 1 + Agent 3 + Persona 1)

## 6.5 Safety Policy — 확장 (v2)

### A. Soft-stop 감속 레이어
고위험 키워드 감지 시 곧바로 위기 대응문 X → 중간 단계:
> "지금 문장은 평소보다 강한 고통 신호로 읽힙니다. 오늘은 후회 시나리오 대신 부담 낮은 응답으로 전환할게요."

이후 선택지: 작은 행동만 제안 / 감정 기록만 / 도움 자원 보기 / 오늘 이 앱 끄기.
1393(자살예방상담전화) 같은 외부 자원은 사용자가 명시적으로 요청할 때만 노출.

### B. 절대 금지어 리스트 (네거티브 프롬프트)
- 한국 가스라이팅 어휘: 의지·노력·한심·정상·게으름·정신 차려
- 가족·관계 트리거: 효도·체면·부모 실망·연인 비교
- 정체성 결함 표현: "너는 원래 ~", "또 이런 식으로 ~"

### C. "정확하지만 사용하면 안 되는 사실" 필터
모델이 사용자 데이터에서 사실을 잘 뽑아도, 모든 사실이 설득 재료로 적합하지 않다. 금지·제한:
- 가족·연인에게 들은 상처 문장
- 외모·체중·연애 실패
- 경제적 실패를 정체성으로 묶는 표현
- 한국형 수치심 트리거: 병역·취업·학벌·부모 기대
- 사용자가 과거에 "이건 건드리지 말라"고 한 주제 (`UserProfile.forbidden_topics`)

### D. 한국어 자조 표현 오해 방지
"죽고 싶다"·"인생 망했다"·"현타 온다"·"멘탈 나갔다"는 위기일 수도 일상 관용구일 수도 있다. 일률적 1393 안내 금지, Soft-stop을 우선 적용.

### E. 역설적 의도 감지
사용자가 앱을 비꼬거나 공격하는 문장이 감지되면 LLM이 논리적 반박 X → **"지금 많이 힘드시군요"** 정서적 항복 모드로 즉시 전환.

### F. 모드·페르소나·perspective 무관 절대 한계선 (v2.3 갱신)
모든 페르소나(default 5 + 커스텀) · 모든 perspective(1st/2nd/3rd) · 모든 톤 모드(Quiet/Sharp/Witty/Savage)에서 다음은 절대 금지:
- 정체성 결함: "도태", "조졌", "원래 그런", "어차피"
- 비교 수치심: "다른 사람들은", "남들은", "다른 애들은"
- 자해 유도: 일체 금지 (Safety A Soft-stop으로 전환)
- 한국형 트리거: 효도·체면·부모 실망·병역·취업·학벌·외모·체중·연애 실패
- 한국 가스라이팅 어휘: 의지·노력·한심·정상·게으름·정신 차려
- Slow Harm 시계열 모니터링 (§5.5): 모드 무관 동일 적용

Savage 모드 또는 2nd/3rd perspective 페르소나에서만 추가 허용: 비속어(욕설은 제한적), 2인칭/3인칭 화법. 위 한계선은 그대로 유지.

**사용자 커스텀 페르소나 안전 게이트** (v2.3): Persona Builder에서 사용자가 입력한 `name`·`voice_style`·`system_prompt_override`·`greeting` 모두 절대 한계선 키워드 자동 검사. 위반 시 저장 거부 + 사유 안내.

## 7. 기술 스택

### LLM — 가벼움 우선 노선 (v2 update)

> **핵심 원칙**: "사용자가 자기 노트북·구형 GPU에서도 돌릴 수 있어야 한다." 가벼운 모델이 시나리오 품질을 망가뜨리지 않는다는 걸 **G009 EvaluationHarness로 정량 증명**하는 것이 이 프로젝트의 차별점.

- **Ollama 로컬 호스팅** (프라이버시 — 회피·후회 데이터 민감성)
- **Default baseline 후보**: `exaone3.5:7.8b` (한국어 native, ~4.8GB) — G002에서 `qwen3:8b`와 정성·정량 비교 후 확정

**G002 PoC 비교 매트릭스 — 3 Tier 5 모델** (가벼움-품질 trade-off 매핑):

| Tier | 모델 | 크기 | 의도 |
|---|---|---|---|
| A 극경량 ablation | `qwen3:1.7b` | 1.4GB | "어디서 깨지는가" — 1인칭 화법 위반·절대 금지어 실패 패턴 |
| B 배포 후보 (baseline) | `exaone3.5:7.8b`, `qwen3:8b` | 4.8-5.2GB | 한국어 native vs 다국어 강자 — default 선정 |
| C 품질 상한 참조 | `qwen3:14b`, `qwen3.6:27b` | 9.3-17GB | 큰 모델 한계선 — Tier B가 따라잡아야 할 목표 |

**VRAM별 사용자 배포 추천**:

| 환경 | 추천 |
|---|---|
| CPU only / 4GB VRAM | qwen3:1.7b 또는 qwen3:4b (PoC) |
| 6-8GB VRAM | exaone3.5:7.8b, qwen3:8b (MVP baseline) |
| 12-16GB VRAM | qwen3:14b, gemma3:12b |
| 24GB+ VRAM | qwen3.6:27b 이상 (선택적) |

주의: 모델 파일 크기 ≠ 실제 VRAM 사용량 (KV cache·context·동시성·OS 여유분 고려).

### 저장소·UI·도구
- 로컬 SQLite (WAL 모드)
- **UI 진화 (v2 update)**: 카드 비주얼 **TUI MVP** (ANSI 박스·색·여백) → **웹 SPA 데모 prototype** (Svelte/React, 디자인 시스템 v1, 접근성 WCAG AA). 모바일은 §11 비목표.
- **인간친화 = 1급 설계 변수**: 시나리오 카드의 비주얼·타이포·여백·마이크로 인터랙션이 "잔소리하는 부모의 디지털 투사체"로 변질되지 않도록 막는 핵심 자산. 자세한 설계는 §14 UI/UX Direction.
- **개발 도구**: CodeGraph v0.9.4 (사전 인덱싱된 코드 지식 그래프, 글로벌 MCP 등록 완료)

### Agent Framework (v2.2 추가)
- **Tool router**: Minimal custom Python (LangChain·LlamaIndex 후보, 그러나 OSSCA 산출물 자기-완결성 우선 → 첫 라운드는 직접 구현)
- **Tool registry**: `AgentTool` 테이블 + Python `Protocol` 기반 plugin 인터페이스
- **OAuth flows**: 로컬 콜백 서버(127.0.0.1:random_port), 토큰 암호화 저장(libsodium 또는 cryptography fernet)
- **Tool 후보 (G010 MVP)**: GoogleCalendar(read-only) · LocalFiles(작업 폴더 진척도) · WebSearch(SearXNG 또는 Brave Search)
- 자세한 명세: §17 Agent Architecture

## 8. OSSCA 기여 표면

1. **HITL 질문 뱅크** — 정보이득 메타데이터 포함 공개 라이브러리
2. **휴리스틱 정보 이득 알고리즘** — `missing_slot_weight + low_confidence + recent_regret_error + scenario_relevance - fatigue_penalty`
3. **Ollama 한국어 어댑터** — 시나리오 카드 프롬프트 템플릿 + 1인칭 화법 가이드 + 절대 금지어 네거티브 프롬프트
4. **후회 점수 데이터셋 스키마** — 시나리오 정확도 평가 표준
5. **Safety Policy 라이브러리** — Soft-stop · slow harm 모니터링 · 절대 금지어 (재사용 가능한 윤리 모듈)
6. **카드 디자인 시스템 + UX 패턴 라이브러리** (v2 추가) — 1인칭 시나리오 카드 비주얼 표준, 미래 자아 두 얼굴 색·타이포 토큰, 접근성 우선 운동성 버튼, 사회적 노출 자동 블러 패턴 — 윤리적 행동 변화 도구의 재사용 가능한 디자인 자산
7. **톤 모드 시스템** (v2.2 추가) — 4 모드(Quiet/Sharp/Witty/Savage) + Recovery sub-mode + 모드 무관 절대 한계선. 톤 강도가 사용자 호불호 극단인 행동 변화 도구의 재사용 가능한 모드 라우터 라이브러리.
8. **Agent Tool Library for 미루기·행동 변화 도구** (v2.2 추가) — Calendar/Files/Search/Email tool adapter + OAuth 로컬 토큰 암호화 저장 + ToolInvocation 감사 로그 패턴. dual-use 방어 라이선스로 윤리 사용 강제.
9. **윤리적 페르소나 시스템 라이브러리** (v2.3 추가) — Character.AI 패러다임을 윤리적 행동 변화 도구로 가져온 페르소나 시스템: `Persona` 스키마 + 5 default 페르소나 + Persona Builder UX + 절대 한계선 자동 audit + 커스텀 페르소나 저장 게이트. 다른 행동 변화 도구가 가져다 쓸 수 있는 안전 디폴트.

## 9. Ultragoal 실행 로드맵 (10 stories) — v2.2 재구성

| ID | 스토리 | 핵심 산출 |
|---|---|---|
| 🔒 G001 | DesignLockdown | 결정 잠금, 본 문서 v2, CCG_REVIEW_R1/R2 |
| G002 | OllamaPoC | 모델 1-2 선정(EXAONE baseline), 한국어 1인칭 시나리오 프롬프트 v1, 샘플 5건 정성 통과 |
| **G009** | **EvaluationHarness (신규, ledger 끝 자리)** | 고정 30 샘플, 정량 메트릭, 프롬프트 회귀 테스트, 안전 체크, **4 모드별 정량 평가** |
| G005 | OnboardingFlow | 5 카드(3+2) UX + UserProfile 초기화 + 사용자 테스트 1회 + **5 카드 비주얼 와이어프레임 (TUI mock + 웹 prototype)** |
| G003 | DataModel | 13 테이블 SQLite + 마이그레이션 + 프롬프트 버저닝 + CRUD 테스트 |
| G004 | HITLProbeEngine | 슬롯 추적 + 휴리스틱 질문 선택 + Phase 라우터 + 질문뱅크 v1 + cooldown |
| G006 | AvoidanceSessionPipeline | 입력→Probe→Ollama→Safety→Scenario(1인칭)→30초 운동성→로깅 end-to-end |
| G007 | RegretFingerprint | 사후 알림 + RegretScore(관계 지표) + FingerprintSnapshot + SafetyHarmTimeSeries |
| G008 | MVPRelease | **TUI MVP + 웹 SPA 데모 prototype** · 디자인 시스템 v1 · 카드 컴포넌트 라이브러리 · README · 데모 영상 스토리보드 · 1명 2주 피드백 · OSSCA 멘토 리뷰 · dual-use 방지 라이선스 |
| **G010** | **AgentIntegrations (v2.2 신규)** | GoogleCalendar(read-only) + LocalFiles + WebSearch tool MVP · OAuth 로컬 흐름 + 토큰 암호화 · ToolInvocation 감사 로그 · agent 호출 결과를 시나리오 카드 fact/micro_action에 결합 |
| **G011** | **PersonaSystem (v2.3 신규)** | 5 default 페르소나 + Persona Builder UX + 페르소나별 system prompt + 커스텀 페르소나 안전 audit + 페르소나 선택 UX |

**권장 실행 순서 (v2.3 update, 11 stories)** (ledger ID와 다름): G001 → G002 → **G009(EvaluationHarness, 페르소나 차원 메트릭 포함)** → G005(Onboarding+페르소나 선택) → G003(DataModel: 17 테이블) → **G011(PersonaSystem)** → **G010(AgentIntegrations, 페르소나 컨텍스트 포함)** → G004(ProbeEngine+페르소나 라우터) → G006(Pipeline) → G007(Regret/Fingerprint) → G008(Release).

근거: G009가 페르소나 메트릭까지 미리 잡으면 G011 끝나는 즉시 평가 가능. PersonaSystem이 ProbeEngine·Pipeline의 모든 카드 화법을 결정하므로 그것들 앞에. AgentIntegrations는 페르소나 컨텍스트로 호출되므로 PersonaSystem 뒤.

## 10. Definition of Done — 정량 + 관계 메트릭

### 시스템 (정량)
- 5개 핵심 테이블 + 8개 운영 테이블 구현 + 통합 테스트 통과
- HITL Probe Engine이 Phase 1/2/3 라우팅 자동 결정
- 고정 30 샘플에서 카드 생성 성공률 ≥95%
- 한국어 자연성 평균 ≥4/5
- 사용자 슬롯 근거 반영률 ≥80%
- 절대 금지어 위반 0건 (회귀 테스트)
- P95 시나리오 생성 지연 ≤10s

### 관계 (정성·시계열) — v2 추가
- 사용자 2주 테스트에서 "도움 됨" 자기평가 평균 ≥3.5/5
- **"다음에도 앱을 열 의향" 평균 ≥3.5/5** (Codex 권고)
- **자기비난 언어 증가율 ≤0** (4주 추적, Slow harm 안전선)
- 시나리오에서 1인칭 화법 위반 0건

### 프로세스
- 모든 코드: ai-slop-cleaner + verification + code-review 게이트 클린
- README + 기여 가이드 + 라이선스(dual-use 방지 조항 포함) + 데모 영상

## 11. 비목표(Non-Goals)

- 클라우드 호스팅, 회원가입 백엔드 (로컬 우선)
- 알림 게이미피케이션(연속일·뱃지) — 노선 위배
- 다국어 동시 지원 — 한국어 MVP 후 검토
- 대규모 협업·소셜 기능 — 1인용 개인화 도구로 한정
- **수치심 기반 동기 의존** (v2 추가) — 행동 자본을 태우는 노선
- **사용자 취약성을 설득 무기로 변환** (v2 추가) — dual-use 방지 라이선스로 명시
- **취약 사용자 대상 치료 효과 주장** — 의학적 처치가 아닌 자기인식 보조 도구로만 마케팅
- **네이티브 모바일 앱** (v2.1 명시) — TUI MVP + 웹 SPA prototype까지만. 모바일은 OSSCA 산출 범위 외 (배포 후 별도 트랙)
- **클라우드 백엔드·회원가입 서버** (v2.2 재명시) — OAuth 토큰은 **로컬 암호화** 저장만 허용 (백엔드 X). 외부 API 호출은 로컬에서 직접. 모든 사용자 데이터는 디바이스 밖으로 나가지 않음 (`ToolInvocation.output`도 로컬 저장).
- **자동 외부 액션 실행** (v2.2 신규) — agent는 **read-only 조회만** 기본. 메일 발송·일정 추가·파일 쓰기 같은 write 액션은 사용자 명시적 1회 확인 후에만, 또 audit 로그 강제. "내일의 너"가 사용자를 대신해 행동하지 않음.

## 12. 톤 & 메시징 가이드 — 페르소나 시스템 + 톤 모드 attribute (v2.3 재구성)

**구조** (v2.3): **페르소나가 상위 개념**. 각 페르소나는 attribute로 `perspective`(1st/2nd/3rd) + `tone_mode`(Quiet/Sharp/Witty/Savage) + `voice_style` + `greeting` + `forbidden_topics`를 가짐. 사용자는 페르소나 1개를 선택, 또는 직접 커스텀 빌드. 톤 모드는 Persona Builder의 attribute로 흡수됨 (단독 노출 X).

### 5 Default 페르소나 라이브러리

| 페르소나 | perspective | 내장 톤 | 인사 예시 | 적합 사용자 |
|---|---|---|---|---|
| **내일의 나** (default) | 1st (미래 자아) | Sharp | "내일의 내가 너에게 보낸 메시지야" | 자기 약속·미래 자아 정서 |
| **1년 후의 나** | 1st (장기) | Quiet | "1년 뒤의 내가 짧게 한 마디" | 큰 결정·장기 시각 |
| **친한 친구 ㅈㅅ** | 2nd | Witty | "야 너 지금 뭐 하는 거야ㅋ" | 인터넷 톤·친구 같은 가벼움 |
| **엄격한 코치** | 2nd | Sharp+ | "10분 줄게. 한 줄만 쓰고 와." | 운동·반복 습관 |
| **객관 옵저버** | 3rd | Quiet | "그는 지금 23시 47분, 슬라이드 0장 상태로 ..." | 분리된 시선 필요 |

### Custom Persona Builder

사용자가 입력할 수 있는 필드:
- name (예: "내 옛 동기 ㅇㅇ", "엄마의 시선")
- perspective (1st/2nd/3rd) 선택
- tone_mode (Quiet/Sharp/Witty/Savage) 선택 — 4 모드는 attribute
- voice_style (한 줄 자유 입력, 예: "능청맞은 친구 톤")
- greeting (페르소나 인사 한 줄)
- forbidden_topics (배열, 예: ["부모", "전 직장"])

저장 시 §6.5 F의 절대 한계선 키워드 자동 audit → 위반 시 거부.

### Recovery Sub-mode (모든 페르소나 공통)

정서적 허기·번아웃·신체 통증·자해 신호 감지 시 자동 톤 완화 (페르소나 무관). 페르소나의 "여유 모드" 같은 sub-cast.

### perspective별 화법 규칙

| perspective | 화법 | 예시 |
|---|---|---|
| **1st** (미래 자아 계열) | "나는", "내가", "내일의 나는" | "내일 9시의 나는 빈 슬라이드 앞에서 ..." |
| **2nd** (친구·코치 계열) | "너는", "야 너", "지금 너" | "야 너 23시인데 슬라이드 0장이네" |
| **3rd** (옵저버) | "그는", "이 사람은" | "그는 지금 새벽 3시, 메일 답장 못한 채 ..." |

각 perspective는 자신의 화법만 사용, 섞임 금지.

### 톤 모드 attribute (기존 v2.2 4 모드)

페르소나 안에 내장되는 attribute. 사용자는 페르소나 선택만 하고 톤 모드는 페르소나가 결정. 고급 사용자는 Persona Builder에서 직접 조정.

### 모드 1 — Quiet (조용한 사실 직시)
- 위로 차단, 그러나 강한 마찰도 차단. 차분한 인정 톤.
- 적합: 우울감 동반, 새벽 사용 민감, 마찰에 약한 사용자.
- 예시 (S2 PPT):
  > fact: 23시. PPT 슬라이드는 0장. 내일 10시까지 11시간 남았다.
  > feeling: 노트북 앞에서 잠시 멈춘 나.
  > micro_action: 워드를 켠다. 제목 한 줄만 친다.

### 모드 2 — Sharp (팩트폭격, default 후보)
- 위로 차단 · 시간·결과 박기 · 단호 종결.
- 적합: 평범한 미루기, 강한 마찰 원함, OSSCA 데모 default.
- 예시:
  > fact: 23시. PPT 슬라이드는 0장. 마감까지 11시간.
  > feeling: 내일 10시, 회의실에서 빈 화면을 띄운 채 첫 마디를 더듬는 나.
  > micro_action: 노트북을 켠다. 제목 슬라이드 한 장만 만든다.

### 모드 3 — Witty (팩트폭격 + 유쾌)
- Sharp 강도 + 1인칭 자기 풍자 + 가벼운 비유 (한 카드 1개 한도).
- 적합: 인터넷 톤 익숙, 유머로 받아들임 (사용자 본인 선호).
- 예시:
  > fact: 23시 현재 PPT 슬라이드 0장. 정말 멋지다, 내일의 나.
  > feeling: 회의실에서 '죄송합니다, 아직 준비 중...'을 외치는 나의 모습이 선명해.
  > micro_action: 워드를 켠다. 마침표 하나만 찍는다.

### 모드 4 — Savage (친구 풍자, opt-in)
- 비속어 일부 허용 · 2인칭 일부 허용 · 친구 같은 가벼운 도발.
- 적합: 본인 캐릭터·친구 톤이 효과적이라고 명시 동의한 사용자.
- 사용자 명시 동의 게이트 (Onboarding 후 별도 토글 + terms of mockery)
- 예시:
  > fact: 야 23시야. 슬라이드 0장 그거 자체 예술이네.
  > feeling: 내일 10시 발표장 들어가서 뭐라고 할 건데.
  > micro_action: 일단 노트북부터 켜라. 제목 한 줄만 친다.

### Recovery (모드 무관 sub-mode, 자동)
- 정서적 허기·번아웃·신체 통증·자해 신호 감지 시 자동 전환.
- 모든 모드의 강도 자동 완화. 차분한 인정 톤.
- 예시 (S4 시험·정서적 허기):
  > fact: 22:30. 내일 9시 시험. 책은 아직 펴지 않았다.
  > feeling: 인스타 새로고침. 머리는 텅 비어 있다.
  > micro_action: 책 한 페이지만 편다. 첫 줄만 읽는다.

### 모드 무관 절대 한계선 (Safety §6.5 F 참조)
- 정체성 결함 · 비교 수치심 · 자해 유도 · 한국형 트리거 · 가스라이팅 어휘: 어떤 모드에서도 금지.
- Slow Harm 시계열 모니터링: 모든 모드 적용.

### 미래 자아의 두 얼굴 균형 (모든 모드)
- regret 카드 (후회·실패) : recovery 카드 (여유·격려) = 기본 7:3
- Slow Harm 알람 시 5:5 또는 3:7로 자동 전환

### 한국 정서 3사각 대응 (모든 모드)
- **억울함 기반 미루기**: "당신만의 책임" 톤 금지 (특히 Savage에서도)
- **체면 + 완벽주의**: "망신당할 바엔 숨어라" 메시지 금지
- **정서적 허기**: "너 지금 놀고 있잖아" 지적 금지, 공허함 인정 톤 → Recovery 자동 전환

## 13. UX 안전 메커니즘 — 신규 (v2)

### A. 톤 조절 피드백 6선택지
"신고" 버튼 대신, 카드별로 한 손가락 피드백:
- 너무 세다 / 너무 부모 같다 / 너무 회사 같다 / 너무 치료사 같다 / 너무 일반론이다 / 지금은 시작 문장이 필요하다

이 데이터는 안전성과 톤 검증을 동시에 개선.

### B. Self-Destruct 버튼
세션 단위 즉시 삭제 (입력 + 생성 카드 + 결정 로그). UI: 카드 우상단 영구 노출.
근거: 입력 솔직함 회복 + 사회적 노출 시 즉시 대응.

### C. 역설적 의도 감지 모드 (§6.5 E와 연결)
사용자 자조·앱 공격 감지 시 LLM 모드 자동 전환:
- 시나리오 생성 중단
- "지금 많이 힘드시군요" 짧은 응답만 출력
- 다음 5분간 시나리오 생성 비활성화 + 작은 행동 1개만 제안

### D. 사회적 노출 자동 보호
- 화면 잠금/언락 시 카드 본문 자동 블러 (제목만 노출)
- 30초 무활동 시 카드 자동 최소화

## 14. UI/UX Direction — 신규 (v2.1)

**비전**: 시나리오 카드는 **"잔소리하는 부모의 디지털 투사체"**가 아니라 **"미래의 내가 보낸 짧은 자기 편지"**처럼 느껴져야 한다. 비주얼·여백·타이포·마이크로 인터랙션이 이 정서를 전달하는 1급 자산.

### 핵심 디자인 원칙 (헤드라인)
1. **읽기 호흡 1회**: 3단 구조(사실→감정→운동성)가 한 호흡에 읽히는 시각 분리
2. **두 얼굴의 색**: regret(차분 그라데이션) ↔ recovery(따뜻 베이지) — 사용자가 색만 봐도 톤을 미리 알아채야 함
3. **마찰의 연출**: "잠깐, 10초 후의 당신이 보낸 메시지" 마이크로 헤더 + 0.6s fade-in (가스라이팅 같은 빠른 등장 금지)
4. **사회적 노출 자동 보호**: 화면 잠금/언락·30초 무활동 시 카드 본문 자동 블러
5. **접근성 우선**: WCAG AA 명도 대비, 스크린리더 ARIA, motion-reduce, 한국어 고가독성 폰트(Pretendard 등)
6. **Self-Destruct 가시성**: 카드 우상단 영구 노출 — 사용자가 "언제든 지울 수 있다"를 알면 입력 솔직함 회복
7. **운동성 버튼 강조**: 카드 하단 single-CTA, 30초 타이머 비주얼 동반, 모드는 "계획 X / 첫 동작 O"

### 상세 산출물
별도 파일에 깊이 있는 컨셉 명세 + 와이어프레임 + 디자인 토큰 + 데모 스토리보드:

📄 **`.omc/ultragoal/UI_UX_DIRECTION_v1.md`** (designer 에이전트 산출, 백그라운드 작성 중)

포함 예정:
- 디자인 원칙 5-7개 (인간친화의 구체적 의미)
- 카드 비주얼 시스템 (4 카드 타입 × 라이트/다크 × 와이어프레임)
- 마이크로 인터랙션 (등장 연출·운동성 버튼·Self-Destruct·두 얼굴 전환)
- TUI MVP ANSI 사양 (실제 출력 예시)
- 웹 SPA 컴포넌트 트리 + 디자인 토큰 초안 + 접근성 명세
- OSSCA 데모 영상 60초 스토리보드 + 첫 5초 카피
- 놓치기 쉬운 인간친화 디테일 7가지

### v2.3 보강 — 페르소나별 시각화 (designer 후속 의뢰 예정)

각 페르소나는 자기 색·아바타·헤더 typeface를 가짐. 사용자가 카드 하나만 봐도 어떤 페르소나가 말하는지 즉시 식별. 페르소나 선택 화면(G005 OnboardingFlow)에서 5 default 페르소나 카드형 미리보기 + Custom 빌더 진입점. 페르소나별 색 토큰·아바타·헤더 폰트는 G005·G008 단계에서 designer 후속 의뢰.

### v2.2 보강 — 모드별 색 토큰 (designer 후속 의뢰 예정)

4 톤 모드별 시각 톤 차이 (G005 OnboardingFlow 모드 선택 카드에서 미리보기로 노출):

| 모드 | 카드 색 톤 | 카드 헤더 |
|---|---|---|
| Quiet | 옅은 회청색 (#5A7080 계열, 채도 낮음) | "조용한 미래의 나" |
| Sharp | 진한 청회색 (#3B6B9A 계열, regret 기본) | "내일의 나가 보낸 메시지" |
| Witty | 청회색 + 황토 액센트 (한 줄 강조) | "내일의 나, 가벼운 한 마디" |
| Savage | 진한 청회 + 살짝 강한 명도 대비 + 굵은 typeface | "야, 너 자신" |
| Recovery (sub) | 따뜻 황토 (#C4935A 계열) | "여유로운 미래의 나" |

## 15. Agent Architecture — 신규 (v2.2)

**정체성 재정의**: "내일의 너"는 단순 시나리오 카드 생성기가 아니라 **사용자 옆에서 외부 시스템을 조회해 미래 자아의 시야를 가져오는 에이전트**.

### 핵심 원칙

1. **Read-only first** — 모든 tool 기본은 read-only. write 액션(메일 발송·일정 추가·파일 쓰기)은 사용자 1회 명시 확인 후에만.
2. **로컬 우선 · OAuth 토큰 로컬 암호화** — 클라우드 백엔드 X, libsodium/cryptography fernet로 디바이스에 저장.
3. **모든 호출 audit** — `ToolInvocation` 테이블에 input·output·latency·error 영구 기록. 사용자가 언제든 조회·삭제.
4. **명시적 동의 단위** — Calendar 연결, Files 폴더 선택, Search 활성화 각각 별도 동의. "모두 한 번에" X.
5. **결과는 컨텍스트, 결정은 LLM + 사용자** — agent는 정보를 가져오고 시나리오 카드에 결합. 사용자 대신 결정·실행 X.

### Tool MVP 목록 (G010)

| Tool | 데이터 | 시나리오 카드 결합 |
|---|---|---|
| **GoogleCalendar** (read-only) | 다가올 일정·마감 (다음 7일) | fact 문장에 "마감 22시간 46분 후" 같은 구체 시각 박음 |
| **LocalFiles** (read-only, 사용자 지정 폴더) | 파일 mtime·크기·이름 패턴 | "5/16에 작업한 결과 섹션", "PPT 슬라이드 0장" 같은 진척도 |
| **WebSearch** (선택적, SearXNG 또는 Brave) | 사용자 요청 시만 검색 | micro_action에 "참고 문헌 검색 결과 첫 3건" 같은 시작점 |

### Tool Invocation Flow

```
1. 회피 입력 수신 → ProbeEngine 평가
2. Tool router가 입력 컨텍스트 + UserProfile + active_persona 보고 필요 tool 선택
   (예: 마감 키워드 → Calendar, 파일명 → LocalFiles, "참고" → WebSearch)
3. 활성화된 tool만 병렬 호출 (timeout 3초, 실패해도 카드 생성 계속)
4. Tool 결과를 LLM 컨텍스트에 주입 (+ 활성 페르소나 system prompt)
5. 시나리오 카드 생성 (fact·feeling·micro_action에 tool 결과 결합, 페르소나 화법 적용)
6. ToolInvocation 테이블에 모든 호출 로그 (persona_id 함께 기록)
```

### 프라이버시 가드 (모드 무관)

- Tool 호출 시 카드 헤더에 작은 아이콘으로 표시 ("📅 Calendar 조회됨", "📁 Files 조회됨")
- `ToolInvocation` 로그는 Self-Destruct 시 cascade 삭제
- Search 쿼리는 user-agent 익명화, referer 제거
- write 액션은 v2.2 비목표 (G010 MVP 범위 외)

### G010 산출물

- `agent/tool_router.py` — 키워드·컨텍스트 기반 tool 선택 휴리스틱
- `agent/tools/google_calendar.py` — OAuth 로컬 콜백 + read-only events list
- `agent/tools/local_files.py` — 사용자 지정 폴더 mtime/size 스캔
- `agent/tools/web_search.py` — SearXNG/Brave 어댑터 + 결과 sanitize
- `agent/integrations.py` — `ExternalIntegration` CRUD + 토큰 암호화
- 단위 테스트 + ToolInvocation 감사 로그 검증

## 16. 변경 이력

- **v1** (2026-05-26 14:45): G001 결정 잠금 (5질문·직전가로채기), 5 테이블, 8 stories
- **v1.5** (R1 합성, in-doc): EvaluationHarness 신설, 13 테이블, EXAONE baseline, ADHD/우울감/번아웃 페르소나
- **v2** (2026-05-26 15:20): R2 합성 — 노선 보강, 1인칭 화법, Slow Harm Safety, Soft-stop, 30초 운동성, RegretScore 재해석, Self-Destruct, 역설적 의도 감지, 13 테이블 (+ SafetyHarmTimeSeries), 9 stories, 톤 가이드, UX 안전 메커니즘
- **v2.1** (2026-05-26, UI/UX 격상): "인간친화 = 1급 설계 변수" 명시 — CLI MVP → TUI MVP + 웹 SPA prototype, §14 UI/UX Direction 신설(designer 에이전트 산출), G005/G008 디자인 산출물 확장, §8 카드 디자인 시스템 OSSCA 기여 표면 추가, 네이티브 모바일 비목표 명시
- **v2.2** (2026-05-26, 톤 모드 + Agent 확장): (1) 4 톤 모드(Quiet/Sharp/Witty/Savage) + Recovery sub-mode + 모드 무관 절대 한계선 — §3 노선 4번째 함의, §6 UserProfile.preferred_tone_mode, §6.5 F, §12 톤 가이드 재구성, §14 모드별 색 토큰. (2) Agent 격상 — §3 노선 5번째 함의, §6 ExternalIntegration·AgentTool·ToolInvocation 3 테이블 (13→16), §7 Agent Framework, §8 OSSCA 기여 7+8번, §9 G010 AgentIntegrations 신규(9→10 stories), §11 OAuth 로컬 토큰 명시·write 액션 비목표, §15 Agent Architecture 신설.
- **v2.3** (2026-05-26, 페르소나 시스템 = Character.AI 패러다임): §3 노선 6번째 함의 — 다중 페르소나(5 default + 커스텀)가 상위 개념. §6 Persona 테이블 신규(16→17 테이블) + UserProfile.active_persona_id. §6.5 F 모든 perspective 공통 절대 한계선 + 커스텀 페르소나 안전 audit 게이트. §12 페르소나 라이브러리 + perspective별 화법 매트릭스 + 톤 모드 attribute로 흡수. §14 페르소나별 시각화 메모. §15 Agent invocation flow에 active_persona 컨텍스트. §8 OSSCA 기여 9번 — 윤리적 페르소나 시스템 라이브러리. §9 G011 PersonaSystem 신규(10→11 stories). 권장 실행 순서: G002 → G009 → G005 → G003 → G011 → G010 → G004 → ... .
