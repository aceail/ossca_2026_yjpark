"""Wave 4 — Calendar API + ICS feed export.

JSON API: GET /api/calendar/{user_id}/events?from=&to=
  → Task와 향후 ScenarioCard 결과를 캘린더 이벤트 형태로 반환.

ICS feed: GET /api/calendar/{user_id}/feed.ics?token=<device_token>
  → Google Calendar / Apple Calendar에서 URL subscribe 가능.
  외부 캘린더가 polling할 때 헤더를 못 보내므로 query param에 토큰을 받음
  (P0-8 device token 그대로 재사용).

ICS는 RFC 5545 plain text — 외부 라이브러리 없이 stdlib로 생성.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel

from backend.deps import assert_user_matches, get_db, require_token

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


# ────────────────────────────────────────────────────────────────────
# JSON events
# ────────────────────────────────────────────────────────────────────


class CalendarEvent(BaseModel):
    id: str
    source: str           # "task" 등
    title: str
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None


class CalendarEventsResponse(BaseModel):
    user_id: str
    events: list[CalendarEvent]


def _task_to_event(row: sqlite3.Row) -> CalendarEvent:
    color = {
        "open": "#3B6B9A",
        "done": "#7A9A30",
        "abandoned": "#888888",
    }.get(row["status"], "#888888")
    return CalendarEvent(
        id=f"task-{row['id']}",
        source="task",
        title=row["title"],
        starts_at=row["deadline_at"],
        ends_at=row["deadline_at"],
        status=row["status"],
        color=color,
    )


@router.get("/{user_id}/events", response_model=CalendarEventsResponse)
def list_events(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    _auth: str = Depends(require_token),
) -> CalendarEventsResponse:
    rows = conn.execute(
        """SELECT id, title, deadline_at, status FROM Task
           WHERE user_id = ? AND deadline_at IS NOT NULL
           ORDER BY deadline_at ASC""",
        (user_id,),
    ).fetchall()
    return CalendarEventsResponse(
        user_id=user_id,
        events=[_task_to_event(r) for r in rows],
    )


# ────────────────────────────────────────────────────────────────────
# ICS feed (RFC 5545)
# ────────────────────────────────────────────────────────────────────


_ICS_ESCAPE_RE = re.compile(r"([,;\\])")


def _escape_ics_text(text: str) -> str:
    """ICS 텍스트 escape: \\ , ; → 백슬래시 prefix + newline → \\n."""
    text = _ICS_ESCAPE_RE.sub(r"\\\1", text)
    return text.replace("\r\n", "\\n").replace("\n", "\\n")


def _to_ics_dt(iso: str) -> Optional[str]:
    """ISO 8601 → ICS UTC format YYYYMMDDTHHMMSSZ."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y%m%dT%H%M%SZ")


def build_ics_feed(user_id: str, tasks: list[sqlite3.Row]) -> str:
    """tasks → ICS calendar text. fold lines at 75 chars per RFC 5545 §3.1."""
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//내일의 너//naeil-local//KO",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:내일의 너 - {user_id[:8]}",
    ]
    for t in tasks:
        deadline = t["deadline_at"]
        if not deadline:
            continue
        dt = _to_ics_dt(deadline)
        if not dt:
            continue
        status_map = {
            "open": "CONFIRMED",
            "done": "COMPLETED",
            "abandoned": "CANCELLED",
        }
        ev_status = status_map.get(t["status"], "CONFIRMED")
        title = _escape_ics_text(t["title"])
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:naeil-task-{t['id']}@local",
            f"DTSTAMP:{now_stamp}",
            f"DTSTART:{dt}",
            f"DTEND:{dt}",
            f"SUMMARY:{title}",
            f"STATUS:{ev_status}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    # RFC 5545 §3.1 line folding: 75 octets — Korean이 multi-byte라 보수적
    folded: list[str] = []
    for line in lines:
        if len(line) <= 73:
            folded.append(line)
            continue
        head, rest = line[:73], line[73:]
        folded.append(head)
        while rest:
            chunk, rest = rest[:72], rest[72:]
            folded.append(" " + chunk)
    return "\r\n".join(folded) + "\r\n"


@router.get("/{user_id}/feed.ics")
def ics_feed(
    user_id: str = Path(...),
    token: str = Query(..., description="device_token (P0-8) — 외부 캘린더 polling용"),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """외부 캘린더 subscribe용 ICS 피드.

    외부 클라이언트는 Authorization 헤더를 못 보내므로 query param `token`으로
    동일 device_token을 검증. 토큰 자체가 capability이므로 URL 누출 시 read-only
    이지만 작업 목록 전체가 노출됨 — README에 명시.
    """
    row = conn.execute(
        "SELECT id FROM User WHERE id = ? AND device_token = ?",
        (user_id, token),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token for this user")

    tasks = conn.execute(
        """SELECT id, title, deadline_at, status FROM Task
           WHERE user_id = ? AND deadline_at IS NOT NULL""",
        (user_id,),
    ).fetchall()

    ics_text = build_ics_feed(user_id, tasks)
    return Response(
        content=ics_text,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="naeil-{user_id[:8]}.ics"',
        },
    )
