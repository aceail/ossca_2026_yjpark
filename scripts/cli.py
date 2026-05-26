#!/usr/bin/env python3
"""내일의 너 — TUI MVP CLI.

실행: python3 scripts/cli.py [--user-id ID]
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db import open_db, migrate, get_persona  # noqa: E402
from persona import seed_builtin_prompts  # noqa: E402
from pipeline import SessionOrchestrator  # noqa: E402
from ui import render_card  # noqa: E402

DB_PATH = PROJECT_ROOT / "tomorrow_you.db"


def _ensure_user(conn, user_id: str) -> None:
    """User + UserProfile 보장 (없으면 생성)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute("SELECT id FROM User WHERE id = ?", (user_id,)).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO User (id, created_at, last_seen_at) VALUES (?, ?, ?)",
            (user_id, now, now),
        )
    else:
        conn.execute("UPDATE User SET last_seen_at = ? WHERE id = ?", (now, user_id))

    profile = conn.execute(
        "SELECT user_id FROM UserProfile WHERE user_id = ?", (user_id,)
    ).fetchone()
    if not profile:
        persona_row = get_persona(conn, "내일의 나")
        persona_id = persona_row["id"] if persona_row else None
        conn.execute(
            """INSERT INTO UserProfile
               (user_id, slots_json, completion_percent, active_persona_id, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, "{}", 0.0, persona_id, now),
        )
    conn.commit()


def _get_active_persona(conn, user_id: str):
    row = conn.execute(
        """SELECT p.* FROM UserProfile up
           JOIN Persona p ON p.id = up.active_persona_id
           WHERE up.user_id = ?""",
        (user_id,),
    ).fetchone()
    return row


def _prompt(msg: str) -> str:
    try:
        return input(msg)
    except (EOFError, KeyboardInterrupt):
        print("\n종료합니다.")
        sys.exit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="내일의 너 TUI MVP")
    parser.add_argument("--user-id", default=None, help="사용자 ID (없으면 자동 생성)")
    args = parser.parse_args()

    user_id = args.user_id or f"local-{uuid.uuid4().hex[:8]}"

    conn = open_db(DB_PATH)
    migrate(conn)
    seed_builtin_prompts(conn)
    _ensure_user(conn, user_id)

    orchestrator = SessionOrchestrator(conn)

    print(f"\n  내일의 너에 오신 것을 환영합니다. (user: {user_id})\n")

    while True:
        avoidance_input = _prompt("지금 뭘 회피 중이야? (q로 종료) > ").strip()
        if avoidance_input.lower() in ("q", "quit", "종료"):
            print("  안녕히 가세요.\n")
            break
        if not avoidance_input:
            continue

        # 1. 세션 시작
        session_id = orchestrator.start_session(user_id, avoidance_input)

        # 2. 프로브 질문
        probe = orchestrator.maybe_probe(user_id)
        if probe:
            print(f"\n  💬 잠깐, 물어볼 게 있어:")
            print(f"  {probe.text}")
            answer = _prompt("  답변 (또는 [s]kip) > ").strip()
            if answer.lower() in ("s", "skip"):
                orchestrator._probe_engine.skip_today(user_id, probe.question_id)
            elif answer:
                orchestrator.record_probe_answer(
                    user_id, probe.question_id, session_id, answer
                )

        # 3. 시나리오 생성
        print("\n  ⏳ 시나리오 생성 중...\n")
        card = orchestrator.generate_scenario(
            user_id, session_id, avoidance_input
        )

        # 4. TUI 카드 출력
        persona = _get_active_persona(conn, user_id)
        sentences: dict | None = None
        message: str | None = None

        if card.card_type in ("regret", "recovery"):
            sentences = {
                "fact": card.fact or "",
                "feeling": card.feeling or "",
                "micro_action": card.micro_action or "",
            }
        else:
            message = card.safety_message

        rendered = render_card(
            card.card_type,
            persona,
            sentences=sentences,
            message=message,
        )
        print(rendered)
        print()

        # 5. 사용자 선택
        choice = _prompt(
            "  선택: [t]시작(transition) / [c]계속 / [r]리포트 / [d]삭제(Self-Destruct) > "
        ).strip().lower()

        decision_map = {
            "t": "transition",
            "c": "continue",
            "r": "report",
            "d": "delete",
        }
        decision = decision_map.get(choice, choice or "continue")
        orchestrator.record_decision(session_id, decision)

        if decision == "delete":
            conn.execute("DELETE FROM AvoidanceSession WHERE id = ?", (session_id,))
            conn.commit()
            print("  삭제됨.\n")
        else:
            print(f"  ✓ 기록됨 (결정: {decision})\n")

        again = _prompt("  계속할까요? [y/n] > ").strip().lower()
        if again not in ("y", "yes", ""):
            print("  안녕히 가세요.\n")
            break


if __name__ == "__main__":
    main()
