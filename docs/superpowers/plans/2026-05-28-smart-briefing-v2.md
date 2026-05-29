# Smart Briefing 2.0 Implementation Plan (Sprint 31)

> Autopilot 단일-PR 실행. lead가 단일 파일(`pipeline/briefing.py`) 확장 + 신규 테스트 파일 생성 일괄 수행. subagent 디스패치 대신 lead가 직접 진행 — task 결속도가 너무 높아 분할하면 직렬 의존성으로 오버헤드만 늘어남.

**Goal:** `pipeline/briefing.py`에 momentum + tendencies + RAG recall을 통합해 daily briefing을 personalize.

**Architecture:** 단일 파일 확장 (184 → ~380줄). 신규 헬퍼 3개 + 기존 함수 3개 확장.

**Branch:** `feature/sprint-31-briefing-v2` (← `feature/sprint-30-rag-code` 위)

---

## File Structure

```
pipeline/briefing.py         EXTEND (single owner, no other file conflicts)
tests/test_briefing_v2.py    NEW
docs/superpowers/specs/...   already written
docs/superpowers/plans/...   this file
```

---

## Task Sequence

### T1: `_compute_momentum` 헬퍼 + 4 unit tests

**Implementation:**
```python
def _compute_momentum(
    conn: sqlite3.Connection, user_id: str, *, now: Optional[datetime] = None,
) -> dict:
    """Streak + stagnation 계산. KST 기준.

    Returns:
      {streak_days: int, last_active_date: str | None,
       stagnant_tasks: list[{title, days}]}
    """
    n = now or _now_kst()
    today_kst = n.date()

    # 최근 14일치 활성 여부 — task closed / folder snap / chat ≥ 3
    activity: dict[str, bool] = {}
    for delta in range(14):
        d = today_kst - timedelta(days=delta)
        start = datetime(d.year, d.month, d.day, 0, 0, 0).isoformat()
        end = (datetime(d.year, d.month, d.day, 0, 0, 0) + timedelta(days=1)).isoformat()

        closed_n = conn.execute(
            "SELECT COUNT(*) FROM Task "
            "WHERE user_id=? AND status='done' AND updated_at >= ? AND updated_at < ?",
            (user_id, start, end),
        ).fetchone()[0]
        snap_n = conn.execute(
            "SELECT COUNT(*) FROM FolderSnapshot s JOIN Task t ON t.id = s.task_id "
            "WHERE t.user_id=? AND s.taken_at >= ? AND s.taken_at < ?",
            (user_id, start, end),
        ).fetchone()[0]
        chat_n = conn.execute(
            "SELECT COUNT(*) FROM ChatMessage m "
            "JOIN ChatSession s ON s.id = m.chat_session_id "
            "WHERE s.user_id=? AND m.role='user' AND m.created_at >= ? AND m.created_at < ?",
            (user_id, start, end),
        ).fetchone()[0]
        activity[d.isoformat()] = bool(closed_n or snap_n or chat_n >= 3)

    # Streak: 오늘부터 거꾸로 활성인 날이 연속 몇 일?
    streak = 0
    last_active = None
    for delta in range(14):
        d = (today_kst - timedelta(days=delta)).isoformat()
        if activity.get(d):
            streak += 1
            if last_active is None:
                last_active = d
        else:
            break

    # Stagnant: open AND updated_at older than 5 days, top 3 by oldest
    cutoff = (n - timedelta(days=5)).isoformat()
    stag_rows = conn.execute(
        "SELECT title, updated_at FROM Task "
        "WHERE user_id=? AND status='open' AND updated_at < ? "
        "ORDER BY updated_at LIMIT 3",
        (user_id, cutoff),
    ).fetchall()
    stagnant = []
    for r in stag_rows:
        try:
            dt = datetime.fromisoformat(r["updated_at"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (n - dt).days
        except ValueError:
            days = 0
        stagnant.append({"title": r["title"], "days": days})

    return {
        "streak_days": streak,
        "last_active_date": last_active,
        "stagnant_tasks": stagnant,
    }
```

**Tests:**
- `test_momentum_streak_continuous` — 3일 연속 활성 → streak=3
- `test_momentum_streak_broken_yesterday` — 오늘만 활성, 어제 비활성 → streak=1
- `test_momentum_streak_zero` — 14일 모두 비활성 → streak=0, last_active=None
- `test_momentum_stagnant_listed` — 7일 전 updated_at task → stagnant_tasks[0].days >= 7

### T2: tendencies loader 통합

`collect_briefing_data()`에 추가:
```python
from pipeline.tendencies import load_from_memory as _load_tendencies
...
tendencies = _load_tendencies(conn, user_id) or {}
```
신규 dict 키: `"tendencies": tendencies`.

**Test:** `test_collect_includes_tendencies` — memory에 미리 INSERT한 dict가 그대로 반환.

### T3: RAG recall 통합

