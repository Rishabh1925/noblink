"""
Pydantic Schemas — request / response models for the REST and WebSocket APIs.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────────────


class WSMessageType(str, Enum):
    """Types of WebSocket messages (both directions)."""

    # Client → Server
    FRAME = "FRAME"
    START_GAME = "START_GAME"

    # Server → Client
    SESSION_READY = "SESSION_READY"
    COUNTDOWN = "COUNTDOWN"
    GAME_ACTIVE = "GAME_ACTIVE"
    EAR_UPDATE = "EAR_UPDATE"
    GAME_OVER = "GAME_OVER"
    ERROR = "ERROR"


class GameOverReason(str, Enum):
    BLINK_DETECTED = "blink_detected"
    CHEATING_DETECTED = "cheating_detected"
    CLIENT_DISCONNECT = "client_disconnect"
    SERVER_ERROR = "server_error"


# ── Landmark Data ────────────────────────────────────────────────────────────


class Landmark(BaseModel):
    x: float
    y: float
    z: float


class EyeLandmarks(BaseModel):
    left_eye: list[Landmark] = Field(..., min_length=6, max_length=6)
    right_eye: list[Landmark] = Field(..., min_length=6, max_length=6)


# ── WebSocket Messages ──────────────────────────────────────────────────────


class WSFrameMessage(BaseModel):
    """Incoming frame message from the client."""

    type: WSMessageType = WSMessageType.FRAME
    timestamp: int = Field(..., description="Client-side Unix timestamp in ms")
    landmarks: EyeLandmarks


class WSStartMessage(BaseModel):
    """Client requests to start the game."""

    type: WSMessageType = WSMessageType.START_GAME
    user_id: str
    username: str


class WSSessionReady(BaseModel):
    type: WSMessageType = WSMessageType.SESSION_READY
    session_id: str


class WSCountdown(BaseModel):
    type: WSMessageType = WSMessageType.COUNTDOWN
    count: int


class WSGameActive(BaseModel):
    type: WSMessageType = WSMessageType.GAME_ACTIVE
    started_at: int


class WSEarUpdate(BaseModel):
    type: WSMessageType = WSMessageType.EAR_UPDATE
    ear: float
    elapsed_ms: int


class WSGameOver(BaseModel):
    type: WSMessageType = WSMessageType.GAME_OVER
    reason: GameOverReason
    duration_ms: int
    final_ear: float | None = None


class WSError(BaseModel):
    type: WSMessageType = WSMessageType.ERROR
    detail: str


# ── REST API Schemas ─────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)


class UserRegister(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    email: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4, max_length=100)


class UserLogin(BaseModel):
    email: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=4, max_length=100)


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None = None
    created_at: datetime
    total_sessions: int
    best_time_ms: int


class GameSessionResponse(BaseModel):
    id: str
    user_id: str
    username: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int
    status: str
    final_ear: float | None
    total_frames: int


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    duration_ms: int


class LeaderboardResponse(BaseModel):
    date: str
    entries: list[LeaderboardEntry]
    total_players: int


class UserStatsResponse(BaseModel):
    user: UserResponse
    recent_sessions: list[GameSessionResponse]


class HealthResponse(BaseModel):
    status: str
    database: str
