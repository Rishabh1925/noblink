"""
Database — async SQLAlchemy engine and session factory for Supabase PostgreSQL.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# ── Engine ───────────────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

# ── Session Factory ──────────────────────────────────────────────────────────

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Base Model ───────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Dependency ───────────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency — yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Lifecycle ────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose of the connection pool."""
    await engine.dispose()
