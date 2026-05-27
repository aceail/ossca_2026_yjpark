-- 005_persona_name_fix.sql — v0.2.1 CRITIQUE fix
-- P0-1: "친한 친구 ㅈㅅ" 약어가 한국어 "죄송/자살"로 읽힘 → "친한 친구"
-- P0-20: "객관 옵저버 👁️"는 감시 메타포 → "기록자 📓" (관찰 → 기록 메타포)

UPDATE Persona
SET
  name = '친한 친구',
  greeting = '야 지금 뭐 해? 한 줄만 같이 쓰자',
  voice_style = '친구 2인칭, 인터넷 톤, 가벼운 자기 풍자 OK'
WHERE name = '친한 친구 ㅈㅅ' AND is_builtin = 1;

UPDATE Persona
SET
  name = '기록자',
  greeting = '23시 47분, 슬라이드 0장. 기록만 남긴다.',
  voice_style = '3인칭 관찰자 화법, 사실만 기록',
  avatar_color = '#6B7280',
  avatar_icon = '📓'
WHERE name = '객관 옵저버' AND is_builtin = 1;
