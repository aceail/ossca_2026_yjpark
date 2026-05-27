-- 007_avoidance_session_timeline.sql — v0.2.1 CRITIQUE P0-4 fix
-- AvoidanceSession에 timeline_hint 컬럼 추가 (이전엔 백엔드에서 무시되어 평가 vs 런타임 분리)

ALTER TABLE AvoidanceSession ADD COLUMN timeline_hint TEXT;
