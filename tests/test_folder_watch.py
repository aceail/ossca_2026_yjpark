"""Wave 2 — LocalFolderProvider + scan_open_tasks loop."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.providers import LocalFolderProvider, get_folder_provider
from db import open_db, migrate, get_persona
from persona import seed_builtin_prompts
from pipeline.folder_watch import scan_open_tasks


def _setup_db_with_user() -> tuple[sqlite3.Connection, str]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    user_id = "watch-user"
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    persona = get_persona(conn, "내일의 나")
    conn.execute(
        """INSERT OR IGNORE INTO UserProfile
           (user_id, slots_json, completion_percent, active_persona_id, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, "{}", 0.0, persona["id"] if persona else None, now),
    )
    conn.commit()
    return conn, user_id


def _make_task(conn: sqlite3.Connection, user_id: str, folder_path: str | None,
               status: str = "open") -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """INSERT INTO Task (user_id, title, folder_path, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, "T", folder_path, status, now, now),
    )
    conn.commit()
    return cur.lastrowid


class TestLocalFolderProvider(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            snap = LocalFolderProvider().snapshot(d)
            self.assertIsNotNone(snap)
            self.assertEqual(snap.file_count, 0)
            self.assertEqual(snap.total_bytes, 0)
            self.assertIsNone(snap.newest_mtime)

    def test_counts_files_and_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.txt").write_text("hello")          # 5 bytes
            (Path(d) / "b.bin").write_bytes(b"\x00" * 100)   # 100 bytes
            snap = LocalFolderProvider().snapshot(d)
            self.assertEqual(snap.file_count, 2)
            self.assertEqual(snap.total_bytes, 105)
            self.assertIsNotNone(snap.newest_mtime)

    def test_nonexistent_returns_none(self):
        self.assertIsNone(LocalFolderProvider().snapshot("/no/such/path/xyz"))

    def test_file_path_returns_none(self):
        with tempfile.NamedTemporaryFile() as f:
            self.assertIsNone(LocalFolderProvider().snapshot(f.name))

    def test_newer_file_wins_in_newest_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "old.txt").write_text("o")
            time.sleep(0.05)
            (Path(d) / "new.txt").write_text("n")
            snap = LocalFolderProvider().snapshot(d)
            new_mtime = next(f for f in snap.files if f["name"] == "new.txt")["mtime"]
            self.assertEqual(snap.newest_mtime, new_mtime)

    def test_max_files_cap(self):
        with tempfile.TemporaryDirectory() as d:
            for i in range(10):
                (Path(d) / f"f{i}.txt").write_text(str(i))
            snap = LocalFolderProvider(max_files=3).snapshot(d)
            self.assertEqual(snap.file_count, 3)


class TestFactory(unittest.TestCase):
    def test_default_mode_returns_local(self):
        os.environ.pop("NAEIL_MODE", None)
        self.assertIsInstance(get_folder_provider(), LocalFolderProvider)

    def test_explicit_local(self):
        os.environ["NAEIL_MODE"] = "local"
        try:
            self.assertIsInstance(get_folder_provider(), LocalFolderProvider)
        finally:
            os.environ.pop("NAEIL_MODE", None)

    def test_unknown_mode_raises(self):
        os.environ["NAEIL_MODE"] = "kubernetes"
        try:
            with self.assertRaises(ValueError):
                get_folder_provider()
        finally:
            os.environ.pop("NAEIL_MODE", None)


class TestScanOpenTasks(unittest.TestCase):
    def test_inserts_snapshot_for_each_open_task_with_folder(self):
        conn, user_id = _setup_db_with_user()
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            (Path(d1) / "x.txt").write_text("hi")
            t1 = _make_task(conn, user_id, d1)
            t2 = _make_task(conn, user_id, d2)
            n = scan_open_tasks(conn)
            self.assertEqual(n, 2)
            rows = conn.execute(
                "SELECT task_id, file_count FROM FolderSnapshot ORDER BY task_id"
            ).fetchall()
            ids = sorted([r["task_id"] for r in rows])
            self.assertEqual(ids, sorted([t1, t2]))

    def test_skips_done_tasks(self):
        conn, user_id = _setup_db_with_user()
        with tempfile.TemporaryDirectory() as d:
            _make_task(conn, user_id, d, status="done")
            self.assertEqual(scan_open_tasks(conn), 0)

    def test_skips_tasks_without_folder(self):
        conn, user_id = _setup_db_with_user()
        _make_task(conn, user_id, None)
        self.assertEqual(scan_open_tasks(conn), 0)

    def test_skips_invalid_folder(self):
        conn, user_id = _setup_db_with_user()
        _make_task(conn, user_id, "/path/that/does/not/exist/xyzzy")
        self.assertEqual(scan_open_tasks(conn), 0)

    def test_files_json_round_trip(self):
        conn, user_id = _setup_db_with_user()
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("body")
            tid = _make_task(conn, user_id, d)
            scan_open_tasks(conn)
            row = conn.execute(
                "SELECT files_json FROM FolderSnapshot WHERE task_id = ?", (tid,)
            ).fetchone()
            files = json.loads(row["files_json"])
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["name"], "a.md")


if __name__ == "__main__":
    unittest.main()
