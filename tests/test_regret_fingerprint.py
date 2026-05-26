"""G007 RegretFingerprint — scheduler, fingerprint, slow harm, accuracy 평가 루프."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from regret import (  # noqa: E402
    FingerprintBuilder,
    SlowHarmMonitor,
    build_weekly_snapshot,
    record_card_accuracy,
    record_return_intent,
    record_regret_score,
    schedule_reminder,
    update_fingerprint_snapshot,
    week_start_iso,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _RegretFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.db_path = Path(self.tmp.name)
        self.conn = open_db(self.db_path)
        migrate(self.conn)
        self.user_id = "u-test"
        self.conn.execute("INSERT INTO User (id, created_at) VALUES (?, ?)", (self.user_id, _now()))
        cur = self.conn.execute(
            "INSERT INTO AvoidanceSession (user_id, avoidance_input, created_at) VALUES (?, ?, ?)",
            (self.user_id, "PPT 0장이야. 또 이러네.", _now()),
        )
        self.session_id = cur.lastrowid
        persona = get_persona(self.conn, "내일의 나")
        cur = self.conn.execute(
            """INSERT INTO ScenarioCard
               (avoidance_session_id, card_type, persona_id, fact, feeling, micro_action, created_at)
               VALUES (?, 'regret', ?, 'f', 'g', 'a', ?)""",
            (self.session_id, persona["id"], _now()),
        )
        self.card_id = cur.lastrowid
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.db_path.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            Path(str(self.db_path) + suffix).unlink(missing_ok=True)


class TestRegretSchedulerAndScore(_RegretFixture):
    def test_schedule_reminder_24h(self):
        reminder = schedule_reminder(self.conn, self.session_id, after_hours=24)
        self.assertEqual(reminder.avoidance_session_id, self.session_id)
        remind_at = datetime.fromisoformat(reminder.remind_at)
        self.assertGreater(remind_at, datetime.now(timezone.utc))

    def test_record_regret_score_in_range(self):
        rid = record_regret_score(self.conn, avoidance_session_id=self.session_id, user_id=self.user_id, intensity=7, free_text="후회됨")
        row = self.conn.execute("SELECT intensity, free_text FROM RegretScore WHERE id = ?", (rid,)).fetchone()
        self.assertEqual(row["intensity"], 7)
        self.assertEqual(row["free_text"], "후회됨")

    def test_record_regret_score_out_of_range(self):
        with self.assertRaises(ValueError):
            record_regret_score(self.conn, avoidance_session_id=self.session_id, user_id=self.user_id, intensity=15)


class TestFingerprint(_RegretFixture):
    def test_corpus_collection(self):
        self.conn.execute(
            "INSERT INTO ProbeAnswer (user_id, avoidance_session_id, probe_question_id, answer_text, answered_at) VALUES (?, ?, ?, ?, ?)",
            (self.user_id, self.session_id, 1, "어제도 미뤘다", _now()),
        )
        self.conn.execute(
            "INSERT INTO ProbeQuestion (text, target_slot, expected_information_gain, created_at) VALUES (?, ?, ?, ?)",
            ("Q?", "slot", 0.5, _now()),
        )
        self.conn.commit()
        builder = FingerprintBuilder(user_id=self.user_id)
        corpus = builder.collect_corpus(self.conn)
        self.assertIn("PPT 0장이야. 또 이러네.", corpus)

    def test_update_snapshot_creates_row(self):
        fid = update_fingerprint_snapshot(self.conn, self.user_id)
        row = self.conn.execute(
            "SELECT embedding_model, embedding_json, stats_json FROM FingerprintSnapshot WHERE id = ?", (fid,)
        ).fetchone()
        self.assertEqual(row["embedding_model"], "tomorrow-you-tf-hash-v1")
        emb = json.loads(row["embedding_json"])
        self.assertEqual(len(emb), 16)
        stats = json.loads(row["stats_json"])
        self.assertGreaterEqual(stats["session_count"], 1)


class TestSlowHarm(_RegretFixture):
    def test_week_start_iso_format(self):
        week = week_start_iso(datetime(2026, 5, 26, tzinfo=timezone.utc))
        self.assertRegex(week, r"^\d{4}-W\d{2}$")

    def test_count_self_blame_words(self):
        monitor = SlowHarmMonitor(user_id=self.user_id)
        n = monitor.count_blame(["나는 한심하다. 또 이러네. 또 이러네."])
        self.assertGreaterEqual(n, 3)

    def test_count_identity_failure_phrases(self):
        monitor = SlowHarmMonitor(user_id=self.user_id)
        n = monitor.count_identity_failure(["또 이러네 어차피 안 돼"])
        self.assertGreaterEqual(n, 2)

    def test_build_weekly_snapshot_upserts(self):
        sid1 = build_weekly_snapshot(self.conn, self.user_id, pre_card_tension_self_report=3.0)
        sid2 = build_weekly_snapshot(self.conn, self.user_id)
        self.assertEqual(sid1, sid2)
        row = self.conn.execute("SELECT self_blame_word_count, identity_failure_phrases_count FROM SafetyHarmTimeSeries WHERE id = ?", (sid1,)).fetchone()
        # AvoidanceSession 입력에 "또 이러네"가 있어서 identity failure 1+ 잡혀야
        self.assertGreaterEqual(row["identity_failure_phrases_count"], 1)

    def test_failure_imagery_ratio(self):
        monitor = SlowHarmMonitor(user_id=self.user_id)
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        ratio = monitor.failure_imagery_ratio(self.conn, since)
        # 1 regret card / total 1 = 1.0
        self.assertEqual(ratio, 1.0)


class TestAccuracyAndReturnIntent(_RegretFixture):
    def test_card_accuracy_4_passes(self):
        eid = record_card_accuracy(self.conn, scenario_card_id=self.card_id, accuracy_score=4)
        row = self.conn.execute("SELECT pass, metrics_json FROM EvaluationResult WHERE id = ?", (eid,)).fetchone()
        self.assertEqual(row["pass"], 1)
        metrics = json.loads(row["metrics_json"])
        self.assertEqual(metrics["accuracy_self_rating"], 4)

    def test_card_accuracy_2_fails(self):
        eid = record_card_accuracy(self.conn, scenario_card_id=self.card_id, accuracy_score=2)
        row = self.conn.execute("SELECT pass FROM EvaluationResult WHERE id = ?", (eid,)).fetchone()
        self.assertEqual(row["pass"], 0)

    def test_return_intent_records(self):
        eid = record_return_intent(self.conn, scenario_card_id=self.card_id, intent_score=5)
        row = self.conn.execute("SELECT metrics_json FROM EvaluationResult WHERE id = ?", (eid,)).fetchone()
        metrics = json.loads(row["metrics_json"])
        self.assertEqual(metrics["return_intent_self_rating"], 5)

    def test_accuracy_invalid_range(self):
        with self.assertRaises(ValueError):
            record_card_accuracy(self.conn, scenario_card_id=self.card_id, accuracy_score=6)


if __name__ == "__main__":
    unittest.main()
