"""
WebSocket Manager — real-time game session over WS.

Endpoint: ``/ws/staring-contest/{client_id}``

Session state machine:
    WAITING → COUNTDOWN → ACTIVE → GAME_OVER
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.anti_cheat import AntiCheatTracker
from app.database import get_db
from app.ml_engine import BlinkDetector
from app.models import SessionStatus, new_game_session_doc, new_user_doc
from app.schemas import (
    GameOverReason,
    WSCountdown,
    WSEarUpdate,
    WSError,
    WSFrameMessage,
    WSGameActive,
    WSGameOver,
    WSSessionReady,
)

logger = logging.getLogger(__name__)

# ── Connection Manager ───────────────────────────────────────────────────────


class ConnectionManager:
    """Track all active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[client_id] = ws
        logger.info("Client %s connected (%d active)", client_id, len(self._connections))

    def disconnect(self, client_id: str) -> None:
        self._connections.pop(client_id, None)
        logger.info("Client %s disconnected (%d active)", client_id, len(self._connections))

    @property
    def active_count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()

# ── Game Session Handler ─────────────────────────────────────────────────────


async def handle_game_session(client_id: str, ws: WebSocket) -> None:
    """
    Main handler for a single game session over WebSocket.

    Flow:
    1. Accept connection, wait for START_GAME message
    2. Create DB session record, send SESSION_READY
    3. Run 3-2-1 countdown
    4. Enter active loop — receive frames, run EAR + anti-cheat
    5. On blink / cheat / disconnect → GAME_OVER, persist results
    """
    await manager.connect(client_id, ws)

    blink_detector = BlinkDetector()
    anti_cheat = AntiCheatTracker()
    session_id: str | None = None
    user_id: str | None = None
    username: str | None = None
    start_time_ns: int = 0
    frame_count: int = 0
    last_ear: float = 0.0
    game_active = False

    try:
        # ── 1. Wait for START_GAME ───────────────────────────────────────
        raw = await ws.receive_json()
        msg_type = raw.get("type", "")

        if msg_type != "START_GAME":
            await ws.send_json(
                WSError(type="ERROR", detail="Expected START_GAME message").model_dump()
            )
            return

        user_id = raw.get("user_id", "")
        username = raw.get("username", f"Player_{client_id[:6]}")

        # ── 2. Create DB session ─────────────────────────────────────────
        db = get_db()

        # Get or verify user exists
        user = None
        if user_id and ObjectId.is_valid(user_id):
            user = await db.users.find_one({"_id": ObjectId(user_id)})

        if user is None:
            # Auto-create user for seamless UX
            user_doc = new_user_doc(username)
            result = await db.users.insert_one(user_doc)
            user_id = str(result.inserted_id)
        else:
            user_id = str(user["_id"])

        # Create game session
        session_doc = new_game_session_doc(user_id, username)
        result = await db.game_sessions.insert_one(session_doc)
        session_id = str(result.inserted_id)

        await ws.send_json(
            WSSessionReady(type="SESSION_READY", session_id=session_id).model_dump()
        )

        # ── 3. Countdown ─────────────────────────────────────────────────
        for count in (3, 2, 1):
            await ws.send_json(
                WSCountdown(type="COUNTDOWN", count=count).model_dump()
            )
            await asyncio.sleep(1)

        # ── 4. Game Active ───────────────────────────────────────────────
        start_time_ns = time.monotonic_ns()
        game_active = True
        started_at_ms = int(time.time() * 1000)

        await ws.send_json(
            WSGameActive(type="GAME_ACTIVE", started_at=started_at_ms).model_dump()
        )

        blink_detector.reset()

        while True:
            raw = await ws.receive_json()
            msg_type = raw.get("type", "")

            if msg_type != "FRAME":
                continue

            # Parse and validate the frame
            try:
                frame = WSFrameMessage(**raw)
            except ValidationError as e:
                await ws.send_json(
                    WSError(
                        type="ERROR", detail=f"Invalid frame: {e.errors()[0]['msg']}"
                    ).model_dump()
                )
                continue

            left_eye = [lm.model_dump() for lm in frame.landmarks.left_eye]
            right_eye = [lm.model_dump() for lm in frame.landmarks.right_eye]
            frame_count += 1

            # Run blink detection
            blink_result = blink_detector.process_frame(left_eye, right_eye)
            last_ear = blink_result.ear_value

            # Run anti-cheat validation
            ac_result = anti_cheat.validate_frame(
                left_eye, right_eye, ear_value=blink_result.ear_value
            )

            elapsed_ns = time.monotonic_ns() - start_time_ns
            elapsed_ms = elapsed_ns // 1_000_000

            # ── Check for blink ──────────────────────────────────────────
            if blink_result.is_blink:
                await _end_game(
                    ws=ws,
                    session_id=session_id,
                    user_id=user_id,
                    username=username,
                    duration_ms=int(elapsed_ms),
                    reason=GameOverReason.BLINK_DETECTED,
                    final_ear=blink_result.ear_value,
                    total_frames=frame_count,
                )
                return

            # ── Check for cheating ───────────────────────────────────────
            if not ac_result.is_valid:
                await _end_game(
                    ws=ws,
                    session_id=session_id,
                    user_id=user_id,
                    username=username,
                    duration_ms=int(elapsed_ms),
                    reason=GameOverReason.CHEATING_DETECTED,
                    final_ear=blink_result.ear_value,
                    total_frames=frame_count,
                    cheat_flag=ac_result.flag.value if ac_result.flag else None,
                )
                return

            # ── Send EAR update (every 3rd frame to reduce bandwidth) ────
            if frame_count % 3 == 0:
                await ws.send_json(
                    WSEarUpdate(
                        type="EAR_UPDATE",
                        ear=round(blink_result.ear_value, 4),
                        elapsed_ms=int(elapsed_ms),
                    ).model_dump()
                )

    except WebSocketDisconnect:
        logger.info("Client %s disconnected", client_id)
        if game_active and session_id:
            elapsed_ns = time.monotonic_ns() - start_time_ns
            elapsed_ms = elapsed_ns // 1_000_000
            await _persist_session(
                session_id=session_id,
                user_id=user_id,
                username=username,
                duration_ms=int(elapsed_ms),
                status=SessionStatus.COMPLETED,
                final_ear=last_ear,
                total_frames=frame_count,
            )
    except Exception as e:
        logger.exception("Error in session for client %s: %s", client_id, e)
        try:
            if game_active and session_id:
                elapsed_ns = time.monotonic_ns() - start_time_ns
                elapsed_ms = elapsed_ns // 1_000_000
                await ws.send_json(
                    WSGameOver(
                        type="GAME_OVER",
                        reason=GameOverReason.SERVER_ERROR,
                        duration_ms=int(elapsed_ms),
                    ).model_dump()
                )
        except Exception:
            pass
    finally:
        manager.disconnect(client_id)


