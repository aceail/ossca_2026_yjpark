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
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from agent.tracing import trace_subsystem, trace_llm


@contextmanager
def _react_round_span(round_index: int):
    """Sparse span around one ReAct iteration. Imported lazily so this
    file stays usable without tracing installed."""
    try:
        from opentelemetry import trace as _trace
        tracer = _trace.get_tracer(__name__)
        with tracer.start_as_current_span("react.round") as span:
            try:
                span.set_attribute("react.round_index", round_index)
            except Exception:
                pass
            yield span
    except Exception:
        yield None

import os as _os_chat
# Sprint 23: docker compose sets OLLAMA_HOST=http://ollama:11434 so the backend
# container can reach the Ollama service container. Bare-metal dev keeps the
# 127.0.0.1 fallback.
OLLAMA_CHAT_URL = (
    _os_chat.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    + "/api/chat"
)
# Sprint 18: Hermes-style agent model. EXAONE은 tools API 미검증.
# qwen3:8b가 OSS·tools API 잘 지원하고 7GB로 가벼움. 환경변수로 swap.
OLLAMA_MODEL = _os_chat.environ.get("NAEIL_AGENT_MODEL", "qwen3:8b")
OLLAMA_FALLBACK_MODEL = _os_chat.environ.get("NAEIL_AGENT_FALLBACK", "exaone3.5:7.8b")
AGENT_MAX_TOOL_ROUNDS = int(_os_chat.environ.get("NAEIL_AGENT_MAX_TOOL_ROUNDS", "4"))
AGENT_TOOLS_ENABLED = _os_chat.environ.get("NAEIL_AGENT_TOOLS", "1") == "1"

def _today_kst_str() -> str:
    """LLM이 연도·월을 추측하지 않도록 매 호출 system prompt에 오늘 날짜를 박는다.
    LLM 학습 cutoff(예: 2023)에 박혀 "내일"·"이번주" 같은 표현을 잘못 해석하는
    것을 막는다. KST 기준.
    """
    from datetime import timedelta
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    return now_kst.strftime("%Y-%m-%d")


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


_KO_WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]


def _current_kst_stamp() -> str:
    """YYYY-MM-DD HH:MM KST (요일) — chat 메시지에 prefix로 박음."""
    from datetime import timedelta
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    wd = _KO_WEEKDAY[now_kst.weekday()]
    return now_kst.strftime(f"%Y-%m-%d %H:%M KST ({wd}요일)")


