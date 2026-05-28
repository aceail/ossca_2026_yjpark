CREATE TABLE IF NOT EXISTS RagDoc (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('chat','memory','task','snapshot')),
  ref_id TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TEXT NOT NULL,
  embed_model TEXT NOT NULL DEFAULT 'nomic-embed-text',
  created_at TEXT NOT NULL,
  UNIQUE (kind, ref_id, embed_model)
);
CREATE INDEX IF NOT EXISTS idx_ragdoc_user_kind ON RagDoc(user_id, kind);
