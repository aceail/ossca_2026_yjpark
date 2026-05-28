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

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from agent.tracing import trace_subsystem


_FEATURE_KEYS = (
    "chat_count_7d",
    "avg_deadline_buffer_days",
    "peak_hour_histogram",
    "sharp_then_progress_ratio",
    "gentle_then_progress_ratio",
    "snapshot_growth_pattern",
)


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


def _classify_growth_series(file_counts: list[int]) -> str:
    """Classify a chronologically-ordered file_count series into
    'late_spike', 'steady', or 'flat'.

    'flat'       — last count <= 1.05 * first count
    'late_spike' — >60% of total growth occurred in the last 20% of points
    'steady'     — otherwise
    """
    import math

    if len(file_counts) < 2:
        return "flat"
    first, last = file_counts[0], file_counts[-1]
    total_growth = last - first
    if total_growth <= max(1, int(first * 0.05)):
        return "flat"
    n = len(file_counts)
    tail_len = max(1, math.ceil(n * 0.2))
    tail_start_idx = n - tail_len
    # Growth in the tail = last value - value before tail starts
    before_tail_val = file_counts[tail_start_idx - 1] if tail_start_idx > 0 else first
    tail_growth = file_counts[-1] - before_tail_val
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
    sharp_ratio, gentle_ratio = _extract_then_progress_ratios(
        conn, user_id, _now
    )
    return {
        "chat_count_7d": _extract_chat_count_7d(conn, user_id, _now),
        "avg_deadline_buffer_days": _extract_avg_deadline_buffer_days(
            conn, user_id, _now
        ),
        "peak_hour_histogram": _extract_peak_hour_histogram(conn, user_id, _now),
        "sharp_then_progress_ratio": sharp_ratio,
        "gentle_then_progress_ratio": gentle_ratio,
        "snapshot_growth_pattern": _extract_snapshot_growth_pattern(
            conn, user_id, _now
        ),
    }
