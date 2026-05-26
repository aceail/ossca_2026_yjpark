# codex advisor artifact

- Provider: codex
- Exit code: 0
- Created at: 2026-05-26T05:52:54.604Z

## Original task

당신은 시니어 백엔드/시스템 아키텍트입니다. 아래는 OSSCA 2026 멘티 산출물로 만들 "내일의 너(Tomorrow's You)" 프로젝트의 최종 목표 문서입니다. Ollama 로컬 LLM 기반 미루기 개입 도구이며, 회피 직전 LLM이 개인화된 미래 후회 시나리오를 생성해 보여줍니다.

이 문서를 **아키텍처·정확성·기술 리스크·구현 가능성** 관점에서 비평해 주세요. 특히 다음을 평가:

1. HITL 3-Phase 콜드스타트 + 5질문 온보딩 + 직전 가로채기 조합의 **기술적 타당성** (Probe Engine 구현 복잡도, 정보이득 계산이 실용적인지)
2. 5개 코어 테이블(User, UserProfile, AvoidanceSession, RegretScore, FingerprintSnapshot)의 **스키마 적합성**과 누락된 엔티티
3. Ollama 7-13B 한국어 모델 가정의 **현실성** (2026년 시점 한국어 모델 추천, VRAM별 옵션, 시나리오 생성 품질 기대치)
4. 8개 스토리(G001-G008) 로드맵의 **순서·의존성·누락** (예: 평가 인프라, 프롬프트 회귀 테스트, 데이터 마이그레이션 전략 등)
5. Definition of Done의 **검증 가능성** ("정확도 평가 통과"가 무엇으로 측정되는지 불명확)
6. **CRITICAL/HIGH 위험** 3-5개 식별 + 각각 완화 전략 제안

답변 형식: 마크다운, 섹션별 정리, 마지막에 "Top 3 우선 수정 권고" 체크리스트.

=== FINAL_GOAL.md ===
# 최종 목표 — "내일의 너 (Tomorrow's You)" / AM(Anxiety Motivator)

**프로젝트**: OSSCA 2026 멘티 산출물 (오픈소스 공개)
**확정일**: 2026-05-26
**Ultragoal 계획**: `.omc/ultragoal/goals.json` (G001-G008, aggregate 모드)

---

## 1. 한 줄 정의

미루기 직전, 사용자 본인의 누적 회피-후회 패턴을 근거로 미래 자아의 후회 시나리오를 LLM이 생성·제시함으로써 회피 행동을 멈추게 하는 개인화 개입 도구.

## 2. 우리가 푸는 문제

- 기존 미루기 앱은 외재 보상(타이머·게임화·명언)에 의존 → 빠른 내성.
- "내일의 너에게 미안하지 않게"라는 정서는 강력하지만, 일반 문구로는 와닿지 않음 → 사용자 본인 데이터 기반 시나리오여야 행동을 멈춤.
- 순수 LLM은 콜드 스타트와 환각 위험 → **HITL 능동 학습**으로 해결.

## 3. 노선(Posture)

> **"양보다 깊이 · 자기선택 · 의도된 마찰"**

품질·정직성·맥락이 가벼움·범용성·편의보다 우선이다. 이 노선이 G004(Probe Engine), G005(Onboarding), G006(Pipeline) 설계의 모든 trade-off 결정의 기준선.

## 4. 잠금된 핵심 설계 결정 (G001 확정)

### 결정 1 — 온보딩 길이: **5질문 ~120초**
- 첫 시나리오 품질이 retention의 결정 변수.
- 깊은 fingerprint를 즉시 확보 → Phase 2 소극 탐문 빈도 최소화.
- 120초는 자기선택 필터로 작동(진짜 멈추려는 사람만 통과).

### 결정 2 — HITL 수집 타이밍: **회피 입력 직전 가로채기 (세션당 최대 1개)**
- 회피 맥락이 살아있을 때 답변이 가장 정직, 시나리오 즉시 반영.
- "마찰"은 의도된 마찰 — 회피 자체를 한 번 더 의식하게 만들어 시나리오와 자매 효과.

## 5. HITL 3-Phase 콜드 스타트 (확정)

| Phase | 트리거 | 동작 |
|---|---|---|
| **Phase 1 — Onboarding** | 첫 진입 1회 | 5질문 120초로 두려움 앵커·미루기 유형·회복 패턴·트리거 카테고리·후회 회상력 슬롯 채우기 |
| **Phase 2 — Adaptive Probing** | 세션 4~15 | 회피 입력 직전 정보이득 최대 질문 1개 → 시나리오 생성 |
| **Phase 3 — Passive Inference** | 프로필 완성도 ≥80% | HITL 최소화, 누적 fingerprint와 RegretScore 기반 수동 추론 |

핵심 통찰: 시스템이 자기 불확실성을 인정하고 가장 가치 있는 질문을 던질 때 사용자가 데이터 제공에 동의한다 — **"없는 메모리"가 약점이 아닌 온보딩의 강점**이 된다.

## 6. 코어 데이터 모델 (확정 — 5 테이블)

| 테이블 | 역할 |
|---|---|
| `User` | 계정·인증·디바이스 식별 |
| `UserProfile` | 두려움 유형, 트리거, 회복 전략, 슬롯 완성도(%) — HITL 우선순위 큐 근거 |
| `AvoidanceSession` | 회피 입력 원문·타임스탬프·생성 시나리오 ID·사용자 결정(전환/지속/신고) |
| `RegretScore` | 사후 후회 강도(0-10) + 자유 텍스트 — 시나리오 정확도 ground truth |
| `FingerprintSnapshot` | 행동 지문(임베딩+통계) — 시나리오 생성 컨텍스트 |

## 7. 기술 스택

- **LLM**: Ollama 로컬 호스팅 (프라이버시 — 회피·후회 데이터 민감성)
- **모델 후보**: 한국어 지원 + 7-13B 범위 (개인 GPU 가용성)
- **저장소**: 로컬 SQLite
- **UI 진화**: CLI MVP → 웹/모바일
- **개발 도구**: CodeGraph v0.9.4 (사전 인덱싱된 코드 지식 그래프, 글로벌 MCP 등록 완료)

## 8. OSSCA 기여 표면

