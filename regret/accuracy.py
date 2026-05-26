"""시나리오 카드 정확도 + 다음 사용 의향 평가 루프 — G007.

CCG R2 권고:
- 카드 정확도(이 카드가 내 상황에 맞았는가) — 1-5 self-rating
- 다음 사용 의향(이 문장을 받은 뒤, 다음 비슷한 상황이 오면 이 앱을 다시 열 것 같나요?) — 1-5
- EvaluationResult에 저장 (sample_id="session_<session_id>")
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_card_accuracy(
    conn: sqlite3.Connection,
    *,
    scenario_card_id: int,
    accuracy_score: int,
    model_run_id: int | None = None,
) -> int:
    """카드 정확도 self-rating (1-5) 저장."""
    if not 1 <= accuracy_score <= 5:
        raise ValueError("accuracy must be 1-5")
    row = conn.execute(
        "SELECT avoidance_session_id, model_run_id FROM ScenarioCard WHERE id = ?",
        (scenario_card_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"ScenarioCard {scenario_card_id} not found")
    sample_id = f"session_{row['avoidance_session_id']}"
    mrid = model_run_id or row["model_run_id"]
    if mrid is None:
        cur = conn.execute(
            "INSERT INTO ModelRun (model_name, ran_at) VALUES (?, ?)",
            ("manual_self_eval", _now()),
        )
        mrid = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO EvaluationResult
           (sample_id, model_run_id, scenario_card_id, pass, issues_json, metrics_json, evaluated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            sample_id,
            mrid,
            scenario_card_id,
            1 if accuracy_score >= 4 else 0,
            json.dumps([], ensure_ascii=False),
            json.dumps({"accuracy_self_rating": accuracy_score}, ensure_ascii=False),
            _now(),
        ),
    )
    conn.commit()
    return cur.lastrowid


def record_return_intent(
    conn: sqlite3.Connection,
    *,
    scenario_card_id: int,
    intent_score: int,
) -> int:
    """다음 사용 의향 1-5 — '다음에도 앱을 열 수 있을 것 같나요?'"""
    if not 1 <= intent_score <= 5:
        raise ValueError("intent must be 1-5")
    row = conn.execute(
        "SELECT avoidance_session_id, model_run_id FROM ScenarioCard WHERE id = ?",
        (scenario_card_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"ScenarioCard {scenario_card_id} not found")
    sample_id = f"session_{row['avoidance_session_id']}_intent"
    mrid = row["model_run_id"]
    if mrid is None:
        cur = conn.execute(
            "INSERT INTO ModelRun (model_name, ran_at) VALUES (?, ?)",
            ("manual_intent_eval", _now()),
        )
        mrid = cur.lastrowid
    cur = conn.execute(
        """INSERT INTO EvaluationResult
           (sample_id, model_run_id, scenario_card_id, pass, issues_json, metrics_json, evaluated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            sample_id,
            mrid,
            scenario_card_id,
            1 if intent_score >= 4 else 0,
            json.dumps([], ensure_ascii=False),
            json.dumps({"return_intent_self_rating": intent_score}, ensure_ascii=False),
            _now(),
        ),
    )
    conn.commit()
    return cur.lastrowid
