"""Sprint 22 — Daily Briefing.

비서가 사용자 chat 진입 시 오늘 첫 1회 알아서 브리핑한다:
"오늘 일정 N개. 마감 임박 M개. 어제 폴더 +K. 추천 다음 행동..."

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


def collect_briefing_data(
    conn: sqlite3.Connection, user_id: str, *, now: Optional[datetime] = None,
) -> dict:
    """오늘·임박·진척 요약. LLM 없이도 자체 fallback 출력 가능."""
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

    # 어제 vs 오늘 폴더 스냅샷 비교 (가벼운 진척)
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

    return {
        "today": _today_kst_str(now),
        "open_count": len(open_tasks),
        "overdue": overdue,
        "imminent": imminent,
        "no_deadline_count": len(no_deadline),
        "progressed_titles": progressed_titles,
    }


def _fallback_brief(data: dict) -> str:
    """LLM 없이도 동작하는 결정적 브리핑 텍스트."""
    parts = [f"📅 오늘 {data['today']}. 진행 중 작업 {data['open_count']}개."]
    if data["overdue"]:
        titles = ", ".join(t["title"] for t in data["overdue"][:3])
        parts.append(f"⏰ 마감 지남: {titles}")
    if data["imminent"]:
        items = ", ".join(
            f"{t['title']} ({t['deadline_at'][:10]})" for t in data["imminent"][:3]
        )
        parts.append(f"🔔 마감 임박(3일 내): {items}")
    if data["progressed_titles"]:
        parts.append("📁 어제 진척 있던 폴더: " + ", ".join(data["progressed_titles"][:3]))
    if not data["overdue"] and not data["imminent"] and not data["progressed_titles"]:
        parts.append("오늘 큰 부담 없어 보여. 한 가지만 골라 시작해볼래?")
    return "\n".join(parts)


def build_briefing_prompt(data: dict) -> str:
    return (
        "당신은 사용자의 친근한 개인 비서입니다. 오늘 첫 브리핑을 한국어로 3~5줄로 작성하세요. "
        "비난 없이, 직설적이지만 짧게. 줄 시작에 ✅·📅·⏰·🔔 같은 짧은 이모지 OK. "
        "마지막 줄에는 오늘 시작할 작은 행동 하나만 제안.\n\n"
        f"근거 데이터:\n{json.dumps(data, ensure_ascii=False)}\n"
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

    force=True면 cooldown 무시. session 없으면 새로 만들지 않고 None 반환
    (호출자가 session_id를 책임지지 않게).
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

    # 사용자의 가장 최근 ChatSession에 INSERT. 없으면 새로 생성.
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

    # cooldown 기록 (KST 오늘 날짜)
    upsert_memory(conn, user_id=user_id, key=LAST_KEY,
                  value=(now or _now_kst()).isoformat(), source="briefing")

    return {"sent": True, "session_id": sid, "message_id": msg_id,
            "content": body, "data": data}