`collect_briefing_data()`에 추가:
```python
# RAG fail-soft 회상
rag_query_parts = [t["title"] for t in open_tasks[:5]]
if rag_query_parts:
    try:
        from rag.retriever import recall_semantic
        rag_recalls = recall_semantic(
            conn, user_id=user_id, query=" ".join(rag_query_parts),
            kinds=("chat", "memory", "task"), k=3,
        )
    except Exception:
        rag_recalls = []
else:
    rag_recalls = []
```
신규 dict 키: `"rag_recalls": rag_recalls`.

**Test:** `test_collect_rag_recalls_empty_when_no_open_tasks` — task 없으면 빈 list.

### T4: `_fallback_brief` adaptive rendering

기존 함수를 `_render_brief_lines(data)`로 위임. 룰:

```python
TONE_LINES = {
    "quiet": "오늘 하나만 가볍게 시작해볼까?",
    "witty": "오늘 한 놈만 패자.",
    "sharp": "오늘 가장 미루던 거 먼저 손대.",
    "savage": "변명 그만, 마감 임박부터.",
}

def _render_brief_lines(data: dict) -> list[str]:
    lines = [f"📅 오늘 {data['today']}. 진행 중 {data['open_count']}개."]
    if data.get("overdue"):
        titles = ", ".join(t["title"] for t in data["overdue"][:3])
        lines.append(f"⏰ 마감 지남: {titles}")
    if data.get("imminent"):
        items = ", ".join(
            f"{t['title']} ({t['deadline_at'][:10]})" for t in data["imminent"][:3]
        )
        lines.append(f"🔔 마감 임박(3일 내): {items}")
    mom = data.get("momentum") or {}
    streak = mom.get("streak_days", 0)
    stagnant = mom.get("stagnant_tasks") or []
    if streak >= 2:
        lines.append(f"🔥 {streak}일 연속 뭐든 진행 중")
    elif streak == 0 and stagnant:
        s = stagnant[0]
        lines.append(f"⏳ \"{s['title']}\"은 {s['days']}일째 멈춰있어")
    recalls = data.get("rag_recalls") or []
    if recalls:
        top = recalls[0]
        snippet = (top.get("content") or "")[:60].replace("\n", " ")
        lines.append(f"💭 {top['kind']}에서 비슷한 맥락: {snippet}")
    tone = ((data.get("tendencies") or {}).get("tone_preference")) or "quiet"
    lines.append(TONE_LINES.get(tone, TONE_LINES["quiet"]))
    return lines


def _fallback_brief(data: dict) -> str:
    lines = _render_brief_lines(data)
    return "\n".join(lines)
```

**Tests:**
- `test_render_skips_empty_dimensions` — momentum 없으면 streak/stagnant 라인 없음
- `test_render_picks_stagnant_when_streak_zero` — streak=0 + stagnant=[X] → "⏳ X" emit
- `test_render_tone_savage` — tendencies.tone_preference="savage" → L6에 savage 라인

### T5: `build_briefing_prompt` 강화 + 통합 테스트

```python
def build_briefing_prompt(data: dict) -> str:
    tone = ((data.get("tendencies") or {}).get("tone_preference")) or "quiet"
    return (
        "당신은 사용자의 친근한 개인 비서입니다. 오늘 첫 브리핑을 한국어로 작성하세요.\n"
        f"어조: {tone} (quiet=차분, witty=가벼운 농담, sharp=단호, savage=거칠게).\n"
        "규칙:\n"
        "- 최대 6줄. 데이터 *있는* 차원만 사용. 데이터 없으면 만들어내지 마라.\n"
        "- 줄 시작 이모지 OK (📅·⏰·🔔·🔥·⏳·💭).\n"
        "- 마지막 줄은 오늘 시작할 작은 행동 하나만 제안.\n"
        "- 신호 mapping: momentum.streak_days=연속 활성, rag_recalls=과거 비슷한 맥락, "
        "tendencies=사용자 평소 패턴.\n\n"
        f"근거 신호:\n{json.dumps(data, ensure_ascii=False, default=str)}\n"
    )
```

**Test:** `test_generate_briefing_integrates_all_signals` — LLM mock + 모든 신호 채워서 generate_briefing 호출. 결과에 streak/recall이 prompt를 통해 전달됐는지 (모의 LLM의 last received prompt 확인).

---

## Verification After Implementation

```
pytest tests/test_briefing.py tests/test_briefing_v2.py -v
pytest -q
python -c "from pipeline.briefing import generate_briefing, _compute_momentum; print('ok')"
```

기대: 기존 12개 + 신규 ~10개 모두 PASS, 전체 회귀 540+ PASS, 0 regression.

## Commit Strategy
1. spec + plan 먼저 staged (PR 본문에 인라인 요약)
2. briefing.py + test_briefing_v2.py 코드 commit
3. PR #13 — code + docs 같은 PR (single-file refactor라 분리 가치 적음)
