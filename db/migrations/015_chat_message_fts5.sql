-- Sprint 19 (autopilot v0.5): SQLite FTS5 전문 검색 인덱스.
-- LLM이 search_memory tool로 사용자의 과거 chat을 자율 검색하기 위함.
-- INSERT/UPDATE/DELETE 트리거로 ChatMessage와 자동 동기화.

CREATE VIRTUAL TABLE IF NOT EXISTS ChatMessageFts USING fts5(
    content,
    role UNINDEXED,
    chat_session_id UNINDEXED,
    content='ChatMessage',
    content_rowid='id'
);

-- 기존 메시지 backfill
INSERT INTO ChatMessageFts (rowid, content, role, chat_session_id)
SELECT id, content, role, chat_session_id FROM ChatMessage;

-- 새 메시지 trigger
CREATE TRIGGER IF NOT EXISTS chat_message_fts_ai
AFTER INSERT ON ChatMessage BEGIN
    INSERT INTO ChatMessageFts (rowid, content, role, chat_session_id)
    VALUES (new.id, new.content, new.role, new.chat_session_id);
END;

-- FTS5 external content table: UPDATE·DELETE는 special command 필요
CREATE TRIGGER IF NOT EXISTS chat_message_fts_au
AFTER UPDATE ON ChatMessage BEGIN
    INSERT INTO ChatMessageFts(ChatMessageFts, rowid, content)
    VALUES('delete', old.id, old.content);
    INSERT INTO ChatMessageFts (rowid, content, role, chat_session_id)
    VALUES (new.id, new.content, new.role, new.chat_session_id);
END;

CREATE TRIGGER IF NOT EXISTS chat_message_fts_ad
AFTER DELETE ON ChatMessage BEGIN
    INSERT INTO ChatMessageFts(ChatMessageFts, rowid, content)
    VALUES('delete', old.id, old.content);
END;
