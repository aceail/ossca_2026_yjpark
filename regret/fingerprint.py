"""FingerprintSnapshot 주기적 업데이트 — G007.

간단한 TF 기반 fingerprint (LLM 호출 없이). 사용자의 누적 회피 입력 + ProbeAnswer
+ RegretScore 패턴을 통계로 요약. 실제 임베딩은 v2 단계에서 sentence-transformers
등 추가 가능.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class FingerprintBuilder:
    user_id: str

    def collect_corpus(self, conn: sqlite3.Connection) -> list[str]:
        rows = conn.execute(
            "SELECT avoidance_input FROM AvoidanceSession WHERE user_id = ?",
            (self.user_id,),
        ).fetchall()
        corpus = [r["avoidance_input"] for r in rows]
        prows = conn.execute(
            "SELECT answer_text FROM ProbeAnswer WHERE user_id = ? AND answer_text != '__skip__'",
            (self.user_id,),
        ).fetchall()
        corpus.extend(r["answer_text"] for r in prows)
        return corpus

    def top_tokens(self, corpus: list[str], k: int = 20) -> list[tuple[str, int]]:
        text = " ".join(corpus).lower()
        tokens = re.findall(r"[가-힣]{2,}|[a-zA-Z]{3,}", text)
        return Counter(tokens).most_common(k)

    def stats(self, conn: sqlite3.Connection) -> dict:
        sess_row = conn.execute(
            "SELECT COUNT(*) AS n FROM AvoidanceSession WHERE user_id = ?", (self.user_id,)
        ).fetchone()
        regret_row = conn.execute(
            "SELECT AVG(intensity) AS avg_i, COUNT(*) AS n FROM RegretScore WHERE user_id = ?",
            (self.user_id,),
        ).fetchone()
        decision_row = conn.execute(
            """SELECT user_decision AS d, COUNT(*) AS n FROM AvoidanceSession
               WHERE user_id = ? AND user_decision IS NOT NULL GROUP BY user_decision""",
            (self.user_id,),
        ).fetchall()
        decisions = {r["d"]: r["n"] for r in decision_row}
        return {
            "session_count": sess_row["n"] if sess_row else 0,
            "regret_count": regret_row["n"] if regret_row else 0,
            "regret_avg_intensity": float(regret_row["avg_i"]) if regret_row and regret_row["avg_i"] is not None else None,
            "decision_distribution": decisions,
        }


def _embedding_placeholder(corpus: list[str]) -> list[float]:
    """LLM 없는 간단 fixed-dim hashing — v2에서 sentence-transformers로 교체 예정."""
    if not corpus:
        return [0.0] * 16
    digest = hashlib.sha256(" ".join(corpus).encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:16]]


def update_fingerprint_snapshot(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    embedding_model: str = "tomorrow-you-tf-hash-v1",
    embedding_model_version: str = "0.1",
) -> int:
    builder = FingerprintBuilder(user_id=user_id)
    corpus = builder.collect_corpus(conn)
    embedding = _embedding_placeholder(corpus)
    stats = builder.stats(conn)
    stats["top_tokens"] = builder.top_tokens(corpus)
    cur = conn.execute(
        """INSERT INTO FingerprintSnapshot
           (user_id, embedding_json, stats_json, embedding_model, embedding_model_version, snapshot_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            user_id,
            json.dumps(embedding),
            json.dumps(stats, ensure_ascii=False),
            embedding_model,
            embedding_model_version,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    return cur.lastrowid
