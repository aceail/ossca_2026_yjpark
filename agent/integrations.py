"""ExternalIntegration CRUD — OAuth 토큰 암호화 저장/조회/삭제.

토큰 암호화:
  - 우선: cryptography.fernet (표준 대칭 암호화)
  - 폴백: base64 인코딩 (cryptography 미설치 환경, 보안 약함)
    → 폴백 사용 시 README 경고 참조

키 관리:
  - 환경변수 TOMORROW_YOU_FERNET_KEY 우선
  - 없으면 ~/.tomorrow_you/fernet.key 자동 생성·저장
"""

from __future__ import annotations

import base64
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ────────────────────────────────────────────────────────────────────
# 암호화 백엔드 초기화
# ────────────────────────────────────────────────────────────────────

_FERNET_AVAILABLE = False
try:
    from cryptography.fernet import Fernet
    _FERNET_AVAILABLE = True
except ImportError:
    pass

_KEY_DIR = Path.home() / ".tomorrow_you"
_KEY_FILE = _KEY_DIR / "fernet.key"


def _load_or_create_key() -> bytes:
    """환경변수 또는 로컬 파일에서 Fernet 키 로드. 없으면 자동 생성."""
    env_key = os.environ.get("TOMORROW_YOU_FERNET_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key

    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()

    if _FERNET_AVAILABLE:
        key = Fernet.generate_key()
    else:
        key = base64.urlsafe_b64encode(os.urandom(32))

    _KEY_DIR.mkdir(parents=True, exist_ok=True)
    _KEY_FILE.write_bytes(key)
    return key


def _encrypt(plaintext: str) -> bytes:
    """평문 문자열을 암호화하여 bytes 반환."""
    key = _load_or_create_key()
    data = plaintext.encode("utf-8")
    if _FERNET_AVAILABLE:
        return Fernet(key).encrypt(data)
    # 폴백: base64 (보안 약함 — README 경고 참조)
    return base64.urlsafe_b64encode(data)


def _decrypt(ciphertext: bytes) -> str:
    """암호화된 bytes를 복호화하여 평문 문자열 반환."""
    key = _load_or_create_key()
    if _FERNET_AVAILABLE:
        return Fernet(key).decrypt(ciphertext).decode("utf-8")
    # 폴백: base64
    return base64.urlsafe_b64decode(ciphertext).decode("utf-8")


# ────────────────────────────────────────────────────────────────────
# ExternalIntegration CRUD
# ────────────────────────────────────────────────────────────────────

def save_integration(
    conn: sqlite3.Connection,
    user_id: str,
    provider: str,
    oauth_token: str,
    refresh_token: Optional[str],
    scopes: list[str],
    expires_at: Optional[str],
) -> None:
    """ExternalIntegration 저장 (upsert). 토큰은 암호화 후 BLOB 저장."""
    import json

    encrypted_oauth = _encrypt(oauth_token)
    encrypted_refresh = _encrypt(refresh_token) if refresh_token else None
    scopes_json = json.dumps(scopes, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """
        INSERT INTO ExternalIntegration
            (user_id, provider, oauth_token_encrypted, refresh_token_encrypted,
             scopes_json, expires_at, enabled, connected_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        ON CONFLICT(user_id, provider) DO UPDATE SET
            oauth_token_encrypted = excluded.oauth_token_encrypted,
            refresh_token_encrypted = excluded.refresh_token_encrypted,
            scopes_json = excluded.scopes_json,
            expires_at = excluded.expires_at,
            enabled = 1,
            connected_at = excluded.connected_at
        """,
        (user_id, provider, encrypted_oauth, encrypted_refresh,
         scopes_json, expires_at, now),
    )
    conn.commit()


def get_integration(
    conn: sqlite3.Connection,
    user_id: str,
    provider: str,
) -> Optional[dict]:
    """ExternalIntegration 조회. 토큰 복호화 후 dict 반환. 없으면 None."""
    import json

    row = conn.execute(
        "SELECT * FROM ExternalIntegration WHERE user_id = ? AND provider = ? AND enabled = 1",
        (user_id, provider),
    ).fetchone()

    if row is None:
        return None

    oauth_token = _decrypt(row["oauth_token_encrypted"]) if row["oauth_token_encrypted"] else None
    refresh_token = _decrypt(row["refresh_token_encrypted"]) if row["refresh_token_encrypted"] else None

    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "provider": row["provider"],
        "oauth_token": oauth_token,
        "refresh_token": refresh_token,
        "scopes": json.loads(row["scopes_json"]),
        "expires_at": row["expires_at"],
        "connected_at": row["connected_at"],
    }


def revoke_integration(
    conn: sqlite3.Connection,
    user_id: str,
    provider: str,
) -> None:
    """ExternalIntegration 삭제. ToolInvocation은 user_id CASCADE로 유지되나
    integration 자체를 삭제함. 연관 ToolInvocation은 별도 정책에 따름."""
    conn.execute(
        "DELETE FROM ExternalIntegration WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    conn.commit()
