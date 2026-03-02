"""
The Global Staring Contest — FastAPI Application

Endpoints:
    REST
        POST /api/users              – Register / get-or-create user
        GET  /api/leaderboard        – Top 100 today
        GET  /api/leaderboard/{uid}  – User's rank
        GET  /api/users/{uid}/stats  – User session history + best time
        GET  /api/health             – Health check

    WebSocket
        WS /ws/staring-contest/{client_id}  – Real-time game session
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory, close_db, get_db, init_db
from app.leaderboard import close_redis, get_redis, get_top_100, get_user_rank
from app.models import GameSession, User
from app.schemas import (
    GameSessionResponse,
    HealthResponse,
    LeaderboardResponse,
    UserCreate,
    UserResponse,
    UserStatsResponse,
)
from app.websocket_manager import handle_game_session

logger = logging.getLogger(__name__)

# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("🚀 Starting %s", settings.app_name)

    # Connect to databases
    await init_db()
    logger.info("✅ PostgreSQL connected")

    await get_redis()
    logger.info("✅ Redis connected")

    yield

    # Shutdown
    await close_redis()
    await close_db()
    logger.info("👋 Shutdown complete")


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    description="Real-time staring contest with blink detection and global leaderboard",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
#  REST ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check — verifies PostgreSQL and Redis connectivity."""
    db_status = "unknown"
    redis_status = "unknown"

    # Check DB
    try:
        async with async_session_factory() as session:
            await session.execute(select(1))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    # Check Redis
    try:
        r = await get_redis()
        await r.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {e}"

    overall = "ok" if db_status == "connected" and redis_status == "connected" else "degraded"

    return HealthResponse(status=overall, database=db_status, redis=redis_status)


# ── Users ────────────────────────────────────────────────────────────────────


@app.post("/api/users", response_model=UserResponse, tags=["Users"])
async def create_or_get_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user or return existing user by username.

    This is a get-or-create endpoint — the frontend can call it on every
    session start without worrying about duplicates.
    """
    result = await db.execute(
        select(User).where(User.username == payload.username)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(username=payload.username)
        db.add(user)
        await db.flush()
        await db.refresh(user)

    return user


@app.get("/api/users/{user_id}/stats", response_model=UserStatsResponse, tags=["Users"])
async def get_user_stats(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a user's profile and recent session history."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    sessions_result = await db.execute(
        select(GameSession)
        .where(GameSession.user_id == user_id)
        .order_by(GameSession.started_at.desc())
        .limit(20)
    )
    sessions = sessions_result.scalars().all()

    return UserStatsResponse(
        user=UserResponse.model_validate(user),
        recent_sessions=[GameSessionResponse.model_validate(s) for s in sessions],
    )


# ── Leaderboard ──────────────────────────────────────────────────────────────


@app.get("/api/leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"])
async def leaderboard_top_100():
    """
    Get today's Top 100 longest stares.

    The frontend should poll this endpoint periodically (e.g. every 5 seconds)
    to display the live global leaderboard.
    """
    return await get_top_100()


@app.get("/api/leaderboard/{user_id}/rank", tags=["Leaderboard"])
async def leaderboard_user_rank(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific user's rank on today's leaderboard."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    rank = await get_user_rank(str(user_id), user.username)

    return {
        "user_id": str(user_id),
        "username": user.username,
        "rank": rank,
        "message": "Ranked" if rank else "No score today",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  WEBSOCKET ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════


@app.websocket("/ws/staring-contest/{client_id}")
async def websocket_staring_contest(websocket: WebSocket, client_id: str):
    """
    Real-time staring contest game session.

    The client connects, sends a START_GAME message, then streams FRAME
    messages containing eye landmark coordinates.  The server validates
    and runs blink detection.  On blink or cheat → GAME_OVER.
    """
    await handle_game_session(client_id, websocket)
