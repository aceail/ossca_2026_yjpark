-- Sprint 11: 멀티턴 chat 흐름.
-- 기존 AvoidanceSession(one-shot 카드)와 분리 — chat은 페르소나와 자유 대화.
-- 데이터 모니터링: 메시지가 평문으로 저장되므로 임상 위험 키워드는
-- 별도 Slow Harm 시계열에 집계되거나 응답 직전 게이트 통과해야 한다.

CREATE TABLE IF NOT EXISTS ChatSession (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    persona_id INTEGER REFERENCES Persona(id) ON DELETE SET NULL,
    title TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_session_user
    ON ChatSession (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS ChatMessage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_session_id INTEGER NOT NULL REFERENCES ChatSession(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_message_session
    ON ChatMessage (chat_session_id, created_at);