def _build_temporal_hints(user_message: str) -> str:
    """Sprint 25: 사용자 발화의 상대 시간 표현 → 절대 날짜 강제 매핑.

    qwen3 같은 모델은 시스템 prompt의 '오늘 날짜' 줄을 무시하고 cutoff
    기준으로 '오늘'을 해석하는 경향이 있다. 사용자 메시지에 상대 단어가
    있으면 그것만 명시 매핑해 다시 박는다.
    """
    if not user_message:
        return ""
    from datetime import date as _date, timedelta
    today_kst = (datetime.now(timezone.utc) + timedelta(hours=9)).date()

    def _line(label: str, d: _date) -> str:
        return f"- {label} = {d.isoformat()} ({_KO_WEEKDAY[d.weekday()]}요일)"

    lines: list[str] = []
    if "오늘" in user_message:
        lines.append(_line("오늘", today_kst))
    if "내일" in user_message:
        lines.append(_line("내일", today_kst + timedelta(days=1)))
    if "모레" in user_message:
        lines.append(_line("모레", today_kst + timedelta(days=2)))
    if "이번주" in user_message:
        end = today_kst + timedelta(days=(6 - today_kst.weekday()))
        lines.append(_line("이번주 끝(일)", end))
    if "다음주" in user_message:
        next_mon = today_kst + timedelta(days=(7 - today_kst.weekday()))
        next_sun = next_mon + timedelta(days=6)
        lines.append(_line("다음주 시작(월)", next_mon))
        lines.append(_line("다음주 끝(일)", next_sun))
    for i, kw in enumerate(_KO_WEEKDAY):
        if f"{kw}요일" in user_message:
            days_ahead = (i - today_kst.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            lines.append(_line(f"다음 {kw}요일", today_kst + timedelta(days=days_ahead)))
            break
    if not lines:
        return ""
    return (
        "\n\n[시간 해석 강제 매핑 — 절대 무시 금지]\n"
        + "\n".join(lines)
        + "\n위 매핑을 그대로 사용. 학습 데이터의 옛 날짜 절대 사용 금지.\n"
    )


def _persona_system_prompt_with_memory(
    conn: sqlite3.Connection,
    persona_id: Optional[int],
    user_id: Optional[str],
) -> str:
    """Sprint 20: 페르소나 prompt + 사용자 top memory + 날짜·action suffix."""
    base = _persona_system_prompt(conn, persona_id)
    if user_id:
        from pipeline.memory import format_for_prompt, top_memories
        memos = top_memories(conn, user_id, limit=5)
        base = base + format_for_prompt(memos)
    return base


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
    # Sprint 16: 날짜 cutoff 보정 — 매 호출 prefix에 오늘 날짜를 박는다
    date_prefix = (
        f"\n\n[시스템 정보]\n오늘 날짜: {_today_kst_str()} (KST). "
        "사용자가 '6월 19일'처럼 말하면 오늘 날짜 기준 다음 6월 19일 (이미 지났으면 "
        "내년)로 해석하세요. 절대 학습 데이터의 옛 연도(2023 등)를 쓰지 마세요.\n"
    )
    # Wave 1: action 추출 안내 suffix
    return base + date_prefix + ACTION_SYSTEM_SUFFIX


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


def _roll_forward_if_past(iso_date: str) -> str:
    """LLM이 학습 cutoff 연도(2023 등)로 잘못 답한 경우 — 이미 지났으면 미래로
    굴려준다. 같은 월·일을 유지하고 연도만 조정.
    """
    from datetime import timedelta
    today_kst = (datetime.now(timezone.utc) + timedelta(hours=9)).date()
    try:
        y, m, d = (int(x) for x in iso_date.split("-"))
    except (ValueError, TypeError):
        return iso_date
    from datetime import date as _date
    try:
        candidate = _date(y, m, d)
    except ValueError:
        return iso_date
    # 1년 이상 과거면 → 같은 월·일의 미래 연도로 (오늘 이후 가장 가까운)
    if candidate < today_kst - timedelta(days=30):
        future_year = today_kst.year
        try:
            shifted = _date(future_year, m, d)
        except ValueError:
            return iso_date
        if shifted < today_kst:
            try:
                shifted = _date(future_year + 1, m, d)
            except ValueError:
                return iso_date
        return shifted.isoformat()
    return iso_date


def _parse_deadline_to_iso(value: Optional[str]) -> Optional[str]:
    """LLM이 준 'YYYY-MM-DD' 또는 ISO 8601을 보존. 형식 오류면 None.
    Sprint 16: 학습 cutoff로 과거 연도 박힌 경우 자동 roll-forward.
    """
    if not value:
        return None
    v = str(value).strip()
    if not v:
        return None
    # YYYY-MM-DD만 오면 roll-forward 검증 + 23:59 KST(=14:59 UTC) 가정
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        v = _roll_forward_if_past(v)
        return f"{v}T23:59:00+09:00"
    # 풀 ISO도 날짜 부분만 빼서 roll-forward 검증
    date_part = v.split("T")[0]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part):
        new_date = _roll_forward_if_past(date_part)
        if new_date != date_part:
            return v.replace(date_part, new_date, 1)
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


