"""Sprint 28 — Adaptive Self-Learning Loop.

Heuristic + LLM hybrid that extracts per-user behavioral tendencies and
persists them under UserMemory["adaptive_tendencies"] as a typed JSON.

Pipeline (called once per user per reflection cycle):

    extract_features(conn, user_id, now) -> dict   # heuristic-only
    llm_critic(features, recent_chat, call_fn)     # LLM-driven qualitative
    merge(features, critic_output) -> dict          # heuristic-first numeric
    save_to_memory(conn, user_id, merged)           # JSON into UserMemory

Read path (called from followup loop):

    load_from_memory(conn, user_id) -> dict | None
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from agent.tracing import trace_subsystem


_FEATURE_KEYS = (
    "chat_count_7d",
    "avg_deadline_buffer_days",
    "peak_hour_histogram",
    "sharp_then_progress_ratio",
    "gentle_then_progress_ratio",
    "snapshot_growth_pattern",
)


def _extract_chat_count_7d(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> int:
    cutoff = (now - timedelta(days=7)).isoformat()
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM ChatMessage m
           JOIN ChatSession s ON s.id = m.chat_session_id
           WHERE s.user_id = ? AND m.role = 'user' AND m.created_at >= ?""",
        (user_id, cutoff),
    ).fetchone()
    return int(row["c"]) if row else 0


def _extract_peak_hour_histogram(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> list[int]:
    """24-bucket KST hour-of-day histogram of the user's chat messages
    over the last 30 days."""
    cutoff = (now - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """SELECT m.created_at FROM ChatMessage m
           JOIN ChatSession s ON s.id = m.chat_session_id
           WHERE s.user_id = ? AND m.role = 'user' AND m.created_at >= ?""",
        (user_id, cutoff),
    ).fetchall()
    buckets = [0] * 24
    for r in rows:
        ts = r["created_at"] or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            kst = dt + timedelta(hours=9)
            buckets[kst.hour] += 1
        except (ValueError, IndexError):
            continue
    return buckets


@trace_subsystem("tendencies")
def extract_features(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Deterministic feature extraction from existing tables.

    Returns a dict with every key in _FEATURE_KEYS. Unmeasurable features
    are None so callers (and the LLM critic) can be cautious.
    """
    _now = now or datetime.now(timezone.utc)
    return {
        "chat_count_7d": _extract_chat_count_7d(conn, user_id, _now),
        "avg_deadline_buffer_days": None,
        "peak_hour_histogram": _extract_peak_hour_histogram(conn, user_id, _now),
        "sharp_then_progress_ratio": None,
        "gentle_then_progress_ratio": None,
        "snapshot_growth_pattern": None,
    }
