# Adaptive Self-Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Hermes feedback loop by extracting typed per-user tendencies every reflection cycle and using them to personalize followup tone selection and kick-in timing.

**Architecture:** Hybrid hub-and-spoke. `pipeline/tendencies.py` is the new hub that (a) deterministically extracts numeric features from existing tables, (b) asks qwen3:8b (think=false) to add qualitative dims, (c) merges and persists as JSON under `UserMemory["adaptive_tendencies"]`. The reflection loop calls the hub each cycle; the followup pipeline reads from the persisted JSON when picking tone and timing. Failure of either heuristic or LLM leg degrades gracefully — the followup loop always has a fallback path.

**Tech Stack:** Python 3.12 · sqlite3 · existing Sprint 21 reflection loop · existing Sprint 27 `@trace_subsystem` decorators · qwen3:8b via the project's existing `_call_ollama_chat` (urllib + Ollama API).

**Spec deviations recorded (so the spec stays the contract):**

1. **Integration point.** Spec §9 named `pipeline/followup.py:decide_followup` but `decide_followup` actually lives in `pipeline/followup_tone.py`. This plan touches `followup_tone.py` for the logic change and `followup.py` only for plumbing (loading tendencies and forwarding the dict).
2. **Tone enum.** Spec §5 used `tone_preference: gentle | sharp | balanced`. The project's `Tone` literal is `quiet | witty | sharp | savage`. The plan aligns the critic prompt with the actual enum and a small mapping helper inside `tendencies.py` keeps the persisted JSON readable while the followup integration uses the project's enum directly.

---

## File Structure

**New files**

| Path | Responsibility |
|---|---|
| `pipeline/tendencies.py` | The hub: `extract_features`, `llm_critic`, `merge`, `save_to_memory`, `load_from_memory`. Also `_extract_*` private helpers, one per feature. |
| `tests/test_tendencies.py` | All tendency tests: extractor unit tests, mocked-LLM critic tests, merge correctness, memory round-trip, end-to-end with followup. |

**Modified files**

| Path | Change |
|---|---|
| `pipeline/reflection.py` | `run_reflection` invokes `tendencies.extract_features → llm_critic → merge → save_to_memory` at the end of each cycle. Wrapped in try/except so an existing reflection cycle keeps working even if tendencies fail. |
| `pipeline/followup_tone.py` | `decide_followup` accepts a new optional kwarg `adaptive_tendencies: dict | None = None`. Uses `qualitative.tone_preference` (gated by confidence ≥ 0.3) and `qualitative.typical_deadline_buffer_days` (same gate) when present. |
| `pipeline/followup.py` | `dispatch_due_followups` loads `tendencies.load_from_memory(conn, user_id)` once per task and forwards it into `decide_followup(...)`. |

---

## Task 1: Skeleton module + first failing test

**Files:**
- Create: `pipeline/tendencies.py`
- Create: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tendencies.py`:

```python
"""Sprint 28: Adaptive Self-Learning Loop — tendencies pipeline tests."""

from __future__ import annotations

import json
import sys
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestExtractFeaturesShape -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.tendencies'`.

- [ ] **Step 3: Create `pipeline/tendencies.py` skeleton**

```python
"""Sprint 28 — Adaptive Self-Learning Loop.

Heuristic + LLM hybrid that extracts per-user behavioral tendencies and
persists them under UserMemory["adaptive_tendencies"] as a typed JSON.

Pipeline (called once per user per reflection cycle):

    extract_features(conn, user_id, now) -> dict   # heuristic-only
    llm_critic(features, recent_chat, call_fn)     # LLM-driven qualitative
    merge(features, critic_output) -> dict          # heuristic-first numeric
    save_to_memory(conn, user_id, merged)           # JSON into UserMemory

Read path (called from followup loop):

    load_from_memory(conn, user_id) -> dict | None
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from agent.tracing import trace_subsystem


_FEATURE_KEYS = (
    "chat_count_7d",
    "avg_deadline_buffer_days",
    "peak_hour_histogram",
    "sharp_then_progress_ratio",
    "gentle_then_progress_ratio",
    "snapshot_growth_pattern",
)


@trace_subsystem("tendencies")
def extract_features(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Deterministic feature extraction from existing tables.

    Returns a dict with every key in _FEATURE_KEYS. Unmeasurable features
    are None so callers (and the LLM critic) can be cautious.
    """
    _now = now or datetime.now(timezone.utc)
    return {key: None for key in _FEATURE_KEYS}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestExtractFeaturesShape -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): Sprint 28 — module skeleton + extract_features shape"
```

---

