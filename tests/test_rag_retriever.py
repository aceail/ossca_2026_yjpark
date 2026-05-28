import sqlite3
from db.schema import migrate
from rag.store import ensure_vec_table, add, EMBED_DIM
from rag.retriever import recall_semantic

def _open():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    migrate(c); ensure_vec_table(c)
    return c

def _v(seed):
    return [(seed % 100) / 100.0] * EMBED_DIM

def test_recall_returns_nearest():
    conn = _open()
    add(conn, user_id="u1", kind="chat", ref_id="1",
        content="alpha", ts="2026-05-28T00:00:00+00:00", embedding=_v(1))
    add(conn, user_id="u1", kind="chat", ref_id="2",
        content="beta", ts="2026-05-28T00:00:01+00:00", embedding=_v(50))
    hits = recall_semantic(conn, user_id="u1", query="x",
                           k=1, _embed_fn=lambda t: _v(50))
    assert hits[0]["content"] == "beta"

def test_recall_user_isolation():
    conn = _open()
    add(conn, user_id="u1", kind="chat", ref_id="1",
        content="mine", ts="2026-05-28T00:00:00+00:00", embedding=_v(1))
    add(conn, user_id="u2", kind="chat", ref_id="2",
        content="theirs", ts="2026-05-28T00:00:01+00:00", embedding=_v(1))
    hits = recall_semantic(conn, user_id="u1", query="x", k=5,
                           _embed_fn=lambda t: _v(1))
    assert all(h["content"] != "theirs" for h in hits)
