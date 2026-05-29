# RAG-Powered Memory — Design Spec (Sprint 30)

**Date:** 2026-05-28
**Status:** Approved — proceed to plan
**Sub-project:** ③ of the 5-sub-project roadmap

## Goal

`pipeline/memory.recall()`의 `LIKE '%query%'` 단순 substring 검색을 **의미 기반 검색**으로 격상시킨다. ChatMessage / UserMemory / Task / FolderSnapshot 네 출처를 모두 임베딩해 단일 벡터 인덱스에 통합하고, chat 런타임에서 (a) 매 턴 자동 컨텍스트 주입과 (b) LLM이 능동 호출하는 `recall_semantic` 도구 두 경로로 노출한다.

## Non-Goals

- 기존 `UserMemory` symbolic k-v 스토어 폐기 — 그대로 유지. 두 layer는 종류가 달라 공존한다.
- 멀티 사용자 스케일 (>10k 동시 활성) — 단일 사용자 가정.
- 외부 벡터 DB (Pinecone/Qdrant/Weaviate) — SQLite-only 철학 유지.
- 임베딩 fine-tuning — 사전학습된 `nomic-embed-text` 그대로 사용.

## Architecture

### 모듈 구조

신규 디렉터리 `rag/`로 격리. `pipeline/memory.py` (symbolic)는 손대지 않음.

```
rag/
├── __init__.py
├── embedder.py     Ollama nomic-embed-text 클라이언트
├── store.py        sqlite-vec setup + add / search / delete
├── indexer.py      주기 backfill loop (4-source LEFT JOIN)
└── retriever.py    고수준 API: recall_semantic(conn, user_id, query, kinds, k)
```

외부에서는 `from rag.retriever import recall_semantic` 한 줄만 import. `embedder/store/indexer`는 내부 구현.

### 의존성 추가

- `sqlite-vec` (PyPI 패키지). `requirements.txt`에 `sqlite-vec>=0.1.6` 추가.
- Ollama 모델 `nomic-embed-text` (768d, ~274MB). 컨테이너 first-boot에 `ollama pull nomic-embed-text` 실행 — `docker/local.compose.yml` ollama 서비스에 healthcheck 이후 init hook으로.

### 스키마

마이그레이션 `db/migrations/017_rag_memory.sql`:

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

`vec0` 가상 테이블은 SQL 파일에 못 들어감 (sqlite-vec extension이 로드돼야 `CREATE VIRTUAL TABLE USING vec0` 가능). `rag.store.ensure_vec_table(conn)`이 런타임에 생성:

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS RagVec
USING vec0(embedding float[768]);
```

`RagDoc.id`와 `RagVec.rowid`가 1:1 매핑 — `store.add()`가 두 테이블에 동시 INSERT 시 같은 rowid 사용.

### 검색 흐름

```
recall_semantic(conn, user_id, query, kinds=("chat","memory"), k=5)
  ↓
embedder.embed_text(query) → list[float] (768d)
  ↓
store.search(emb, kinds=kinds, k=k) → KNN via vec0
  ↓
JOIN RagDoc ON rowid=id, filter user_id=?, return list[Hit]
```

`Hit = {kind, ref_id, content, ts, score}` — score는 cosine distance (작을수록 가까움).

### 인덱싱 — 주기 backfill loop

`backend/main.py` lifespan에 네 번째 task 추가 (기존 folder_watch/followup/reflection과 동일 패턴):

```python
async def _rag_index_loop(interval_seconds: int) -> None:
    while True:
        try:
            conn = open_db()
            n = rag.indexer.tick(conn)
            if n: log.info(f"rag indexed {n} docs")
        except Exception as e:
            log.exception("rag index loop")
        finally:
            conn.close()
        await asyncio.sleep(interval_seconds)
```

`indexer.tick(conn)`이 4개 source 테이블 각각에 대해:

```sql
SELECT s.* FROM ChatMessage s
LEFT JOIN RagDoc d
  ON d.kind='chat' AND d.ref_id=CAST(s.id AS TEXT)
WHERE d.id IS NULL LIMIT 50;
```

unindexed row 50개씩 batch embedding → INSERT. UNIQUE(kind, ref_id, embed_model)로 idempotent.

**왜 sync hook이 아닌가:** ChatMessage INSERT마다 동기 임베딩하면 chat 응답 latency에 ~80ms 누적되고, Ollama 일시 장애 시 chat 자체가 막힌다. eventually-consistent 60초 lag이 훨씬 안전하다.

### 런타임 통합

`pipeline/chat.py` 단일 파일 수정 (worker-4):

1. `post_user_message`에서 system prompt 조립 직후, 사용자 최근 입력으로 RAG hits 조회 후 prefix:

```python
hits = recall_semantic(conn, user_id=user_id, query=last_user_text,
                       kinds=("chat","memory"), k=3)
