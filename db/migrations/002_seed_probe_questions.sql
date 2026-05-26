-- 002_seed_probe_questions.sql — 12 default ProbeQuestion seed (G004 v1)

INSERT OR IGNORE INTO ProbeQuestion (text, target_slot, expected_information_gain, enabled, version, created_at) VALUES
  ('이번 회피가 시작된 정확한 시각이 언제예요? (예: 23:14)', 'time_window_start', 0.7, 1, 'v1', datetime('now')),
  ('지금까지 그 일을 안 한 시간이 얼마나 됐어요?', 'time_window_duration', 0.6, 1, 'v1', datetime('now')),
  ('지난번 비슷한 상황에서 가장 후회됐던 한 가지 순간이 있었나요?', 'regret_recall', 0.8, 1, 'v1', datetime('now')),
  ('그 후회 순간을 한 줄로 적는다면?', 'regret_recall_text', 0.7, 1, 'v1', datetime('now')),
  ('이번에 시작만 하면 회피가 풀린다고 느낀 가장 작은 행동은?', 'recovery_action_seed', 0.8, 1, 'v1', datetime('now')),
  ('과거에 비슷한 늪에서 빠져나왔을 때 첫 30초에 한 행동은?', 'recovery_pattern', 0.7, 1, 'v1', datetime('now')),
  ('지금 회피하는 동안 머릿속에 가장 자주 떠오르는 사람은?', 'fear_anchor', 0.6, 1, 'v1', datetime('now')),
  ('그 사람이 지금 너를 보면 가장 처음 어떤 말을 할 것 같아요?', 'fear_anchor_voice', 0.5, 1, 'v1', datetime('now')),
  ('회피가 끝난 직후 가장 자주 드는 감정은? (한 단어)', 'post_avoidance_emotion', 0.6, 1, 'v1', datetime('now')),
  ('지금 한 가지 슬라이드/문장/메시지를 30초 안에 만든다면 무엇?', 'micro_action_hint', 0.7, 1, 'v1', datetime('now')),
  ('이번 회피의 마감 시각(있다면)이 언제예요?', 'deadline_time', 0.7, 1, 'v1', datetime('now')),
  ('이 시나리오에서 절대 건드리지 말아줬으면 하는 주제가 있다면?', 'forbidden_topic_addition', 0.4, 1, 'v1', datetime('now'));
