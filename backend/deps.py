"""FastAPI 의존성 주입 — DB connection + 디바이스 토큰 인증 (P0-8)."""

from __future__ import annotations

import os
import sqlite3
from typing import Generator, Optional

from fastapi import Depends, Header, HTTPException, Path, status

DB_PATH = os.environ.get("TOMORROW_YOU_DB", "tomorrow_you.db")


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """각 request에서 새 sqlite3 connection (thread-safety 보장)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


# ────────────────────────────────────────────────────────────────────
# P0-8: 디바이스 토큰 인증
#
# 사용자별 endpoint에서 다음 검증을 강제한다:
#   1. Authorization 헤더가 "Bearer <token>" 형식이어야 함
#   2. 해당 토큰이 path의 user_id의 device_token과 일치해야 함
#
# 토큰 미스매치는 401 — 사용자 ID 노출 회피 (404로 알리지 않음)
# 토큰 누락도 401.
# ────────────────────────────────────────────────────────────────────


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def require_token(
    user_id: str = Path(...),
    authorization: Optional[str] = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> str:
    """Path의 user_id와 Authorization Bearer 토큰이 일치하는지 검증."""
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = conn.execute(
        "SELECT device_token FROM User WHERE id = ?", (user_id,)
    ).fetchone()
    if not row or not row["device_token"] or row["device_token"] != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token for this user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def require_token_for_session(
    session_id: int = Path(...),
    authorization: Optional[str] = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> str:
    """세션-소유자 매핑 후 토큰 검증.

    /api/sessions/{session_id}/* 라우터는 path에 user_id가 없으므로
    먼저 AvoidanceSession에서 user_id를 조회한다.
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = conn.execute(
        """SELECT u.device_token
           FROM AvoidanceSession s
           JOIN User u ON u.id = s.user_id
           WHERE s.id = ?""",
        (session_id,),
    ).fetchone()
    if not row or not row["device_token"] or row["device_token"] != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token for this session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def require_token_for_card(
    card_id: int = Path(...),
    authorization: Optional[str] = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> str:
    """/api/scenario-cards/{card_id}/* — card → session → user 트랜지티브 검증."""
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = conn.execute(
        """SELECT u.device_token
           FROM ScenarioCard c
           JOIN AvoidanceSession s ON s.id = c.avoidance_session_id
           JOIN User u ON u.id = s.user_id
           WHERE c.id = ?""",
        (card_id,),
    ).fetchone()
    if not row or not row["device_token"] or row["device_token"] != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token for this card",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


def resolve_user_from_token(
    authorization: Optional[str] = Header(default=None),
    conn: sqlite3.Connection = Depends(get_db),
) -> str:
    """토큰으로 user_id를 역으로 식별 — body/query에 user_id가 있는 endpoint용.

    Body/query의 user_id와 일치 여부는 endpoint에서 직접 확인하거나,
    `require_token_matches_body_user_id` factory를 사용해 자동 검증한다.
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = conn.execute(
        "SELECT id FROM User WHERE device_token = ?", (token,)
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return row["id"]


def assert_user_matches(token_user_id: str, claimed_user_id: str) -> None:
    """body/query의 user_id가 토큰 소유자와 일치하는지 검증."""
    if token_user_id != claimed_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token does not match user_id",
        )
