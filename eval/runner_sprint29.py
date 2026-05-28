"""Sprint 29: chat agent eval orchestrator.

각 시나리오에 대해:
  1. 임시 DB 생성 (또는 db_path 사용)
  2. 유저 + 챗 세션 생성
  3. pipeline.chat.post_user_message 호출 (call_fn으로 LLM 모킹 가능)
  4. 해당 유저의 Task 행 읽기 → actual_actions 빌드
  5. eval.metrics_hermes 로 스코어링
  6. 요약 반환
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

CallFn = Callable[..., dict]


def _insert_user(conn, user_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
        (user_id, now, now),
    )
    conn.commit()


def _task_rows_to_actions(rows) -> list[dict]:
    """DB Task 행 목록 → actual_actions 리스트."""
    result = []
    for row in rows:
        entry: dict = {"type": "create_task", "title": row["title"]}
        dl = row["deadline_at"]
        if dl:
            # YYYY-MM-DD 부분만 추출
            entry["deadline"] = str(dl)[:10]
        else:
            entry["deadline"] = None
        fp = row["folder_path"]
        if fp:
            entry["folder_path"] = fp
        result.append(entry)
    return result


def run_chat_eval(
    scenarios: list[dict],
    *,
    db_path: Optional[str] = None,
    call_fn: Optional[CallFn] = None,
    now: Optional[datetime] = None,
) -> dict:
    """시나리오 목록을 실행하고 점수를 반환한다.

    Args:
        scenarios: 각 시나리오는 다음 키를 포함한다:
            - id: 식별자
            - user_input: 채팅 입력 문자열
            - expected_actions: [{"type": "create_task", "title": ..., ...}, ...]
        db_path: 지정 시 해당 파일을 재사용, None이면 임시 DB 생성
        call_fn: LLM 호출 함수 (테스트 시 모킹용). None이면 실제 Ollama 호출
        now: 현재 시각 override (현재 미사용, 확장 대비)

    Returns:
        {
            "per_sample": [
                {"id": ..., "passed": bool, "extraction": {...}, "format": {...}},
                ...
            ],
            "summary": {...}
        }
    """
    from db import open_db, migrate
    from persona import seed_builtin_prompts
    from pipeline.chat import create_chat_session, post_user_message
    from eval.metrics_hermes import score_action_extraction, score_response_format, summarize_metrics

    per_sample: list[dict] = []

    for scenario in scenarios:
        scenario_id = scenario.get("id", "unknown")
        user_input: str = scenario.get("user_input", "")
        expected_actions: list[dict] = scenario.get("expected_actions", [])
        user_id = f"eval-user-{scenario_id}"

        # DB 준비
        if db_path:
            db_file = Path(db_path)
        else:
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            db_file = Path(tmp.name)

        conn = open_db(db_file)
        migrate(conn)
        seed_builtin_prompts(conn)
        _insert_user(conn, user_id)

        # call_fn을 래핑해 raw LLM 응답을 캡처 (format 채점용)
        # format 채점은 pipeline이 후처리하기 전 raw content 기준으로 해야
        # thinking leak 같은 문제를 정확히 잡을 수 있다.
        raw_llm_content: list[str] = []

        def _capturing_call_fn(messages, **kwargs):
            from pipeline.chat import _call_ollama_chat
            base_fn = call_fn if call_fn is not None else _call_ollama_chat
            msg = base_fn(messages, **kwargs)
            if isinstance(msg, dict):
                raw_llm_content.append(msg.get("content") or "")
            elif isinstance(msg, str):
                raw_llm_content.append(msg)
            return msg

        # 챗 세션 생성 후 메시지 전송
        session_id = create_chat_session(conn, user_id=user_id, persona_id=None)
        result = post_user_message(
            conn,
            session_id=session_id,
            content=user_input,
            call_fn=_capturing_call_fn,
        )
        # format 채점은 raw LLM 응답 기준 (처리 전 thinking leak 감지)
        raw_content_for_format = raw_llm_content[0] if raw_llm_content else result.get("content", "")

        # Task 행 읽기
        rows = conn.execute(
            "SELECT title, deadline_at, folder_path FROM Task WHERE user_id = ? ORDER BY id ASC",
            (user_id,),
        ).fetchall()
        actual_actions = _task_rows_to_actions(rows)

        # 스코어링
        extraction_score = score_action_extraction(actual_actions, expected_actions)
        format_score = score_response_format(raw_content_for_format)

        passed = extraction_score.get("passed", False) and format_score.get("passed", False)

        per_sample.append({
            "id": scenario_id,
            "passed": passed,
            "extraction": extraction_score,
            "format": format_score,
        })

    summary = summarize_metrics(per_sample)

    return {
        "per_sample": per_sample,
        "summary": summary,
    }
