-- P0-16: Idempotency-Key 캐시 (POST 중복 방지).
-- 같은 (user_id, endpoint, key)로 재요청하면 처음 응답을 그대로 반환.
-- TTL은 read 시 created_at 비교 — 24h 초과 행은 무시 + 같이 정리.

CREATE TABLE IF NOT EXISTS IdempotencyKey (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    endpoint TEXT NOT NULL,
    key TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL DEFAULT 200,
    created_at TEXT NOT NULL,
    UNIQUE (user_id, endpoint, key)
);

CREATE INDEX IF NOT EXISTS idx_idem_user_created
    ON IdempotencyKey (user_id, created_at);
