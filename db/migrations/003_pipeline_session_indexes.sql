-- G006 Pipeline Session 인덱스 (새 테이블 X, 성능 인덱스만)
-- 적용: db/migrations/003_pipeline_session_indexes.sql

CREATE INDEX IF NOT EXISTS idx_avoidance_session_user_id
    ON AvoidanceSession(user_id);

CREATE INDEX IF NOT EXISTS idx_avoidance_session_created_at
    ON AvoidanceSession(created_at);

CREATE INDEX IF NOT EXISTS idx_scenario_card_session_id
    ON ScenarioCard(avoidance_session_id);

CREATE INDEX IF NOT EXISTS idx_scenario_card_card_type
    ON ScenarioCard(card_type);

CREATE INDEX IF NOT EXISTS idx_probe_answer_user_session
    ON ProbeAnswer(user_id, avoidance_session_id);
