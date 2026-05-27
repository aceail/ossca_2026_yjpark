"""G003 DataModel — 17 테이블 + 마이그레이션 + 5 페르소나 seed + 기본 CRUD 테스트."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, list_personas, get_persona  # noqa: E402

EXPECTED_TABLES = {
    "User", "UserProfile", "AvoidanceSession", "RegretScore", "FingerprintSnapshot",
    "ScenarioCard", "ProbeQuestion", "ProbeAnswer", "ModelRun", "PromptVersion",
    "EvaluationResult", "SchemaMigration",
    "SafetyHarmTimeSeries",
    "ExternalIntegration", "AgentTool", "ToolInvocation",
    "Persona",
}

BUILTIN_PERSONAS = {"내일의 나", "1년 후의 나", "친한 친구", "엄격한 코치", "기록자"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_initial_migration_applies(self):
        applied = migrate(self.conn)
        self.assertIn("001_initial", applied)

    def test_idempotent_migration(self):
        migrate(self.conn)
        applied2 = migrate(self.conn)
        self.assertEqual(applied2, [])

    def test_all_17_tables_present(self):
        migrate(self.conn)
        tables = {
            r["name"]
            for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing = EXPECTED_TABLES - tables
        self.assertFalse(missing, f"missing tables: {missing}")
        self.assertEqual(len(EXPECTED_TABLES), 17)

    def test_schema_migration_record(self):
        migrate(self.conn)
        rows = self.conn.execute("SELECT version, checksum FROM SchemaMigration ORDER BY version").fetchall()
        self.assertGreaterEqual(len(rows), 1)
        versions = [r["version"] for r in rows]
        self.assertIn("001_initial", versions)
        for r in rows:
            self.assertIsNotNone(r["checksum"])


class TestPersonaSeed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_five_builtin_personas_seeded(self):
        personas = list_personas(self.conn, builtin_only=True)
        names = {p["name"] for p in personas}
        self.assertEqual(names, BUILTIN_PERSONAS)

    def test_persona_perspectives_distribution(self):
        personas = list_personas(self.conn, builtin_only=True)
        perspectives = {p["name"]: p["perspective"] for p in personas}
        self.assertEqual(perspectives["내일의 나"], "1st")
        self.assertEqual(perspectives["친한 친구"], "2nd")
        self.assertEqual(perspectives["기록자"], "3rd")

    def test_get_persona_by_name(self):
        row = get_persona(self.conn, "내일의 나")
        self.assertIsNotNone(row)
        self.assertEqual(row["tone_mode"], "Sharp")
        self.assertEqual(row["avatar_icon"], "🌙")


class TestCRUDFlow(unittest.TestCase):
    """End-to-end CRUD: User → UserProfile → AvoidanceSession → ScenarioCard → RegretScore."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)
        self.user_id = f"local-{uuid4().hex[:8]}"
        self.conn.execute(
            "INSERT INTO User (id, created_at) VALUES (?, ?)",
            (self.user_id, now()),
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)

    def test_user_profile_with_persona(self):
        persona = get_persona(self.conn, "내일의 나")
        self.conn.execute(
            """INSERT INTO UserProfile
               (user_id, slots_json, completion_percent, forbidden_topics_json, active_persona_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                self.user_id,
                json.dumps({"trigger_category": {"value": "글쓰기"}}),
                60.0,
                json.dumps([]),
                persona["id"],
                now(),
            ),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM UserProfile WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        self.assertEqual(row["completion_percent"], 60.0)
        self.assertEqual(row["active_persona_id"], persona["id"])

    def test_avoidance_session_to_scenario_card(self):
        cur = self.conn.execute(
            "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
            (self.user_id, "PPT 0장이야", now()),
        )
        session_id = cur.lastrowid
        persona = get_persona(self.conn, "내일의 나")
        cur = self.conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, persona_id, fact, feeling, micro_action, created_at)
               VALUES (?, 'regret', ?, ?, ?, ?, ?)""",
            (session_id, persona["id"], "새벽 1시 14분", "내일 9시의 나", "워드를 켠다", now()),
        )
        card_id = cur.lastrowid
        self.conn.execute("UPDATE AvoidanceSession SET scenario_card_id = ? WHERE id = ?", (card_id, session_id))
        self.conn.commit()
        joined = self.conn.execute(
            """SELECT a.avoidance_input, c.fact, c.micro_action
               FROM AvoidanceSession a JOIN ScenarioCard c ON c.avoidance_session_id = a.id
               WHERE a.id = ?""",
            (session_id,),
        ).fetchone()
        self.assertEqual(joined["fact"], "새벽 1시 14분")
        self.assertEqual(joined["micro_action"], "워드를 켠다")

    def test_regret_score_constraint(self):
        cur = self.conn.execute(
            "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
            (self.user_id, "x", now()),
        )
        sid = cur.lastrowid
        # 정상 범위
        self.conn.execute(
            "INSERT INTO RegretScore (avoidance_session_id, user_id, intensity, recorded_at) VALUES (?, ?, ?, ?)",
            (sid, self.user_id, 7, now()),
        )
        # 범위 초과 → CHECK 위반
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO RegretScore (avoidance_session_id, user_id, intensity, recorded_at) VALUES (?, ?, ?, ?)",
                (sid, self.user_id, 15, now()),
            )

    def test_cascade_delete_user(self):
        cur = self.conn.execute(
            "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
            (self.user_id, "y", now()),
        )
        self.conn.commit()
        before = self.conn.execute(
            "SELECT COUNT(*) FROM AvoidanceSession WHERE user_id = ?", (self.user_id,)
        ).fetchone()[0]
        self.assertEqual(before, 1)
        self.conn.execute("DELETE FROM User WHERE id = ?", (self.user_id,))
        self.conn.commit()
        after = self.conn.execute(
            "SELECT COUNT(*) FROM AvoidanceSession WHERE user_id = ?", (self.user_id,)
        ).fetchone()[0]
        self.assertEqual(after, 0)

    def test_safety_harm_time_series(self):
        self.conn.execute(
            """INSERT INTO SafetyHarmTimeSeries (user_id, week_start, self_blame_word_count, snapshot_at)
               VALUES (?, ?, ?, ?)""",
            (self.user_id, "2026-W21", 4, now()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT self_blame_word_count FROM SafetyHarmTimeSeries WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        self.assertEqual(row["self_blame_word_count"], 4)

    def test_tool_invocation_audit(self):
        # 004 마이그레이션 seed와 충돌 회피 — 테스트 전용 이름
        cur = self.conn.execute(
            "INSERT INTO AgentTool (name, type, created_at) VALUES (?, ?, ?)",
            ("test_only.list_events", "calendar", now()),
        )
        tool_id = cur.lastrowid
        self.conn.execute(
            """INSERT INTO ToolInvocation (user_id, agent_tool_id, input_json, output_json, latency_ms, invoked_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (self.user_id, tool_id, json.dumps({"q": "next 7 days"}), json.dumps([]), 142, now()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT latency_ms FROM ToolInvocation WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        self.assertEqual(row["latency_ms"], 142)


if __name__ == "__main__":
    unittest.main()
