import sqlite3
from db.schema import migrate
from rag.store import ensure_vec_table, EMBED_DIM
from rag.indexer import tick

def _open():
    c = sqlite3.connect(":memory:"); c.row_factory = sqlite3.Row
    migrate(c); ensure_vec_table(c)
    return c

def _fake_embed(text):
    # deterministic per-text vec
    h = abs(hash(text)) % 1000 / 1000.0
    return [h] * EMBED_DIM

def test_tick_indexes_chat_messages():
    conn = _open()
    conn.execute("INSERT INTO User (id, created_at) VALUES ('u1', '2026-05-28')")
    conn.commit()
    sid = conn.execute(
        "INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at) "
        "VALUES ('u1', NULL, 't', '2026-05-28', '2026-05-28')"
    ).lastrowid
    for i in range(3):
        conn.execute(
            "INSERT INTO ChatMessage (chat_session_id, role, content, created_at) "
            "VALUES (?, 'user', ?, '2026-05-28')",
            (sid, f"msg {i}"),
        )
    conn.commit()
    n = tick(conn, embed_fn=_fake_embed, batch_size=10)
    assert n == 3
    docs = conn.execute("SELECT COUNT(*) FROM RagDoc WHERE kind='chat'").fetchone()[0]
    assert docs == 3

def test_tick_idempotent():
    conn = _open()
    conn.execute("INSERT INTO User (id, created_at) VALUES ('u1', '2026-05-28')")
    conn.commit()
    sid = conn.execute(
        "INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at) "
        "VALUES ('u1', NULL, 't', '2026-05-28', '2026-05-28')"
    ).lastrowid
    conn.execute(
        "INSERT INTO ChatMessage (chat_session_id, role, content, created_at) "
        "VALUES (?, 'user', 'hello', '2026-05-28')", (sid,))
    conn.commit()
    n1 = tick(conn, embed_fn=_fake_embed)
    n2 = tick(conn, embed_fn=_fake_embed)
    assert n1 == 1 and n2 == 0
