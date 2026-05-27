"""Wave 6 — Web Push helpers (VAPID).

`pywebpush` (BSD-3 OSS)가 설치되어 있으면 실제 발송. 아니면 dry-run으로
DB에만 흔적 남기고 silent skip — 개발 환경에서 backend 부팅을 깨지 않게.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

try:
    from pywebpush import WebPushException, webpush  # type: ignore
    _WEBPUSH_AVAILABLE = True
except ImportError:
    _WEBPUSH_AVAILABLE = False
    WebPushException = Exception  # type: ignore
    webpush = None  # type: ignore


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def push_enabled() -> bool:
    """라이브러리 + VAPID 키 모두 있어야 진짜 발송."""
    return (
        _WEBPUSH_AVAILABLE
        and bool(os.environ.get("NAEIL_VAPID_PRIVATE_KEY"))
        and bool(os.environ.get("NAEIL_VAPID_PUBLIC_KEY"))
    )


def list_active_subscriptions(
    conn: sqlite3.Connection, user_id: str,
) -> list[dict]:
    rows = conn.execute(
        """SELECT id, endpoint, p256dh, auth FROM PushSubscription
           WHERE user_id = ? AND enabled = 1""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def send_push_to_user(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    title: str,
    body: str,
    url: str | None = None,
) -> int:
    """user의 모든 활성 subscription에 push 발송. 반환: 발송 성공 수.

    dry-run (라이브러리 미설치 or 키 미설정)이면 0 반환 — 호출자는 항상
    이 함수를 부르되 결과를 best-effort로 취급.
    """
    subs = list_active_subscriptions(conn, user_id)
    if not subs:
        return 0
    if not push_enabled():
        return 0

    private_key = os.environ["NAEIL_VAPID_PRIVATE_KEY"]
    subject = os.environ.get("NAEIL_VAPID_SUBJECT", "mailto:admin@example.com")
    payload = {"title": title, "body": body}
    if url:
        payload["url"] = url

    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub["endpoint"],
                    "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]},
                },
                data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=3600,
            )
            sent += 1
            conn.execute(
                "UPDATE PushSubscription SET last_seen_at = ? WHERE id = ?",
                (_now_iso(), sub["id"]),
            )
        except WebPushException as exc:
            # 410 Gone — 영구 만료. enabled=0으로 비활성화.
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):
                conn.execute(
                    "UPDATE PushSubscription SET enabled = 0 WHERE id = ?",
                    (sub["id"],),
                )
            continue
        except Exception:
            continue

    if sent:
        conn.commit()
    return sent