if hits:
    system_prompt += "\n\n[관련 과거 기억 — 의미 검색]\n"
    for h in hits:
        system_prompt += f"- [{h['kind']}] {h['content'][:120]}\n"
```

2. `pipeline/tools.py:tool_schemas_for_ollama()`에 새 tool 추가:

```python
{
  "type": "function",
  "function": {
    "name": "recall_semantic",
    "description": "의미 검색으로 과거 대화/기억/작업에서 관련 항목 찾기",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string"},
        "k": {"type": "integer", "default": 5}
      },
      "required": ["query"]
    }
  }
}
```

3. `pipeline/tools.py:dispatch()` (L394 근방) tool 디스패치에 새 case 추가 — `name == "recall_semantic"` → `rag.retriever.recall_semantic(...)` 호출.

### 통합 컴포넌트 매트릭스

| 컴포넌트 | 신규 | 수정 | 비고 |
|---|---|---|---|
| `rag/embedder.py` | ✅ | | Ollama `/api/embeddings` 호출 |
| `rag/store.py` | ✅ | | sqlite-vec init + add/search |
| `rag/indexer.py` | ✅ | | 4-source backfill |
| `rag/retriever.py` | ✅ | | recall_semantic 공개 API |
| `db/migrations/017_rag_memory.sql` | ✅ | | RagDoc 테이블 |
| `backend/main.py` | | append-only | `_rag_index_loop` 추가 |
| `pipeline/chat.py` | | patch | system prompt prefix + tool 등록 |
| `pipeline/tools.py` | | patch | `tool_schemas_for_ollama` schema 추가 + `dispatch` case 추가 |
| `requirements.txt` | | append | sqlite-vec |
| `tests/test_rag_*.py` | ✅ | | 모듈별 unit + 통합 |
| `eval/scenarios/sprint30.json` | ✅ | | 5 RAG recall 시나리오 |

## Error Handling

- **Ollama embedding 실패**: indexer는 batch 단위로 retry, 실패한 row는 다음 tick에 자연 재시도 (LEFT JOIN이 여전히 unindexed로 잡음). retriever는 fail-soft — 임베딩 실패 시 빈 list 반환, chat 흐름은 그대로 진행 (symbolic memory만으로 동작).
- **sqlite-vec extension 로드 실패**: backend startup에서 fail-fast. DEPLOY.md에 "sqlite-vec 설치 확인" 체크 추가.
- **임베딩 차원 불일치**: `RagVec(embedding float[768])`이 컴파일타임 고정. 모델 변경 시 마이그레이션 + 재인덱싱 (별도 sprint).

## Testing Strategy

- **Unit** — 각 모듈 mock 기반 테스트 (embedder는 fake call_fn, store는 in-memory db).
- **Integration** — 실제 sqlite-vec 로드된 in-memory db에 5개 ChatMessage 삽입, `indexer.tick` 한 번, `recall_semantic` 호출, 의미상 가까운 top-1 검증.
- **Eval** — `eval/scenarios/sprint30.json` 5케이스. Sprint 29 harness 그대로 재사용.
  - 시나리오 예: "운동 안 하고 있는데 동기부여 좀" → 과거 비슷한 맥락의 ChatMessage가 top-3에 잡혀야 PASS.

## Observability

- `@trace_subsystem("rag")` 데코레이터를 embedder/store/indexer/retriever 진입점에 부착. Phoenix에서 RAG 호출 latency·hit-rate 가시화.
- indexer tick마다 `log.info(f"rag indexed {n} docs")` — 인덱싱 정체 감지.

## Migration / Rollout

1. PR 머지 후 컨테이너 재빌드 (`docker compose -f docker/local.compose.yml build backend`).
2. `ollama pull nomic-embed-text` (호스트에서 1회).
3. backend 재시작 — lifespan에서 마이그레이션 자동 적용, indexer loop 시작.
4. 초기 60초 안에 기존 ChatMessage backfill 완료. UI/UX 변화 없음 (system prompt에만 영향).

## Open Questions (해결됨)

- ~~검색 범위~~ → Chat + Memory + Task + Snapshot (4-source 모두)
- ~~벡터 저장소~~ → sqlite-vec
- ~~통합 정책~~ → Auto-inject + Tool 둘 다
- ~~인덱싱 트리거~~ → 주기 backfill loop (60s 주기)

## Future Work (Sprint 31+)

- ⑤ Smart Briefing 2.0 — `collect_briefing_data()` 직후 RAG로 "지난주 비슷한 패턴" 회상 후 prompt에 prefix
- 임베딩 모델 업그레이드 경로 (multilingual-e5-large 등)
- 사용자가 "그거 잊어" 요청 시 RagDoc + RagVec 동시 삭제 (`forget_semantic`)