1. **HITL 질문 뱅크** — 정보이득 메타데이터 포함 공개 라이브러리
2. **정보 이득 알고리즘** — 슬롯 완성도 + 예측 정확도 증분 기반 질문 선택
3. **Ollama 한국어 어댑터** — 시나리오 카드 프롬프트 템플릿 + 톤 가이드
4. **후회 점수 데이터셋 스키마** — 시나리오 정확도 평가 표준

## 9. Ultragoal 실행 로드맵 (8 stories)

| ID | 스토리 | 핵심 산출 |
|---|---|---|
| ✅ G001 | DesignLockdown | 5질문·직전가로채기 결정 잠금, 본 문서 |
| G002 | OllamaPoC | 모델 1-2 선정, 한국어 시나리오 프롬프트 v1, 샘플 5건 정성 통과 |
| G003 | DataModel | 5테이블 SQLite 스키마 + 마이그레이션 + CRUD 단위 테스트 |
| G004 | HITLProbeEngine | 슬롯 추적 + 정보이득 질문 선택 + Phase 라우터 + 질문뱅크 v1 |
| G005 | OnboardingFlow | 5질문 120초 UX + UserProfile 초기화 + 사용자 테스트 1회 |
| G006 | AvoidanceSessionPipeline | 입력→Probe→Ollama→결정 로깅 end-to-end 통합 테스트 |
| G007 | RegretFingerprint | 사후 회고 알림 + RegretScore 기록 + FingerprintSnapshot 갱신 |
| G008 | MVPRelease | CLI MVP 패키징 · README · 데모 · 사용자 2주 피드백 · 멘토 리뷰 |

## 10. Definition of Done (Ultragoal 종료 조건)

- 5개 코어 테이블 구현 + 통합 테스트 통과
- HITL Probe Engine이 Phase 1/2/3 라우팅 자동 결정
- Ollama로 한국어 시나리오 카드가 일관된 톤으로 생성됨 (정확도 평가 통과)
- 최소 1명의 실제 사용자가 2주간 사용한 사용성 피드백 수집
- README + 기여 가이드 + 라이선스 + 데모로 OSSCA 멘토 리뷰 통과
- 모든 코드: ai-slop-cleaner + verification + code-review 게이트 클린

## 11. 비목표(Non-Goals)

- 클라우드 호스팅, 회원가입 백엔드 (로컬 우선)
- 알림 게이미피케이션(연속일·뱃지) — 노선 위배
- 다국어 동시 지원 — 한국어 MVP 후 검토
- 대규모 협업·소셜 기능 — 1인용 개인화 도구로 한정

## Final prompt

당신은 시니어 백엔드/시스템 아키텍트입니다. 아래는 OSSCA 2026 멘티 산출물로 만들 "내일의 너(Tomorrow's You)" 프로젝트의 최종 목표 문서입니다. Ollama 로컬 LLM 기반 미루기 개입 도구이며, 회피 직전 LLM이 개인화된 미래 후회 시나리오를 생성해 보여줍니다.

이 문서를 **아키텍처·정확성·기술 리스크·구현 가능성** 관점에서 비평해 주세요. 특히 다음을 평가:

1. HITL 3-Phase 콜드스타트 + 5질문 온보딩 + 직전 가로채기 조합의 **기술적 타당성** (Probe Engine 구현 복잡도, 정보이득 계산이 실용적인지)
2. 5개 코어 테이블(User, UserProfile, AvoidanceSession, RegretScore, FingerprintSnapshot)의 **스키마 적합성**과 누락된 엔티티
3. Ollama 7-13B 한국어 모델 가정의 **현실성** (2026년 시점 한국어 모델 추천, VRAM별 옵션, 시나리오 생성 품질 기대치)
4. 8개 스토리(G001-G008) 로드맵의 **순서·의존성·누락** (예: 평가 인프라, 프롬프트 회귀 테스트, 데이터 마이그레이션 전략 등)
5. Definition of Done의 **검증 가능성** ("정확도 평가 통과"가 무엇으로 측정되는지 불명확)
6. **CRITICAL/HIGH 위험** 3-5개 식별 + 각각 완화 전략 제안

답변 형식: 마크다운, 섹션별 정리, 마지막에 "Top 3 우선 수정 권고" 체크리스트.

=== FINAL_GOAL.md ===
# 최종 목표 — "내일의 너 (Tomorrow's You)" / AM(Anxiety Motivator)

**프로젝트**: OSSCA 2026 멘티 산출물 (오픈소스 공개)
**확정일**: 2026-05-26
**Ultragoal 계획**: `.omc/ultragoal/goals.json` (G001-G008, aggregate 모드)

---

## 1. 한 줄 정의

미루기 직전, 사용자 본인의 누적 회피-후회 패턴을 근거로 미래 자아의 후회 시나리오를 LLM이 생성·제시함으로써 회피 행동을 멈추게 하는 개인화 개입 도구.

## 2. 우리가 푸는 문제

- 기존 미루기 앱은 외재 보상(타이머·게임화·명언)에 의존 → 빠른 내성.
- "내일의 너에게 미안하지 않게"라는 정서는 강력하지만, 일반 문구로는 와닿지 않음 → 사용자 본인 데이터 기반 시나리오여야 행동을 멈춤.
- 순수 LLM은 콜드 스타트와 환각 위험 → **HITL 능동 학습**으로 해결.

## 3. 노선(Posture)

> **"양보다 깊이 · 자기선택 · 의도된 마찰"**

품질·정직성·맥락이 가벼움·범용성·편의보다 우선이다. 이 노선이 G004(Probe Engine), G005(Onboarding), G006(Pipeline) 설계의 모든 trade-off 결정의 기준선.

## 4. 잠금된 핵심 설계 결정 (G001 확정)

### 결정 1 — 온보딩 길이: **5질문 ~120초**
- 첫 시나리오 품질이 retention의 결정 변수.
- 깊은 fingerprint를 즉시 확보 → Phase 2 소극 탐문 빈도 최소화.
- 120초는 자기선택 필터로 작동(진짜 멈추려는 사람만 통과).

### 결정 2 — HITL 수집 타이밍: **회피 입력 직전 가로채기 (세션당 최대 1개)**
- 회피 맥락이 살아있을 때 답변이 가장 정직, 시나리오 즉시 반영.
- "마찰"은 의도된 마찰 — 회피 자체를 한 번 더 의식하게 만들어 시나리오와 자매 효과.

