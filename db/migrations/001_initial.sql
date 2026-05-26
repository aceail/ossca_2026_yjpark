-- 001_initial.sql — Tomorrow's You 17 테이블 초기 스키마 (G003 v1)
-- Generated: 2026-05-26
-- 연계: FINAL_GOAL.md v2.3 §6 코어 데이터 모델

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ────────────────────────────────────────────────────────────────────
-- Group A: 사용자 상태 (5 테이블)
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS User (
    id TEXT PRIMARY KEY,                       -- device-local uuid
    created_at TEXT NOT NULL,
    last_seen_at TEXT,
    settings_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS UserProfile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    slots_json TEXT NOT NULL DEFAULT '{}',     -- {slot_name: {value, confidence, source}}
    completion_percent REAL NOT NULL DEFAULT 0,
    forbidden_topics_json TEXT NOT NULL DEFAULT '[]',
    active_persona_id INTEGER REFERENCES Persona(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS AvoidanceSession (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    avoidance_input TEXT NOT NULL,
    created_at TEXT NOT NULL,
    scenario_card_id INTEGER REFERENCES ScenarioCard(id) ON DELETE SET NULL,
    user_decision TEXT,                        -- 'transition' | 'continue' | 'report'
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_avoidance_user_time ON AvoidanceSession (user_id, created_at);

CREATE TABLE IF NOT EXISTS RegretScore (
    -- ground truth가 아닌 "관계 지표" (v2 재해석)
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avoidance_session_id INTEGER NOT NULL REFERENCES AvoidanceSession(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    intensity INTEGER NOT NULL CHECK(intensity BETWEEN 0 AND 10),
    free_text TEXT,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_regret_user_time ON RegretScore (user_id, recorded_at);

CREATE TABLE IF NOT EXISTS FingerprintSnapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    embedding_json TEXT,                       -- 행동 지문 벡터
    stats_json TEXT,                            -- 통계 요약
    embedding_model TEXT NOT NULL,
    embedding_model_version TEXT NOT NULL,
    snapshot_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fingerprint_user_time ON FingerprintSnapshot (user_id, snapshot_at);

-- ────────────────────────────────────────────────────────────────────
-- Group B: LLM 운영·평가 (7 테이블)
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ScenarioCard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    avoidance_session_id INTEGER REFERENCES AvoidanceSession(id) ON DELETE CASCADE,
    card_type TEXT NOT NULL,                   -- 'regret' | 'recovery' | 'soft_stop' | 'paradoxical_validation'
    persona_id INTEGER REFERENCES Persona(id) ON DELETE SET NULL,
    fact TEXT,
    feeling TEXT,
    micro_action TEXT,
    safety_message TEXT,                       -- soft_stop / paradoxical_validation 메시지
    raw_response TEXT,
    model_run_id INTEGER REFERENCES ModelRun(id) ON DELETE SET NULL,
    prompt_version_id INTEGER REFERENCES PromptVersion(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scenario_session ON ScenarioCard (avoidance_session_id);

CREATE TABLE IF NOT EXISTS ProbeQuestion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    target_slot TEXT NOT NULL,
    expected_information_gain REAL NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    version TEXT NOT NULL DEFAULT 'v1',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ProbeAnswer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    avoidance_session_id INTEGER REFERENCES AvoidanceSession(id) ON DELETE SET NULL,
    probe_question_id INTEGER NOT NULL REFERENCES ProbeQuestion(id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL,
    extracted_slot_updates_json TEXT DEFAULT '{}',
    answered_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_probeanswer_user ON ProbeAnswer (user_id, answered_at);

CREATE TABLE IF NOT EXISTS ModelRun (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,                  -- 예: exaone3.5:7.8b
    quantization TEXT,                          -- Q4_K_M 등
    temperature REAL,
    top_p REAL,
    prompt_version_id INTEGER REFERENCES PromptVersion(id) ON DELETE SET NULL,
    latency_ms INTEGER,
    input_tokens INTEGER,
    output_tokens INTEGER,
    error TEXT,
    ran_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_modelrun_time ON ModelRun (ran_at);

CREATE TABLE IF NOT EXISTS PromptVersion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                        -- 'scenario_witty_v2', 'safety_softstop_v1'
    version TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS EvaluationResult (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id TEXT NOT NULL,                   -- e.g. 'S01' from golden_samples
    model_run_id INTEGER NOT NULL REFERENCES ModelRun(id) ON DELETE CASCADE,
    scenario_card_id INTEGER REFERENCES ScenarioCard(id) ON DELETE SET NULL,
    pass INTEGER NOT NULL DEFAULT 0,
    issues_json TEXT DEFAULT '[]',
    metrics_json TEXT DEFAULT '{}',
    evaluated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_eval_sample_model ON EvaluationResult (sample_id, model_run_id);

CREATE TABLE IF NOT EXISTS SchemaMigration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT NOT NULL UNIQUE,              -- '001_initial'
    applied_at TEXT NOT NULL,
    checksum TEXT
);

-- ────────────────────────────────────────────────────────────────────
-- Group C: Safety (1 테이블)
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SafetyHarmTimeSeries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,                  -- ISO 8601 date
    self_blame_word_count INTEGER DEFAULT 0,
    failure_imagery_ratio REAL DEFAULT 0,
    identity_failure_phrases_count INTEGER DEFAULT 0,
    pre_card_tension_self_report REAL,         -- 0-5
    snapshot_at TEXT NOT NULL,
    UNIQUE (user_id, week_start)
);
CREATE INDEX IF NOT EXISTS idx_safetyharm_user_week ON SafetyHarmTimeSeries (user_id, week_start);

-- ────────────────────────────────────────────────────────────────────
-- Group D: Agent (3 테이블)
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ExternalIntegration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,                    -- 'google_calendar' | 'gmail' | 'local_files' | 'search'
    oauth_token_encrypted BLOB,
    refresh_token_encrypted BLOB,
    scopes_json TEXT DEFAULT '[]',
    expires_at TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    connected_at TEXT NOT NULL,
    UNIQUE (user_id, provider)
);

CREATE TABLE IF NOT EXISTS AgentTool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,                 -- 'google_calendar.list_events'
    type TEXT NOT NULL,                        -- 'calendar' | 'files' | 'search' | 'email' | 'notification'
    enabled INTEGER NOT NULL DEFAULT 1,
    config_json TEXT DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ToolInvocation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES User(id) ON DELETE CASCADE,
    avoidance_session_id INTEGER REFERENCES AvoidanceSession(id) ON DELETE SET NULL,
    persona_id INTEGER REFERENCES Persona(id) ON DELETE SET NULL,
    agent_tool_id INTEGER NOT NULL REFERENCES AgentTool(id) ON DELETE CASCADE,
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT,
    latency_ms INTEGER,
    error TEXT,
    invoked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tool_user_time ON ToolInvocation (user_id, invoked_at);
CREATE INDEX IF NOT EXISTS idx_tool_session ON ToolInvocation (avoidance_session_id);

-- ────────────────────────────────────────────────────────────────────
-- Group E: Persona (1 테이블)
-- ────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS Persona (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    perspective TEXT NOT NULL CHECK(perspective IN ('1st','2nd','3rd')),
    tone_mode TEXT NOT NULL CHECK(tone_mode IN ('Quiet','Sharp','Witty','Savage')),
    voice_style TEXT,
    greeting TEXT,
    forbidden_topics_json TEXT DEFAULT '[]',
    system_prompt_override TEXT,
    avatar_color TEXT,                         -- #RRGGBB
    avatar_icon TEXT,                          -- emoji or asset key
    is_builtin INTEGER NOT NULL DEFAULT 0,
    created_by_user TEXT REFERENCES User(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_persona_builtin ON Persona (is_builtin, name);
-- builtin persona는 이름 고유, 사용자 커스텀은 user별 이름 고유
CREATE UNIQUE INDEX IF NOT EXISTS idx_persona_builtin_name ON Persona(name) WHERE created_by_user IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_persona_user_name ON Persona(name, created_by_user) WHERE created_by_user IS NOT NULL;

-- ────────────────────────────────────────────────────────────────────
-- Seed: 5 default 페르소나
-- ────────────────────────────────────────────────────────────────────

INSERT OR IGNORE INTO Persona (name, perspective, tone_mode, voice_style, greeting, avatar_color, avatar_icon, is_builtin, created_at)
VALUES
  ('내일의 나',  '1st', 'Sharp', '미래 자아 1인칭, 차분한 직시', '내일의 내가 너에게 보낸 메시지야', '#3B6B9A', '🌙', 1, datetime('now')),
  ('1년 후의 나','1st', 'Quiet', '장기 미래 자아 1인칭, 차분',   '1년 뒤의 내가 짧게 한 마디',     '#5A7080', '🌅', 1, datetime('now')),
  ('친한 친구 ㅈㅅ','2nd', 'Witty', '친구 2인칭, 인터넷 톤',       '야 너 지금 뭐 하는 거야ㅋ',       '#C4935A', '🤝', 1, datetime('now')),
  ('엄격한 코치','2nd', 'Sharp', '2인칭 단호한 시간 명령',        '10분 줄게. 한 줄만 쓰고 와.',     '#3B6B9A', '🎯', 1, datetime('now')),
  ('객관 옵저버','3rd', 'Quiet', '3인칭 묘사형, 분리된 시선',     '그는 지금 23시 47분, 슬라이드 0장...', '#5A7080', '👁️', 1, datetime('now'));
