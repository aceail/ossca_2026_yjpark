"""P0-15: 사용자별 외부 도구 사용 동의 (Consent gate).

기본은 미동의. 사용자가 명시 grant 하지 않은 tool은 ToolRouter가 반환하지 않는다.
revoked_at이 NULL이어야 활성 동의로 간주한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def has_consent(conn: sqlite3.Connection, user_id: str, agent_tool_id: int) -> bool:
    """user_id가 agent_tool_id에 대해 활성 동의를 가지고 있는가."""
    row = conn.execute(
        """SELECT 1 FROM UserAgentToolConsent
           WHERE user_id = ? AND agent_tool_id = ? AND revoked_at IS NULL""",
        (user_id, agent_tool_id),
    ).fetchone()
    return row is not None


def grant_consent(conn: sqlite3.Connection, user_id: str, agent_tool_id: int) -> None:
    """동의 부여 (upsert) — 기존 revoked였다면 revoked_at NULL로 재활성화."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO UserAgentToolConsent (user_id, agent_tool_id, granted_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id, agent_tool_id) DO UPDATE SET
               granted_at = excluded.granted_at,
               revoked_at = NULL""",
        (user_id, agent_tool_id, now),
    )
    conn.commit()


def revoke_consent(conn: sqlite3.Connection, user_id: str, agent_tool_id: int) -> None:
    """동의 철회 — 행은 보존 (감사 흔적), revoked_at만 set."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE UserAgentToolConsent
           SET revoked_at = ?
           WHERE user_id = ? AND agent_tool_id = ?""",
        (now, user_id, agent_tool_id),
    )
    conn.commit()


def list_consents(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    """사용자의 모든 외부 tool에 대한 consent 상태 — UI 토글용.

    AgentTool과 LEFT JOIN하여 동의 이력이 없는 tool도 포함.
    type IN ('integration','search','file')로 외부 도구만 필터링 — LLM 등 내부는 제외.
    """
    rows = conn.execute(
        """SELECT t.id AS tool_id, t.name AS tool_name, t.type AS tool_type,
                  c.granted_at, c.revoked_at
           FROM AgentTool t
           LEFT JOIN UserAgentToolConsent c
               ON c.agent_tool_id = t.id AND c.user_id = ?
           WHERE t.type IN ('calendar', 'files', 'search')
             AND t.enabled = 1
           ORDER BY t.name""",
        (user_id,),
    ).fetchall()
    return [
        {
            "tool_id": r["tool_id"],
            "tool_name": r["tool_name"],
            "tool_type": r["tool_type"],
            "granted_at": r["granted_at"],
            "revoked_at": r["revoked_at"],
            "active": r["granted_at"] is not None and r["revoked_at"] is None,
        }
        for r in rows
    ]
