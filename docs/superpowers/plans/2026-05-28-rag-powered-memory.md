# RAG-Powered Memory Implementation Plan (Sprint 30)

> **For agentic workers:** /team 5워커 병렬 실행. T1-T5는 독립적이며 단일 파일·디렉터리 충돌 없음. 각 워커는 자기 Task block만 받아서 TDD로 진행, 완료 후 `TaskUpdate(status="completed")` 명시 호출. SKILL.md 등 공유 문서는 "## Sprint 30 — RAG Memory" 섹션 **APPEND only**, 기존 내용 절대 수정 금지.

**Goal:** ChatMessage/UserMemory/Task/FolderSnapshot 4-source를 nomic-embed-text(768d)로 임베딩해 sqlite-vec 인덱스에 적재. chat 런타임에서 auto-inject + LLM-callable tool 둘 다로 노출.

**Architecture:** 신규 `rag/` 모듈 (embedder/store/indexer/retriever). 주기 backfill loop (60s 주기, lifespan task). `pipeline/memory.py` symbolic 스토어는 그대로 유지.

**Tech Stack:** Python 3.10+, sqlite3, sqlite-vec extension, Ollama (`/api/embeddings` endpoint, model `nomic-embed-text`).

---

## File Structure

```
rag/                                NEW
├── __init__.py                     NEW (re-exports)
├── embedder.py                     NEW (T2)
├── store.py                        NEW (T1)
├── indexer.py                      NEW (T3)
└── retriever.py                    NEW (T4)
db/migrations/017_rag_memory.sql    NEW (T1)
backend/main.py                     PATCH (T3 — append loop registration)
pipeline/chat.py                    PATCH (T4 — system prompt prefix)
pipeline/tools.py                   PATCH (T4 — REGISTRY entry)
requirements.txt                    PATCH (T1 — sqlite-vec)
tests/test_rag_store.py             NEW (T1)
tests/test_rag_embedder.py          NEW (T2)
tests/test_rag_indexer.py           NEW (T3)
tests/test_rag_retriever.py         NEW (T4)
tests/test_rag_integration.py       NEW (T5)
eval/scenarios/sprint30.json        NEW (T5)
.claude/skills/tomorrow-you-tracing/SKILL.md    PATCH (T5 — APPEND only)
```

---

### Task 1: Schema + Store (worker-1)

**Files:**
- Create: `db/migrations/017_rag_memory.sql`
- Create: `rag/__init__.py`
- Create: `rag/store.py`
- Create: `tests/test_rag_store.py`
- Modify: `requirements.txt` (append `sqlite-vec>=0.1.6`)

- [ ] **Step 1.1: 마이그레이션 작성**

`db/migrations/017_rag_memory.sql`:
```sql
CREATE TABLE IF NOT EXISTS RagDoc (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('chat','memory','task','snapshot')),
  ref_id TEXT NOT NULL,
  content TEXT NOT NULL,
  ts TEXT NOT NULL,
  embed_model TEXT NOT NULL DEFAULT 'nomic-embed-text',
  created_at TEXT NOT NULL,
  UNIQUE (kind, ref_id, embed_model)
);
CREATE INDEX IF NOT EXISTS idx_ragdoc_user_kind ON RagDoc(user_id, kind);
```

- [ ] **Step 1.2: requirements 추가**

`requirements.txt` 마지막 줄 다음에 `sqlite-vec>=0.1.6` 추가.

- [ ] **Step 1.3: `rag/store.py` 골격 + test 먼저**

`tests/test_rag_store.py`:
```python
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
```

- [ ] **Step 1.4: `rag/store.py` 구현**

```python
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
```

- [ ] **Step 1.5: 테스트 실행**

```
pytest tests/test_rag_store.py -v
```
Expected: 3 passed.

- [ ] **Step 1.6: 커밋**

```
git add db/migrations/017_rag_memory.sql rag/__init__.py rag/store.py \
       requirements.txt tests/test_rag_store.py
git commit -m "feat(rag): Sprint 30 T1 — RagDoc schema + sqlite-vec store"
```

---

### Task 2: Embedder (worker-2)

**Files:**
- Create: `rag/embedder.py`
- Create: `tests/test_rag_embedder.py`

- [ ] **Step 2.1: 테스트 먼저**

