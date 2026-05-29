"""Sprint 30 — public RAG API."""
from __future__ import annotations

import sqlite3
from typing import Callable, Optional, Sequence

from agent.tracing import trace_subsystem
from rag import embedder as _emb
from rag import store as _store


@trace_subsystem("rag")
def recall_semantic(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    query: str,
    kinds: Optional[Sequence[str]] = None,
    k: int = 5,
    _embed_fn: Optional[Callable[[str], list[float]]] = None,
) -> list[dict]:
    """Semantic recall across RAG-indexed sources. Fail-soft: returns [] on error."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        emb_fn = _embed_fn or _emb.embed_text
        qv = emb_fn(q)
    except Exception:
        return []
    try:
        return _store.search(conn, user_id=user_id, query_embedding=qv,
                             kinds=kinds, k=k)
    except Exception:
        return []


def format_for_prompt(hits: list[dict]) -> str:
    if not hits:
        return ""
    lines = []
    for h in hits[:5]:
        snippet = (h.get("content") or "")[:120].replace("\n", " ")
        lines.append(f"- [{h['kind']}] {snippet}")
    return "\n\n[관련 과거 기억 — 의미 검색]\n" + "\n".join(lines)