## 5. HITL 3-Phase 콜드 스타트 (확정)

| Phase | 트리거 | 동작 |
|---|---|---|
| **Phase 1 — Onboarding** | 첫 진입 1회 | 5질문 120초로 두려움 앵커·미루기 유형·회복 패턴·트리거 카테고리·후회 회상력 슬롯 채우기 |
| **Phase 2 — Adaptive Probing** | 세션 4~15 | 회피 입력 직전 정보이득 최대 질문 1개 → 시나리오 생성 |
| **Phase 3 — Passive Inference** | 프로필 완성도 ≥80% | HITL 최소화, 누적 fingerprint와 RegretScore 기반 수동 추론 |

핵심 통찰: 시스템이 자기 불확실성을 인정하고 가장 가치 있는 질문을 던질 때 사용자가 데이터 제공에 동의한다 — **"없는 메모리"가 약점이 아닌 온보딩의 강점**이 된다.

## 6. 코어 데이터 모델 (확정 — 5 테이블)

| 테이블 | 역할 |
|---|---|
| `User` | 계정·인증·디바이스 식별 |
| `UserProfile` | 두려움 유형, 트리거, 회복 전략, 슬롯 완성도(%) — HITL 우선순위 큐 근거 |
| `AvoidanceSession` | 회피 입력 원문·타임스탬프·생성 시나리오 ID·사용자 결정(전환/지속/신고) |
| `RegretScore` | 사후 후회 강도(0-10) + 자유 텍스트 — 시나리오 정확도 ground truth |
| `FingerprintSnapshot` | 행동 지문(임베딩+통계) — 시나리오 생성 컨텍스트 |

## 7. 기술 스택

- **LLM**: Ollama 로컬 호스팅 (프라이버시 — 회피·후회 데이터 민감성)
- **모델 후보**: 한국어 지원 + 7-13B 범위 (개인 GPU 가용성)
- **저장소**: 로컬 SQLite
- **UI 진화**: CLI MVP → 웹/모바일
- **개발 도구**: CodeGraph v0.9.4 (사전 인덱싱된 코드 지식 그래프, 글로벌 MCP 등록 완료)

## 8. OSSCA 기여 표면

1. **HITL 질문 뱅크** — 정보이득 메타데이터 포함 공개 라이브러리
2. **정보 이득 알고리즘** — 슬롯 완성도 + 예측 정확도 증분 기반 질문 선택
3. **Ollama 한국어 어댑터** — 시나리오 카드 프롬프트 템플릿 + 톤 가이드
4. **후회 점수 데이터셋 스키마** — 시나리오 정확도 평가 표준

## 9. Ultragoal 실행 로드맵 (8 stories)

| ID | 스토리 | 핵심 산출 |
|---|---|---|
| ✅ G001 | DesignLockdown | 5질문·직전가로채기 결정 잠금, 본 문서 |
| G002 | OllamaPoC | 모델 1-2 선정, 한국어 시나리오 프롬프트 v1, 샘플 5건 정성 통과 |
| G003 | DataModel | 5테이블 SQLite 스키마 + 마이그레이션 + CRUD 단위 테스트 |
| G004 | HITLProbeEngine | 슬롯 추적 + 정보이득 질문 선택 + Phase 라우터 + 질문뱅크 v1 |
| G005 | OnboardingFlow | 5질문 120초 UX + UserProfile 초기화 + 사용자 테스트 1회 |
| G006 | AvoidanceSessionPipeline | 입력→Probe→Ollama→결정 로깅 end-to-end 통합 테스트 |
| G007 | RegretFingerprint | 사후 회고 알림 + RegretScore 기록 + FingerprintSnapshot 갱신 |
| G008 | MVPRelease | CLI MVP 패키징 · README · 데모 · 사용자 2주 피드백 · 멘토 리뷰 |

## 10. Definition of Done (Ultragoal 종료 조건)

- 5개 코어 테이블 구현 + 통합 테스트 통과
- HITL Probe Engine이 Phase 1/2/3 라우팅 자동 결정
- Ollama로 한국어 시나리오 카드가 일관된 톤으로 생성됨 (정확도 평가 통과)
- 최소 1명의 실제 사용자가 2주간 사용한 사용성 피드백 수집
- README + 기여 가이드 + 라이선스 + 데모로 OSSCA 멘토 리뷰 통과
- 모든 코드: ai-slop-cleaner + verification + code-review 게이트 클린

## 11. 비목표(Non-Goals)

- 클라우드 호스팅, 회원가입 백엔드 (로컬 우선)
- 알림 게이미피케이션(연속일·뱃지) — 노선 위배
- 다국어 동시 지원 — 한국어 MVP 후 검토
- 대규모 협업·소셜 기능 — 1인용 개인화 도구로 한정

## Raw output

```text
**총평**

방향은 강합니다. “회피 직전의 자기 관련 후회 시나리오”는 명확한 제품 가설이고, 로컬 LLM + SQLite + CLI MVP도 OSSCA 산출물로 구현 가능성이 있습니다. 다만 현재 문서는 **제품 철학은 잠겨 있지만, 검증 가능한 시스템 명세는 덜 잠겨 있습니다.** 특히 `정보이득`, `정확도 평가`, `시나리오 품질`, `안전성`, `프롬프트/모델 회귀`가 아직 구현자가 각자 해석할 여지가 큽니다.

---

## 1. HITL 3-Phase + 5질문 + 직전 가로채기 타당성

**기술적으로 가능하지만, “정보이득 최대화”를 진짜 통계적 active learning으로 구현하려 하면 과합니다.**

현실적인 MVP 구현은 다음 수준이 적합합니다.

- Phase 1: 5질문 온보딩으로 고정 슬롯 초기화
- Phase 2: 세션 4~15에서 `slot_confidence`, `missingness`, `recent_prediction_error`, `question_fatigue`를 조합한 휴리스틱 점수로 질문 선택
- Phase 3: 프로필 완성도 80% 이상이면 질문 빈도 제한

즉, 초기 Probe Engine은 정보이득을 엄밀한 엔트로피/베이지안 업데이트로 계산하기보다:

```text
question_score =
  missing_slot_weight
