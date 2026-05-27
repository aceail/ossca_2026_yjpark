"""SQLite migration + connection helpers — G003 DataModel v1.

Migrations:
    db/migrations/NNN_name.sql files applied in lexical order.
    SchemaMigration table records applied versions + checksums.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH_DEFAULT = Path(__file__).resolve().parent.parent / "tomorrow_you.db"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def open_db(path: Path | str = DB_PATH_DEFAULT) -> sqlite3.Connection:
    """Open SQLite connection with foreign_keys + WAL."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS SchemaMigration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL,
            checksum TEXT
        );
        """
    )
    conn.commit()


def _applied_versions(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT version FROM SchemaMigration").fetchall()
    return {r["version"] for r in rows}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def migrate(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations in order. Returns list of applied version IDs."""
    _ensure_migration_table(conn)
    applied = _applied_versions(conn)
    sql_files = sorted(migrations_dir.glob("*.sql"))
    newly_applied: list[str] = []
    for path in sql_files:
        version = path.stem
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO SchemaMigration (version, applied_at, checksum) VALUES (?, ?, ?)",
                (version, datetime.now(timezone.utc).isoformat(), _sha256(sql)),
            )
            conn.commit()
            newly_applied.append(version)
        except sqlite3.Error as exc:
            conn.rollback()
            raise RuntimeError(f"Migration {version} failed: {exc}") from exc
    return newly_applied


def list_personas(conn: sqlite3.Connection, *, builtin_only: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM Persona"
    if builtin_only:
        sql += " WHERE is_builtin = 1"
    sql += " ORDER BY is_builtin DESC, name"
    return conn.execute(sql).fetchall()


def get_persona(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM Persona WHERE name = ?", (name,)).fetchone()


def upsert_prompt_version(
    conn: sqlite3.Connection,
    *,
    name: str,
    system_prompt: str,
    notes: str | None = None,
) -> int:
    """P0-12: 같은 (name, system_prompt 해시) 조합엔 같은 PromptVersion.id 반환.

    version = SHA256(system_prompt)[:12] — 같은 내용이면 같은 version이라
    재호출이 자연 idempotent. 시나리오 생성 직전 호출해 ToolInvocation에
    prompt_version_id로 기록하면 평가·재현 시 정확한 system_prompt를 복원할 수 있다.
    """
    version = _sha256(system_prompt)[:12]
    row = conn.execute(
        "SELECT id FROM PromptVersion WHERE name = ? AND version = ?",
        (name, version),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO PromptVersion (name, version, system_prompt, notes, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (name, version, system_prompt, notes, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    return cur.lastrowid
