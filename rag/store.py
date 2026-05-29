"""Sprint 30 — sqlite-vec backed vector store for RAG."""
from __future__ import annotations

import sqlite3
import struct
from datetime import datetime, timezone
from typing import Optional, Sequence

EMBED_DIM = 768  # nomic-embed-text
EMBED_MODEL = "nomic-embed-text"


def _pack(vec: Sequence[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _load_extension(conn: sqlite3.Connection) -> None:
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def ensure_vec_table(conn: sqlite3.Connection) -> None:
    """Load sqlite-vec extension + create RagVec virtual table if absent."""
    _load_extension(conn)
    conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS RagVec "
        f"USING vec0(embedding float[{EMBED_DIM}])"
    )
    conn.commit()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    kind: str,
    ref_id: str,
    content: str,
    ts: str,
    embedding: Sequence[float],
    embed_model: str = EMBED_MODEL,
) -> Optional[int]:
    """Insert into RagDoc + RagVec atomically. Returns row id or None if duplicate."""
    if len(embedding) != EMBED_DIM:
        raise ValueError(f"embedding dim {len(embedding)} != {EMBED_DIM}")
    try:
        cur = conn.execute(
            """INSERT INTO RagDoc
               (user_id, kind, ref_id, content, ts, embed_model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, kind, ref_id, content, ts, embed_model, _now_iso()),
        )
    except sqlite3.IntegrityError:
        return None
    rowid = cur.lastrowid
    conn.execute(
        "INSERT INTO RagVec (rowid, embedding) VALUES (?, ?)",
        (rowid, _pack(embedding)),
    )
    conn.commit()
    return rowid


def search(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    query_embedding: Sequence[float],
    kinds: Optional[Sequence[str]] = None,
    k: int = 5,
) -> list[dict]:
    """KNN search via vec0 + join RagDoc + filter by user_id (and optionally kinds)."""
    if len(query_embedding) != EMBED_DIM:
        raise ValueError(f"query dim {len(query_embedding)} != {EMBED_DIM}")
    kind_filter = ""
    params: list = [_pack(query_embedding), k * 4]
    if kinds:
        ph = ",".join("?" for _ in kinds)
        kind_filter = f"AND d.kind IN ({ph})"
        params.extend(kinds)
    params.append(user_id)
    params.append(k)
    sql = f"""
        SELECT d.kind, d.ref_id, d.content, d.ts, v.distance
        FROM RagVec v
        JOIN RagDoc d ON d.id = v.rowid
        WHERE v.embedding MATCH ?
          AND k = ?
          {kind_filter}
          AND d.user_id = ?
        ORDER BY v.distance
        LIMIT ?
    """
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
