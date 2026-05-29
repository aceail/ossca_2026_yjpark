import sqlite3, struct
from db.schema import migrate
from rag.store import ensure_vec_table, add, search, EMBED_DIM

def _open():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn

def test_ensure_vec_table_creates_virtual_table():
    conn = _open(); migrate(conn); ensure_vec_table(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE name='RagVec'"
    ).fetchone()
    assert row is not None

def test_add_and_search_roundtrip():
    conn = _open(); migrate(conn); ensure_vec_table(conn)
    emb_a = [1.0] + [0.0] * (EMBED_DIM - 1)
    emb_b = [0.0, 1.0] + [0.0] * (EMBED_DIM - 2)
    add(conn, user_id="u1", kind="chat", ref_id="1",
        content="hello", ts="2026-05-28T00:00:00+00:00", embedding=emb_a)
    add(conn, user_id="u1", kind="chat", ref_id="2",
        content="world", ts="2026-05-28T00:00:01+00:00", embedding=emb_b)
    hits = search(conn, user_id="u1", query_embedding=emb_a, k=1)
    assert len(hits) == 1
    assert hits[0]["content"] == "hello"

def test_unique_constraint_idempotent():
    conn = _open(); migrate(conn); ensure_vec_table(conn)
    emb = [0.5] * EMBED_DIM
    add(conn, user_id="u1", kind="chat", ref_id="1",
        content="x", ts="2026-05-28T00:00:00+00:00", embedding=emb)
    add(conn, user_id="u1", kind="chat", ref_id="1",
        content="x", ts="2026-05-28T00:00:00+00:00", embedding=emb)
    n = conn.execute("SELECT COUNT(*) FROM RagDoc").fetchone()[0]
    assert n == 1
