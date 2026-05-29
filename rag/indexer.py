"""Sprint 30 — periodic backfill indexer for RAG."""
from __future__ import annotations

import sqlite3
from typing import Callable, Optional

from agent.tracing import trace_subsystem
from rag import embedder as _emb
from rag import store as _store

EmbedFn = Callable[[str], list[float]]


def _default_embed(text: str) -> list[float]:
    return _emb.embed_text(text)


SOURCES = [
    # (kind, sql_select, content_lambda, ts_field, user_id_field)
    (
        "chat",
        """SELECT m.id, m.content, m.created_at, s.user_id
           FROM ChatMessage m JOIN ChatSession s ON s.id = m.chat_session_id
           LEFT JOIN RagDoc d ON d.kind='chat' AND d.ref_id = CAST(m.id AS TEXT)
           WHERE d.id IS NULL AND m.content IS NOT NULL AND m.content != ''
           LIMIT ?""",
    ),
    (
        "memory",
        """SELECT id, (key || ': ' || value) AS content, updated_at AS created_at, user_id
           FROM UserMemory
           WHERE id NOT IN (
             SELECT CAST(ref_id AS INTEGER) FROM RagDoc WHERE kind='memory'
           )
           LIMIT ?""",
    ),
    (
        "task",
        """SELECT id, (title || ' [' || status || ']' ||
                       COALESCE(' deadline=' || deadline_at, '')) AS content,
                  created_at, user_id
           FROM Task
           WHERE id NOT IN (
             SELECT CAST(ref_id AS INTEGER) FROM RagDoc WHERE kind='task'
           )
           LIMIT ?""",
    ),
    (
        "snapshot",
        """SELECT s.id, ('files=' || s.file_count || ' bytes=' || s.total_bytes) AS content,
                  s.taken_at AS created_at, t.user_id
           FROM FolderSnapshot s JOIN Task t ON t.id = s.task_id
           LEFT JOIN RagDoc d ON d.kind='snapshot' AND d.ref_id = CAST(s.id AS TEXT)
           WHERE d.id IS NULL
           LIMIT ?""",
    ),
]


@trace_subsystem("rag")
def tick(
    conn: sqlite3.Connection,
    *,
    embed_fn: Optional[EmbedFn] = None,
    batch_size: int = 50,
) -> int:
    """Index up to batch_size unindexed rows per source. Returns total inserted."""
    fn = embed_fn or _default_embed
    total = 0
    for kind, sql in SOURCES:
        rows = conn.execute(sql, (batch_size,)).fetchall()
        for r in rows:
            content = (r["content"] or "").strip()
            if not content:
                continue
            try:
                emb = fn(content[:2000])  # truncate to embedder limit
            except Exception:
                continue  # next tick will retry
            rid = _store.add(
                conn, user_id=r["user_id"], kind=kind, ref_id=str(r["id"]),
                content=content, ts=r["created_at"], embedding=emb,
            )
            if rid is not None:
                total += 1
    return total
