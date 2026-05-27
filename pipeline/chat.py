"""Sprint 11: 멀티턴 chat 엔진.

Ollama /api/chat을 사용해 페르소나 system_prompt + 누적 메시지 컨텍스트로
응답을 생성한다. 모든 user/assistant 턴은 ChatMessage에 자동 저장되어
나중에 직접 SQL로 모니터링할 수 있다.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from typing import Optional

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "exaone3.5:7.8b"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persona_system_prompt(conn: sqlite3.Connection, persona_id: Optional[int]) -> str:
    if not persona_id:
        return "당신은 사용자의 미래 자아입니다. 1인칭으로 짧게 대답하세요."
    row = conn.execute(
        "SELECT system_prompt_override, voice_style, name FROM Persona WHERE id = ?",
        (persona_id,),
    ).fetchone()
    if not row:
        return "당신은 사용자의 미래 자아입니다."
    prompt = (row["system_prompt_override"] or "").strip()
    if prompt:
        return prompt
    voice = (row["voice_style"] or "").strip()
    name = row["name"] or "내일의 나"
    return f"당신은 '{name}'입니다. 톤: {voice}. 한국어로 짧고 인간친화적으로 응답."


def _call_ollama_chat(
    messages: list[dict],
    *,
    timeout: int = 60,
    num_predict: int = 300,
    temperature: float = 0.7,
) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_CHAT_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Ollama chat 호출 실패: {exc}") from exc
    parsed = json.loads(body)
    return (parsed.get("message") or {}).get("content", "")


def create_chat_session(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    persona_id: Optional[int],
    title: Optional[str] = None,
) -> int:
    now = _now_iso()
    cur = conn.execute(
        """INSERT INTO ChatSession (user_id, persona_id, title, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, persona_id, title, now, now),
    )
    conn.commit()
    return cur.lastrowid


def _load_history(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT role, content FROM ChatMessage
           WHERE chat_session_id = ? ORDER BY id ASC""",
        (session_id,),
    ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _record_message(
    conn: sqlite3.Connection,
    session_id: int,
    role: str,
    content: str,
) -> int:
    now = _now_iso()
    cur = conn.execute(
        """INSERT INTO ChatMessage (chat_session_id, role, content, created_at)
           VALUES (?, ?, ?, ?)""",
        (session_id, role, content, now),
    )
    conn.execute(
        "UPDATE ChatSession SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()
    return cur.lastrowid


def post_user_message(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    content: str,
    call_fn=_call_ollama_chat,
) -> dict:
    """사용자 메시지 → 저장 → LLM 응답 생성 → 저장. assistant 메시지 dict 반환.

    call_fn은 테스트에서 mock 가능 (signature: (messages) -> str).
    """
    sess = conn.execute(
        "SELECT user_id, persona_id FROM ChatSession WHERE id = ?", (session_id,),
    ).fetchone()
    if not sess:
        raise ValueError(f"ChatSession {session_id} not found")

    # 1. user 메시지 저장
    _record_message(conn, session_id, "user", content)

    # 2. 누적 메시지 + system prompt 구성
    system_prompt = _persona_system_prompt(conn, sess["persona_id"])
    history = _load_history(conn, session_id)
    messages = [{"role": "system", "content": system_prompt}] + history

    # 3. LLM 호출
    try:
        reply = call_fn(messages).strip()
    except Exception as exc:
        reply = f"(응답 생성 중 오류: {exc})"

    if not reply:
        reply = "(빈 응답)"

    # 4. assistant 저장
    msg_id = _record_message(conn, session_id, "assistant", reply)

    return {
        "id": msg_id,
        "role": "assistant",
        "content": reply,
        "session_id": session_id,
    }


def list_messages(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT id, role, content, created_at FROM ChatMessage
           WHERE chat_session_id = ? ORDER BY id ASC""",
        (session_id,),
    ).fetchall()
    return [
        {"id": r["id"], "role": r["role"], "content": r["content"], "created_at": r["created_at"]}
        for r in rows
    ]


def list_sessions(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT cs.id, cs.persona_id, p.name AS persona_name, p.avatar_icon,
                  cs.title, cs.created_at, cs.updated_at,
                  (SELECT COUNT(*) FROM ChatMessage m WHERE m.chat_session_id = cs.id) AS message_count
           FROM ChatSession cs
           LEFT JOIN Persona p ON p.id = cs.persona_id
           WHERE cs.user_id = ?
           ORDER BY cs.updated_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]