@trace_llm
def _call_ollama_chat(
    messages: list[dict],
    *,
    timeout: int = 60,
    num_predict: int = 300,
    temperature: float = 0.7,
    tools: Optional[list[dict]] = None,
) -> dict:
    """Ollama /api/chat 호출 — tools 인자 지원 (Sprint 18 Hermes-style).

    반환은 raw message dict: {"role":"assistant","content":"...","tool_calls":[...]}.
    이전 시그니처(.strip() 호출)와의 호환을 위해 caller가 str으로 받으면 안 되므로
    backend 호출 패턴을 dispatch 위주로 갱신.
    """
    payload: dict = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        # qwen3 etc. emit chain-of-thought as `content` unless think=false. That
        # breaks the JSON action format the system prompt asks for. Force off.
        "think": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }
    if tools and AGENT_TOOLS_ENABLED:
        payload["tools"] = tools
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
    return parsed.get("message") or {"role": "assistant", "content": ""}


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
    # Sprint 24: session title 자동 생성 — 첫 user 메시지의 첫 ~24자를 title로
    if role == "user":
        row = conn.execute(
            "SELECT title FROM ChatSession WHERE id = ?", (session_id,),
        ).fetchone()
        if row and not (row["title"] or "").strip():
            snippet = content.strip().replace("\n", " ")
            if len(snippet) > 24:
                snippet = snippet[:24] + "…"
            conn.execute(
                "UPDATE ChatSession SET title = ?, updated_at = ? WHERE id = ?",
                (snippet, now, session_id),
            )
        else:
            conn.execute(
                "UPDATE ChatSession SET updated_at = ? WHERE id = ?",
                (now, session_id),
            )
    else:
        conn.execute(
            "UPDATE ChatSession SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
    conn.commit()
    return cur.lastrowid


@trace_subsystem("chat")
def post_user_message(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    content: str,
    call_fn=None,
) -> dict:
    """Sprint 18: ReAct-style agent loop.

    각 round:
      1) Ollama /api/chat 호출 (tools 첨부)
      2) message.tool_calls 있으면 각 tool 실행 → role=tool 메시지 누적 → 다음 round
      3) 없으면 종료. content가 비어 있고 tool_calls 라인만 있으면 요약 후처리

    AGENT_MAX_TOOL_ROUNDS 횟수 초과 시 강제 종료. tools 미지원·실패 시 plain
    content로 fallback. backward compat: 이전의 JSON-action 패턴도 LLM이 그렇게
    응답하면 동일하게 처리.
    """
    from pipeline.tools import dispatch as _tool_dispatch
    from pipeline.tools import tool_schemas_for_ollama

    sess = conn.execute(
        "SELECT user_id, persona_id FROM ChatSession WHERE id = ?", (session_id,),
    ).fetchone()
    if not sess:
        raise ValueError(f"ChatSession {session_id} not found")

    # 1. user 메시지 저장
    _record_message(conn, session_id, "user", content)

    # 2. 누적 메시지 + system prompt (+ Sprint 20: top memory + Sprint 25: 시간 hint)
    system_prompt = _persona_system_prompt_with_memory(
        conn, sess["persona_id"], sess["user_id"],
    )
    system_prompt = system_prompt + _build_temporal_hints(content)
    history = _load_history(conn, session_id)

    # Sprint 25 보강: 마지막 user 메시지에 현재 시각을 직접 prefix. system prompt를
    # 무시하는 모델도 user 메시지의 명시 시각은 따른다 (qwen3:8b 검증).
    if history and history[-1].get("role") == "user":
        original = history[-1]["content"]
        history = history[:-1] + [{
            "role": "user",
            "content": f"[현재: {_current_kst_stamp()}]\n{original}",
        }]

    messages: list[dict] = [{"role": "system", "content": system_prompt}] + history

    fn = call_fn if call_fn is not None else _call_ollama_chat
    tools = tool_schemas_for_ollama() if AGENT_TOOLS_ENABLED else None

    final_content = ""
    action_lines: list[str] = []
    tool_calls_total = 0
    last_msg: dict = {}

    for _round in range(AGENT_MAX_TOOL_ROUNDS):
        with _react_round_span(_round):
            try:
                msg = fn(messages, tools=tools) if tools else fn(messages)
            except TypeError:
                # 옛 시그니처 (tools 인자 미지원) — fallback
                msg = fn(messages)
            except Exception as exc:
                final_content = f"(응답 생성 중 오류: {exc})"
                break

            # 이전 모듈 시그니처(str)와 새 시그니처(dict) 모두 호환
            if isinstance(msg, str):
                final_content = msg
                break

            last_msg = msg if isinstance(msg, dict) else {}
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                final_content = (msg.get("content") or "").strip()
                break

            # tool 실행 + 결과를 다음 round 메시지로
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                tool_calls_total += 1
                fn_block = call.get("function") or {}
                name = fn_block.get("name", "")
                args = fn_block.get("arguments")
                result = _tool_dispatch(
                    conn, user_id=sess["user_id"], name=name, arguments=args,
                )
                # 사용자에게 보일 간략 라인
                if result.get("ok"):
                    if name == "create_task":
                        action_lines.append(f"✅ '{result.get('title')}' 등록 — 마감 {result.get('deadline') or '미정'}")
                    elif name == "update_task":
                        action_lines.append(f"✓ '{result.get('title')}' 갱신")
                    elif name == "delete_task":
                        action_lines.append(f"⊗ '{result.get('title')}' 삭제")
                else:
                    action_lines.append(f"⚠ {name}: {result.get('error', '실패')}")
                messages.append({
                    "role": "tool",
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

    # Sprint 24: qwen3 같은 모델은 reasoning을 thinking 필드에 분리해
    # content를 빈 채로 응답. action_lines가 있으면 그것만으로 충분; 둘 다
    # 비면 thinking을 한두 문장 요약해 보여주고, 그것도 없으면 친절 안내.
    if not final_content and last_msg:
        thinking = (last_msg.get("thinking") or "").strip()
        if thinking:
            # 첫 한두 문장만 사용 — 너무 길게 보이지 않게
            short = thinking.split(". ")[:2]
            final_content = ". ".join(s.strip() for s in short if s.strip()).strip()
            if final_content and not final_content.endswith("."):
                final_content += "."

    if not final_content and not action_lines:
        final_content = (
            "방금 메시지에 응답을 못 만들었어요. 좀 더 짧게 또는 구체적으로 다시 말씀해주실래요?"
        )

    # backward compat: JSON-action 패턴도 처리
    parsed = _try_parse_action_response(final_content)
    if parsed is not None:
        legacy_lines = _execute_actions(
            conn, user_id=sess["user_id"], actions=parsed["actions"],
        )
        action_lines = legacy_lines + action_lines
        final_content = parsed["speak"]

    # 최종 메시지 조립
    if action_lines:
        final_reply = "\n".join(action_lines)
        if final_content:
            final_reply += "\n\n" + final_content
    else:
        final_reply = final_content or "(빈 응답)"

    msg_id = _record_message(conn, session_id, "assistant", final_reply)

    return {
        "id": msg_id,
        "role": "assistant",
        "content": final_reply,
        "session_id": session_id,
        "tool_calls": tool_calls_total,
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
        """SELECT cs.id, cs.persona_id, p.name AS persona_name,
                  p.avatar_icon, p.avatar_color,
                  cs.title, cs.created_at, cs.updated_at,
                  (SELECT COUNT(*) FROM ChatMessage m WHERE m.chat_session_id = cs.id) AS message_count,
                  (SELECT m.content FROM ChatMessage m
                     WHERE m.chat_session_id = cs.id ORDER BY m.id DESC LIMIT 1) AS last_message
           FROM ChatSession cs
           LEFT JOIN Persona p ON p.id = cs.persona_id
           WHERE cs.user_id = ?
           ORDER BY cs.updated_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]
