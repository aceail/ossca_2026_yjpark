-- 004_seed_agent_tools.sql — AgentTool 5개 seed (G010 AgentIntegrations)
-- Generated: 2026-05-26
-- 연계: FINAL_GOAL.md v2.3 §15 Agent Architecture

-- AgentTool.enabled = 1: MVP 활성 tool
-- AgentTool.enabled = 0: 향후 라운드용 (사용자 활성화 전까지 비활성)

INSERT OR IGNORE INTO AgentTool (name, type, enabled, config_json, created_at)
VALUES
  (
    'google_calendar.list_events',
    'calendar',
    1,
    '{"description": "Google Calendar 다가올 일정 조회 (read-only)", "days_ahead": 7}',
    datetime('now')
  ),
  (
    'local_files.recent',
    'files',
    1,
    '{"description": "로컬 파일 최근 수정 목록 조회 (read-only)", "default_hours": 72}',
    datetime('now')
  ),
  (
    'web_search.brave',
    'search',
    1,
    '{"description": "Brave Search / SearXNG 웹 검색 (mock, 향후 실제 API 연동)", "max_results": 3}',
    datetime('now')
  ),
  (
    'google_calendar.event_detail',
    'calendar',
    0,
    '{"description": "Google Calendar 특정 일정 상세 조회 (향후 라운드)", "status": "future"}',
    datetime('now')
  ),
  (
    'local_files.search',
    'files',
    0,
    '{"description": "로컬 파일 전문 검색 (향후 라운드, FTS5 연동)", "status": "future"}',
    datetime('now')
  );
