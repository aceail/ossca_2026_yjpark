"""FastAPI 의존성 주입 — DB connection."""

from __future__ import annotations

import os
import sqlite3
from typing import Generator

DB_PATH = os.environ.get("TOMORROW_YOU_DB", "tomorrow_you.db")


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """각 request에서 새 sqlite3 connection (thread-safety 보장)."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()