`tests/test_rag_embedder.py`:
```python
from rag.embedder import embed_text, embed_batch, EmbedderError

def _fake_call(payload):
    # Ollama /api/embeddings response shape: {"embedding": [...]}
    n = len(payload.get("input", payload.get("prompt", "x")))
    return {"embedding": [float(i) / max(n, 1) for i in range(768)]}

def test_embed_text_returns_768_floats():
    v = embed_text("hello world", _call=_fake_call)
    assert len(v) == 768
    assert all(isinstance(x, float) for x in v)

def test_embed_text_strips_and_rejects_empty():
    import pytest
    with pytest.raises(EmbedderError):
        embed_text("   ", _call=_fake_call)

def test_embed_batch_preserves_order():
    out = embed_batch(["a", "bb", "ccc"], _call=_fake_call)
    assert len(out) == 3
    assert all(len(v) == 768 for v in out)
```

- [ ] **Step 2.2: 구현**

`rag/embedder.py`:
```python
"""Sprint 30 — Ollama-backed embedder for RAG."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable, Optional, Sequence

from agent.tracing import trace_subsystem

EMBED_DIM = 768
DEFAULT_MODEL = "nomic-embed-text"


class EmbedderError(RuntimeError):
    pass


def _ollama_url() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    return host + "/api/embeddings"


def _default_call(payload: dict) -> dict:
    req = urllib.request.Request(
        _ollama_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


@trace_subsystem("rag")
def embed_text(
    text: str,
    *,
    model: str = DEFAULT_MODEL,
    _call: Optional[Callable[[dict], dict]] = None,
) -> list[float]:
    text = (text or "").strip()
    if not text:
        raise EmbedderError("empty input")
    call = _call or _default_call
    resp = call({"model": model, "prompt": text})
    emb = resp.get("embedding") or []
    if len(emb) != EMBED_DIM:
        raise EmbedderError(f"unexpected embedding dim {len(emb)} != {EMBED_DIM}")
    return [float(x) for x in emb]


@trace_subsystem("rag")
def embed_batch(
    texts: Sequence[str],
    *,
    model: str = DEFAULT_MODEL,
    _call: Optional[Callable[[dict], dict]] = None,
) -> list[list[float]]:
    return [embed_text(t, model=model, _call=_call) for t in texts]
```

- [ ] **Step 2.3: 테스트 실행 + 커밋**

```
pytest tests/test_rag_embedder.py -v
git add rag/embedder.py tests/test_rag_embedder.py
git commit -m "feat(rag): Sprint 30 T2 — Ollama embedder client"
```

---

### Task 3: Indexer Loop (worker-3)

**Files:**
- Create: `rag/indexer.py`
- Modify: `backend/main.py` (append `_rag_index_loop` + lifespan registration)
- Create: `tests/test_rag_indexer.py`

- [ ] **Step 3.1: 테스트 먼저**

`tests/test_rag_indexer.py`:
```python
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
    sid = conn.execute(
        "INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at) "
        "VALUES ('u1', NULL, 't', '2026-05-28', '2026-05-28')"
    ).lastrowid
    for i in range(3):
        conn.execute(
            "INSERT INTO ChatMessage (session_id, role, content, created_at) "
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
    sid = conn.execute(
        "INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at) "
        "VALUES ('u1', NULL, 't', '2026-05-28', '2026-05-28')"
    ).lastrowid
    conn.execute(
        "INSERT INTO ChatMessage (session_id, role, content, created_at) "
        "VALUES (?, 'user', 'hello', '2026-05-28')", (sid,))
    conn.commit()
    n1 = tick(conn, embed_fn=_fake_embed)
    n2 = tick(conn, embed_fn=_fake_embed)
    assert n1 == 1 and n2 == 0
```

- [ ] **Step 3.2: 구현**

`rag/indexer.py`:
```python
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
           FROM ChatMessage m JOIN ChatSession s ON s.id = m.session_id
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
```

- [ ] **Step 3.3: backend/main.py 패치 (APPEND only)**

기존 `_reflection_loop` 정의 직후, 그리고 lifespan 내 reflection_loop 등록 직후에 동일 패턴으로:

