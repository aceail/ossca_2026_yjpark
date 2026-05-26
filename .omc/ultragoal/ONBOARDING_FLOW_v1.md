# Onboarding Flow v1 — G005

**버전**: v1 (G005 산출)
**작성일**: 2026-05-26
**연계**: FINAL_GOAL.md v2.3 §4 (결정 1: 카드형 3+2) · §12 (페르소나 시스템) · §14 (UI/UX Direction)
**대상**: G003 DataModel · G011 PersonaSystem · G008 MVPRelease 구현 담당자

---

## 0. 원칙

> **첫 시나리오 품질이 retention의 결정 변수**. 5 카드 ~120초로 깊은 fingerprint를 즉시 확보. 120초는 자기선택 필터.
> 마찰 최소화: 주관식 입력 X, **카드 소팅/밸런스 게임** 형식. 3 카드 ESCape 경로(60초)로 첫 시나리오 생성 가능, 5 카드 완료 시 fingerprint 정밀도 향상.

## 1. 5 카드 구조

### Required (3 카드, ~60초)

#### Card 1 — 트리거 카테고리 (UserProfile.trigger_category)
> **"지금 당신을 도망치게 만드는 건 무엇인가요?"**

옵션 (single-select, 카드 소팅 형식):
- 글쓰기·논문·보고서
- 발표·PPT·프레젠테이션
- 이메일·연락·답장
- 공부·시험 준비
- 운동·습관 만들기
- 정리·청소·집안일
- 의사결정·결단
- 행정·서류·세금
- 관계·사과·고백
- 기타

#### Card 2 — 회피처 (UserProfile.avoidance_destination)
> **"도망치면 주로 어디로 가나요?"**

옵션 (single-select):
- 유튜브·릴스·쇼츠
- 잠·침대·휴식
- SNS·인스타·X
- 음식·간식·배달
- 게임
- 넷플릭스·OTT
- 인터넷 서핑·뉴스
- 기타

#### Card 3 — 페르소나 선택 (UserProfile.active_persona_id)
> **"누가 당신에게 말을 걸어줄까요?"**

5 default 페르소나 미리보기 카드 + Custom 빌더 진입점:

| 카드 | 한 줄 미리보기 | perspective | 톤 |
|---|---|---|---|
| 🌙 **내일의 나** | "내일 9시 5분 전의 내가 너에게..." | 1st | Sharp |
| 🌅 **1년 후의 나** | "1년 뒤의 내가 짧게 한 마디" | 1st (장기) | Quiet |
| 🤝 **친한 친구 ㅈㅅ** | "야 너 지금 뭐 하는 거야ㅋ" | 2nd | Witty |
| 🎯 **엄격한 코치** | "10분 줄게. 한 줄만 쓰고 와." | 2nd | Sharp+ |
| 👁️ **객관 옵저버** | "그는 지금 23시 47분, 슬라이드 0장..." | 3rd | Quiet |
| ✨ **내가 직접 만들래요** | Custom Persona Builder 진입 | - | - |

각 페르소나 카드를 탭하면 **30초 샘플 시나리오** 미리보기 (가상 회피 입력에 대한 카드 1개). 사용자가 가장 와닿는 톤 선택.

### Bonus (2 카드, ~60초 추가)

#### Card 4 — 두려움 앵커 (UserProfile.fear_anchor, optional)
> **"당신이 제자리에 머물 때 가장 좋아할 사람은 누구인가요?"**

옵션 (single-select, 능청맞은 표현):
- 나를 한심하게 보는 옛 동기
- 내가 따라잡지 못한 친구
- 어쩐지 잘 살고 있는 그 사람
- 부모의 기대와 다른 모습 (선택 시 §6.5 F 한국형 트리거 발동 — 사용 시 신중)
- 어제의 나
- 내가 약속한 미래의 나
- 기타·없음

#### Card 5 — 회복 패턴 (UserProfile.recovery_pattern, optional)
> **"과거에 늪에서 당신을 꺼내준 단 하나의 행동은?"**

자유 텍스트 (한 줄, 80자 한도) + 4 quick option:
- 첫 문장 쓰기
- 운동복 갈아입기
- 한 페이지만 읽기
- 메시지 한 줄 보내기
- (자유 입력)

## 2. UserProfile 초기화 스키마

