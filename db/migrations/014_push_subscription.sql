-- Wave 6: Web Push subscriptions per user.
-- VAPID public key는 environment에 별도 보관 (NAEIL_VAPID_PUBLIC_KEY).
-- endpoint UNIQUE per user — 같은 디바이스 재구독 시 upsert.

CREATE TABLE IF NOT EXISTS PushSubscription (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    p256dh TEXT NOT NULL,
    auth TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_seen_at TEXT,
    UNIQUE (user_id, endpoint)
);

CREATE INDEX IF NOT EXISTS idx_push_user_enabled
    ON PushSubscription (user_id, enabled);
