"""Wave 4 — Calendar API + ICS feed export."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB_PATH = _tmp_db.name
_tmp_db.close()
os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH
os.environ["NAEIL_DISABLE_WATCH"] = "1"
os.environ["NAEIL_DISABLE_FOLLOWUP"] = "1"

from backend.main import app
from backend.deps import get_db
from backend.api.calendar import build_ics_feed, _to_ics_dt, _escape_ics_text
from db import open_db, migrate
from persona import seed_builtin_prompts


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_TMP_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def _get_test_db():
    c = _conn()
    try:
        yield c
    finally:
        c.close()


app.dependency_overrides[get_db] = _get_test_db


def setUpModule():
    os.environ["TOMORROW_YOU_DB"] = _TMP_DB_PATH
    app.dependency_overrides[get_db] = _get_test_db
    c = open_db(_TMP_DB_PATH)
    migrate(c)
    seed_builtin_prompts(c)
    c.close()


def tearDownModule():
    try:
        os.unlink(_TMP_DB_PATH)
    except Exception:
        pass


client = TestClient(app, raise_server_exceptions=True)


def _create_user() -> tuple[str, str, dict]:
    r = client.post("/api/users", json={})
    d = r.json()
    return d["user_id"], d["device_token"], {"Authorization": f"Bearer {d['device_token']}"}


def _make_task(user_id: str, h: dict, title: str, deadline: str | None) -> int:
    r = client.post("/api/tasks", headers=h, json={
        "user_id": user_id,
        "title": title,
        "deadline_at": deadline,
    })
    return r.json()["id"]


# ────────────────────────────────────────────────────────────────────
# JSON events endpoint
# ────────────────────────────────────────────────────────────────────


class TestCalendarEventsAPI(unittest.TestCase):
    def test_events_returned_only_with_deadline(self):
        uid, _, h = _create_user()
        _make_task(uid, h, "유관", "2026-05-31T23:59:00+09:00")
        _make_task(uid, h, "무관", None)
        r = client.get(f"/api/calendar/{uid}/events", headers=h)
        self.assertEqual(r.status_code, 200)
        titles = [e["title"] for e in r.json()["events"]]
        self.assertIn("유관", titles)
        self.assertNotIn("무관", titles)

    def test_events_requires_token(self):
        uid, _, _ = _create_user()
        r = client.get(f"/api/calendar/{uid}/events")
        self.assertEqual(r.status_code, 401)


# ────────────────────────────────────────────────────────────────────
# ICS helpers
# ────────────────────────────────────────────────────────────────────


class TestICSHelpers(unittest.TestCase):
    def test_to_ics_dt_with_kst_converts_to_utc(self):
        self.assertEqual(_to_ics_dt("2026-05-31T23:59:00+09:00"), "20260531T145900Z")

    def test_to_ics_dt_naive_assumed_utc(self):
        self.assertEqual(_to_ics_dt("2026-05-31T00:00:00"), "20260531T000000Z")

    def test_to_ics_dt_malformed_returns_none(self):
        self.assertIsNone(_to_ics_dt("not a date"))

    def test_escape_text(self):
        self.assertEqual(_escape_ics_text("a, b; c\\d"), "a\\, b\\; c\\\\d")
        self.assertEqual(_escape_ics_text("line1\nline2"), "line1\\nline2")


# ────────────────────────────────────────────────────────────────────
# ICS feed endpoint
# ────────────────────────────────────────────────────────────────────


class TestICSFeedEndpoint(unittest.TestCase):
    def test_feed_returns_ics_with_event(self):
        uid, token, h = _create_user()
        _make_task(uid, h, "발표자료", "2026-05-31T23:59:00+09:00")
        r = client.get(f"/api/calendar/{uid}/feed.ics?token={token}")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/calendar", r.headers["content-type"])
        text = r.text
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("END:VCALENDAR", text)
        self.assertIn("SUMMARY:발표자료", text)
        self.assertIn("DTSTART:20260531T145900Z", text)

    def test_feed_skips_tasks_without_deadline(self):
        uid, token, h = _create_user()
        _make_task(uid, h, "마감없음", None)
        _make_task(uid, h, "마감있음", "2026-06-01T00:00:00+09:00")
        r = client.get(f"/api/calendar/{uid}/feed.ics?token={token}")
        self.assertIn("SUMMARY:마감있음", r.text)
        self.assertNotIn("SUMMARY:마감없음", r.text)

    def test_feed_rejects_wrong_token(self):
        uid, _, _ = _create_user()
        r = client.get(f"/api/calendar/{uid}/feed.ics?token=wrong")
        self.assertEqual(r.status_code, 401)

    def test_feed_rejects_missing_token(self):
        uid, _, _ = _create_user()
        r = client.get(f"/api/calendar/{uid}/feed.ics")
        self.assertEqual(r.status_code, 422)  # FastAPI required query param

    def test_event_status_maps_to_ics(self):
        uid, token, h = _create_user()
        tid = _make_task(uid, h, "T", "2026-05-31T00:00:00+09:00")
        client.patch(f"/api/tasks/{tid}", headers=h, json={"status": "done"})
        text = client.get(f"/api/calendar/{uid}/feed.ics?token={token}").text
        self.assertIn("STATUS:COMPLETED", text)


# ────────────────────────────────────────────────────────────────────
# build_ics_feed unit
# ────────────────────────────────────────────────────────────────────


class TestBuildICSFeed(unittest.TestCase):
    def test_empty_tasks(self):
        text = build_ics_feed("u", [])
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertNotIn("BEGIN:VEVENT", text)
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))


if __name__ == "__main__":
    unittest.main()
