"""
ORM Models — User and GameSession tables.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# ── Enums ────────────────────────────────────────────────────────────────────


class SessionStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CHEATING_DETECTED = "cheating_detected"


# ── Users ────────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    username: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
    )
    total_sessions: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0")
    )
    best_time_ms: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0")
    )

    # relationships
    sessions: Mapped[list["GameSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User {self.username} best={self.best_time_ms}ms>"


# ── Game Sessions ────────────────────────────────────────────────────────────


class GameSession(Base):
    __tablename__ = "game_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    username: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(
        BigInteger, default=0
    )
    status: Mapped[SessionStatus] = mapped_column(
        SAEnum(SessionStatus, name="session_status", create_constraint=True),
        default=SessionStatus.ACTIVE,
    )
    final_ear: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    total_frames: Mapped[int] = mapped_column(
        Integer, default=0
    )

    # relationships
    user: Mapped["User"] = relationship(back_populates="sessions")

    def __repr__(self) -> str:
        return f"<GameSession {self.id} user={self.username} status={self.status}>"
