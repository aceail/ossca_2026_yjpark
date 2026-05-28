"""Sprint 22 — Daily Briefing.

비서가 사용자 chat 진입 시 오늘 첫 1회 알아서 브리핑한다:
"오늘 일정 N개. 마감 임박 M개. 어제 폴더 +K. 추천 다음 행동..."

Sprint 31 — Smart Briefing 2.0: momentum(streak/stagnation) + adaptive
tendencies + RAG episodic recall을 통합. 모든 신규 신호는 fail-soft —
미존재 시 기존 v1 brief와 동일 결과.

UserMemory의 `_last_briefing_at` 으로 같은 KST 날짜 재호출 skip.
LLM 미가능·실패 시 결정적 fallback 텍스트로 graceful.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from agent.tracing import trace_subsystem
from pipeline.memory import upsert_memory

LAST_KEY = "_last_briefing_at"

TONE_LINES = {
    "quiet": "오늘 하나만 가볍게 시작해볼까?",
    "witty": "오늘 한 놈만 패자.",
    "sharp": "오늘 가장 미루던 거 먼저 손대.",
    "savage": "변명 그만, 마감 임박부터.",
}


def _now_kst() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=9)


def _today_kst_str(now: Optional[datetime] = None) -> str:
    n = now or _now_kst()
    return n.strftime("%Y-%m-%d")


def should_brief(
    conn: sqlite3.Connection, user_id: str, *, now: Optional[datetime] = None,
) -> bool:
    """오늘 (KST 기준) 아직 브리핑 안 했으면 True."""
    today = _today_kst_str(now)
    row = conn.execute(
        "SELECT value FROM UserMemory WHERE user_id = ? AND key = ?",
        (user_id, LAST_KEY),
    ).fetchone()
    if not row:
        return True
    last_str = (row["value"] or "")[:10]
    return last_str != today


_KST = timezone(timedelta(hours=9))


def _compute_momentum(
    conn: sqlite3.Connection, user_id: str, *, now: Optional[datetime] = None,
) -> dict:
    """오늘 기준 연속 활성 일수 + stagnant open tasks. fail-soft 빈 dict.

    now가 None이면 현재 UTC. now는 tz-aware로 가정 (naive면 UTC로 간주).
    일별 윈도우는 KST 자정 기준으로 생성하고 UTC ISO로 변환해 저장값과 비교.
    """
    try:
        if now is None:
            n_utc = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            n_utc = now.replace(tzinfo=timezone.utc)
        else:
            n_utc = now.astimezone(timezone.utc)
        today = n_utc.astimezone(_KST).date()
        activity: dict[str, bool] = {}
        for delta in range(14):
            d = today - timedelta(days=delta)
            day_start_kst = datetime(d.year, d.month, d.day, tzinfo=_KST)
            day_end_kst = day_start_kst + timedelta(days=1)
            start = day_start_kst.astimezone(timezone.utc).isoformat()
            end = day_end_kst.astimezone(timezone.utc).isoformat()
            closed_n = conn.execute(
                "SELECT COUNT(*) FROM Task "
                "WHERE user_id=? AND status='done' AND updated_at >= ? AND updated_at < ?",
                (user_id, start, end),
            ).fetchone()[0]
            snap_n = conn.execute(
                "SELECT COUNT(*) FROM FolderSnapshot s JOIN Task t ON t.id = s.task_id "
                "WHERE t.user_id=? AND s.taken_at >= ? AND s.taken_at < ?",
                (user_id, start, end),
            ).fetchone()[0]
            chat_n = conn.execute(
                "SELECT COUNT(*) FROM ChatMessage m "
                "JOIN ChatSession s ON s.id = m.chat_session_id "
                "WHERE s.user_id=? AND m.role='user' "
                "AND m.created_at >= ? AND m.created_at < ?",
                (user_id, start, end),
            ).fetchone()[0]
            activity[d.isoformat()] = bool(closed_n or snap_n or chat_n >= 3)

        streak = 0
        last_active: Optional[str] = None
        for delta in range(14):
            d_str = (today - timedelta(days=delta)).isoformat()
            if activity.get(d_str):
                streak += 1
                if last_active is None:
                    last_active = d_str
            else:
                break

        cutoff = (n_utc - timedelta(days=5)).isoformat()
        stag_rows = conn.execute(
            "SELECT title, updated_at FROM Task "
            "WHERE user_id=? AND status='open' AND updated_at < ? "
            "ORDER BY updated_at LIMIT 3",
            (user_id, cutoff),
        ).fetchall()
        stagnant = []
        for r in stag_rows:
            days = 0
            try:
                dt = datetime.fromisoformat(r["updated_at"])
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days = max(0, (n_utc - dt).days)
            except (ValueError, TypeError):
                days = 0
            stagnant.append({"title": r["title"], "days": days})

        return {
            "streak_days": streak,
            "last_active_date": last_active,
            "stagnant_tasks": stagnant,
        }
    except sqlite3.Error:
        return {"streak_days": 0, "last_active_date": None, "stagnant_tasks": []}


def _load_tendencies(conn: sqlite3.Connection, user_id: str) -> dict:
    """Sprint 28 산출물 로드. None/실패 시 빈 dict.

    좁은 예외만 잡음 — schema rename 같은 코드 버그는 surface up.
    """
    try:
        from pipeline.tendencies import load_from_memory
    except ImportError:
        return {}
    try:
        loaded = load_from_memory(conn, user_id)
    except sqlite3.Error:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _recall_rag(
    conn: sqlite3.Connection,
    user_id: str,
    open_titles: list[str],
) -> list[dict]:
    """RAG episodic 회상. open task 제목들을 query로 사용. fail-soft.

    좁은 예외만 잡음 — retriever 내부에 이미 fail-soft 있음.
    """
    if not open_titles:
        return []
    try:
        from rag.retriever import recall_semantic
    except ImportError:
        return []
    try:
        query = " ".join(open_titles[:5])
        return recall_semantic(
            conn, user_id=user_id, query=query,
            kinds=("chat", "memory", "task"), k=3,
        )
    except sqlite3.Error:
        return []


def collect_briefing_data(
    conn: sqlite3.Connection, user_id: str, *, now: Optional[datetime] = None,
) -> dict:
    """오늘·임박·진척 + Sprint 31 신호(momentum/tendencies/rag_recalls)."""
    now = now or _now_kst()
    today = now.date()
    cutoff_3d = (now + timedelta(days=3)).date()

    open_tasks = conn.execute(
        """SELECT id, title, deadline_at, folder_path FROM Task
           WHERE user_id = ? AND status = 'open'
           ORDER BY deadline_at IS NULL, deadline_at""",
        (user_id,),
    ).fetchall()

    imminent: list[dict] = []
    overdue: list[dict] = []
    no_deadline: list[dict] = []
    for t in open_tasks:
        if not t["deadline_at"]:
            no_deadline.append(dict(t))
            continue
        try:
            dt = datetime.fromisoformat(t["deadline_at"])
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        d = dt.date()
        if d < today:
            overdue.append(dict(t))
        elif d <= cutoff_3d:
            imminent.append(dict(t))

    yesterday_cut = (now - timedelta(days=1)).isoformat()
    progress = conn.execute(
        """SELECT t.title, COUNT(s.id) AS snap_count
           FROM Task t LEFT JOIN FolderSnapshot s
             ON s.task_id = t.id AND s.taken_at >= ?
           WHERE t.user_id = ? AND t.status = 'open' AND t.folder_path IS NOT NULL
           GROUP BY t.id""",
        (yesterday_cut, user_id),
    ).fetchall()
    progressed_titles = [p["title"] for p in progress if p["snap_count"] > 0]

    momentum = _compute_momentum(conn, user_id, now=now)
    tendencies = _load_tendencies(conn, user_id)
    rag_recalls = _recall_rag(
        conn, user_id, [dict(t)["title"] for t in open_tasks],
    )

    return {
        "today": _today_kst_str(now),
        "open_count": len(open_tasks),
        "overdue": overdue,
        "imminent": imminent,
        "no_deadline_count": len(no_deadline),
        "progressed_titles": progressed_titles,
        "momentum": momentum,
        "tendencies": tendencies,
        "rag_recalls": rag_recalls,
    }


def _render_brief_lines(data: dict) -> list[str]:
    """Adaptive 3-7 line renderer. 데이터 있는 차원만 emit."""
    lines = [
        f"📅 오늘 {data.get('today', '')}. 진행 중 작업 {data.get('open_count', 0)}개."
    ]

    overdue = data.get("overdue") or []
    imminent = data.get("imminent") or []
    progressed = data.get("progressed_titles") or []
    momentum = data.get("momentum") or {}
    streak = int(momentum.get("streak_days") or 0)
    stagnant = momentum.get("stagnant_tasks") or []
    recalls = data.get("rag_recalls") or []
    tendencies = data.get("tendencies") or {}

    if overdue:
        titles = ", ".join(t["title"] for t in overdue[:3])
        lines.append(f"⏰ 마감 지남: {titles}")
    if imminent:
        items = ", ".join(
            f"{t['title']} ({(t.get('deadline_at') or '')[:10]})" for t in imminent[:3]
        )
        lines.append(f"🔔 마감 임박(3일 내): {items}")
    if progressed:
        lines.append("📁 어제 진척 있던 폴더: " + ", ".join(progressed[:3]))
    if streak >= 2:
        lines.append(f"🔥 {streak}일 연속 뭐든 진행 중")
    elif streak == 0 and stagnant:
        s = stagnant[0]
        lines.append(f"⏳ \"{s.get('title', '')}\"은 {s.get('days', 0)}일째 멈춰있어")
    if recalls:
        top = recalls[0]
        snippet = (top.get("content") or "")[:60].replace("\n", " ")
        lines.append(f"💭 {top.get('kind', '')}에서 비슷한 맥락: {snippet}")

    any_signal = bool(overdue or imminent or progressed or streak or stagnant or recalls)
    if any_signal:
        tone = tendencies.get("tone_preference") or "quiet"
        lines.append(TONE_LINES.get(tone, TONE_LINES["quiet"]))
    else:
        lines.append("오늘 큰 부담 없어 보여. 한 가지만 골라 시작해볼래?")

    return lines


def _fallback_brief(data: dict) -> str:
    """LLM 없이도 동작하는 결정적 브리핑 텍스트."""
    return "\n".join(_render_brief_lines(data))


def build_briefing_prompt(data: dict) -> str:
    tone = ((data.get("tendencies") or {}).get("tone_preference")) or "quiet"
    return (
        "당신은 사용자의 친근한 개인 비서입니다. "
        "오늘 첫 브리핑을 한국어로 작성하세요.\n"
        f"어조: {tone} "
        "(quiet=차분, witty=가벼운 농담, sharp=단호, savage=거칠게).\n"
        "규칙:\n"
        "- 최대 6줄. 데이터가 *있는* 차원만 사용. 없으면 만들어내지 마라.\n"
        "- 줄 시작 이모지 OK (📅·⏰·🔔·🔥·⏳·💭).\n"
        "- 마지막 줄은 오늘 시작할 작은 행동 하나만 제안.\n"
        "- 신호 매핑: momentum.streak_days=연속 활성 일수, "
        "rag_recalls=의미 검색으로 찾은 과거 비슷한 맥락, "
        "tendencies=사용자 평소 패턴.\n\n"
        f"근거 신호:\n{json.dumps(data, ensure_ascii=False, default=str)}\n"
    )


LLMCallFn = Callable[[list[dict]], dict]


@trace_subsystem("briefing")
def generate_briefing(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    now: Optional[datetime] = None,
    call_fn: Optional[LLMCallFn] = None,
    force: bool = False,
) -> dict:
    """오늘 첫 브리핑 한 줄을 생성하고 chat session에 assistant 메시지로 INSERT.

    force=True면 cooldown 무시. session 없으면 새로 만들어 INSERT.
    """
    if not force and not should_brief(conn, user_id, now=now):
        return {"sent": False, "reason": "already_briefed_today"}

    data = collect_briefing_data(conn, user_id, now=now)

    body = ""
    if call_fn is not None:
        try:
            msg = call_fn([{"role": "system", "content": build_briefing_prompt(data)}])
            body = (msg.get("content") if isinstance(msg, dict) else str(msg)) or ""
            body = body.strip()
        except Exception:
            body = ""

    if not body:
        body = _fallback_brief(data)

    row = conn.execute(
        "SELECT id FROM ChatSession WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if row:
        sid = row["id"]
    else:
        from pipeline.chat import create_chat_session
        sid = create_chat_session(conn, user_id=user_id, persona_id=None,
                                  title="오늘 첫 브리핑")

    from pipeline.chat import _record_message
    msg_id = _record_message(conn, sid, "assistant", body)

    upsert_memory(conn, user_id=user_id, key=LAST_KEY,
                  value=(now or _now_kst()).isoformat(), source="briefing")

    return {"sent": True, "session_id": sid, "message_id": msg_id,
            "content": body, "data": data}
