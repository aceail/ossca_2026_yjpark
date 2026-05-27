"""Wave 3 — Tone matrix for automated follow-ups.

세 축으로 톤·메시지를 결정한다:
  1. 마감 거리 (days_until_deadline)
  2. 폴더 진척도 (latest snapshot vs second-latest)
  3. Slow Harm 신호 (normal | elevated | high)

핵심 규칙:
- Slow Harm `high` → follow-up 자체 skip (soft_stop 일관).
- Slow Harm `elevated` → 모든 follow-up이 Quiet 톤으로 강제 완화.
- 마감 < 0 (지남) → 회고 톤 1회만.
- 진척 변화 있음 → 격려 톤. 변화 없음 → 추궁 톤.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Tone = Literal["quiet", "witty", "sharp", "savage"]


@dataclass(frozen=True)
class FollowupDecision:
    should_send: bool
    cooldown_hours: int     # 다음 follow-up까지 최소 대기
    tone: Tone
    message: str            # 사용자에게 보일 어시스턴트 메시지


def _phrase_for(tone: Tone, *,
                title: str,
                days: int,
                progressed: bool,
                deadline_passed: bool) -> str:
    """톤·상황 조합으로 메시지 문자열 생성. 짧고 한국어 1인칭/2인칭."""
    if deadline_passed:
        if progressed:
            return f"'{title}' 마감 지났어. 마지막 push는 봤어. 결과 한 줄 적어줄래?"
        return f"'{title}' 마감 지났어. 폴더는 그대로네. 어떻게 됐는지 짧게라도 알려줘."

    # 진척 변화 + 톤별 표현
    if tone == "quiet":
        if progressed:
            return f"'{title}' D-{days}. 한 발자국 움직였네. 무리하지 말고 한 줄만 더."
        return f"'{title}' D-{days}. 오늘은 여기까지여도 괜찮아. 한 줄만 적어볼래?"
    if tone == "witty":
        if progressed:
            return f"'{title}' D-{days}. 오 시작했네 👀 한 줄만 보여줘."
        return f"'{title}' D-{days}. 아직 안 켰지? 일단 파일 켜기, 그것만."
    if tone == "sharp":
        if progressed:
            return f"'{title}' D-{days}. 움직이긴 하네. 다음 단락 하나, 30분 안."
        return f"'{title}' D-{days}. 어제부터 폴더 그대로야. 뭐가 막혔어?"
    # savage
    if progressed:
        return f"'{title}' D-{days}. 진행은 있는데 속도가 모자라. 지금 30분 박아."
    return f"'{title}' D-{days}. 폴더 0개야. '거의 다 했어' 같은 말은 안 통해."


def decide_followup(
    *,
    title: str,
    days_until_deadline: Optional[int],   # None = 마감 없음
    last_followup_hours_ago: Optional[float],
    progressed: bool,
    signal_level: str = "normal",
    persona_tone: Optional[str] = None,
) -> FollowupDecision:
    """다음 follow-up을 보낼지·언제·어떤 톤으로 결정.

    persona_tone은 페르소나가 가진 기본 톤(Quiet/Sharp/Witty/Savage). 환경(마감
    거리·신호)에 따라 한 단계씩 조절된다.
    """
    # 0. 안전 게이트
    if signal_level == "high":
        return FollowupDecision(False, 24, "quiet", "")

    # 1. 마감 없음 → 부드러운 daily 체크인만
    if days_until_deadline is None:
        if last_followup_hours_ago is not None and last_followup_hours_ago < 24:
            return FollowupDecision(False, 24, "quiet", "")
        tone: Tone = "quiet" if signal_level == "elevated" else "witty"
        return FollowupDecision(
            True, 24, tone,
            f"'{title}' 진행 어떻게 돼가? 한 줄만 적어줘.",
        )

    # 2. 마감 거리 → cooldown + 기본 톤
    if days_until_deadline > 3:
        return FollowupDecision(False, 24, "quiet", "")  # 너무 멀음, 묵묵히 기다림
    if days_until_deadline >= 2:
        base_cooldown = 24
        base_tone: Tone = "witty"
    elif days_until_deadline == 1:
        base_cooldown = 6
        base_tone = "sharp"
    elif days_until_deadline == 0:
        base_cooldown = 2
        base_tone = "savage" if not progressed else "sharp"
    else:
        # 마감 지남 — 회고 1회만 (24h cooldown)
        base_cooldown = 24
        base_tone = "quiet"

    # 3. Slow Harm elevated → 강제 Quiet
    if signal_level == "elevated":
        base_tone = "quiet"

    # 4. 페르소나 기본 톤이 Quiet이면 모든 단계에서 Quiet 유지
    if (persona_tone or "").lower() == "quiet":
        base_tone = "quiet"

    # 5. cooldown 체크
    if last_followup_hours_ago is not None and last_followup_hours_ago < base_cooldown:
        return FollowupDecision(False, base_cooldown, base_tone, "")

    msg = _phrase_for(
        base_tone,
        title=title,
        days=max(days_until_deadline, 0),
        progressed=progressed,
        deadline_passed=days_until_deadline < 0,
    )
    return FollowupDecision(True, base_cooldown, base_tone, msg)
