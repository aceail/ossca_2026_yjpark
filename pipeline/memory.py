"""Sprint 20 — UserMemory CRUD + system prompt inject.

LLM이 자율 호출하는 tool과 backend가 매 chat 호출 시 inject하는 헬퍼.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_memory(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    key: str,
    value: str,
    source: str = "assistant",
    salience_delta: int = 1,
) -> int:
    """기존 key 있으면 value 업데이트 + salience += delta, 없으면 새로 INSERT."""
    now = _now_iso()
    row = conn.execute(
        "SELECT id, salience FROM UserMemory WHERE user_id = ? AND key = ?",
        (user_id, key),
    ).fetchone()
    if row:
        new_sal = max(1, row["salience"] + salience_delta)
        conn.execute(
            "UPDATE UserMemory SET value = ?, salience = ?, source = ?, updated_at = ? WHERE id = ?",
            (value, new_sal, source, now, row["id"]),
        )
        conn.commit()
        return row["id"]
    cur = conn.execute(
        """INSERT INTO UserMemory (user_id, key, value, salience, source, created_at, updated_at)
           VALUES (?, ?, ?, 1, ?, ?, ?)""",
        (user_id, key, value, source, now, now),
    )
    conn.commit()
    return cur.lastrowid


def top_memories(
    conn: sqlite3.Connection, user_id: str, *, limit: int = 5,
) -> list[dict]:
    rows = conn.execute(
        """SELECT key, value, salience, source, updated_at
           FROM UserMemory WHERE user_id = ?
           ORDER BY salience DESC, updated_at DESC LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def recall(
    conn: sqlite3.Connection, user_id: str, *, query: str, limit: int = 5,
) -> list[dict]:
    """단순 LIKE 검색. key·value 모두 매칭. salience 가중치 정렬."""
    q = f"%{query.strip()}%"
    rows = conn.execute(
        """SELECT key, value, salience, source, updated_at
           FROM UserMemory
           WHERE user_id = ? AND (key LIKE ? OR value LIKE ?)
           ORDER BY salience DESC, updated_at DESC LIMIT ?""",
        (user_id, q, q, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def forget(
    conn: sqlite3.Connection, user_id: str, *, key: str,
) -> bool:
    cur = conn.execute(
        "DELETE FROM UserMemory WHERE user_id = ? AND key = ?",
        (user_id, key),
    )
    conn.commit()
    return cur.rowcount > 0


def format_for_prompt(memories: list[dict]) -> str:
    """system prompt에 prefix할 텍스트. 비어있으면 빈 문자열."""
    if not memories:
        return ""
    lines = [f"- {m['key']}: {m['value']}" for m in memories]
    return (
        "\n\n[기억하는 것들 — 매 대화에 자동 주입]\n"
        + "\n".join(lines)
    )
