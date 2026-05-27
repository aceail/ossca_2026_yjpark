"""P0-16 Idempotency-Key 헬퍼.

명시 패턴: endpoint가 직접 check → 캐시 hit 시 캐시 반환, 아니면 처리 후 store.
이유: Starlette middleware로는 request body capture/replay와 dependency 주입
(특히 require_token, resolve_user_from_token) 호환이 복잡해진다. 적용 대상도
실제로는 회피 입력처럼 중복-위험이 큰 POST 일부에 한정되므로 명시 호출이 깔끔.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

IDEMPOTENCY_TTL_HOURS = 24


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def check_idempotency(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    endpoint: str,
    key: Optional[str],
) -> Optional[dict[str, Any]]:
    """캐시 hit이면 response dict, 아니면 None."""
    if not key:
        return None
    cutoff = (_now_utc() - timedelta(hours=IDEMPOTENCY_TTL_HOURS)).isoformat()
    row = conn.execute(
        """SELECT response_json FROM IdempotencyKey
           WHERE user_id = ? AND endpoint = ? AND key = ?
             AND created_at >= ?""",
        (user_id, endpoint, key, cutoff),
    ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["response_json"])
    except json.JSONDecodeError:
        return None


def store_idempotency(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    endpoint: str,
    key: Optional[str],
    response: dict[str, Any],
    status_code: int = 200,
) -> None:
    """응답을 캐시. 같은 (user_id, endpoint, key)면 덮어쓰기 X — 첫 응답 보존."""
    if not key:
        return
    now = _now_utc().isoformat()
    conn.execute(
        """INSERT OR IGNORE INTO IdempotencyKey
           (user_id, endpoint, key, response_json, status_code, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, endpoint, key, json.dumps(response, ensure_ascii=False),
         status_code, now),
    )
    conn.commit()
