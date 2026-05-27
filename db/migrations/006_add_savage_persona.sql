-- 006_add_savage_persona.sql — v0.2.1 사용자 요청
-- "난폭모드" 강화 — 6번째 default 페르소나 'Savage' 톤 추가
-- 절대 한계선 유지: 정체성 결함·비교 수치심·심각 욕설 금지

INSERT OR IGNORE INTO Persona (
  name, perspective, tone_mode, voice_style, greeting,
  forbidden_topics_json, system_prompt_override,
  avatar_color, avatar_icon, is_builtin, created_at
) VALUES (
  '뼈때리는 친구',
  '2nd',
  'Savage',
  '친구 2인칭, 직설적, 사정 봐주지 않음 (정체성 비난 X)',
  '야 진짜로. 안 하면 어떡할 건데?',
  '[]',
  NULL,
  '#7A2424',
  '🗯️',
  1,
  datetime('now')
);
