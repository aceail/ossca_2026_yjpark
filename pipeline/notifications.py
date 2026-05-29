"""Sprint 39 — Smart Push Notifications.

compute_due_notifications: 트리거 평가 → max 3건 후보 산출.
send_pending: 후보별 NotificationLog INSERT + VAPID send.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from agent.tracing import trace_subsystem

_KST = timezone(timedelta(hours=9))
_DEFAULT_QUIET_START = 22
_DEFAULT_QUIET_END = 8
_DEFAULT_MAX_PER_DAY = 3
_MOMENTUM_STALL_DAYS = 5
_DEADLINE_IMMINENT_DAYS = 3
_PREFS_KEY = "notification_prefs"


def _load_prefs(conn: sqlite3.Connection, user_id: str) -> dict:
    row = conn.execute(
        "SELECT value FROM UserMemory WHERE user_id = ? AND key = ?",
        (user_id, _PREFS_KEY),
    ).fetchone()
    if not row:
        return {}
    try:
        parsed = json.loads(row["value"])
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _in_quiet_hours(now: datetime, prefs: dict) -> bool:
    start = int(prefs.get("quiet_start", _DEFAULT_QUIET_START))
    end = int(prefs.get("quiet_end", _DEFAULT_QUIET_END))
    hr = now.astimezone(_KST).hour
    if start == end:
        return False
    if start < end:
        return start <= hr < end
    # wrap (예: 22 → 8)
    return hr >= start or hr < end


def _today_count(conn: sqlite3.Connection, user_id: str, now: datetime) -> int:
    day = now.astimezone(_KST).date().isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM NotificationLog "
        "WHERE user_id = ? AND date(sent_at) = ?",
        (user_id, day),
    ).fetchone()
    return int(row["n"]) if row else 0


def _max_per_day(prefs: dict) -> int:
    try:
        v = int(prefs.get("max_per_day", _DEFAULT_MAX_PER_DAY))
        return max(0, min(10, v))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_PER_DAY


def _safe_recall(
    conn: sqlite3.Connection, user_id: str, query: str,
) -> Optional[str]:
    """RAG 회상 1줄. fail-soft None."""
    if not query:
        return None
    try:
        from rag.retriever import recall_semantic
    except ImportError:
        return None
    try:
        hits = recall_semantic(
            conn, user_id=user_id, query=query, kinds=("chat", "task"), k=1,
        )
    except sqlite3.Error:
        return None
    if not hits:
        return None
    snippet = (hits[0].get("content") or "")[:80].replace("\n", " ")
    return snippet or None


_TONE_PREFIXES = {
    "quiet": "",
    "witty": "",
    "sharp": "지금 ",
    "savage": "그만 미루고 ",
}


def _tone_prefix(conn: sqlite3.Connection, user_id: str) -> str:
    try:
        from pipeline.tendencies import load_from_memory
    except ImportError:
        return ""
    try:
        t = load_from_memory(conn, user_id)
    except sqlite3.Error:
        return ""
    if not isinstance(t, dict):
        return ""
    return _TONE_PREFIXES.get(t.get("tone_preference"), "")


def _build_deadline_candidates(
    conn: sqlite3.Connection, user_id: str, now: datetime,
) -> list[dict]:
    cutoff = (now + timedelta(days=_DEADLINE_IMMINENT_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT id, title, deadline_at FROM Task "
        "WHERE user_id = ? AND status = 'open' "
        "AND deadline_at IS NOT NULL AND deadline_at <= ? "
        "ORDER BY deadline_at",
        (user_id, cutoff),
    ).fetchall()
    out = []
    tone = _tone_prefix(conn, user_id)
    for r in rows:
        days_left = "곧"
        try:
            dt = datetime.fromisoformat(r["deadline_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            delta = (dt - now).days
            if delta < 0:
                days_left = f"{abs(delta)}일 지남"
            elif delta == 0:
                days_left = "오늘"
            else:
                days_left = f"{delta}일 남음"
        except (ValueError, TypeError):
            pass
        body = _safe_recall(conn, user_id, r["title"]) or "지금 30분만 손대보자."
        out.append({
            "key": f"deadline-task-{r['id']}",
            "kind": "deadline",
            "title": f"🔔 {r['title']} 마감 {days_left}",
            "body": f"{tone}{body}",
            "url": f"/tasks?focus={r['id']}",
            "actions": [
                {"action": f"done:{r['id']}", "title": "✓ 완료"},
                {"action": f"snooze:deadline-task-{r['id']}", "title": "30분 후"},
            ],
            "task_id": r["id"],
        })
    return out


def _build_momentum_candidates(
    conn: sqlite3.Connection, user_id: str, now: datetime,
) -> list[dict]:
    cutoff = (now - timedelta(days=_MOMENTUM_STALL_DAYS)).isoformat()
    row = conn.execute(
        "SELECT id, title, updated_at FROM Task "
        "WHERE user_id = ? AND status = 'open' AND updated_at < ? "
        "ORDER BY updated_at ASC LIMIT 1",
        (user_id, cutoff),
    ).fetchone()
    if not row:
        return []
    try:
        ut = datetime.fromisoformat(row["updated_at"])
        if ut.tzinfo is None:
            ut = ut.replace(tzinfo=timezone.utc)
        days = max(0, (now - ut).days)
    except (ValueError, TypeError):
        days = _MOMENTUM_STALL_DAYS
    tone = _tone_prefix(conn, user_id)
    body = _safe_recall(conn, user_id, row["title"]) or "한 줄만 적어보자."
    return [{
        "key": f"momentum-task-{row['id']}",
        "kind": "momentum",
        "title": f"⏳ '{row['title']}' {days}일 멈춤",
        "body": f"{tone}{body}",
        "url": f"/tasks?focus={row['id']}",
        "actions": [
            {"action": f"done:{row['id']}", "title": "✓ 완료"},
            {"action": f"snooze:momentum-task-{row['id']}", "title": "30분 후"},
        ],
        "task_id": row["id"],
    }]


def _build_peak_candidates(
    conn: sqlite3.Connection, user_id: str, now: datetime,
) -> list[dict]:
    try:
        from pipeline.tendencies import load_from_memory
    except ImportError:
        return []
    try:
        t = load_from_memory(conn, user_id)
    except sqlite3.Error:
        return []
    if not isinstance(t, dict):
        return []
    peak = t.get("peak_hour")
    try:
        peak_h = int(peak)
    except (TypeError, ValueError):
        return []
    n_kst = now.astimezone(_KST)
    # peak_h 30분 전 → 현재 시각이 (peak_h - 1) 시간대에 있을 때 트리거
    target_hour = (peak_h - 1) % 24
    if n_kst.hour != target_hour:
        return []
    return [{
        "key": f"peak-{n_kst.date().isoformat()}",
        "kind": "peak",
        "title": "📅 지금이 좋은 타이밍",
        "body": _tone_prefix(conn, user_id) + "평소 잘 풀리던 시간이야. 30분 집중 어때?",
        "url": "/chat",
        "actions": [
            {"action": "snooze:peak", "title": "30분 후"},
        ],
        "task_id": None,
    }]


@trace_subsystem("notifications")
def compute_due_notifications(
    conn: sqlite3.Connection, user_id: str, *, now: datetime,
) -> list[dict]:
    """현재 send 후보 list. quiet hours · cooldown · max/day 모두 적용."""
    prefs = _load_prefs(conn, user_id)
    if _in_quiet_hours(now, prefs):
        return []
    remaining = _max_per_day(prefs) - _today_count(conn, user_id, now)
    if remaining <= 0:
        return []

    deadline = _build_deadline_candidates(conn, user_id, now)
    momentum = _build_momentum_candidates(conn, user_id, now)
    # Peak는 다른 게 0일 때만
    other_count = len(deadline) + len(momentum)
    peak = _build_peak_candidates(conn, user_id, now) if other_count == 0 else []

    # 우선순위 순 + cooldown 필터
    candidates = deadline + momentum + peak
    today = now.astimezone(_KST).date().isoformat()
    existing = set(
        row["key"]
        for row in conn.execute(
            "SELECT key FROM NotificationLog "
            "WHERE user_id = ? AND date(sent_at) = ?",
            (user_id, today),
        ).fetchall()
    )
    fresh = [c for c in candidates if c["key"] not in existing]
    return fresh[:remaining]


@trace_subsystem("notifications")
def send_pending(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    now: datetime,
    push_fn: Optional[Callable[[sqlite3.Connection, str, dict], int]] = None,
) -> dict:
    """compute_due_notifications + NotificationLog INSERT + VAPID send.

    push_fn(conn, user_id, payload) → 발송된 subscription 수. 미지정이면
    backend.push.send_push_to_user 사용.
    """
    candidates = compute_due_notifications(conn, user_id, now=now)
    sent = []
    for c in candidates:
        try:
            cur = conn.execute(
                "INSERT INTO NotificationLog "
                "(user_id, key, kind, title, body, sent_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, c["key"], c["kind"], c["title"], c["body"], now.isoformat()),
            )
            conn.commit()
            nid = cur.lastrowid
        except sqlite3.IntegrityError:
            continue  # 중복 — cooldown 약속 유지
        payload = {
            "title": c["title"],
            "body": c["body"],
            "url": c["url"],
            "actions": c["actions"],
            "data": {"notification_id": nid, "url": c["url"]},
        }
        # Bare Exception OK: 3rd-party VAPID push (network/protocol errors) must not crash the loop. Degrade gracefully to dispatched=0.
        try:
            fn = push_fn or _default_push
            n = fn(conn, user_id, payload)
        except Exception:  # noqa: BLE001
            n = 0
        conn.execute(
            "UPDATE NotificationLog SET dispatched = ? WHERE id = ?", (n, nid),
        )
        conn.commit()
        sent.append({"id": nid, "key": c["key"], "kind": c["kind"], "dispatched": n})
    return {"user_id": user_id, "sent": sent, "count": len(sent)}


def _default_push(conn: sqlite3.Connection, user_id: str, payload: dict) -> int:
    from backend.push import send_push_to_user
    return send_push_to_user(conn, user_id, payload)


@trace_subsystem("notifications")
def redispatch_snoozed(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    push_fn: Optional[Callable[[sqlite3.Connection, str, dict], int]] = None,
) -> int:
    """snooze_until ≤ now 인 NotificationLog 행 재발송."""
    rows = conn.execute(
        "SELECT id, user_id, key, kind, title, body "
        "FROM NotificationLog "
        "WHERE snooze_until IS NOT NULL AND snooze_until <= ?",
        (now.isoformat(),),
    ).fetchall()
    n = 0
    for r in rows:
        payload = {
            "title": r["title"],
            "body": r["body"],
            "url": "/chat",
            "data": {"notification_id": r["id"]},
        }
        # Bare Exception OK: 3rd-party VAPID push (network/protocol errors) must not crash the loop. Degrade gracefully to dispatched=0.
        try:
            fn = push_fn or _default_push
            fn(conn, r["user_id"], payload)
            n += 1
        except Exception:  # noqa: BLE001
            pass
        conn.execute(
            "UPDATE NotificationLog SET snooze_until = NULL WHERE id = ?",
            (r["id"],),
        )
    conn.commit()
    return n
