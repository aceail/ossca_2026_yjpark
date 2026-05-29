CREATE TABLE IF NOT EXISTS NotificationLog (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  key TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('deadline','momentum','peak')),
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  sent_at TEXT NOT NULL,
  dispatched INTEGER NOT NULL DEFAULT 0,
  clicked_at TEXT,
  click_action TEXT,
  snooze_until TEXT
);
CREATE INDEX IF NOT EXISTS idx_nlog_user_sent ON NotificationLog(user_id, sent_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_nlog_dedup
  ON NotificationLog(user_id, key, date(sent_at));
CREATE INDEX IF NOT EXISTS idx_nlog_snooze ON NotificationLog(snooze_until)
  WHERE snooze_until IS NOT NULL;
