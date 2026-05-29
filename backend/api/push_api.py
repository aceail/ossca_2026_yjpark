"""Wave 6 — Push subscription API.

POST /api/push/subscriptions   — frontend가 PushSubscription을 등록.
DELETE /api/push/subscriptions/{id} — 사용자 토글 off.
GET  /api/push/vapid-public-key — frontend가 subscribe 시 필요.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from backend.deps import (
    assert_user_matches,
    get_db,
    resolve_user_from_token,
)

router = APIRouter(prefix="/api/push", tags=["push"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VapidPublicKeyResponse(BaseModel):
    vapid_public_key: Optional[str] = None
    enabled: bool


class PushSubscriptionRequest(BaseModel):
    user_id: str
    endpoint: str
    p256dh: str
    auth: str


class PushSubscriptionItem(BaseModel):
    id: int
    endpoint: str
    enabled: bool
    created_at: str
    last_seen_at: Optional[str] = None


class PushSubscriptionResponse(BaseModel):
    id: int
    endpoint: str
    enabled: bool


class PushSubscriptionListResponse(BaseModel):
    user_id: str
    subscriptions: list[PushSubscriptionItem]


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
def get_vapid_public_key() -> VapidPublicKeyResponse:
    pub = os.environ.get("NAEIL_VAPID_PUBLIC_KEY")
    return VapidPublicKeyResponse(vapid_public_key=pub, enabled=bool(pub))


@router.post("/subscriptions", response_model=PushSubscriptionResponse, status_code=201)
def create_subscription(
    body: PushSubscriptionRequest,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> PushSubscriptionResponse:
    assert_user_matches(token_user_id, body.user_id)
    now = _now_iso()
    conn.execute(
        """INSERT INTO PushSubscription (user_id, endpoint, p256dh, auth, enabled, created_at)
           VALUES (?, ?, ?, ?, 1, ?)
           ON CONFLICT(user_id, endpoint) DO UPDATE SET
               p256dh = excluded.p256dh,
               auth = excluded.auth,
               enabled = 1""",
        (body.user_id, body.endpoint, body.p256dh, body.auth, now),
    )
    conn.commit()
    row = conn.execute(
        """SELECT id, endpoint, enabled FROM PushSubscription
           WHERE user_id = ? AND endpoint = ?""",
        (body.user_id, body.endpoint),
    ).fetchone()
    return PushSubscriptionResponse(
        id=row["id"], endpoint=row["endpoint"], enabled=bool(row["enabled"]),
    )


@router.get("/users/{user_id}/subscriptions", response_model=PushSubscriptionListResponse)
def list_subscriptions(
    user_id: str,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> PushSubscriptionListResponse:
    assert_user_matches(token_user_id, user_id)
    rows = conn.execute(
        """SELECT id, endpoint, enabled, created_at, last_seen_at
           FROM PushSubscription WHERE user_id = ?
           ORDER BY id DESC""",
        (user_id,),
    ).fetchall()
    items = [
        PushSubscriptionItem(
            id=r["id"],
            endpoint=r["endpoint"],
            enabled=bool(r["enabled"]),
            created_at=r["created_at"],
            last_seen_at=r["last_seen_at"],
        )
        for r in rows
    ]
    return PushSubscriptionListResponse(user_id=user_id, subscriptions=items)


@router.delete("/subscriptions/{sub_id}", status_code=204)
def delete_subscription(
    sub_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    token_user_id: str = Depends(resolve_user_from_token),
) -> None:
    row = conn.execute(
        "SELECT user_id FROM PushSubscription WHERE id = ?", (sub_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="PushSubscription not found")
    assert_user_matches(token_user_id, row["user_id"])
    conn.execute("DELETE FROM PushSubscription WHERE id = ?", (sub_id,))
    conn.commit()


# Sprint 39: notification action endpoints. SW에서 호출되므로 auth 헤더 없음
# (OS notification UI에서는 헤더 못 붙임). notification_id가 implicit identity.

@router.post("/{notification_id}/clicked")
def notification_clicked(
    notification_id: int,
    body: dict = Body(default={}),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """SW가 클릭 보고. clicked_at이 NULL인 행만 첫 클릭으로 기록."""
    from datetime import datetime, timezone as _tz
    action = (body.get("action") or "open")[:32]
    now = datetime.now(_tz.utc).isoformat()
    cur = conn.execute(
        "UPDATE NotificationLog SET clicked_at = ?, click_action = ? "
        "WHERE id = ? AND clicked_at IS NULL",
        (now, action, notification_id),
    )
    conn.commit()
    return {"ok": True, "updated": cur.rowcount}


@router.post("/{notification_id}/snooze")
def notification_snooze(
    notification_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """30분 후 재발송 예약. _push_notification_loop가 redispatch_snoozed로 처리."""
    from datetime import datetime, timedelta, timezone as _tz
    until = (datetime.now(_tz.utc) + timedelta(minutes=30)).isoformat()
    cur = conn.execute(
        "UPDATE NotificationLog SET snooze_until = ? WHERE id = ?",
        (until, notification_id),
    )
    conn.commit()
    return {"ok": True, "until": until, "updated": cur.rowcount}
