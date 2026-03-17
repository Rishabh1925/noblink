"""
The Global Staring Contest — FastAPI Application

Endpoints:
    REST
        POST /api/users              – Register / get-or-create user
        GET  /api/leaderboard        – All-time Top 100
        GET  /api/leaderboard/{uid}  – User's rank
        GET  /api/users/{uid}/stats  – User session history + best time
        GET  /api/health             – Health check

    WebSocket
        WS /ws/staring-contest/{client_id}  – Real-time game session
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import bcrypt
from bson import ObjectId
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, get_db, init_db
from app.leaderboard import get_top_100, get_user_rank
from app.models import new_user_doc, serialize_doc
from app.schemas import (
    GameSessionResponse,
    HealthResponse,
    LeaderboardResponse,
    UserCreate,
    UserLogin,
    UserRegister,
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

    # Connect to databases (graceful degradation if unavailable)
    try:
        await init_db()
        logger.info("✅ MongoDB connected")
    except Exception as e:
        logger.warning("⚠️  MongoDB unavailable: %s — running in degraded mode", e)

    yield

    # Shutdown
    try:
        await close_db()
    except Exception:
        pass
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
    """Health check — verifies MongoDB connectivity."""
    db_status = "unknown"

    # Check DB
    try:
        db = get_db()
        await db.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    overall = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(status=overall, database=db_status)


# ── Users ────────────────────────────────────────────────────────────────────


@app.post("/api/users", response_model=UserResponse, tags=["Users"])
async def create_or_get_user(payload: UserCreate):
    """
    Register a new user or return existing user by username.

    This is a get-or-create endpoint — the frontend can call it on every
    session start without worrying about duplicates.
    """
    db = get_db()
    user = await db.users.find_one({"username": payload.username})

    if user is None:
        doc = new_user_doc(payload.username)
        result = await db.users.insert_one(doc)
        doc["_id"] = result.inserted_id
        user = doc

    return serialize_doc(user)


@app.post("/api/users/register", response_model=UserResponse, tags=["Users"])
async def register_user(payload: UserRegister):
    """Register a new user with email and password."""
    db = get_db()

    # Check if email already exists
    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Check if username already exists
    existing = await db.users.find_one({"username": payload.username})
    if existing:
        raise HTTPException(status_code=409, detail="Username already taken")

    # Hash password and create user
    hashed = bcrypt.hashpw(payload.password.encode("utf-8"), bcrypt.gensalt())
    doc = new_user_doc(
        username=payload.username,
        email=payload.email,
        hashed_password=hashed.decode("utf-8"),
    )
    result = await db.users.insert_one(doc)
    doc["_id"] = result.inserted_id

    return serialize_doc(doc)


@app.post("/api/users/login", response_model=UserResponse, tags=["Users"])
async def login_user(payload: UserLogin):
    """Sign in with email and password."""
    db = get_db()

    user = await db.users.find_one({"email": payload.email})
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    stored_hash = user.get("hashed_password", "")
    if not stored_hash or not bcrypt.checkpw(
        payload.password.encode("utf-8"), stored_hash.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return serialize_doc(user)


@app.get("/api/users/{user_id}/stats", response_model=UserStatsResponse, tags=["Users"])
async def get_user_stats(user_id: str):
    """Get a user's profile and recent session history."""
    db = get_db()

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    sessions_cursor = (
        db.game_sessions
        .find({"user_id": user_id})
        .sort("started_at", -1)
        .limit(20)
    )
    sessions = await sessions_cursor.to_list(length=20)

    return UserStatsResponse(
        user=UserResponse(**serialize_doc(user)),
        recent_sessions=[
            GameSessionResponse(**serialize_doc(s)) for s in sessions
        ],
    )


# ── Leaderboard ──────────────────────────────────────────────────────────────


@app.get("/api/leaderboard", response_model=LeaderboardResponse, tags=["Leaderboard"])
async def leaderboard_top_100():
    """
    Get the all-time Top 100 longest stares.

    The frontend should poll this endpoint periodically (e.g. every 30 seconds)
    to display the live global leaderboard.
    """
    try:
        return await get_top_100()
    except Exception:
        return LeaderboardResponse(
            entries=[],
            total_players=0,
        )


@app.get("/api/leaderboard/{user_id}/rank", tags=["Leaderboard"])
async def leaderboard_user_rank(user_id: str):
    """Get a specific user's all-time rank on the leaderboard."""
    db = get_db()

    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    rank = None
    try:
        rank = await get_user_rank(user_id, user["username"])
    except Exception:
        pass

    return {
        "user_id": user_id,
        "username": user["username"],
        "rank": rank,
        "message": "Ranked" if rank else "No score recorded",
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
