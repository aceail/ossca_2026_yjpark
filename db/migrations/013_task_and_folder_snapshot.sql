-- Sprint 12 / Wave 1: Task 모델 + FolderSnapshot.
-- Task = 사용자 자연어("5/31 발표자료")에서 추출되어 캘린더에 박힌 작업.
-- folder_path가 지정되면 FolderWatcher가 주기 스냅샷을 누적 (Wave 2).
-- status open|done|abandoned — Self-Destruct cascade는 user_id ON DELETE CASCADE에 의존.

CREATE TABLE IF NOT EXISTS Task (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL REFERENCES User(id) ON DELETE CASCADE,
    persona_id INTEGER REFERENCES Persona(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    deadline_at TEXT,                  -- ISO 8601, NULL 가능 (마감 없음)
    folder_path TEXT,                  -- 절대 경로 또는 NULL
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'done', 'abandoned')),
    last_followup_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_user_status
    ON Task (user_id, status, deadline_at);

CREATE TABLE IF NOT EXISTS FolderSnapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES Task(id) ON DELETE CASCADE,
    taken_at TEXT NOT NULL,
    file_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    newest_mtime TEXT,
    files_json TEXT NOT NULL DEFAULT '[]'  -- [{path, mtime, size}] 압축
);

CREATE INDEX IF NOT EXISTS idx_snapshot_task_time
    ON FolderSnapshot (task_id, taken_at DESC);
