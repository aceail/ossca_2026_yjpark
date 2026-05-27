-- Sprint 20: 사용자별 누적 메모리.
-- LLM이 remember(key, value)로 적고, recall(query)로 찾는다. 매 chat
-- 호출 시 상위 N개 salient memory를 system prompt에 자동 inject.
-- salience: 호출 빈도·최근성·중요도를 합산한 점수. 자기참조로 업데이트.

CREATE TABLE IF NOT EXISTS UserMemory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    salience INTEGER NOT NULL DEFAULT 1,   -- 1 = 최저, 사용·확인될수록 +1
    source TEXT,                            -- 'user', 'assistant', 'reflection', 'system'
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, key)
);

CREATE INDEX IF NOT EXISTS idx_user_memory_user_salience
    ON UserMemory (user_id, salience DESC, updated_at DESC);
