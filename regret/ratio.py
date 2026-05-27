"""P0-11 두 얼굴 비율 스케줄러 — regret:recovery 자동 균형.

핵심 디자인 원칙: 미래 자아는 후회 카드만 보여주지 않는다.
같은 사용자에게 regret만 누적되면 Slow Harm `failure_imagery_ratio`가
elevated로 밀려 게이트가 닫히고, 도구 자체가 우울 강화제가 된다.

본 모듈은 최근 N개 카드의 regret/recovery 비율을 보고, 한쪽이 과도하면
다음 카드 생성 시 LLM에 부드러운 hint를 주입한다. 강제 분류가 아닌 권장.

- soft_stop / paradoxical_validation은 안전 카드이므로 분모에서 제외.
- elevated/high 신호와 결합되면 안전 게이트가 ratio hint보다 우선.
"""

from __future__ import annotations

import sqlite3
from typing import Literal


CardTypeHint = Literal["regret", "recovery", "auto"]

RATIO_LOOKBACK = 5
RATIO_SKEW_THRESHOLD = 0.7  # ≥70%면 반대 유형 권장


def recommend_card_type(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    lookback: int = RATIO_LOOKBACK,
) -> CardTypeHint:
    """최근 N개 카드(regret+recovery)의 비율로 다음 카드 유형 권장.

    Returns:
        "recovery" — regret 비율이 임계 이상이면 recovery 권장.
        "regret"   — recovery 비율이 임계 이상이면 regret 권장.
        "auto"     — 그 외(균형 OK 또는 표본 부족). LLM 자유.
    """
    rows = conn.execute(
        """SELECT sc.card_type
           FROM ScenarioCard sc
           JOIN AvoidanceSession a ON sc.avoidance_session_id = a.id
           WHERE a.user_id = ?
             AND sc.card_type IN ('regret', 'recovery')
           ORDER BY sc.created_at DESC
           LIMIT ?""",
        (user_id, lookback),
    ).fetchall()

    if len(rows) < lookback:
        return "auto"  # 표본 부족 — 강제하지 않음

    types = [r["card_type"] for r in rows]
    regret_n = types.count("regret")
    recovery_n = types.count("recovery")
    total = regret_n + recovery_n
    if total == 0:
        return "auto"

    if regret_n / total >= RATIO_SKEW_THRESHOLD:
        return "recovery"
    if recovery_n / total >= RATIO_SKEW_THRESHOLD:
        return "regret"
    return "auto"


def build_ratio_hint(hint: CardTypeHint) -> str | None:
    """LLM system_prompt 끝에 부드럽게 주입할 한 줄."""
    if hint == "recovery":
        return (
            "[비율 권장] 최근 카드들이 후회 쪽으로 쏠려 있습니다. "
            "이번에는 가능하면 card_type='recovery' 카드를 생성하세요."
        )
    if hint == "regret":
        return (
            "[비율 권장] 최근 카드들이 회복 쪽으로 쏠려 있습니다. "
            "이번에는 가능하면 card_type='regret' 카드를 생성하세요."
        )
    return None
