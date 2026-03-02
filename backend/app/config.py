"""
Configuration — loads settings from .env via pydantic-settings.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "The Global Staring Contest"
    debug: bool = False

    # ── Database (Supabase PostgreSQL) ───────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/noblink",
        description="Async SQLAlchemy connection string for PostgreSQL",
    )

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379",
        description="Redis connection URL",
    )

    # ── ML / Blink Detection ─────────────────────────────────────────────────
    ear_threshold: float = Field(
        default=0.21,
        description="EAR below this value indicates eyes closing",
    )
    ear_consec_frames: int = Field(
        default=2,
        description="Consecutive low-EAR frames required to confirm a blink",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated allowed CORS origins",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


settings = Settings()