+ low_confidence_weight
+ recent_regret_error_weight
+ scenario_relevance_weight
- fatigue_penalty
```

정도로 시작하는 것이 실용적입니다.

**직전 가로채기**는 제품 가설상 타당하지만, UX 리스크가 큽니다. 회피 입력 직전은 맥락이 살아있는 대신 사용자의 저항도 가장 큽니다. “세션당 최대 1개”는 좋은 제한이지만, 추가로 필요합니다.

- 즉시 건너뛰기 옵션
- 질문 대신 바로 시나리오 생성하는 fallback
- 반복 질문 방지
- 사용자가 “오늘은 묻지 않기”를 선택할 수 있는 cooldown

**5질문 120초**는 자기선택 필터로는 합리적이지만, MVP에서는 retention 손실이 클 수 있습니다. “5문항 전체 완료”를 강제하기보다 **최소 3문항으로 첫 카드 생성 가능, 5문항 완료 시 품질 향상** 구조가 더 안전합니다.

---

## 2. 5개 코어 테이블 스키마 평가

현재 5개 테이블은 “핵심 사용자 상태”에는 충분하지만, **LLM 시스템 운영·평가·재현성**에는 부족합니다.

**현재 테이블 평가**

| 테이블 | 평가 |
|---|---|
| `User` | 로컬 MVP에서는 계정보다 `local_user_id`, 디바이스, 설정 중심이면 충분 |
| `UserProfile` | 슬롯 완성도와 confidence를 반드시 분리해야 함 |
| `AvoidanceSession` | 원문, 결정, 생성 결과 연결은 적절하나 `ScenarioCard`가 분리되어야 함 |
| `RegretScore` | ground truth 후보지만 “정확도” 단독 기준으로는 약함 |
| `FingerprintSnapshot` | 좋지만 임베딩 모델/버전/생성 시점을 같이 저장해야 재현 가능 |

**누락된 엔티티**

필수에 가깝습니다.

- `ScenarioCard`: 생성된 후회 시나리오 본문, 톤, 사용 프롬프트, 모델, 안전 필터 결과
- `ProbeQuestion`: 질문 뱅크, 타겟 슬롯, 예상 정보가치, 활성 여부, 버전
- `ProbeAnswer`: 사용자 답변, 연결된 세션, 추출된 슬롯 업데이트
- `ModelRun`: Ollama 모델명, quantization, temperature, prompt version, latency, token 수, 에러
- `PromptTemplate` 또는 `PromptVersion`: 프롬프트 회귀 테스트와 재현성을 위해 필요
- `EvaluationResult`: 샘플별 품질 평가, 안전성 평가, 회귀 테스트 결과
- `SchemaMigration`: SQLite 마이그레이션 버전 추적

특히 `AvoidanceSession.scenario_id`가 언급되어 있는데 `ScenarioCard` 테이블이 없다는 점은 명백한 스키마 불일치입니다.

---

## 3. Ollama 7-13B 한국어 모델 가정 현실성

**7-13B 가정은 대체로 현실적이지만, 한국어 품질 기준이면 EXAONE 계열을 1순위 후보로 둬야 합니다.** Ollama에는 EXAONE 3.5가 영어/한국어 bilingual 모델로 제공되며 2.4B, 7.8B, 32B 크기가 있습니다. Ollama 페이지 기준 `exaone3.5:7.8b`는 약 4.8GB, 32K 컨텍스트입니다. [Ollama EXAONE 3.5](https://ollama.com/library/exaone3.5)

보조 후보로는 Qwen3와 Gemma 3가 적절합니다. Qwen3는 4B/8B/14B/30B/32B 등 폭이 넓고, Ollama 기준 `qwen3:8b` 약 5.2GB, `qwen3:14b` 약 9.3GB입니다. [Ollama Qwen3](https://ollama.com/library/qwen3) Gemma 3는 4B/12B/27B가 있고 140개 이상 언어와 128K 컨텍스트를 지원한다고 공개되어 있습니다. [Ollama Gemma 3](https://ollama.com/library/gemma3)

**VRAM별 추천**

| 환경 | 추천 |
|---|---|
| CPU only / 4GB VRAM | EXAONE 3.5 2.4B, Qwen3 4B. 품질은 PoC/테스트용 |
| 6-8GB VRAM | EXAONE 3.5 7.8B, Qwen3 8B. MVP 기본선 |
| 12-16GB VRAM | Qwen3 14B, Gemma 3 12B, EXAONE 7.8B 고속 모드 |
| 24GB VRAM | EXAONE 3.5 32B, Qwen3 30B/32B, Gemma 3 27B |

주의할 점은 Ollama의 모델 파일 크기와 실제 VRAM 사용량은 다릅니다. KV cache, 컨텍스트 길이, 동시 요청, OS/GPU 여유분 때문에 8.1GB 모델이 8GB VRAM에서 안정적으로 돈다고 가정하면 안 됩니다.

**품질 기대치**

7-8B급은 한국어 문장은 충분히 만들 수 있지만, “사용자 데이터에 근거한 정밀한 후회 시나리오”는 프롬프트와 평가가 없으면 쉽게 일반 조언문으로 흐릅니다. 13-14B급부터 일관성과 뉘앙스가 개선되고, 30B급은 품질은 좋아지지만 로컬 MVP 접근성이 떨어집니다. 따라서 기본 목표는 “최고 품질 생성”이 아니라 **근거 슬롯을 명시적으로 사용하고, 금지 톤을 피하며, 반복 가능하게 평가되는 카드 생성**이어야 합니다.

---

## 4. G001-G008 로드맵 평가

현재 순서는 큰 틀에서 맞지만, **평가 인프라가 너무 늦거나 암묵적**입니다.

권장 순서:

1. G002 OllamaPoC  
   모델 후보 + 프롬프트 v1 + 실패 케이스 수집
2. G002.5 EvaluationHarness  
   고정 샘플, 프롬프트 회귀 테스트, 안전성 체크, golden outputs
3. G003 DataModel  
   현재 5테이블이 아니라 운영/평가 테이블 포함
4. G005 OnboardingFlow  
   실제 슬롯이 어떤 데이터로 채워지는지 먼저 검증
5. G004 HITLProbeEngine  
   온보딩 데이터 형태를 본 뒤 Probe 점수화
6. G006 AvoidanceSessionPipeline  
   end-to-end 연결
7. G007 RegretFingerprint  
   사후 점수와 fingerprint 업데이트
8. G008 MVPRelease

**누락된 스토리**

- EvaluationHarness: 프롬프트 회귀, 모델 비교, 안전성 검사
- SafetyPolicy: 자해/우울/불안 악화 표현 방지, 위기 문구 대응
- MigrationStrategy: SQLite schema versioning
- PromptVersioning: 프롬프트와 결과 재현성
- PrivacyExportDelete: 로컬 데이터 export/delete
- FailureFallback: Ollama 미실행, 모델 없음, 생성 timeout, 저품질 응답 처리

---

## 5. Definition of Done 검증 가능성

현재 DoD의 약점은 “정확도 평가 통과”가 측정 불가능하다는 점입니다.

다음처럼 바꾸는 것이 좋습니다.

**시나리오 품질 DoD 예시**

- 고정 평가 샘플 30개에서 카드 생성 성공률 ≥ 95%
- 한국어 문장 자연성 평균 4/5 이상
- 사용자 슬롯 근거 반영률 ≥ 80%
- 금지 표현 위반 0건
- 동일 입력 회귀 테스트에서 구조 필드 누락 0건
- P95 생성 지연 시간: 목표 하드웨어에서 10초 이하 또는 명시된 fallback 제공
- 실제 사용자 2주 테스트에서 “도움 됨” 자기평가 평균 3.5/5 이상
- RegretScore 예측 방향성과 사후 점수의 Spearman correlation을 수집하되, MVP 통과 기준은 exploratory로 둠

“정확도”라는 단어는 이 프로젝트에 애매합니다. 추천 표현은 **개인화 적합도, 근거 충실도, 안전성, 행동 전환율, 사후 공감도**입니다.

---

## 6. CRITICAL / HIGH 위험과 완화 전략

| 위험 | 등급 | 설명 | 완화 |
|---|---:|---|---|
| 불안/죄책감 증폭 | CRITICAL | 후회 시나리오가 취약 사용자에게 해로울 수 있음 | 안전 프롬프트, 금지 표현 목록, 강도 조절, “격려형 전환”, 위기 키워드 감지, 사용 중단/도움말 제공 |
| 평가 기준 부재 | CRITICAL | “좋은 시나리오”가 주관적이면 모델/프롬프트 개선 불가 | EvaluationHarness를 G002 직후 추가, golden sample, 루브릭, 회귀 테스트 도입 |
| 개인정보/민감정보 로컬 저장 리스크 | HIGH | 회피·후회 텍스트는 매우 민감함 | DB 암호화 옵션, export/delete, 민감정보 마스킹, 로컬-only 명시, 로그 비식별화 |
| Probe Engine 과설계 | HIGH | 정보이득 계산을 과학적으로 만들려다 구현 지연 가능 | v1은 휴리스틱 점수화, 나중에 실제 regret feedback으로 보정 |
| 로컬 모델 품질/성능 편차 | HIGH | 사용자 하드웨어와 모델에 따라 품질·속도 차이 큼 | 모델 tier 명시, timeout/fallback, EXAONE 7.8B baseline, Qwen/Gemma 대체 프로파일 제공 |

---

## Top 3 우선 수정 권고

- [ ] `G002.5 EvaluationHarness`를 추가하고 “정확도 평가 통과”를 루브릭·샘플·회귀 테스트 기준으로 재정의
- [ ] 데이터 모델에 `ScenarioCard`, `ProbeQuestion`, `ProbeAnswer`, `ModelRun`, `PromptVersion`, `EvaluationResult`를 추가
- [ ] Probe Engine v1을 엄밀한 정보이득 계산이 아니라 슬롯 confidence 기반 휴리스틱으로 낮추고, 안전/프라이버시 요구사항을 DoD에 포함


2026-05-26T05:51:36.810847Z ERROR codex_core::session: failed to load skill /home/gpuuser/.agents/skills/one/SKILL.md: invalid description: exceeds maximum length of 1024 characters
2026-05-26T05:51:36.810887Z ERROR codex_core::session: failed to load skill /home/gpuuser/.agents/skills/one/SKILL.md: invalid description: exceeds maximum length of 1024 characters
OpenAI Codex v0.128.0 (research preview)
--------
workdir: /dataset/yjpark/ossca_yjpark
model: gpt-5.5
provider: openai
approval: never
sandbox: danger-full-access
reasoning effort: medium
reasoning summaries: none
session id: 019e62d6-af82-7fc2-a10b-7b3ddabb06c7
--------
user
당신은 시니어 백엔드/시스템 아키텍트입니다. 아래는 OSSCA 2026 멘티 산출물로 만들 "내일의 너(Tomorrow's You)" 프로젝트의 최종 목표 문서입니다. Ollama 로컬 LLM 기반 미루기 개입 도구이며, 회피 직전 LLM이 개인화된 미래 후회 시나리오를 생성해 보여줍니다.

이 문서를 **아키텍처·정확성·기술 리스크·구현 가능성** 관점에서 비평해 주세요. 특히 다음을 평가:

1. HITL 3-Phase 콜드스타트 + 5질문 온보딩 + 직전 가로채기 조합의 **기술적 타당성** (Probe Engine 구현 복잡도, 정보이득 계산이 실용적인지)
2. 5개 코어 테이블(User, UserProfile, AvoidanceSession, RegretScore, FingerprintSnapshot)의 **스키마 적합성**과 누락된 엔티티
3. Ollama 7-13B 한국어 모델 가정의 **현실성** (2026년 시점 한국어 모델 추천, VRAM별 옵션, 시나리오 생성 품질 기대치)
4. 8개 스토리(G001-G008) 로드맵의 **순서·의존성·누락** (예: 평가 인프라, 프롬프트 회귀 테스트, 데이터 마이그레이션 전략 등)
5. Definition of Done의 **검증 가능성** ("정확도 평가 통과"가 무엇으로 측정되는지 불명확)
6. **CRITICAL/HIGH 위험** 3-5개 식별 + 각각 완화 전략 제안

답변 형식: 마크다운, 섹션별 정리, 마지막에 "Top 3 우선 수정 권고" 체크리스트.

=== FINAL_GOAL.md ===
# 최종 목표 — "내일의 너 (Tomorrow's You)" / AM(Anxiety Motivator)

**프로젝트**: OSSCA 2026 멘티 산출물 (오픈소스 공개)
**확정일**: 2026-05-26
**Ultragoal 계획**: `.omc/ultragoal/goals.json` (G001-G008, aggregate 모드)

---

## 1. 한 줄 정의

미루기 직전, 사용자 본인의 누적 회피-후회 패턴을 근거로 미래 자아의 후회 시나리오를 LLM이 생성·제시함으로써 회피 행동을 멈추게 하는 개인화 개입 도구.

## 2. 우리가 푸는 문제

- 기존 미루기 앱은 외재 보상(타이머·게임화·명언)에 의존 → 빠른 내성.
- "내일의 너에게 미안하지 않게"라는 정서는 강력하지만, 일반 문구로는 와닿지 않음 → 사용자 본인 데이터 기반 시나리오여야 행동을 멈춤.
- 순수 LLM은 콜드 스타트와 환각 위험 → **HITL 능동 학습**으로 해결.

## 3. 노선(Posture)

> **"양보다 깊이 · 자기선택 · 의도된 마찰"**

품질·정직성·맥락이 가벼움·범용성·편의보다 우선이다. 이 노선이 G004(Probe Engine), G005(Onboarding), G006(Pipeline) 설계의 모든 trade-off 결정의 기준선.

## 4. 잠금된 핵심 설계 결정 (G001 확정)

### 결정 1 — 온보딩 길이: **5질문 ~120초**
- 첫 시나리오 품질이 retention의 결정 변수.
- 깊은 fingerprint를 즉시 확보 → Phase 2 소극 탐문 빈도 최소화.
- 120초는 자기선택 필터로 작동(진짜 멈추려는 사람만 통과).

### 결정 2 — HITL 수집 타이밍: **회피 입력 직전 가로채기 (세션당 최대 1개)**
- 회피 맥락이 살아있을 때 답변이 가장 정직, 시나리오 즉시 반영.
- "마찰"은 의도된 마찰 — 회피 자체를 한 번 더 의식하게 만들어 시나리오와 자매 효과.

## 5. HITL 3-Phase 콜드 스타트 (확정)

| Phase | 트리거 | 동작 |
|---|---|---|
| **Phase 1 — Onboarding** | 첫 진입 1회 | 5질문 120초로 두려움 앵커·미루기 유형·회복 패턴·트리거 카테고리·후회 회상력 슬롯 채우기 |
| **Phase 2 — Adaptive Probing** | 세션 4~15 | 회피 입력 직전 정보이득 최대 질문 1개 → 시나리오 생성 |
| **Phase 3 — Passive Inference** | 프로필 완성도 ≥80% | HITL 최소화, 누적 fingerprint와 RegretScore 기반 수동 추론 |

핵심 통찰: 시스템이 자기 불확실성을 인정하고 가장 가치 있는 질문을 던질 때 사용자가 데이터 제공에 동의한다 — **"없는 메모리"가 약점이 아닌 온보딩의 강점**이 된다.

## 6. 코어 데이터 모델 (확정 — 5 테이블)

| 테이블 | 역할 |
|---|---|
| `User` | 계정·인증·디바이스 식별 |
| `UserProfile` | 두려움 유형, 트리거, 회복 전략, 슬롯 완성도(%) — HITL 우선순위 큐 근거 |
| `AvoidanceSession` | 회피 입력 원문·타임스탬프·생성 시나리오 ID·사용자 결정(전환/지속/신고) |
| `RegretScore` | 사후 후회 강도(0-10) + 자유 텍스트 — 시나리오 정확도 ground truth |
| `FingerprintSnapshot` | 행동 지문(임베딩+통계) — 시나리오 생성 컨텍스트 |

## 7. 기술 스택

- **LLM**: Ollama 로컬 호스팅 (프라이버시 — 회피·후회 데이터 민감성)
- **모델 후보**: 한국어 지원 + 7-13B 범위 (개인 GPU 가용성)
- **저장소**: 로컬 SQLite
- **UI 진화**: CLI MVP → 웹/모바일
- **개발 도구**: CodeGraph v0.9.4 (사전 인덱싱된 코드 지식 그래프, 글로벌 MCP 등록 완료)

## 8. OSSCA 기여 표면

1. **HITL 질문 뱅크** — 정보이득 메타데이터 포함 공개 라이브러리
2. **정보 이득 알고리즘** — 슬롯 완성도 + 예측 정확도 증분 기반 질문 선택
3. **Ollama 한국어 어댑터** — 시나리오 카드 프롬프트 템플릿 + 톤 가이드
4. **후회 점수 데이터셋 스키마** — 시나리오 정확도 평가 표준

## 9. Ultragoal 실행 로드맵 (8 stories)

| ID | 스토리 | 핵심 산출 |
|---|---|---|
| ✅ G001 | DesignLockdown | 5질문·직전가로채기 결정 잠금, 본 문서 |
| G002 | OllamaPoC | 모델 1-2 선정, 한국어 시나리오 프롬프트 v1, 샘플 5건 정성 통과 |
| G003 | DataModel | 5테이블 SQLite 스키마 + 마이그레이션 + CRUD 단위 테스트 |
| G004 | HITLProbeEngine | 슬롯 추적 + 정보이득 질문 선택 + Phase 라우터 + 질문뱅크 v1 |
| G005 | OnboardingFlow | 5질문 120초 UX + UserProfile 초기화 + 사용자 테스트 1회 |
| G006 | AvoidanceSessionPipeline | 입력→Probe→Ollama→결정 로깅 end-to-end 통합 테스트 |
| G007 | RegretFingerprint | 사후 회고 알림 + RegretScore 기록 + FingerprintSnapshot 갱신 |
| G008 | MVPRelease | CLI MVP 패키징 · README · 데모 · 사용자 2주 피드백 · 멘토 리뷰 |

## 10. Definition of Done (Ultragoal 종료 조건)

- 5개 코어 테이블 구현 + 통합 테스트 통과
- HITL Probe Engine이 Phase 1/2/3 라우팅 자동 결정
- Ollama로 한국어 시나리오 카드가 일관된 톤으로 생성됨 (정확도 평가 통과)
- 최소 1명의 실제 사용자가 2주간 사용한 사용성 피드백 수집
- README + 기여 가이드 + 라이선스 + 데모로 OSSCA 멘토 리뷰 통과
- 모든 코드: ai-slop-cleaner + verification + code-review 게이트 클린

## 11. 비목표(Non-Goals)

- 클라우드 호스팅, 회원가입 백엔드 (로컬 우선)
- 알림 게이미피케이션(연속일·뱃지) — 노선 위배
- 다국어 동시 지원 — 한국어 MVP 후 검토
- 대규모 협업·소셜 기능 — 1인용 개인화 도구로 한정
hook: SessionStart
hook: SessionStart Completed
hook: UserPromptSubmit
hook: UserPromptSubmit Completed
codex
현재 모델 가정은 2026년 기준으로 변동성이 커서, Ollama 라이브러리와 주요 한국어 모델 정보를 먼저 확인한 뒤 문서 자체의 구조와 리스크를 평가하겠습니다.
web search: 
web search: site:ollama.com/library qwen3 ollama model sizes 7b 14b 2026 ...
web search: 
web search: https://ollama.com/library/exaone3.5
codex
**총평**

방향은 강합니다. “회피 직전의 자기 관련 후회 시나리오”는 명확한 제품 가설이고, 로컬 LLM + SQLite + CLI MVP도 OSSCA 산출물로 구현 가능성이 있습니다. 다만 현재 문서는 **제품 철학은 잠겨 있지만, 검증 가능한 시스템 명세는 덜 잠겨 있습니다.** 특히 `정보이득`, `정확도 평가`, `시나리오 품질`, `안전성`, `프롬프트/모델 회귀`가 아직 구현자가 각자 해석할 여지가 큽니다.

---

## 1. HITL 3-Phase + 5질문 + 직전 가로채기 타당성

**기술적으로 가능하지만, “정보이득 최대화”를 진짜 통계적 active learning으로 구현하려 하면 과합니다.**

현실적인 MVP 구현은 다음 수준이 적합합니다.

- Phase 1: 5질문 온보딩으로 고정 슬롯 초기화
- Phase 2: 세션 4~15에서 `slot_confidence`, `missingness`, `recent_prediction_error`, `question_fatigue`를 조합한 휴리스틱 점수로 질문 선택
- Phase 3: 프로필 완성도 80% 이상이면 질문 빈도 제한

즉, 초기 Probe Engine은 정보이득을 엄밀한 엔트로피/베이지안 업데이트로 계산하기보다:

```text
question_score =
  missing_slot_weight