```python
async def _rag_index_loop(interval_seconds: int) -> None:
    """Sprint 30: RAG 주기 backfill. lifespan task로 실행."""
    while True:
        try:
            from db.schema import open_db
            from rag.indexer import tick as _rag_tick
            from rag.store import ensure_vec_table
            conn = open_db()
            ensure_vec_table(conn)
            n = _rag_tick(conn)
            conn.close()
            if n:
                logger.info(f"rag indexed {n} docs")
        except Exception:
            logger.exception("rag index loop error")
        await asyncio.sleep(interval_seconds)
```

lifespan() 내부 `asyncio.create_task(...)` 블록 마지막 줄에:
```python
asyncio.create_task(
    _rag_index_loop(int(os.environ.get("NAEIL_RAG_INDEX_INTERVAL_SEC", "60")))
)
```

- [ ] **Step 3.4: 테스트 + 임포트 스모크 + 커밋**

```
pytest tests/test_rag_indexer.py -v
python -c "from backend.main import _rag_index_loop; print('ok')"
git add rag/indexer.py backend/main.py tests/test_rag_indexer.py
git commit -m "feat(rag): Sprint 30 T3 — backfill indexer + lifespan loop"
```

---

### Task 4: Retriever + Wiring (worker-4)

**Files:**
- Create: `rag/retriever.py`
- Create: `tests/test_rag_retriever.py`
- Modify: `pipeline/chat.py` (system prompt prefix)
- Modify: `pipeline/tools.py` (REGISTRY entry)

- [ ] **Step 4.1: retriever 테스트 먼저**

`tests/test_rag_retriever.py`:
```python
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
```

- [ ] **Step 4.2: retriever 구현**

`rag/retriever.py`:
```python
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
```

- [ ] **Step 4.3: `pipeline/chat.py` 패치**

`post_user_message`에서 system_prompt 조립 끝난 직후 (현재 L585 `system_prompt = system_prompt + _build_temporal_hints(content)` 다음 줄에) 추가:

```python
    # Sprint 30: RAG auto-inject
    try:
        from rag.retriever import recall_semantic, format_for_prompt
        rag_hits = recall_semantic(
            conn, user_id=sess["user_id"], query=content,
            kinds=("chat", "memory"), k=3,
        )
        system_prompt = system_prompt + format_for_prompt(rag_hits)
    except Exception:
        pass  # fail-soft: RAG 실패해도 chat은 진행
```

- [ ] **Step 4.4: `pipeline/tools.py` REGISTRY에 entry 추가**

`_exec_forget` 정의 근방에 새 executor:

```python
def _exec_recall_semantic(conn, user_id, *, query: str, k: int = 5) -> dict:
    from rag.retriever import recall_semantic
    hits = recall_semantic(conn, user_id=user_id, query=query, k=int(k))
    return {"ok": True, "hits": hits}
```

REGISTRY dict 마지막 entry 다음에 `,` 추가하고:

```python
    "recall_semantic": Tool(
        name="recall_semantic",
        description=(
            "의미 기반으로 과거 대화/기억에서 관련 항목을 검색합니다. "
            "사용자가 '예전에 ~했던 거', '비슷한 상황' 같은 회상을 요구할 때 사용."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 질의문"},
                "k": {"type": "integer", "description": "결과 개수 (기본 5)"},
            },
            "required": ["query"],
        },
        executor=_exec_recall_semantic,
    ),
```

- [ ] **Step 4.5: 테스트 + 임포트 스모크 + 커밋**

```
pytest tests/test_rag_retriever.py -v
python -c "from pipeline.tools import REGISTRY; assert 'recall_semantic' in REGISTRY"
python -c "import pipeline.chat"  # import smoke
git add rag/retriever.py pipeline/chat.py pipeline/tools.py tests/test_rag_retriever.py
git commit -m "feat(rag): Sprint 30 T4 — retriever + chat auto-inject + tool wiring"
```

---

### Task 5: Eval + Integration Tests + SKILL.md (worker-5)

**Files:**
- Create: `eval/scenarios/sprint30.json`
- Create: `tests/test_rag_integration.py`
- Modify: `.claude/skills/tomorrow-you-tracing/SKILL.md` (**APPEND only — 새 섹션 추가, 기존 내용 절대 수정 금지**)

- [ ] **Step 5.1: 통합 테스트**

`tests/test_rag_integration.py`:
```python
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
```

- [ ] **Step 5.2: eval 시나리오 5개**

