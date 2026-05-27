-- P0-12: ToolInvocation에 prompt_version_id FK 추가.
-- 시나리오 생성 시 실제로 사용된 system_prompt를 PromptVersion으로 추적해
-- 평가·디버깅·재현 가능성을 확보한다.

ALTER TABLE ToolInvocation ADD COLUMN prompt_version_id INTEGER
    REFERENCES PromptVersion(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tool_prompt_version
    ON ToolInvocation (prompt_version_id);