```python
{
    "user_id": "device_local_uuid",
    "created_at": "2026-05-26T...",
    "slots": {
        "trigger_category": {"value": "글쓰기", "confidence": 1.0, "source": "onboarding_card_1"},
        "avoidance_destination": {"value": "유튜브", "confidence": 1.0, "source": "onboarding_card_2"},
        "active_persona_id": {"value": "persona_default_morning_self", "confidence": 1.0, "source": "onboarding_card_3"},
        "fear_anchor": {"value": "내가 따라잡지 못한 친구", "confidence": 0.7, "source": "onboarding_card_4", "optional": true},
        "recovery_pattern": {"value": "운동복 갈아입기", "confidence": 0.7, "source": "onboarding_card_5", "optional": true},
    },
    "completion_percent": 60.0,  # Required 완료=60%, Bonus 포함=100%
    "forbidden_topics": [],
    "preferred_tone_mode_attribute": null,  # 페르소나 attribute로 흡수
}
```

## 3. UX 플로우

```
앱 첫 실행
   ↓
[Welcome Card] "5장만 카드를 골라주세요. 60초면 첫 시나리오 가능, 120초면 깊은 개인화."
   ↓
Card 1 (트리거) → Card 2 (회피처) → Card 3 (페르소나)
   ↓
[Branch] "여기까지로 충분해 (60초)"  vs  "조금 더 깊이 (60초 더)"
   ↓
[Branch=깊이] Card 4 (두려움 앵커) → Card 5 (회복 패턴)
   ↓
[First Scenario Generation] 가상 회피 입력 1건으로 첫 시나리오 카드 생성 → 사용자 검토 + 톤 피드백 6선택지
   ↓
UserProfile 저장 + 메인 화면 진입
```

## 4. 60초 ESCape 보장

3 카드만으로도 시나리오 생성 가능. 4-5번 카드는 절대 강제 X. "여기까지로 충분해" 버튼은 Card 3 직후 등장.

## 5. 페르소나 선택 미리보기 — 가상 입력

미리보기 카드 생성에 사용할 고정 가상 입력:
> "내일 발표인데 슬라이드 0장. 새벽 1시야."

각 페르소나가 같은 입력에 어떻게 응답하는지 보여줘서 사용자가 톤 차이 체감.

(미리보기 샘플은 G011 PersonaSystem에서 5 페르소나 × 1 입력 = 5 카드 사전 생성 후 캐시)

## 6. 카드 비주얼 (designer UI_UX_DIRECTION_v1.md 연계)

- 카드 등장 300ms fade-in (광고 팝업 회피)
- 옵션은 가로 스크롤 또는 카드형 그리드
- 선택 시 0.4s 부드러운 색 변화
- 진행도: 상단에 "1/5" 점 표시, 명도 낮음
- Self-Destruct 버튼: 우상단 영구 노출 (opacity 40%)
- 사회적 노출 자동 보호: 30초 무활동 시 본문 블러

## 7. Sensitive Topic 자동 검출

Card 4(두려움 앵커) 선택 시:
- "부모의 기대와 다른 모습" 선택 → §6.5 F 한국형 트리거 발동, `forbidden_topics`에 "부모 기대" 자동 추가 + 사용자에게 "이 주제를 시나리오에 쓰지 않을게요" 안내

Card 5(회복 패턴) 자유 입력 시:
- 절대 금지어 키워드 검출 → 입력 거부 + 사유 안내

## 8. G005 Definition of Done

- [ ] 5 카드 명세 (본 문서)
- [ ] UserProfile 초기화 스키마
- [ ] TUI ASCII 와이어프레임 (onboarding_wireframes_v1.md)
- [ ] 웹 prototype mock (Markdown 또는 HTML 스켈레톤)
- [ ] onboarding 시뮬레이터 (scripts/onboarding_simulator.py) — 사용자 본인 1회 시뮬레이션
- [ ] 페르소나 선택 미리보기 캐시 명세 (G011 의존)
- [ ] Sensitive topic 자동 검출 로직 명세

## 9. 의존 스토리

- G003 DataModel — UserProfile 슬롯 스키마 구현
- G011 PersonaSystem — 5 default 페르소나 + 미리보기 시나리오
- G004 HITLProbeEngine — 슬롯 완성도 추적 → Phase 1 후 Phase 2 활성화
- G008 MVPRelease — 디자인 시스템 v1 적용