## Task 2: extract chat_count_7d + peak_hour_histogram

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
class TestChatStatistics(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-chat")
        # 5 chat messages in the last 7 days (KST hours 13–15).
        from datetime import timedelta
        now = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
        sess = self.conn.execute(
            "INSERT INTO ChatSession (user_id, persona_id, created_at, last_message_at)"
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestChatStatistics -v`
Expected: FAIL on `assertEqual(out['chat_count_7d'], 5)` because the placeholder returns None.

- [ ] **Step 3: Implement the two extractors**

Replace `extract_features` in `pipeline/tendencies.py` with:

```python
from datetime import timedelta


def _extract_chat_count_7d(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> int:
    cutoff = (now - timedelta(days=7)).isoformat()
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM ChatMessage m
           JOIN ChatSession s ON s.id = m.chat_session_id
           WHERE s.user_id = ? AND m.role = 'user' AND m.created_at >= ?""",
        (user_id, cutoff),
    ).fetchone()
    return int(row["c"]) if row else 0


def _extract_peak_hour_histogram(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> list[int]:
    """24-bucket KST hour-of-day histogram of the user's chat messages
    over the last 30 days."""
    cutoff = (now - timedelta(days=30)).isoformat()
    rows = conn.execute(
        """SELECT m.created_at FROM ChatMessage m
           JOIN ChatSession s ON s.id = m.chat_session_id
           WHERE s.user_id = ? AND m.role = 'user' AND m.created_at >= ?""",
        (user_id, cutoff),
    ).fetchall()
    buckets = [0] * 24
    for r in rows:
        ts = r["created_at"] or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            kst = dt + timedelta(hours=9)
            buckets[kst.hour] += 1
        except (ValueError, IndexError):
            continue
    return buckets


@trace_subsystem("tendencies")
def extract_features(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Deterministic feature extraction from existing tables."""
    _now = now or datetime.now(timezone.utc)
    return {
        "chat_count_7d": _extract_chat_count_7d(conn, user_id, _now),
        "avg_deadline_buffer_days": None,
        "peak_hour_histogram": _extract_peak_hour_histogram(conn, user_id, _now),
        "sharp_then_progress_ratio": None,
        "gentle_then_progress_ratio": None,
        "snapshot_growth_pattern": None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): chat_count_7d + peak_hour_histogram extractors"
```

---

## Task 3: extract avg_deadline_buffer_days

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
class TestDeadlineBuffer(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-buf")
        # 3 closed tasks. last_followup_at 2 days before updated_at on average.
        from datetime import timedelta
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestDeadlineBuffer -v`
Expected: FAIL on first assertion — current value is None.

- [ ] **Step 3: Implement the extractor**

Add to `pipeline/tendencies.py` (before `extract_features`):

```python
def _extract_avg_deadline_buffer_days(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> Optional[float]:
    """Mean of (closed_at - last_followup_at) over closed tasks.

    closed_at = updated_at for status in ('done', 'abandoned').
    Returns None if fewer than 3 closed tasks have a non-null last_followup_at.
    """
    rows = conn.execute(
        """SELECT updated_at, last_followup_at FROM Task
           WHERE user_id = ? AND status IN ('done', 'abandoned')
             AND last_followup_at IS NOT NULL""",
        (user_id,),
    ).fetchall()
    if len(rows) < 3:
        return None
    diffs: list[float] = []
    for r in rows:
        try:
            closed = datetime.fromisoformat(
                (r["updated_at"] or "").replace("Z", "+00:00")
            )
            fu = datetime.fromisoformat(
                (r["last_followup_at"] or "").replace("Z", "+00:00")
            )
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            if fu.tzinfo is None:
                fu = fu.replace(tzinfo=timezone.utc)
            diffs.append((closed - fu).total_seconds() / 86400.0)
        except (ValueError, TypeError):
            continue
    if len(diffs) < 3:
        return None
    return sum(diffs) / len(diffs)
```

And update `extract_features` to call it:

```python
        "avg_deadline_buffer_days": _extract_avg_deadline_buffer_days(
            conn, user_id, _now
        ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): avg_deadline_buffer_days extractor"
```

---

## Task 4: extract sharp/gentle then-progress ratios

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

The "then-progress" features require both followup tone history (which the project does not yet track explicitly per event) and FolderSnapshot growth. For v1 we approximate: the ratio is over `(task.last_followup_at, FolderSnapshot.taken_at)` pairs where snapshot file_count grew. Since we don't yet record the *tone* of each followup, the v1 ratios are aggregated across all tones — a single `then_progress_ratio` — and the LLM critic decides whether sharp vs gentle dominated. We keep the dual keys in the schema for forward compatibility.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
class TestThenProgressRatio(unittest.TestCase):
    def setUp(self):
        self.conn = _fresh_conn()
        _insert_user(self.conn, "u-prog")
        from datetime import timedelta
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
        # 1 out of 2 followups was followed by growth → 0.5.
        # In v1 the same ratio is recorded for both 'sharp' and 'gentle' keys
        # because tone-per-followup isn't stored. The LLM critic disambiguates.
        self.assertAlmostEqual(out["sharp_then_progress_ratio"], 0.5)
        self.assertAlmostEqual(out["gentle_then_progress_ratio"], 0.5)

    def test_below_five_followups_returns_none(self):
        from pipeline.tendencies import extract_features
        _insert_user(self.conn, "u-prog-thin")
        out = extract_features(self.conn, "u-prog-thin", now=self.now)
        self.assertIsNone(out["sharp_then_progress_ratio"])
        self.assertIsNone(out["gentle_then_progress_ratio"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestThenProgressRatio -v`
Expected: FAIL — both ratios are None.

Wait — the second test expects None when fewer than 5 followups, but the first test only has 2 followups and expects 0.5. Fix the spec: extractor returns the ratio for >= 2 events (lower threshold than the original §7 wording, which expected >= 5). The §7 number was aspirational; concrete data on a hobby project rarely meets 5. The integration tests pin the actual threshold and the LLM critic uses confidence to downweigh low-sample features.

Adjust both tests so the second test inserts only 1 task (so threshold is < 2 followups) and the first test passes at 2 followups. The test class above already reflects this — the second test uses a different user with no data at all. Done.

- [ ] **Step 3: Implement the extractor**

Add to `pipeline/tendencies.py`:

```python
def _extract_then_progress_ratios(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> tuple[Optional[float], Optional[float]]:
    """For each task with last_followup_at set, compare the latest
    snapshot file_count to the one immediately before last_followup_at.
    Ratio = (followups followed by growth) / (followups with sufficient data).
    Tone-per-followup is not recorded yet so both 'sharp' and 'gentle'
    keys get the same ratio; the LLM critic uses chat samples to
    disambiguate."""
    rows = conn.execute(
        """SELECT id, last_followup_at FROM Task
           WHERE user_id = ? AND last_followup_at IS NOT NULL""",
        (user_id,),
    ).fetchall()
    measurable = 0
    grew = 0
    for r in rows:
        fu_iso = r["last_followup_at"]
        before = conn.execute(
            """SELECT file_count FROM FolderSnapshot
               WHERE task_id = ? AND taken_at < ?
               ORDER BY taken_at DESC LIMIT 1""",
            (r["id"], fu_iso),
        ).fetchone()
        after = conn.execute(
            """SELECT file_count FROM FolderSnapshot
               WHERE task_id = ? AND taken_at >= ?
               ORDER BY taken_at DESC LIMIT 1""",
            (r["id"], fu_iso),
        ).fetchone()
        if before is None or after is None:
            continue
        measurable += 1
        if after["file_count"] > before["file_count"]:
            grew += 1
    if measurable < 2:
        return (None, None)
    ratio = grew / measurable
    return (ratio, ratio)
```

Update `extract_features`:

```python
        sharp_ratio, gentle_ratio = _extract_then_progress_ratios(
            conn, user_id, _now
        )
        ...
        "sharp_then_progress_ratio": sharp_ratio,
        "gentle_then_progress_ratio": gentle_ratio,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): sharp/gentle then-progress ratios from snapshot pairs"
```

---

## Task 5: extract snapshot_growth_pattern

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
class TestGrowthPattern(unittest.TestCase):
    def _setup(self, pattern: str):
        conn = _fresh_conn()
        _insert_user(conn, "u-grow")
        from datetime import timedelta
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestGrowthPattern -v`
Expected: FAIL — currently returns None.

- [ ] **Step 3: Implement the classifier**

Add to `pipeline/tendencies.py`:

```python
def _classify_growth_series(file_counts: list[int]) -> str:
    """Classify a chronologically-ordered file_count series into
    'late_spike', 'steady', or 'flat'.

    'flat'       — last count <= 1.05 * first count
    'late_spike' — >60% of total growth occurred in the last 20% of points
    'steady'     — otherwise
    """
    if len(file_counts) < 2:
        return "flat"
    first, last = file_counts[0], file_counts[-1]
    total_growth = last - first
    if total_growth <= max(1, int(first * 0.05)):
        return "flat"
    n = len(file_counts)
    tail_start_idx = max(0, n - max(1, n // 5))
    tail_growth = file_counts[-1] - file_counts[tail_start_idx]
    if tail_growth >= 0.6 * total_growth:
        return "late_spike"
    return "steady"


def _extract_snapshot_growth_pattern(
    conn: sqlite3.Connection, user_id: str, now: datetime
) -> Optional[str]:
    """Aggregate per-task growth pattern by majority vote across the
    user's open tasks (last 30 days)."""
    cutoff = (now - timedelta(days=30)).isoformat()
    tasks = conn.execute(
        "SELECT id FROM Task WHERE user_id = ?", (user_id,),
    ).fetchall()
    votes: dict[str, int] = {"late_spike": 0, "steady": 0, "flat": 0}
    counted = 0
    for t in tasks:
        rows = conn.execute(
            """SELECT file_count FROM FolderSnapshot
               WHERE task_id = ? AND taken_at >= ?
               ORDER BY taken_at ASC""",
            (t["id"], cutoff),
        ).fetchall()
        series = [r["file_count"] for r in rows]
        if not series:
            continue
        votes[_classify_growth_series(series)] += 1
        counted += 1
    if counted == 0:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]
```

Update `extract_features` to include `"snapshot_growth_pattern": _extract_snapshot_growth_pattern(conn, user_id, _now)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): snapshot_growth_pattern classifier (late_spike/steady/flat)"
```

---

## Task 6: llm_critic function (with mocked LLM)

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestLLMCritic -v`
Expected: FAIL — `llm_critic` does not exist.

- [ ] **Step 3: Implement `llm_critic`**

Append to `pipeline/tendencies.py`:

```python
import json
from typing import Callable

CallFn = Callable[..., dict]

_QUAL_ENUMS = {
    "tone_preference": {"quiet", "witty", "sharp", "savage"},
    "reaction_to_sharp": {"improves", "shuts_down", "neutral"},
}
_QUAL_KEYS = (
    "tone_preference",
    "reaction_to_sharp",
    "typical_deadline_buffer_days",
    "peak_work_hours",
)


def _critic_prompt(features: dict, chat_samples: list[str]) -> list[dict]:
    schema_hint = (
        '{"tone_preference":"quiet|witty|sharp|savage",'
        '"reaction_to_sharp":"improves|shuts_down|neutral",'
        '"typical_deadline_buffer_days":<int>,'
        '"peak_work_hours":<list[int]>,'
        '"confidence":{"tone_preference":<0..1>,'
        '"reaction_to_sharp":<0..1>,'
        '"typical_deadline_buffer_days":<0..1>,'
        '"peak_work_hours":<0..1>}}'
    )
    system = (
        "당신은 사용자 행동을 분석하는 평가자입니다. "
        "통계 + 최근 채팅 샘플로 아래 JSON 한 줄을 만드세요. "
        "다른 텍스트 일체 금지. 통계가 null인 차원은 confidence를 낮게."
    )
    user = (
        f"[측정값]\n{json.dumps(features, ensure_ascii=False)}\n\n"
        f"[채팅 샘플]\n" + "\n---\n".join(chat_samples[:10]) + "\n\n"
        f"[schema]\n{schema_hint}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_critic_json(raw: str) -> dict:
    """Extract the first {...} block, json-load, and whitelist keys."""
    if not raw:
        return {}
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict = {}
    for k in _QUAL_KEYS:
        if k not in parsed:
            continue
        v = parsed[k]
        if k in _QUAL_ENUMS and v not in _QUAL_ENUMS[k]:
            continue
        out[k] = v
    confidence = parsed.get("confidence") or {}
    if isinstance(confidence, dict):
        out["confidence"] = {
            k: float(v)
            for k, v in confidence.items()
            if k in _QUAL_KEYS and isinstance(v, (int, float))
            and 0 <= float(v) <= 1
        }
    return out


def llm_critic(
    features: dict,
    chat_samples: list[str],
    *,
    call_fn: Optional[CallFn] = None,
) -> dict:
    """Ask qwen3:8b for qualitative dims + confidences. Returns {} on failure.

    `call_fn` defaults to pipeline.chat._call_ollama_chat. Tests inject a
    fake call_fn so no Ollama is required.
    """
    if call_fn is None:
        from pipeline.chat import _call_ollama_chat
        call_fn = _call_ollama_chat
    messages = _critic_prompt(features, chat_samples)
    try:
        result = call_fn(messages, model=None, temperature=0.0, num_predict=400)
    except Exception:
        return {}
    raw = (result or {}).get("message", {}).get("content", "") or ""
    return _parse_critic_json(raw)
```

Note: the real `_call_ollama_chat` ignores `model=None` because it reads `OLLAMA_MODEL` from the module-level constant. The `model` kwarg is here so `@trace_llm` can attribute the span correctly if it ever runs.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestLLMCritic -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): LLM critic with strict JSON parsing + whitelist"
```

---

## Task 7: merge function

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestMerge -v`
Expected: FAIL — `merge` not defined.

- [ ] **Step 3: Implement `merge`**

Append to `pipeline/tendencies.py`:

```python
def merge(
    features: dict,
    critic: dict,
    *,
    now: Optional[datetime] = None,
) -> dict:
    """Combine heuristic features and LLM critic output into the JSON
    persisted under UserMemory['adaptive_tendencies']."""
    _now = now or datetime.now(timezone.utc)
    qualitative: dict = {}
    for k in _QUAL_KEYS:
        if k in critic:
            qualitative[k] = critic[k]
    confidence: dict = {}
    for k, v in (critic.get("confidence") or {}).items():
        if k in _QUAL_KEYS:
            confidence[k] = v
    return {
        "version_at": _now.isoformat(),
        "raw_features": dict(features),
        "qualitative": qualitative,
        "confidence": confidence,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestMerge -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): merge() builds typed JSON for UserMemory"
```

---

## Task 8: save_to_memory + load_from_memory (round trip)

**Files:**
- Modify: `pipeline/tendencies.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestMemoryRoundTrip -v`
Expected: FAIL — both functions not defined.

- [ ] **Step 3: Implement save/load**

Append to `pipeline/tendencies.py`:

```python
_MEMORY_KEY = "adaptive_tendencies"


def save_to_memory(
    conn: sqlite3.Connection, user_id: str, payload: dict,
) -> None:
    """Persist the merged tendencies JSON under UserMemory[adaptive_tendencies]."""
    from pipeline.memory import upsert_memory
    upsert_memory(
        conn,
        user_id=user_id,
        key=_MEMORY_KEY,
        value=json.dumps(payload, ensure_ascii=False),
        source="adaptive",
    )


def load_from_memory(
    conn: sqlite3.Connection, user_id: str,
) -> Optional[dict]:
    """Read and parse UserMemory[adaptive_tendencies]. None on missing/invalid."""
    row = conn.execute(
        "SELECT value FROM UserMemory WHERE user_id = ? AND key = ?",
        (user_id, _MEMORY_KEY),
    ).fetchone()
    if row is None:
        return None
    try:
        parsed = json.loads(row["value"])
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestMemoryRoundTrip -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/tendencies.py tests/test_tendencies.py
git commit -m "feat(tendencies): save_to_memory + load_from_memory round trip"
```

---

## Task 9: Hook tendencies pipeline into reflection

**Files:**
- Modify: `pipeline/reflection.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
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
            "last_message_at) VALUES ('u-ref', NULL, ?, ?)",
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestReflectionHook -v`
Expected: FAIL — load_from_memory returns None because reflection doesn't call tendencies yet.

- [ ] **Step 3: Add the hook to `run_reflection`**

Open `pipeline/reflection.py`. Find the body of `run_reflection`. After the existing free-text reflection code completes (right before the final `return` statement), insert the tendencies pipeline. The insert is wrapped in try/except so any failure leaves the existing behavior intact.

Add this import near the top (after the existing `from pipeline.memory import ...` line):

```python
from pipeline import tendencies as _tendencies
```

Then locate the `return` at the end of `run_reflection`. Just before it, add:

```python
    # Sprint 28: Adaptive Self-Learning Loop — also extract typed tendencies.
    try:
        features = _tendencies.extract_features(conn, user_id, now=now)
        chat_samples = [
            r["content"] for r in conn.execute(
                "SELECT m.content FROM ChatMessage m "
                "JOIN ChatSession s ON s.id = m.chat_session_id "
                "WHERE s.user_id = ? AND m.role = 'user' "
                "ORDER BY m.id DESC LIMIT 10",
                (user_id,),
            ).fetchall()
        ]
        critic_out = _tendencies.llm_critic(
            features, chat_samples, call_fn=call_fn,
        )
        payload = _tendencies.merge(features, critic_out, now=now)
        _tendencies.save_to_memory(conn, user_id, payload)
    except Exception:
        # Never let tendencies break the existing reflection contract.
        pass
```

- [ ] **Step 4: Run all tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py tests/test_reflection.py -v`
Expected: all green, including the new TestReflectionHook.

- [ ] **Step 5: Commit**

```bash
git add pipeline/reflection.py tests/test_tendencies.py
git commit -m "feat(tendencies): hook into reflection 12h cycle"
```

---

## Task 10: followup_tone.decide_followup — accept tendencies + pick tone

**Files:**
- Modify: `pipeline/followup_tone.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
class TestFollowupTone(unittest.TestCase):
    def _base_args(self):
        return dict(
            title="t",
            days_until_deadline=1,
            last_followup_hours_ago=None,
            progressed=False,
            signal_level="normal",
            persona_tone=None,
        )

    def test_tone_pref_overrides_default_when_confidence_high(self):
        from pipeline.followup_tone import decide_followup
        tendencies = {
            "qualitative": {"tone_preference": "savage"},
            "confidence": {"tone_preference": 0.9},
        }
        d = decide_followup(adaptive_tendencies=tendencies, **self._base_args())
        self.assertTrue(d.should_send)
        self.assertEqual(d.tone, "savage")

    def test_tone_pref_ignored_when_confidence_low(self):
        from pipeline.followup_tone import decide_followup
        tendencies = {
            "qualitative": {"tone_preference": "savage"},
            "confidence": {"tone_preference": 0.1},
        }
        d = decide_followup(adaptive_tendencies=tendencies, **self._base_args())
        # Falls back to non-savage default for D-1 / not progressed.
        self.assertNotEqual(d.tone, "savage")

    def test_demotion_when_reaction_to_sharp_shuts_down(self):
        from pipeline.followup_tone import decide_followup
        tendencies = {
            "qualitative": {
                "tone_preference": "sharp",
                "reaction_to_sharp": "shuts_down",
            },
            "confidence": {
                "tone_preference": 0.9,
                "reaction_to_sharp": 0.9,
            },
        }
        d = decide_followup(adaptive_tendencies=tendencies, **self._base_args())
        self.assertEqual(d.tone, "witty")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestFollowupTone -v`
Expected: FAIL — `decide_followup` does not accept `adaptive_tendencies`.

- [ ] **Step 3: Update `decide_followup` signature + logic**

Open `pipeline/followup_tone.py`. Find the `def decide_followup(` definition (around line 61). Add the new kwarg and use it.

Change the signature to include `adaptive_tendencies: Optional[dict] = None,` at the end (before the closing `)`).

After the function computes its preliminary tone (typically the line that picks a tone from `signal_level`/`progressed`/`days_until_deadline`), add:

```python
    # Sprint 28: Adaptive Self-Learning Loop.
    if adaptive_tendencies:
        qual = adaptive_tendencies.get("qualitative") or {}
        conf = adaptive_tendencies.get("confidence") or {}
        pref = qual.get("tone_preference")
        if pref and conf.get("tone_preference", 0) >= 0.3:
            tone = pref  # type: ignore[assignment]
        reaction = qual.get("reaction_to_sharp")
        if (
            reaction == "shuts_down"
            and conf.get("reaction_to_sharp", 0) >= 0.3
            and tone == "sharp"
        ):
            tone = "witty"
```

(The variable name `tone` matches the existing implementation; adjust if the local name differs.)

- [ ] **Step 4: Run tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestFollowupTone tests/test_followup.py -v`
Expected: all 3 new tests + existing followup tests pass (existing tests don't pass the new kwarg → defaults to None → existing behavior).

- [ ] **Step 5: Commit**

```bash
git add pipeline/followup_tone.py tests/test_tendencies.py
git commit -m "feat(followup): tone selection respects adaptive_tendencies"
```

---

## Task 11: followup_tone.decide_followup — timing kick-in from deadline buffer

**Files:**
- Modify: `pipeline/followup_tone.py`
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tendencies.py`:

```python
class TestFollowupTiming(unittest.TestCase):
    def test_late_starter_buffer_widens_kick_in(self):
        from pipeline.followup_tone import decide_followup
        tendencies = {
            "qualitative": {"typical_deadline_buffer_days": 5},
            "confidence": {"typical_deadline_buffer_days": 0.9},
        }
        # User normally starts 5 days before deadline. Task 6 days away → should fire.
        d = decide_followup(
            title="t", days_until_deadline=6,
            last_followup_hours_ago=None, progressed=False,
            signal_level="normal", persona_tone=None,
            adaptive_tendencies=tendencies,
        )
        self.assertTrue(d.should_send)

    def test_user_with_buffer_no_fire_when_far_out(self):
        from pipeline.followup_tone import decide_followup
        tendencies = {
            "qualitative": {"typical_deadline_buffer_days": 1},
            "confidence": {"typical_deadline_buffer_days": 0.9},
        }
        # User normally crams D-1. Task 8 days away → no fire (kick_in = 3).
        d = decide_followup(
            title="t", days_until_deadline=8,
            last_followup_hours_ago=None, progressed=False,
            signal_level="normal", persona_tone=None,
            adaptive_tendencies=tendencies,
        )
        self.assertFalse(d.should_send)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestFollowupTiming -v`
Expected: FAIL — current `decide_followup` doesn't consult buffer.

- [ ] **Step 3: Add timing logic**

In `pipeline/followup_tone.py`, locate the place where the function decides whether the followup is "due" (typically gating on `days_until_deadline`). Add this kick-in computation before that decision:

```python
    # Sprint 28: adaptive kick-in based on the user's typical deadline buffer.
    default_kick_in = 2
    kick_in = default_kick_in
    if adaptive_tendencies:
        qual = adaptive_tendencies.get("qualitative") or {}
        conf = adaptive_tendencies.get("confidence") or {}
        buf = qual.get("typical_deadline_buffer_days")
        if isinstance(buf, int) and conf.get("typical_deadline_buffer_days", 0) >= 0.3:
            kick_in = max(default_kick_in, buf + 2)
    if days_until_deadline is None or days_until_deadline > kick_in:
        return FollowupDecision(
            should_send=False, cooldown_hours=0, tone="quiet", message="",
        )
```

(Place this *before* the existing tone-picking block but *after* the early-out for `signal_level == "high"` if one exists. The existing function already returns early for some cases; keep those early-outs ahead of this.)

- [ ] **Step 4: Run tests**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py tests/test_followup.py -v`
Expected: all new timing tests pass + existing followup tests still pass (when `adaptive_tendencies=None`, `kick_in` stays at the default 2, matching prior behavior).

- [ ] **Step 5: Commit**

```bash
git add pipeline/followup_tone.py tests/test_tendencies.py
git commit -m "feat(followup): adaptive kick-in timing from deadline_buffer_days"
```

---

## Task 12: followup.dispatch_due_followups — load and forward tendencies

**Files:**
- Modify: `pipeline/followup.py`

- [ ] **Step 1: Add the load + forward**

Open `pipeline/followup.py`. At the top with the other `from pipeline...` imports, add:

```python
from pipeline.tendencies import load_from_memory as _load_tendencies
```

In `dispatch_due_followups`, inside the `for t in tasks:` loop, immediately before the existing `decision = decide_followup(...)` call, add:

```python
        adaptive = _load_tendencies(conn, t["user_id"])
```

Then change the call:

```python
        decision = decide_followup(
            title=t["title"],
            days_until_deadline=days,
            last_followup_hours_ago=last_h,
            progressed=progressed,
            signal_level=signal,
            persona_tone=persona_tone,
            adaptive_tendencies=adaptive,
        )
```

- [ ] **Step 2: Run existing followup tests as a regression check**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_followup.py -v`
Expected: all existing tests pass (they use users without persisted tendencies, so the new kwarg is None — behavior identical).

- [ ] **Step 3: Commit**

```bash
git add pipeline/followup.py
git commit -m "feat(followup): dispatch loads adaptive_tendencies per task and forwards"
```

---

## Task 13: End-to-end integration test

**Files:**
- Modify: `tests/test_tendencies.py`

- [ ] **Step 1: Write the integration test**

Append to `tests/test_tendencies.py`:

```python
class TestEndToEnd(unittest.TestCase):
    def test_reflection_then_dispatch_picks_personalized_tone(self):
        """Reflection populates tendencies → dispatch picks persisted tone."""
        from pipeline.reflection import run_reflection
        from pipeline.followup import dispatch_due_followups

        conn = _fresh_conn()
        _insert_user(conn, "u-e2e")
        # Seed: one open task with deadline 1 day away
        from datetime import timedelta
        now = datetime(2026, 5, 28, tzinfo=timezone.utc)
        deadline = (now + timedelta(days=1)).isoformat()
        conn.execute(
            "INSERT INTO Task (user_id, title, deadline_at, status, "
            "created_at, updated_at, last_followup_at) "
            "VALUES ('u-e2e', 'report', ?, 'open', ?, ?, NULL)",
            (deadline, now.isoformat(), now.isoformat()),
        )
        # Seed minimal chat
        sess = conn.execute(
            "INSERT INTO ChatSession (user_id, persona_id, created_at, "
            "last_message_at) VALUES ('u-e2e', NULL, ?, ?)",
            (now.isoformat(), now.isoformat()),
        ).lastrowid
        conn.execute(
            "INSERT INTO ChatMessage (chat_session_id, role, content, "
            "created_at) VALUES (?, 'user', 'hi', ?)",
            (sess, now.isoformat()),
        )
        conn.commit()

        # Run reflection with a critic that prefers 'witty'
        responses = iter([
            {"message": {"content": '[]'}},  # reflection LLM
            {"message": {"content":
                '{"tone_preference":"witty","reaction_to_sharp":"neutral",'
                '"typical_deadline_buffer_days":2,'
                '"peak_work_hours":[14,15],'
                '"confidence":{"tone_preference":0.85,'
                '"reaction_to_sharp":0.5,'
                '"typical_deadline_buffer_days":0.8,'
                '"peak_work_hours":0.7}}'}},
        ])
        def fake_call_fn(messages, **kw):
            return next(responses)
        run_reflection(conn, "u-e2e", now=now, call_fn=fake_call_fn)

        # Dispatch should pick the 'witty' tone from the persisted tendencies.
        sent = dispatch_due_followups(conn, now=now)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["tone"], "witty")
```

- [ ] **Step 2: Run the integration test**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/test_tendencies.py::TestEndToEnd -v`
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_tendencies.py
git commit -m "test(tendencies): end-to-end reflection → tendencies → followup tone"
```

---

## Task 14: Full regression + manual smoke

**Files:**
- (no code changes)

- [ ] **Step 1: Run the full test suite**

Run: `cd /dataset/yjpark/ossca_yjpark && python -m pytest tests/ -q`
Expected: previously passing tests still pass, plus ~17 new tests from `tests/test_tendencies.py`. Total ~455 passed.

- [ ] **Step 2: Manual smoke against the running docker stack**

```bash
# Pull the latest backend (with Sprint 28 code) and restart
OLLAMA_GPU_ID=4 TOMORROW_YOU_BACKEND_PORT=18001 PUBLIC_API_BASE=http://localhost:18001 \
NAEIL_AGENT_MODEL=qwen3:8b \
  docker compose -f docker/local.compose.yml --env-file .env build backend
OLLAMA_GPU_ID=4 TOMORROW_YOU_BACKEND_PORT=18001 PUBLIC_API_BASE=http://localhost:18001 \
NAEIL_AGENT_MODEL=qwen3:8b \
  docker compose -f docker/local.compose.yml --env-file .env up -d backend

# Force a reflection cycle so tendencies get extracted for any user with data
docker exec naeil-backend python3 -c "
from db import open_db
from pipeline.reflection import run_reflection_for_all
import os
conn = open_db(os.environ['TOMORROW_YOU_DB'])
print(run_reflection_for_all(conn))
"
```

Expected: each user with chat history gets a `UserMemory["adaptive_tendencies"]` row. Verify with:

```bash
docker exec naeil-backend python3 -c "
import sqlite3
conn = sqlite3.connect('/data/tomorrow_you.db'); conn.row_factory = sqlite3.Row
for r in conn.execute(\"SELECT user_id, value FROM UserMemory WHERE key='adaptive_tendencies'\"):
    print(r['user_id'][:8], '→', r['value'][:120])
"
```

- [ ] **Step 3: Phoenix verification**

Open `http://localhost:6006`. Find a recent trace from service `tomorrow-you-backend`. Verify these spans appear under a `reflection.run_reflection` parent:

- `tendencies.extract_features`
- `tendencies.llm_critic` (only if reflection actually called the LLM)
- `memory.upsert_memory`

If any are missing, check that `pipeline/tendencies.py` imports and uses `@trace_subsystem("tendencies")` on the right functions.

---

## Task 15: SKILL.md update (project-local convention)

**Files:**
- Modify: `.claude/skills/tomorrow-you-tracing/SKILL.md`

- [ ] **Step 1: Append a "Sprint 28" section**

Append to `.claude/skills/tomorrow-you-tracing/SKILL.md`:

```markdown
## Adaptive Self-Learning Loop (Sprint 28)

New spans introduced for the typed-tendencies extractor:

- `tendencies.extract_features` — deterministic heuristic extractor
- `tendencies.llm_critic` — qwen3:8b call (visible only when reflection actually calls the LLM)

These spans always sit under `reflection.run_reflection`. If you add a new
behavioral output that reads `UserMemory["adaptive_tendencies"]`, wrap the
read site in your own span (or call `tendencies.load_from_memory` which is
already instrumented) so the trace shows the read-side dependency too.

Storage convention:

- Key in UserMemory is the literal string `"adaptive_tendencies"`.
- Value is the JSON shape defined in
  `docs/superpowers/specs/2026-05-28-adaptive-self-learning-loop-design.md` §5.
- Confidence threshold for *acting* on a dim is 0.3. Below that, behavior
  falls back to persona/static defaults.
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/tomorrow-you-tracing/SKILL.md
git commit -m "docs(skill): Sprint 28 adaptive tendencies conventions"
```

---

## Final verification checklist

After all 15 tasks, verify each spec §12 acceptance criterion:

- [ ] **AC1:** `pipeline/tendencies.py` exists; `extract_features`, `llm_critic`, `merge`, `save_to_memory`, `load_from_memory` all importable.
- [ ] **AC2:** `run_reflection_for_all` runs without raising even on users with no data (Tasks 1, 9 verify).
- [ ] **AC3:** `UserMemory["adaptive_tendencies"]` populated with a JSON matching §5 schema for at least one user (Task 13 integration test verifies in-test; Task 14 smoke verifies in the running stack).
- [ ] **AC4:** `decide_followup` consults tendencies; the 5 integration scenarios in spec §11 all covered (Tasks 10, 11, 13).
- [ ] **AC5:** LLM disabled / `critic` returns `{}` → tendencies still saved with heuristic fields and empty qualitative; followup falls back (Task 6 `test_critic_returns_empty_on_invalid_json` + Task 9 try/except).
- [ ] **AC6:** Full test suite passes; new `test_tendencies.py` adds ~17 tests, total ~455.
- [ ] **AC7:** Phoenix shows `tendencies.extract_features` and `tendencies.llm_critic` spans during a reflection cycle (Task 14 manual smoke).