+ low_confidence_weight
+ recent_regret_error_weight
+ scenario_relevance_weight
- fatigue_penalty
```

정도로 시작하는 것이 실용적입니다.

**직전 가로채기**는 제품 가설상 타당하지만, UX 리스크가 큽니다. 회피 입력 직전은 맥락이 살아있는 대신 사용자의 저항도 가장 큽니다. “세션당 최대 1개”는 좋은 제한이지만, 추가로 필요합니다.

- 즉시 건너뛰기 옵션
- 질문 대신 바로 시나리오 생성하는 fallback
- 반복 질문 방지
- 사용자가 “오늘은 묻지 않기”를 선택할 수 있는 cooldown

**5질문 120초**는 자기선택 필터로는 합리적이지만, MVP에서는 retention 손실이 클 수 있습니다. “5문항 전체 완료”를 강제하기보다 **최소 3문항으로 첫 카드 생성 가능, 5문항 완료 시 품질 향상** 구조가 더 안전합니다.

---

## 2. 5개 코어 테이블 스키마 평가

현재 5개 테이블은 “핵심 사용자 상태”에는 충분하지만, **LLM 시스템 운영·평가·재현성**에는 부족합니다.

**현재 테이블 평가**

| 테이블 | 평가 |
|---|---|
| `User` | 로컬 MVP에서는 계정보다 `local_user_id`, 디바이스, 설정 중심이면 충분 |
| `UserProfile` | 슬롯 완성도와 confidence를 반드시 분리해야 함 |
| `AvoidanceSession` | 원문, 결정, 생성 결과 연결은 적절하나 `ScenarioCard`가 분리되어야 함 |
| `RegretScore` | ground truth 후보지만 “정확도” 단독 기준으로는 약함 |
| `FingerprintSnapshot` | 좋지만 임베딩 모델/버전/생성 시점을 같이 저장해야 재현 가능 |

**누락된 엔티티**

필수에 가깝습니다.

- `ScenarioCard`: 생성된 후회 시나리오 본문, 톤, 사용 프롬프트, 모델, 안전 필터 결과
- `ProbeQuestion`: 질문 뱅크, 타겟 슬롯, 예상 정보가치, 활성 여부, 버전
- `ProbeAnswer`: 사용자 답변, 연결된 세션, 추출된 슬롯 업데이트
- `ModelRun`: Ollama 모델명, quantization, temperature, prompt version, latency, token 수, 에러
- `PromptTemplate` 또는 `PromptVersion`: 프롬프트 회귀 테스트와 재현성을 위해 필요
- `EvaluationResult`: 샘플별 품질 평가, 안전성 평가, 회귀 테스트 결과
- `SchemaMigration`: SQLite 마이그레이션 버전 추적

특히 `AvoidanceSession.scenario_id`가 언급되어 있는데 `ScenarioCard` 테이블이 없다는 점은 명백한 스키마 불일치입니다.

---

## 3. Ollama 7-13B 한국어 모델 가정 현실성

**7-13B 가정은 대체로 현실적이지만, 한국어 품질 기준이면 EXAONE 계열을 1순위 후보로 둬야 합니다.** Ollama에는 EXAONE 3.5가 영어/한국어 bilingual 모델로 제공되며 2.4B, 7.8B, 32B 크기가 있습니다. Ollama 페이지 기준 `exaone3.5:7.8b`는 약 4.8GB, 32K 컨텍스트입니다. [Ollama EXAONE 3.5](https://ollama.com/library/exaone3.5)

보조 후보로는 Qwen3와 Gemma 3가 적절합니다. Qwen3는 4B/8B/14B/30B/32B 등 폭이 넓고, Ollama 기준 `qwen3:8b` 약 5.2GB, `qwen3:14b` 약 9.3GB입니다. [Ollama Qwen3](https://ollama.com/library/qwen3) Gemma 3는 4B/12B/27B가 있고 140개 이상 언어와 128K 컨텍스트를 지원한다고 공개되어 있습니다. [Ollama Gemma 3](https://ollama.com/library/gemma3)

**VRAM별 추천**

| 환경 | 추천 |
|---|---|
| CPU only / 4GB VRAM | EXAONE 3.5 2.4B, Qwen3 4B. 품질은 PoC/테스트용 |
| 6-8GB VRAM | EXAONE 3.5 7.8B, Qwen3 8B. MVP 기본선 |
| 12-16GB VRAM | Qwen3 14B, Gemma 3 12B, EXAONE 7.8B 고속 모드 |
| 24GB VRAM | EXAONE 3.5 32B, Qwen3 30B/32B, Gemma 3 27B |

주의할 점은 Ollama의 모델 파일 크기와 실제 VRAM 사용량은 다릅니다. KV cache, 컨텍스트 길이, 동시 요청, OS/GPU 여유분 때문에 8.1GB 모델이 8GB VRAM에서 안정적으로 돈다고 가정하면 안 됩니다.

**품질 기대치**

7-8B급은 한국어 문장은 충분히 만들 수 있지만, “사용자 데이터에 근거한 정밀한 후회 시나리오”는 프롬프트와 평가가 없으면 쉽게 일반 조언문으로 흐릅니다. 13-14B급부터 일관성과 뉘앙스가 개선되고, 30B급은 품질은 좋아지지만 로컬 MVP 접근성이 떨어집니다. 따라서 기본 목표는 “최고 품질 생성”이 아니라 **근거 슬롯을 명시적으로 사용하고, 금지 톤을 피하며, 반복 가능하게 평가되는 카드 생성**이어야 합니다.

---

## 4. G001-G008 로드맵 평가

현재 순서는 큰 틀에서 맞지만, **평가 인프라가 너무 늦거나 암묵적**입니다.

권장 순서:

1. G002 OllamaPoC  
   모델 후보 + 프롬프트 v1 + 실패 케이스 수집
2. G002.5 EvaluationHarness  
   고정 샘플, 프롬프트 회귀 테스트, 안전성 체크, golden outputs
3. G003 DataModel  
   현재 5테이블이 아니라 운영/평가 테이블 포함
4. G005 OnboardingFlow  
   실제 슬롯이 어떤 데이터로 채워지는지 먼저 검증
5. G004 HITLProbeEngine  
   온보딩 데이터 형태를 본 뒤 Probe 점수화
6. G006 AvoidanceSessionPipeline  
   end-to-end 연결
7. G007 RegretFingerprint  
   사후 점수와 fingerprint 업데이트
8. G008 MVPRelease

**누락된 스토리**

- EvaluationHarness: 프롬프트 회귀, 모델 비교, 안전성 검사
- SafetyPolicy: 자해/우울/불안 악화 표현 방지, 위기 문구 대응
- MigrationStrategy: SQLite schema versioning
- PromptVersioning: 프롬프트와 결과 재현성
- PrivacyExportDelete: 로컬 데이터 export/delete
- FailureFallback: Ollama 미실행, 모델 없음, 생성 timeout, 저품질 응답 처리

---

## 5. Definition of Done 검증 가능성

현재 DoD의 약점은 “정확도 평가 통과”가 측정 불가능하다는 점입니다.

다음처럼 바꾸는 것이 좋습니다.

**시나리오 품질 DoD 예시**

- 고정 평가 샘플 30개에서 카드 생성 성공률 ≥ 95%
- 한국어 문장 자연성 평균 4/5 이상
- 사용자 슬롯 근거 반영률 ≥ 80%
- 금지 표현 위반 0건
- 동일 입력 회귀 테스트에서 구조 필드 누락 0건
- P95 생성 지연 시간: 목표 하드웨어에서 10초 이하 또는 명시된 fallback 제공
- 실제 사용자 2주 테스트에서 “도움 됨” 자기평가 평균 3.5/5 이상
- RegretScore 예측 방향성과 사후 점수의 Spearman correlation을 수집하되, MVP 통과 기준은 exploratory로 둠

“정확도”라는 단어는 이 프로젝트에 애매합니다. 추천 표현은 **개인화 적합도, 근거 충실도, 안전성, 행동 전환율, 사후 공감도**입니다.

---

## 6. CRITICAL / HIGH 위험과 완화 전략

| 위험 | 등급 | 설명 | 완화 |
|---|---:|---|---|
| 불안/죄책감 증폭 | CRITICAL | 후회 시나리오가 취약 사용자에게 해로울 수 있음 | 안전 프롬프트, 금지 표현 목록, 강도 조절, “격려형 전환”, 위기 키워드 감지, 사용 중단/도움말 제공 |
| 평가 기준 부재 | CRITICAL | “좋은 시나리오”가 주관적이면 모델/프롬프트 개선 불가 | EvaluationHarness를 G002 직후 추가, golden sample, 루브릭, 회귀 테스트 도입 |
| 개인정보/민감정보 로컬 저장 리스크 | HIGH | 회피·후회 텍스트는 매우 민감함 | DB 암호화 옵션, export/delete, 민감정보 마스킹, 로컬-only 명시, 로그 비식별화 |
| Probe Engine 과설계 | HIGH | 정보이득 계산을 과학적으로 만들려다 구현 지연 가능 | v1은 휴리스틱 점수화, 나중에 실제 regret feedback으로 보정 |
| 로컬 모델 품질/성능 편차 | HIGH | 사용자 하드웨어와 모델에 따라 품질·속도 차이 큼 | 모델 tier 명시, timeout/fallback, EXAONE 7.8B baseline, Qwen/Gemma 대체 프로파일 제공 |

---

## Top 3 우선 수정 권고

- [ ] `G002.5 EvaluationHarness`를 추가하고 “정확도 평가 통과”를 루브릭·샘플·회귀 테스트 기준으로 재정의
- [ ] 데이터 모델에 `ScenarioCard`, `ProbeQuestion`, `ProbeAnswer`, `ModelRun`, `PromptVersion`, `EvaluationResult`를 추가
- [ ] Probe Engine v1을 엄밀한 정보이득 계산이 아니라 슬롯 confidence 기반 휴리스틱으로 낮추고, 안전/프라이버시 요구사항을 DoD에 포함
hook: Stop
hook: Stop Completed
tokens used
37,716

```

## Concise summary

Provider completed successfully. Review the raw output for details.

## Action items

- Review the response and extract decisions you want to apply.
- Capture follow-up implementation tasks if needed.
