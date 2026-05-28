"""Sprint 28: Adaptive Self-Learning Loop — tendencies pipeline tests."""

from __future__ import annotations

import json
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate
from persona import seed_builtin_prompts


def _fresh_conn() -> sqlite3.Connection:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = open_db(Path(tmp.name))
    migrate(conn)
    seed_builtin_prompts(conn)
    return conn


def _insert_user(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute(
        "INSERT INTO User (id, created_at) VALUES (?, ?)",
        (user_id, "2026-05-01T00:00:00Z"),
    )
    conn.commit()


class TestExtractFeaturesShape(unittest.TestCase):
    def test_no_data_returns_dict_with_nulls(self):
        from pipeline.tendencies import extract_features

        conn = _fresh_conn()
        _insert_user(conn, "u-empty")
        now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        out = extract_features(conn, "u-empty", now=now)
        self.assertIsInstance(out, dict)
        # All defined keys exist even when there's no data.
        for k in (
            "chat_count_7d",
            "avg_deadline_buffer_days",
            "peak_hour_histogram",
            "sharp_then_progress_ratio",
            "gentle_then_progress_ratio",
            "snapshot_growth_pattern",
        ):
            self.assertIn(k, out)


class TestDeadlineBuffer(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-buf")
        # 3 closed tasks. last_followup_at vs updated_at gap → buffer.
        now = datetime(2026, 5, 28, tzinfo=timezone.utc)
        for i, (status, last_fu_offset, closed_offset) in enumerate([
            ("done", 5, 1),       # last followup 5d ago, closed 1d ago → buf=4
            ("done", 7, 5),       # buf=2
            ("abandoned", 4, 1),  # buf=3
        ]):
            last_fu = (now - timedelta(days=last_fu_offset)).isoformat()
            closed_at = (now - timedelta(days=closed_offset)).isoformat()
            deadline = (now + timedelta(days=10)).isoformat()
            self.conn.execute(
                "INSERT INTO Task (user_id, title, deadline_at, status, "
                "created_at, updated_at, last_followup_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("u-buf", f"t{i}", deadline, status,
                 last_fu, closed_at, last_fu),
            )
        self.conn.commit()
        self.now = now

    def test_avg_deadline_buffer_days_mean_of_closed_tasks(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-buf", now=self.now)
        self.assertAlmostEqual(out["avg_deadline_buffer_days"], 3.0, places=1)

    def test_below_three_closed_returns_none(self):
        from pipeline.tendencies import extract_features
        _insert_user(self.conn, "u-buf-thin")
        out = extract_features(self.conn, "u-buf-thin", now=self.now)
        self.assertIsNone(out["avg_deadline_buffer_days"])


class TestChatStatistics(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-chat")
        # 5 chat messages in the last 7 days (KST hours 13–15).
        now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        sess = self.conn.execute(
            "INSERT INTO ChatSession (user_id, persona_id, created_at, updated_at)"
            " VALUES (?, NULL, ?, ?)",
            ("u-chat", now.isoformat(), now.isoformat()),
        ).lastrowid
        # KST = UTC+9. 13–15 KST = 04–06 UTC.
        for i, h in enumerate([4, 5, 5, 5, 6]):
            t = (now - timedelta(days=i, hours=0, minutes=0)).replace(hour=h)
            self.conn.execute(
                "INSERT INTO ChatMessage (chat_session_id, role, content, created_at)"
                " VALUES (?, 'user', ?, ?)",
                (sess, f"msg{i}", t.isoformat()),
            )
        self.conn.commit()
        self.now = now

    def test_chat_count_7d_counts_recent_user_messages(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-chat", now=self.now)
        self.assertEqual(out["chat_count_7d"], 5)

    def test_peak_hour_histogram_is_24_buckets_kst(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-chat", now=self.now)
        hist = out["peak_hour_histogram"]
        self.assertIsInstance(hist, list)
        self.assertEqual(len(hist), 24)
        # 4 UTC = 13 KST, 5 UTC = 14 KST, 6 UTC = 15 KST.
        self.assertEqual(hist[13], 1)
        self.assertEqual(hist[14], 3)
        self.assertEqual(hist[15], 1)
        self.assertEqual(sum(hist), 5)


class TestThenProgressRatio(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-prog")
        now = datetime(2026, 5, 28, tzinfo=timezone.utc)
        # 2 tasks, each with a followup then snapshots.
        for i, grew in enumerate([True, False]):
            fu = (now - timedelta(days=2)).isoformat()
            self.conn.execute(
                "INSERT INTO Task (id, user_id, title, deadline_at, status, "
                "created_at, updated_at, last_followup_at) "
                "VALUES (?, ?, ?, ?, 'open', ?, ?, ?)",
                (100 + i, "u-prog", f"t{i}",
                 (now + timedelta(days=5)).isoformat(),
                 fu, fu, fu),
            )
            # Snapshot before
            self.conn.execute(
                "INSERT INTO FolderSnapshot (task_id, taken_at, file_count, "
                "total_bytes, newest_mtime, files_json) "
                "VALUES (?, ?, 3, 300, ?, '[]')",
                (100 + i, (now - timedelta(days=3)).isoformat(),
                 (now - timedelta(days=3)).isoformat()),
            )
            # Snapshot after followup
            self.conn.execute(
                "INSERT INTO FolderSnapshot (task_id, taken_at, file_count, "
                "total_bytes, newest_mtime, files_json) "
                "VALUES (?, ?, ?, ?, ?, '[]')",
                (100 + i, (now - timedelta(days=1)).isoformat(),
                 5 if grew else 3, 500 if grew else 300,
                 (now - timedelta(days=1)).isoformat()),
            )
        self.conn.commit()
        self.now = now

    def test_then_progress_ratio_uses_growth_after_followup(self):
        from pipeline.tendencies import extract_features
        out = extract_features(self.conn, "u-prog", now=self.now)
        # 1 of 2 followups followed by growth → 0.5. Same value for both keys
        # in v1 because per-followup tone is not yet stored.
        self.assertAlmostEqual(out["sharp_then_progress_ratio"], 0.5)
        self.assertAlmostEqual(out["gentle_then_progress_ratio"], 0.5)

    def test_below_two_followups_returns_none(self):
        from pipeline.tendencies import extract_features
        _insert_user(self.conn, "u-prog-thin")
        out = extract_features(self.conn, "u-prog-thin", now=self.now)
        self.assertIsNone(out["sharp_then_progress_ratio"])
        self.assertIsNone(out["gentle_then_progress_ratio"])


class TestGrowthPattern(unittest.TestCase):
    def _setup(self, pattern: str):
        conn = _fresh_conn()
        _insert_user(conn, "u-grow")
        now = datetime(2026, 5, 28, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=10)).isoformat()
        conn.execute(
            "INSERT INTO Task (id, user_id, title, deadline_at, status, "
            "created_at, updated_at) VALUES (200, 'u-grow', 't', ?, 'open', ?, ?)",
            (deadline, (now - timedelta(days=30)).isoformat(), now.isoformat()),
        )
        # 5 snapshots over 30 days. file_count series:
        # 'late_spike': 0,0,0,1,8
        # 'steady':     1,3,5,7,9
        # 'flat':       1,1,1,1,1
        series = {
            "late_spike": [0, 0, 0, 1, 8],
            "steady": [1, 3, 5, 7, 9],
            "flat": [1, 1, 1, 1, 1],
        }[pattern]
        for i, fc in enumerate(series):
            t = (now - timedelta(days=30 - i * 6)).isoformat()
            conn.execute(
                "INSERT INTO FolderSnapshot (task_id, taken_at, file_count, "
                "total_bytes, newest_mtime, files_json) "
                "VALUES (200, ?, ?, ?, ?, '[]')",
                (t, fc, fc * 100, t),
            )
        conn.commit()
        return conn, now

    def test_late_spike_classification(self):
        from pipeline.tendencies import extract_features
        conn, now = self._setup("late_spike")
        out = extract_features(conn, "u-grow", now=now)
        self.assertEqual(out["snapshot_growth_pattern"], "late_spike")

    def test_steady_classification(self):
        from pipeline.tendencies import extract_features
        conn, now = self._setup("steady")
        out = extract_features(conn, "u-grow", now=now)
        self.assertEqual(out["snapshot_growth_pattern"], "steady")

    def test_flat_classification(self):
        from pipeline.tendencies import extract_features
        conn, now = self._setup("flat")
        out = extract_features(conn, "u-grow", now=now)
        self.assertEqual(out["snapshot_growth_pattern"], "flat")


class TestLLMCritic(unittest.TestCase):
    def test_critic_parses_well_formed_json(self):
        from pipeline.tendencies import llm_critic

        features = {
            "chat_count_7d": 12,
            "avg_deadline_buffer_days": 1.4,
            "peak_hour_histogram": [0]*13 + [4, 5, 4] + [0]*8,
            "sharp_then_progress_ratio": 0.7,
            "gentle_then_progress_ratio": 0.7,
            "snapshot_growth_pattern": "late_spike",
        }
        chat_samples = ["오늘 보고서 마지막 챕터", "이번엔 정말 미리 하자"]

        canned_response = """
        {"tone_preference":"sharp","reaction_to_sharp":"improves",
         "typical_deadline_buffer_days":1,"peak_work_hours":[13,14,15],
         "confidence":{"tone_preference":0.78,"reaction_to_sharp":0.55,
         "typical_deadline_buffer_days":0.92,"peak_work_hours":0.7}}
        """
        def fake_call_fn(messages, **kw):
            return {"message": {"content": canned_response}}

        out = llm_critic(features, chat_samples, call_fn=fake_call_fn)
        self.assertEqual(out["tone_preference"], "sharp")
        self.assertEqual(out["reaction_to_sharp"], "improves")
        self.assertEqual(out["typical_deadline_buffer_days"], 1)
        self.assertEqual(out["peak_work_hours"], [13, 14, 15])
        self.assertEqual(out["confidence"]["tone_preference"], 0.78)

    def test_critic_returns_empty_on_invalid_json(self):
        from pipeline.tendencies import llm_critic
        def bad_call_fn(messages, **kw):
            return {"message": {"content": "I'm thinking about this..."}}
        out = llm_critic({}, [], call_fn=bad_call_fn)
        self.assertEqual(out, {})

    def test_critic_drops_unknown_keys(self):
        from pipeline.tendencies import llm_critic
        def call_fn(messages, **kw):
            return {"message": {"content":
                '{"tone_preference":"sharp","unknown_dim":"x",'
                '"confidence":{"tone_preference":0.5}}'}}
        out = llm_critic({}, [], call_fn=call_fn)
        self.assertIn("tone_preference", out)
        self.assertNotIn("unknown_dim", out)

    def test_critic_does_not_pass_model_kwarg(self):
        """Regression: real _call_ollama_chat doesn't accept `model`."""
        from pipeline.tendencies import llm_critic
        received_kwargs: dict = {}
        def capturing_call_fn(messages, **kw):
            received_kwargs.update(kw)
            return {"message": {"content": "{}"}}
        llm_critic({}, [], call_fn=capturing_call_fn)
        self.assertNotIn("model", received_kwargs)
        # Sanity: the kwargs we DO send are still there
        self.assertEqual(received_kwargs["temperature"], 0.0)
        self.assertEqual(received_kwargs["num_predict"], 400)


class TestMerge(unittest.TestCase):
    def test_merge_writes_version_at_and_both_subtrees(self):
        from pipeline.tendencies import merge
        features = {"chat_count_7d": 5, "avg_deadline_buffer_days": 1.4,
                    "peak_hour_histogram": [0]*24,
                    "sharp_then_progress_ratio": None,
                    "gentle_then_progress_ratio": None,
                    "snapshot_growth_pattern": "flat"}
        critic = {"tone_preference": "sharp",
                  "reaction_to_sharp": "improves",
                  "typical_deadline_buffer_days": 1,
                  "peak_work_hours": [13, 14],
                  "confidence": {"tone_preference": 0.8}}
        now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        out = merge(features, critic, now=now)
        self.assertEqual(out["version_at"], "2026-05-28T12:00:00+00:00")
        self.assertEqual(out["raw_features"], features)
        self.assertEqual(out["qualitative"]["tone_preference"], "sharp")
        self.assertEqual(out["confidence"]["tone_preference"], 0.8)

    def test_merge_default_confidence_zero_for_missing_dims(self):
        from pipeline.tendencies import merge
        out = merge({}, {}, now=datetime(2026, 5, 28, tzinfo=timezone.utc))
        self.assertEqual(out["qualitative"], {})
        self.assertEqual(out["confidence"], {})

    def test_merge_critic_only_qualitative(self):
        """Heuristic-first numeric / critic-only qualitative."""
        from pipeline.tendencies import merge
        features = {"avg_deadline_buffer_days": 2.0}
        critic = {"typical_deadline_buffer_days": 99,
                  "tone_preference": "savage",
                  "confidence": {"tone_preference": 0.9,
                                 "typical_deadline_buffer_days": 0.3}}
        out = merge(features, critic, now=datetime(2026, 5, 28, tzinfo=timezone.utc))
        # qualitative.typical_deadline_buffer_days comes from critic (qualitative subtree)
        self.assertEqual(out["qualitative"]["typical_deadline_buffer_days"], 99)
        # raw_features still has the heuristic value
        self.assertEqual(out["raw_features"]["avg_deadline_buffer_days"], 2.0)


class TestMemoryRoundTrip(unittest.TestCase):
    def test_save_then_load_returns_same_dict(self):
        from pipeline.tendencies import save_to_memory, load_from_memory, merge

        conn = _fresh_conn()
        _insert_user(conn, "u-mem")
        payload = merge(
            {"chat_count_7d": 7, "avg_deadline_buffer_days": 1.4,
             "peak_hour_histogram": [0]*24, "sharp_then_progress_ratio": 0.5,
             "gentle_then_progress_ratio": 0.5, "snapshot_growth_pattern": "flat"},
            {"tone_preference": "sharp",
             "confidence": {"tone_preference": 0.8}},
            now=datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc),
        )
        save_to_memory(conn, "u-mem", payload)
        loaded = load_from_memory(conn, "u-mem")
        self.assertEqual(loaded["qualitative"]["tone_preference"], "sharp")
        self.assertEqual(loaded["confidence"]["tone_preference"], 0.8)
        self.assertEqual(loaded["raw_features"]["chat_count_7d"], 7)

    def test_load_returns_none_when_missing(self):
        from pipeline.tendencies import load_from_memory
        conn = _fresh_conn()
        _insert_user(conn, "u-empty")
        self.assertIsNone(load_from_memory(conn, "u-empty"))

    def test_load_returns_none_on_invalid_json(self):
        from pipeline.tendencies import load_from_memory
        from pipeline.memory import upsert_memory
        conn = _fresh_conn()
        _insert_user(conn, "u-bad")
        upsert_memory(conn, user_id="u-bad",
                      key="adaptive_tendencies", value="{not json")
        self.assertIsNone(load_from_memory(conn, "u-bad"))


class TestReflectionHook(unittest.TestCase):
    def test_run_reflection_invokes_tendencies(self):
        """run_reflection should populate UserMemory[adaptive_tendencies]."""
        from pipeline.reflection import run_reflection
        from pipeline.tendencies import load_from_memory

        conn = _fresh_conn()
        _insert_user(conn, "u-ref")
        # Seed minimal chat + closed task so extract_features has data
        sess = conn.execute(
            "INSERT INTO ChatSession (user_id, persona_id, created_at, "
            "updated_at) VALUES ('u-ref', NULL, ?, ?)",
            ("2026-05-27T05:00:00Z", "2026-05-27T05:00:00Z"),
        ).lastrowid
        conn.execute(
            "INSERT INTO ChatMessage (chat_session_id, role, content, created_at) "
            "VALUES (?, 'user', 'hi', ?)",
            (sess, "2026-05-27T05:00:00Z"),
        )
        conn.commit()

        # call_fn: first call is the existing reflection LLM, second is tendencies.
        # Both should be tolerant of "no actions" / "no qualitative" answers.
        responses = iter([
            {"message": {"content": '[]'}},
            {"message": {"content":
                '{"tone_preference":"sharp",'
                '"confidence":{"tone_preference":0.6}}'}},
        ])
        def fake_call_fn(messages, **kw):
            return next(responses)

        result = run_reflection(
            conn, "u-ref",
            now=datetime(2026, 5, 28, tzinfo=timezone.utc),
            call_fn=fake_call_fn,
        )
        # The existing reflection result keys are preserved.
        self.assertIn("ran", result)
        # And the new tendencies persisted.
        tendencies = load_from_memory(conn, "u-ref")
        self.assertIsNotNone(tendencies)
        self.assertEqual(tendencies["qualitative"]["tone_preference"], "sharp")


if __name__ == "__main__":
    unittest.main()
