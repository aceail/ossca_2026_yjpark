"""Sprint 21 — Weekly Self-Reflection.

매 N일마다 LLM이 사용자의 최근 데이터(Task, ChatMessage, FolderSnapshot,
RegretScore)를 종합 review해 UserMemory에 패턴 요약을 자동 추가한다.
Hermes의 'self-improvement loop' 아이디어를 우리 시스템에 박은 것.

사용자가 일일이 가르치지 않아도 점점 자신을 안다 — 그 시점에 진짜 비서.

LLM 호출 실패·미가능 시 graceful skip; 마지막 실행 시각은 UserMemory에
key `_last_reflection_at` 으로 기록해 cooldown 검사.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from agent.tracing import trace_subsystem
from pipeline.memory import top_memories, upsert_memory

LAST_KEY = "_last_reflection_at"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_since_last(conn: sqlite3.Connection, user_id: str, now: datetime) -> Optional[float]:
    row = conn.execute(
        "SELECT value FROM UserMemory WHERE user_id = ? AND key = ?",
        (user_id, LAST_KEY),
    ).fetchone()
    if not row:
        return None
    try:
        last = datetime.fromisoformat(row["value"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return max(0.0, (now - last).total_seconds() / 3600)


def collect_evidence(
    conn: sqlite3.Connection, user_id: str, *, since: datetime,
) -> dict:
    """N일치 사용자 데이터를 dict로 정리해 LLM 입력으로 만든다."""
    since_iso = since.isoformat()
    tasks = conn.execute(
        """SELECT title, status, deadline_at, created_at FROM Task
           WHERE user_id = ? AND created_at >= ?""",
        (user_id, since_iso),
    ).fetchall()
    messages = conn.execute(
        """SELECT m.role, m.content, m.created_at
           FROM ChatMessage m JOIN ChatSession s ON s.id = m.chat_session_id
           WHERE s.user_id = ? AND m.created_at >= ?
           ORDER BY m.id ASC LIMIT 200""",
        (user_id, since_iso),
    ).fetchall()
    snapshots = conn.execute(
        """SELECT t.title, f.taken_at, f.file_count, f.total_bytes
           FROM FolderSnapshot f JOIN Task t ON t.id = f.task_id
           WHERE t.user_id = ? AND f.taken_at >= ?""",
        (user_id, since_iso),
    ).fetchall()
    regrets = conn.execute(
        """SELECT intensity, free_text, recorded_at FROM RegretScore
           WHERE user_id = ? AND recorded_at >= ?""",
        (user_id, since_iso),
    ).fetchall()
    return {
        "task_count": len(tasks),
        "done_count": sum(1 for t in tasks if t["status"] == "done"),
        "abandoned_count": sum(1 for t in tasks if t["status"] == "abandoned"),
        "tasks": [dict(t) for t in tasks],
        "message_count": len(messages),
        "user_message_count": sum(1 for m in messages if m["role"] == "user"),
        "snapshots_total": len(snapshots),
        "regret_count": len(regrets),
        "avg_regret": (
            sum((r["intensity"] or 0) for r in regrets) / len(regrets)
            if regrets else None
        ),
    }


def build_reflection_prompt(evidence: dict, existing_memories: list[dict]) -> str:
    """LLM에 줄 1회용 system + user prompt 텍스트 묶음."""
    existing_lines = (
        "\n".join(f"- {m['key']}: {m['value']}" for m in existing_memories)
        if existing_memories else "(없음)"
    )
    return (
        "당신은 사용자의 지난 7일 데이터를 검토하고 새로운 패턴·선호·반복 신호를 "
        "1~3개의 짧은 메모리로 추출하는 self-reflection 모듈입니다.\n\n"
        "이미 기록된 메모리 (중복 작성 금지):\n"
        f"{existing_lines}\n\n"
        "JSON 한 줄로만 응답하세요:\n"
        '{"memories":[{"key":"...","value":"..."}]}\n'
        "각 memory의 key는 짧은 라벨(예: '마감 패턴', '활동 시간대'), value는 한 문장.\n"
        "추출할 만한 패턴이 없으면 {\"memories\":[]} 반환.\n"
        "코드 블록·다른 텍스트 일체 금지.\n\n"
        "근거 데이터:\n"
        f"{json.dumps(evidence, ensure_ascii=False)}\n"
    )


def parse_reflection_response(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if not text:
        return []
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    memos = parsed.get("memories") or []
    out: list[dict] = []
    for m in memos:
        if not isinstance(m, dict):
            continue
        k = str(m.get("key", "")).strip()
        v = str(m.get("value", "")).strip()
        if k and v:
            out.append({"key": k, "value": v})
    return out


LLMCallFn = Callable[[list[dict]], dict]


@trace_subsystem("reflection")
def run_reflection(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    days: int = 7,
    cooldown_hours: float = 6 * 24,    # 6일
    now: Optional[datetime] = None,
    call_fn: Optional[LLMCallFn] = None,
) -> dict:
    """사용자별 reflection 1회 실행. cooldown 내 호출은 skip.

    call_fn=None이면 pipeline.chat._call_ollama_chat를 사용.
    LLM이 응답하지 못하면 skip (memory 추가 0건). 마지막 시각만 기록.
    """
    now = now or _now()
    last_h = _hours_since_last(conn, user_id, now)
    if last_h is not None and last_h < cooldown_hours:
        return {"ran": False, "reason": "cooldown", "hours_since_last": last_h}

    since = now - timedelta(days=days)
    evidence = collect_evidence(conn, user_id, since=since)
    if evidence["task_count"] == 0 and evidence["message_count"] == 0:
        # 데이터 거의 없음 — reflection 없이 cooldown만 기록
        upsert_memory(conn, user_id=user_id, key=LAST_KEY,
                      value=now.isoformat(), source="reflection")
        return {"ran": False, "reason": "no_data", "evidence": evidence}

    existing = top_memories(conn, user_id, limit=10)
    prompt = build_reflection_prompt(evidence, existing)
    messages = [{"role": "system", "content": prompt}]

    if call_fn is None:
        try:
            from pipeline.chat import _call_ollama_chat as _llm
        except ImportError:
            return {"ran": False, "reason": "no_llm"}
        call_fn = _llm

    try:
        msg = call_fn(messages)
    except Exception as exc:  # noqa: BLE001
        upsert_memory(conn, user_id=user_id, key=LAST_KEY,
                      value=now.isoformat(), source="reflection")
        return {"ran": False, "reason": f"llm_error: {exc}"}

    raw = msg.get("content") if isinstance(msg, dict) else str(msg)
    new_memos = parse_reflection_response(raw or "")
    added = 0
    for m in new_memos:
        upsert_memory(conn, user_id=user_id, key=m["key"], value=m["value"],
                      source="reflection")
        added += 1
    upsert_memory(conn, user_id=user_id, key=LAST_KEY,
                  value=now.isoformat(), source="reflection")
    return {"ran": True, "added": added, "evidence": evidence, "memories": new_memos}


@trace_subsystem("reflection")
def run_reflection_for_all(
    conn: sqlite3.Connection,
    *,
    days: int = 7,
    cooldown_hours: float = 6 * 24,
    now: Optional[datetime] = None,
    call_fn: Optional[LLMCallFn] = None,
) -> list[dict]:
    """모든 사용자에 대해 한 사이클. backend lifespan에서 호출."""
    rows = conn.execute("SELECT id FROM User").fetchall()
    results = []
    for r in rows:
        results.append({
            "user_id": r["id"],
            **run_reflection(conn, r["id"], days=days,
                             cooldown_hours=cooldown_hours,
                             now=now, call_fn=call_fn),
        })
    return results
