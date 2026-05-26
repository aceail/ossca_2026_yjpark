# EvaluationHarness v1 — 설계 (G009)

**버전**: v1 (정량 메트릭 자동화)
**대상 baseline**: EXAONE 3.5 7.8B + Witty 모드 (scenario_prompt_v2.md)
**작성일**: 2026-05-26
**연계**: `.omc/ultragoal/FINAL_GOAL.md` v2.3 §10 DoD · §12 톤 가이드 · §6.5 Safety Policy

---

## 0. 목적

G002에서 발견한 **자동 메트릭의 한계**(qwen3:1.7b의 한자 누출·의미 깨짐·부적절 어휘를 못 잡음)와 **v2 결과 회귀 위험**(길이 초과·위로 어구 누수·컨텍스트 누수)을 자동으로 잡는 평가 파이프라인 v1. 정성 메트릭(LLM-as-judge)은 v2에서, 페르소나 차원은 v3에서 (G011 이후).

## 1. 평가 차원 9개 (정량 자동)

| # | 차원 | 측정 방법 | 통과 기준 (per card) | CI Fail 조건 |
|---|---|---|---|---|
| 1 | **JSON 유효성** | `json.loads()` 성공 + `card_type`·`sentences` 존재 | True | 30/30 미만 |
| 2 | **3문장 완비** | `fact`·`feeling`·`micro_action` 비어있지 않음 | True | 30/30 미만 |
| 3 | **1인칭 화법** (perspective=1st) | regex: `^(너는|너가|당신은|당신이|당신을|당신의)\s` 부재 | True | 1건 이상 위반 |
| 4 | **절대 금지어** | 7 그룹 모든 키워드 부재 (의지·노력·한심·정상·게으름·정신 차려·도태·조졌·다른 사람·다른 애들·남들·효도·체면·부모 실망·병역·취업·학벌·외모·체중·연애 실패·씨발·좆·존나) | 0건 위반 | 1건 이상 |
| 5 | **길이 80-150자** | `len(fact)+len(feeling)+len(action)` ∈ [80,150] | True | < 80% of cards |
| 6 | **시간 구체화** (regret only) | regex: `\d+시\s*\d+분|\d+시간\s*\d+분|\d+분|\d+시` 존재 | True | < 90% of regret cards |
| 7 | **위로 어휘 차단** (regret only) | regex: `괜찮(아\|다\|을)|여유롭게|천천히|급하지 않|지\s*않아도|조금\s*\S+이지만` 부재 | True | 1건 이상 |
| 8 | **단호한 종결** (regret only) | `micro_action`이 명령형 동사로 끝남: `(켠다\|쓴다\|친다\|보낸다\|연다\|열어라\|시작한다\|읽는다\|마신다\|...)$` | True | < 80% of regret cards |
| 9 | **외래 문자 누출** | regex: 한글·영문·숫자·기본 구두점 외 한자(`[\u4e00-\u9fff]`)·일본어·키릴 부재 | True | 1건 이상 |

## 2. 통과 기준 종합

| 차원 | Per-card | CI |
|---|---|---|
| 1,2,3,4,7,9 | strict (1건 위반 = fail) | 0 violations |
| 5,6,8 | tolerance (% 기반) | ≥ threshold |

CI fail 정책: 위 차원 중 strict 1건 위반 또는 tolerance < threshold → `pytest` exit 1.

## 3. 골든 샘플 구성 (30건)

`.omc/ultragoal/golden_samples_v1.json` — 30 entries.

분포:
- **mode**: regret 24 · recovery 5 · soft_stop 1 (위기 신호 감지 negative test)
- **persona context**: 대학원생/직장인/프리랜서/학생/30대 직장인/40대 자영업/공시생/시니어/주부/창업자 등 다양성
- **회피 카테고리**: 글쓰기/발표/이메일/연락/공부/운동/세금·서류/병원 약속/저축·재무/관계 메시지/창의 작업 등
- **TIMELINE 분포**: 마감 시각 1h/6h/24h/3d/1주/없음 분산
- **각 샘플 metadata**: persona_context, avoidance_input, profile_summary, timeline_hint, expected_mode, expected_card_type, expected_metrics_overrides(샘플별 예외)

5 샘플은 G002 v2 재활용(S1~S5), 25 신규 합성.
사용자 본인 5건은 G009 v2/v3 단계에서 추가 예정 (현재는 placeholder).

## 4. 회귀 테스트 정책

### Tier 1 — 매 commit pytest
- 30 골든 샘플 EXAONE Witty 모드 1회 실행
- 차원 1·2·3·4·9 (strict) 모든 위반 0건
- 차원 5·6·7·8 (tolerance) 임계치 통과
- 평균 latency < 5s per card

### Tier 2 — 매주 회귀
- 30 샘플 × 2 모델 (EXAONE + qwen3:8b) — A/B 비교
- 결과 diff 저장: `.omc/ultragoal/eval_history/`

### Tier 3 — G011 후 추가
- 5 페르소나 × 30 샘플 = 150 카드
- perspective별 화법 일관성 (1st 화법 페르소나만 1인칭 검사, 2nd 페르소나는 2인칭 검사)
- 페르소나 간 절대 한계선 공통 유지 검증

## 5. v2/v3 단계 예고

### v2 (LLM-as-judge 추가)
- evaluator: `qwen3:14b` (EXAONE과 다른 family, 자기참조 편향 회피)
- 정성 차원 5: 한국어 자연성 · 의미 정합성 · 사용자 입력과의 fact 정합성 · 톤 적절성 · 행동 전환 가능성 추정
- 각 카드를 evaluator에게 보여주고 5점 척도 + 자유 코멘트
- 출력 JSON 구조화 + 결과 aggregation

### v3 (페르소나 차원)
- G011 PersonaSystem 산출 후
- 5 default 페르소나 × 30 샘플 = 150 카드
- perspective별 화법·voice_style 일관성
- 커스텀 페르소나 안전 audit 자동 회귀

## 6. 산출물 (G009 v1)

| 파일 | 역할 |
|---|---|
| `.omc/ultragoal/EVAL_HARNESS_DESIGN_v1.md` | 본 설계 (이 문서) |
| `.omc/ultragoal/golden_samples_v1.json` | 30 골든 샘플 |
| `scripts/eval_harness.py` | 자동 메트릭 9차원 + EXAONE 호출 + 결과 집계 |
| `tests/test_eval_harness.py` | pytest 회귀 (Tier 1) |
| `.omc/ultragoal/eval_v1_results.md` | 첫 실행 결과 상세 |
| `.omc/ultragoal/eval_v1_summary.json` | CI machine-readable summary |

## 7. 통과 기준 (G009 v1 close 조건)

- [ ] 30 골든 샘플 작성 완료
- [ ] 9 차원 자동 메트릭 구현 완료
- [ ] EXAONE Witty 모드 첫 실행 통과 (strict 0, tolerance ≥ threshold)
- [ ] pytest 회귀 1회 green
- [ ] 결과 markdown + JSON 산출
- [ ] G002 v2 회귀 위험 5건(길이·괜찮아·컨텍스트·자기반박·과한 비유) 중 자동 잡히는 항목 명시
