"""Tomorrow's You — FastAPI Backend (port 8001)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (기존 모듈 import용)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import open_db, migrate
from persona import seed_builtin_prompts
from pipeline.folder_watch import scan_open_tasks
from pipeline.followup import dispatch_due_followups
from backend.deps import DB_PATH
from backend.api import users, personas, onboarding, sessions, regret, safety, tone_feedback, consent, chat, tasks, calendar as calendar_api


async def _folder_watch_loop(interval_seconds: int) -> None:
    """Wave 2: 주기 폴더 스캔 loop. lifespan task로 실행."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            conn = open_db(DB_PATH)
            try:
                scan_open_tasks(conn)
            finally:
                conn.close()
        except asyncio.CancelledError:
            break
        except Exception:
            # 스캔 실패가 backend를 죽이지 않게 — 다음 cycle로
            continue


async def _followup_loop(interval_seconds: int) -> None:
    """Wave 3: 주기 follow-up dispatch."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            conn = open_db(DB_PATH)
            try:
                dispatch_due_followups(conn)
            finally:
                conn.close()
        except asyncio.CancelledError:
            break
        except Exception:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """시작 시 DB migrate + seed_builtin_prompts + folder watch task."""
    conn = open_db(DB_PATH)
    migrate(conn)
    seed_builtin_prompts(conn)
    conn.close()

    watch_task = None
    followup_task = None
    if os.environ.get("NAEIL_DISABLE_WATCH") != "1":
        interval_min = int(os.environ.get("NAEIL_WATCH_INTERVAL_MIN", "30"))
        watch_task = asyncio.create_task(
            _folder_watch_loop(max(interval_min, 1) * 60)
        )
    if os.environ.get("NAEIL_DISABLE_FOLLOWUP") != "1":
        fu_min = int(os.environ.get("NAEIL_FOLLOWUP_INTERVAL_MIN", "60"))
        followup_task = asyncio.create_task(
            _followup_loop(max(fu_min, 1) * 60)
        )

    try:
        yield
    finally:
        for t in (watch_task, followup_task):
            if t:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass


app = FastAPI(
    title="Tomorrow's You API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — localhost:3000 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(users.router)
app.include_router(personas.router)
app.include_router(onboarding.router)
app.include_router(sessions.router)
app.include_router(regret.router)
app.include_router(safety.router)
app.include_router(tone_feedback.router)
app.include_router(consent.router)
app.include_router(chat.router)
app.include_router(tasks.router)
app.include_router(calendar_api.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
