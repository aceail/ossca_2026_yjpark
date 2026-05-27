"""Sprint 11: 멀티턴 chat 엔진. Sprint 12 (Wave 1): action extraction.

Ollama /api/chat을 사용해 페르소나 system_prompt + 누적 메시지 컨텍스트로
응답을 생성한다. 모든 user/assistant 턴은 ChatMessage에 자동 저장되어
나중에 직접 SQL로 모니터링할 수 있다.

Wave 1 — Action 추출:
  LLM이 응답을 다음 형식으로 줄 수 있다:
    {"speak": "...", "actions": [{"type":"create_task", ...}]}
  actions가 있으면 backend가 처리해 Task INSERT 등 side effect 수행 후
  결과를 speak 텍스트에 자동 prefix해 사용자에게 보여준다.
  형식 아니면 평문 그대로 저장 (backward compat).
"""

from __future__ import annotations

import json
import re
import sqlite3
import urllib.request
from datetime import datetime, timezone
from typing import Optional

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "exaone3.5:7.8b"

ACTION_SYSTEM_SUFFIX = """

[중요: 사용자는 UI 폼을 누르지 않습니다. 모든 작업 조작이 채팅 한 입력으로 일어나야 합니다]
사용자 발화에서 작업·마감·폴더·상태 변경을 추출해 다음 JSON 한 줄로 응답:
{"speak":"사용자에게 보일 메시지","actions":[ ... ]}

가능한 action types:

1. create_task — 새 작업 등록 ("5월 31일까지 발표자료 만들어야해"):
   {"type":"create_task","title":"발표자료","deadline":"2026-05-31","folder":"/optional/path"}

2. set_folder — 기존 작업의 폴더 등록 ("발표자료 폴더는 ~/Desktop/work야"):
   {"type":"set_folder","task":"발표자료","folder":"/Users/yj/Desktop/work"}

3. update_status — 완료·중단 ("발표자료 다 했어", "발표자료 그만둘래"):
   {"type":"update_status","task":"발표자료","status":"done"}   ← done | abandoned | open

4. update_deadline — 마감 변경 ("발표자료 마감 6월 15일로 바꿔"):
   {"type":"update_deadline","task":"발표자료","deadline":"2026-06-15"}

5. update_title — 제목 변경:
   {"type":"update_title","task":"발표자료","new_title":"OSSCA 발표"}

규칙:
- task 필드는 기존 작업 제목의 일부 (LLM은 정확한 id를 모르므로 substring 매칭).
- deadline은 YYYY-MM-DD (시간 미상이면 날짜만).
- folder는 사용자가 말한 경로 그대로 (~ tilde 포함 OK).
- actions가 없으면 그냥 평문으로 응답.
- JSON으로 줄 때는 코드 블록 ```·다른 텍스트 일체 금지.
- 한 입력에서 여러 action 추출 가능 (예: 새 작업 + 폴더 동시 등록).
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persona_system_prompt(conn: sqlite3.Connection, persona_id: Optional[int]) -> str:
    if not persona_id:
        base = "당신은 사용자의 미래 자아입니다. 1인칭으로 짧게 대답하세요."
    else:
        row = conn.execute(
            "SELECT system_prompt_override, voice_style, name FROM Persona WHERE id = ?",
            (persona_id,),
        ).fetchone()
        if not row:
            base = "당신은 사용자의 미래 자아입니다."
        else:
            prompt = (row["system_prompt_override"] or "").strip()
            if prompt:
                base = prompt
            else:
                voice = (row["voice_style"] or "").strip()
                name = row["name"] or "내일의 나"
                base = f"당신은 '{name}'입니다. 톤: {voice}. 한국어로 짧고 인간친화적으로 응답."
    # Wave 1: action 추출 안내 suffix
    return base + ACTION_SYSTEM_SUFFIX


# ────────────────────────────────────────────────────────────────────
# Wave 1: action 파싱 + dispatch
# ────────────────────────────────────────────────────────────────────


def _try_parse_action_response(raw: str) -> Optional[dict]:
    """LLM 응답에서 JSON action payload 추출.

    반환: {"speak": str, "actions": [...]} 또는 None (평문 응답).
    ```json ... ``` 코드 블록 wrapping도 처리. 첫 { 와 마지막 } 사이를 시도.
    """
    text = (raw or "").strip()
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "speak" not in parsed:
        return None
    actions = parsed.get("actions") or []
    if not isinstance(actions, list):
        actions = []
    return {"speak": str(parsed["speak"]), "actions": actions}


def _parse_deadline_to_iso(value: Optional[str]) -> Optional[str]:
    """LLM이 준 'YYYY-MM-DD' 또는 ISO 8601을 보존. 형식 오류면 None."""
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    # YYYY-MM-DD만 오면 23:59 KST(=14:59 UTC) 가정 — 마감 통상 의도
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        return f"{v}T23:59:00+09:00"
    return v


VALID_TASK_STATUSES = {"open", "done", "abandoned"}


def _resolve_task_by_hint(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    hint,
) -> Optional[dict]:
    """task_id(정수) 또는 title substring으로 사용자의 task 1개 식별.

    매칭 우선순위: open > done > abandoned, 그 안에서는 가장 최근 created_at.
    """
    if hint is None:
        return None
    # int 또는 숫자 문자열 — id 직접 lookup
    try:
        tid = int(hint)
        row = conn.execute(
            "SELECT * FROM Task WHERE id = ? AND user_id = ?", (tid, user_id),
        ).fetchone()
        if row:
            return dict(row)
    except (TypeError, ValueError):
        pass
    # title substring
    s = str(hint).strip()
    if not s:
        return None
    row = conn.execute(
        """SELECT * FROM Task WHERE user_id = ? AND title LIKE ?
           ORDER BY CASE status WHEN 'open' THEN 0 WHEN 'done' THEN 1 ELSE 2 END,
                    created_at DESC
           LIMIT 1""",
        (user_id, f"%{s}%"),
    ).fetchone()
    return dict(row) if row else None


def _execute_actions(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    actions: list[dict],
) -> list[str]:
    """action 처리 후 사용자에게 보여줄 짧은 결과 라인들 반환.

    지원: create_task / set_folder / update_status / update_deadline / update_title.
    알려지지 않은 type은 silent skip.
    """
    now = _now_iso()
    lines: list[str] = []
    for act in actions:
        if not isinstance(act, dict):
            continue
        t = act.get("type")

        # 알려지지 않은 type은 hint 검색 없이 silent skip
        if t not in ("create_task", "set_folder", "update_status",
                     "update_deadline", "update_title"):
            continue

        if t == "create_task":
            title = str(act.get("title", "")).strip()
            if not title:
                continue
            deadline = _parse_deadline_to_iso(act.get("deadline"))
            folder = act.get("folder")
            conn.execute(
                """INSERT INTO Task (user_id, title, deadline_at, folder_path,
                                     status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'open', ?, ?)""",
                (
                    user_id,
                    title,
                    deadline,
                    folder if isinstance(folder, str) and folder else None,
                    now,
                    now,
                ),
            )
            conn.commit()
            if deadline:
                lines.append(f"✅ '{title}' — 마감 {deadline[:10]} 캘린더에 박았어")
            else:
                lines.append(f"✅ '{title}' — 등록은 했는데 마감일은 안 적었어")
            continue

        # 이하 action들은 기존 task가 필요
        existing = _resolve_task_by_hint(
            conn, user_id=user_id, hint=act.get("task") or act.get("task_id"),
        )
        if not existing:
            hint_s = act.get("task") or act.get("task_id") or "?"
            lines.append(f"⚠ '{hint_s}'에 해당하는 작업을 못 찾았어")
            continue

        if t == "set_folder":
            folder = str(act.get("folder", "")).strip()
            if not folder:
                lines.append(f"⚠ '{existing['title']}' 폴더 경로가 비어있어")
                continue
            conn.execute(
                "UPDATE Task SET folder_path = ?, updated_at = ? WHERE id = ?",
                (folder, now, existing["id"]),
            )
            conn.commit()
            lines.append(f"📁 '{existing['title']}' 폴더 등록: {folder}")
            continue

        if t == "update_status":
            new_status = str(act.get("status", "")).strip().lower()
            if new_status not in VALID_TASK_STATUSES:
                lines.append(f"⚠ '{existing['title']}' status는 open/done/abandoned만 가능")
                continue
            conn.execute(
                "UPDATE Task SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, existing["id"]),
            )
            conn.commit()
            verb = {"done": "완료 처리", "abandoned": "중단 처리", "open": "재개"}[new_status]
            lines.append(f"✓ '{existing['title']}' {verb}")
            continue

        if t == "update_deadline":
            new_deadline = _parse_deadline_to_iso(act.get("deadline"))
            if not new_deadline:
                lines.append(f"⚠ '{existing['title']}' 마감일 형식이 이상해")
                continue
            conn.execute(
                "UPDATE Task SET deadline_at = ?, updated_at = ? WHERE id = ?",
                (new_deadline, now, existing["id"]),
            )
            conn.commit()
            lines.append(f"📅 '{existing['title']}' 마감 {new_deadline[:10]}로 변경")
            continue

        if t == "update_title":
            new_title = str(act.get("new_title", "")).strip()
            if not new_title:
                lines.append(f"⚠ 새 제목이 비어있어")
                continue
            conn.execute(
                "UPDATE Task SET title = ?, updated_at = ? WHERE id = ?",
                (new_title, now, existing["id"]),
            )
            conn.commit()
            lines.append(f"✏ '{existing['title']}' → '{new_title}'")
            continue

    return lines


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
    call_fn=None,
) -> dict:
    """사용자 메시지 → 저장 → LLM 응답 생성 → action 처리 → 저장.

    LLM이 JSON {"speak":..., "actions":[...]} 형식으로 응답하면 actions를
    backend가 실행한 뒤 결과 라인을 speak 위에 prefix해 사용자에게 보여준다.
    평문이면 그대로 저장.

    call_fn=None이면 모듈 globals에서 _call_ollama_chat을 조회 — 테스트가
    `patch("pipeline.chat._call_ollama_chat", ...)` 로 대체할 수 있게 한다.
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

    # 3. LLM 호출 (module-level lookup for patchability)
    fn = call_fn if call_fn is not None else _call_ollama_chat
    try:
        raw_reply = fn(messages).strip()
    except Exception as exc:
        raw_reply = f"(응답 생성 중 오류: {exc})"

    if not raw_reply:
        raw_reply = "(빈 응답)"

    # 4. Wave 1: action 파싱·실행
    parsed = _try_parse_action_response(raw_reply)
    if parsed is None:
        final_reply = raw_reply
    else:
        action_lines = _execute_actions(
            conn,
            user_id=sess["user_id"],
            actions=parsed["actions"],
        )
        # action 결과 라인이 있으면 speak 위에 prefix, 없으면 speak만
        if action_lines:
            final_reply = "\n".join(action_lines) + "\n\n" + parsed["speak"]
        else:
            final_reply = parsed["speak"]

    # 5. assistant 저장
    msg_id = _record_message(conn, session_id, "assistant", final_reply)

    return {
        "id": msg_id,
        "role": "assistant",
        "content": final_reply,
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
