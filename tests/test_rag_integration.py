import sqlite3
from db.schema import migrate
from rag.store import ensure_vec_table, EMBED_DIM
from rag.indexer import tick
from rag.retriever import recall_semantic


def _v(seed):
    return [(seed % 100) / 100.0] * EMBED_DIM


def _setup_with_messages(messages):
    conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row
    migrate(conn); ensure_vec_table(conn)
    sid = conn.execute(
        "INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at) "
        "VALUES ('u1', NULL, 't', '2026-05-28', '2026-05-28')"
    ).lastrowid
    for i, m in enumerate(messages):
        conn.execute(
            "INSERT INTO ChatMessage (session_id, role, content, created_at) "
            "VALUES (?, 'user', ?, ?)",
            (sid, m, f"2026-05-28T00:00:{i:02d}"),
        )
    conn.commit()
    return conn


def test_full_index_then_recall_top1():
    msgs = ["운동 가기 싫어", "오늘 책 읽었다", "점심 뭐 먹지"]
    conn = _setup_with_messages(msgs)
    # 결정적 fake embed: 메시지 i에 seed=i
    seed_of = {m: i for i, m in enumerate(msgs)}
    embed = lambda t: _v(seed_of.get(t, 99))
    n = tick(conn, embed_fn=embed)
    assert n == 3
    # 쿼리 임베딩이 msgs[1]과 동일하면 top-1이 그것이어야 함
    hits = recall_semantic(conn, user_id="u1", query="anything",
                           k=1, _embed_fn=lambda q: _v(1))
    assert hits[0]["content"] == "오늘 책 읽었다"


def test_recall_empty_query_returns_empty():
    conn = _setup_with_messages(["x"])
    hits = recall_semantic(conn, user_id="u1", query="",
                           k=5, _embed_fn=lambda q: _v(0))
    assert hits == []
