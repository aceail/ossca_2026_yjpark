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
