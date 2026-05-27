"""Tomorrow's You — FastAPI Backend (port 8001)."""

from __future__ import annotations

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
from backend.deps import DB_PATH
from backend.api import users, personas, onboarding, sessions, regret, safety, tone_feedback, consent, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """시작 시 DB migrate + seed_builtin_prompts."""
    conn = open_db(DB_PATH)
    migrate(conn)
    seed_builtin_prompts(conn)
    conn.close()
    yield


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


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8001, reload=True)
