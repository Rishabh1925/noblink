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

    # ── Database (MongoDB) ───────────────────────────────────────────────────
    mongodb_url: str = Field(
        default="mongodb://localhost:27017",
        description="MongoDB connection string",
    )
    mongodb_db_name: str = Field(
        default="noblink",
        description="MongoDB database name",
    )

    # ── ML / Blink Detection ─────────────────────────────────────────────────
    ear_threshold: float = Field(
        default=0.18,
        description="EAR below this value indicates eyes closing",
    )
    ear_consec_frames: int = Field(
        default=3,
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
        "extra": "ignore",
    }


settings = Settings()
