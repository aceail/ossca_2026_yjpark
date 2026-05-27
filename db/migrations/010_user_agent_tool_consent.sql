-- P0-15: 사용자별 외부 도구 사용 동의.
-- 기본은 미동의 — 사용자가 settings에서 명시 토글해야 ToolRouter가 해당 tool을 반환한다.
-- 회피·후회 데이터가 외부 서비스(Google Calendar, web search 등)로 흘러갈 수 있는
-- 모든 경로는 이 게이트를 통과해야 한다.

CREATE TABLE IF NOT EXISTS UserAgentToolConsent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    agent_tool_id INTEGER NOT NULL REFERENCES AgentTool(id) ON DELETE CASCADE,
    granted_at TEXT NOT NULL,
    revoked_at TEXT,
    UNIQUE (user_id, agent_tool_id)
);

CREATE INDEX IF NOT EXISTS idx_consent_user
    ON UserAgentToolConsent (user_id);
CREATE INDEX IF NOT EXISTS idx_consent_active
    ON UserAgentToolConsent (user_id, agent_tool_id)
    WHERE revoked_at IS NULL;