# ── Internal Helpers ─────────────────────────────────────────────────────────


async def _end_game(
    *,
    ws: WebSocket,
    session_id: str,
    user_id: str | None,
    username: str | None,
    duration_ms: int,
    reason: GameOverReason,
    final_ear: float | None = None,
    total_frames: int = 0,
    cheat_flag: str | None = None,
) -> None:
    """Send GAME_OVER to the client and persist the session."""
    payload = WSGameOver(
        type="GAME_OVER",
        reason=reason,
        duration_ms=duration_ms,
        final_ear=final_ear,
    ).model_dump()

    if cheat_flag:
        payload["cheat_flag"] = cheat_flag

    await ws.send_json(payload)

    status = (
        SessionStatus.CHEATING_DETECTED
        if reason == GameOverReason.CHEATING_DETECTED
        else SessionStatus.COMPLETED
    )

    await _persist_session(
        session_id=session_id,
        user_id=user_id,
        username=username,
        duration_ms=duration_ms,
        status=status,
        final_ear=final_ear,
        total_frames=total_frames,
    )


async def _persist_session(
    *,
    session_id: str,
    user_id: str | None,
    username: str | None,
    duration_ms: int,
    status: SessionStatus,
    final_ear: float | None = None,
    total_frames: int = 0,
) -> None:
    """Update the game session in MongoDB and submit to the leaderboard."""
    try:
        db = get_db()

        # Update game session
        await db.game_sessions.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$set": {
                    "ended_at": datetime.now(timezone.utc),
                    "duration_ms": duration_ms,
                    "status": status.value,
                    "final_ear": final_ear,
                    "total_frames": total_frames,
                }
            },
        )

        # Update user stats
        if user_id and ObjectId.is_valid(user_id):
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if user:
                update_fields: dict = {"$inc": {"total_sessions": 1}}
                if duration_ms > user.get("best_time_ms", 0):
                    update_fields["$set"] = {"best_time_ms": duration_ms}
                    await db.users.update_one(
                        {"_id": ObjectId(user_id)},
                        update_fields,
                    )

    except Exception as e:
        logger.exception("Failed to persist session %s: %s", session_id, e)