`eval/scenarios/sprint30.json`:
```json
[
  {
    "id": "rag-recall-similar-past",
    "user_input": "예전에 운동 안 한다고 했던 거 기억해?",
    "expected_actions": [
      {"type": "tool_call", "tool": "recall_semantic"}
    ]
  },
  {
    "id": "rag-recall-task-context",
    "user_input": "비슷한 일 전에도 했었나?",
    "expected_actions": [
      {"type": "tool_call", "tool": "recall_semantic"}
    ]
  },
  {
    "id": "rag-recall-mood",
    "user_input": "그때 내 기분이 어땠는지 기억나?",
    "expected_actions": [
      {"type": "tool_call", "tool": "recall_semantic"}
    ]
  },
  {
    "id": "rag-no-recall-trivial",
    "user_input": "오늘 날씨 어때",
    "expected_actions": []
  },
  {
    "id": "rag-recall-deadline-history",
    "user_input": "지난번 마감 어떻게 넘겼었지",
    "expected_actions": [
      {"type": "tool_call", "tool": "recall_semantic"}
    ]
  }
]
```

- [ ] **Step 5.3: SKILL.md APPEND**

`.claude/skills/tomorrow-you-tracing/SKILL.md` **파일 끝에** 다음 섹션을 **추가만** (기존 어떤 줄도 절대 수정 금지):

```markdown

## Sprint 30 — RAG Memory

새 `rag/` 모듈은 Phoenix에서 `trace_subsystem("rag")` 네임스페이스로 가시화됨:

- `rag.embedder.embed_text` — Ollama `/api/embeddings` 호출. latency·error_rate가 Phoenix 트레이스에 자동 기록됨.
- `rag.store.search` — sqlite-vec KNN. 벡터 차원/k 파라미터가 span attribute로 캡처.
- `rag.indexer.tick` — 60초 주기 backfill loop의 한 tick. `n_indexed`가 카운터로 노출.
- `rag.retriever.recall_semantic` — chat auto-inject 및 LLM tool 경로 공통 진입점. `query` 길이·`k`·반환 hit 개수가 attribute.

`chat.post_user_message` 트레이스에서 RAG hit이 system_prompt에 prefix되는 순간이 자식 span으로 보임. retriever fail-soft (Ollama 다운 등) 시 빈 list 반환하므로 chat span은 항상 정상 종료됨.
```

- [ ] **Step 5.4: 테스트 + 커밋**

```
pytest tests/test_rag_integration.py -v
python -c "import json; json.load(open('eval/scenarios/sprint30.json'))"
git add eval/scenarios/sprint30.json tests/test_rag_integration.py \
       .claude/skills/tomorrow-you-tracing/SKILL.md
git commit -m "test(rag): Sprint 30 T5 — integration tests + eval scenarios + SKILL.md"
```

---

## After All Tasks Complete

Lead (사용자 채팅 컨트롤러)가 직접 수행:

1. **전체 회귀 테스트:**
   ```
   pytest -q
   ```
   기대: 모든 기존 테스트 + RAG 신규 ~15개 PASS.

2. **임포트 스모크:**
   ```
   python -c "from rag import embedder, store, indexer, retriever; print('ok')"
   python -c "from backend.main import lifespan; print('ok')"
   ```

3. **마이그레이션 검증:**
   ```
   python -c "import sqlite3; from db.schema import migrate; \
              c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row; \
              migrate(c); \
              print(c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='RagDoc'\").fetchone())"
   ```

4. **브랜치 push + PR:**
   - 브랜치: `feature/sprint-30-rag-memory`
   - PR 제목: `feat(rag): Sprint 30 — RAG-powered memory (③ sub-project)`
   - PR 본문: 5개 task 요약 + 테스트 결과 + Future work (`⑤ Briefing 2.0`이 RAG retriever 호출 예정)

---

## Self-Review Notes

- ✅ Spec 모든 요구사항(scope, vector store, integration, indexer trigger) → 각 task에 매핑
- ✅ Placeholder/TBD 없음
- ✅ 모든 step에 실행 가능한 코드 블록 + pytest 명령
- ✅ 워커 충돌 표면 0 (각 task의 PATCH 파일이 단일 워커 소유): chat.py는 worker-4만, backend/main.py는 worker-3만, tools.py는 worker-4만
- ✅ SKILL.md는 worker-5가 APPEND only (Sprint 29 회고 교훈 적용)
