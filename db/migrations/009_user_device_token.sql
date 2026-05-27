-- P0-8: 사용자별 디바이스 토큰 (Bearer 인증).
-- 사용자 생성 시 1회 자동 발급, 모든 사용자별 API 호출의 Authorization 헤더로 검증.
-- 로컬 1인 환경에선 자기 데이터 자기만 접근 가능하게 하는 최소 게이트.

ALTER TABLE User ADD COLUMN device_token TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_device_token
    ON User (device_token) WHERE device_token IS NOT NULL;
