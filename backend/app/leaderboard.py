"""
Leaderboard — Redis Sorted Set operations for the real-time global leaderboard.

Key format: ``leaderboard:daily:YYYY-MM-DD``
Score = duration in milliseconds (higher is better).
Member = ``user_id::username`` (composite key for easy display).
"""

from __future__ import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config import settings
from app.schemas import LeaderboardEntry, LeaderboardResponse

# ── Redis Connection ─────────────────────────────────────────────────────────

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return the shared Redis connection (lazily initialised)."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
    return _redis_pool


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _today_key() -> str:
    """Return the Redis key for today's leaderboard."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"leaderboard:daily:{today}"


def _make_member(user_id: str, username: str) -> str:
    """Encode user_id and username as a sorted-set member."""
    return f"{user_id}::{username}"


def _parse_member(member: str) -> tuple[str, str]:
    """Decode a sorted-set member into (user_id, username)."""
    parts = member.split("::", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


# ── Public API ───────────────────────────────────────────────────────────────


async def submit_score(
    user_id: str,
    username: str,
    duration_ms: int,
) -> None:
    """
    Submit (or update) a score on today's leaderboard.

    Uses ``ZADD`` with the ``GT`` flag so the score is only updated if the
    new value is *greater* than the existing one (personal best for today).
    Also sets a 48-hour TTL on the key to auto-clean old leaderboards.
    """
    r = await get_redis()
    key = _today_key()
    member = _make_member(user_id, username)

    await r.zadd(key, {member: duration_ms}, gt=True)

    # Ensure the key expires after 48 hours (refresh on each write)
    await r.expire(key, 48 * 60 * 60)


async def get_top_100() -> LeaderboardResponse:
    """
    Retrieve the top 100 scores for today.

    Returns a ``LeaderboardResponse`` with rank-ordered entries.
    """
    r = await get_redis()
    key = _today_key()

    # ZREVRANGE returns highest-first, with scores
    raw = await r.zrevrange(key, 0, 99, withscores=True)

    entries: list[LeaderboardEntry] = []
    for rank, (member, score) in enumerate(raw, start=1):
        user_id, username = _parse_member(member)
        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=user_id,
                username=username,
                duration_ms=int(score),
            )
        )

    total = await r.zcard(key)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return LeaderboardResponse(
        date=today_str,
        entries=entries,
        total_players=total,
    )


async def get_user_rank(user_id: str, username: str) -> int | None:
    """
    Get a user's rank on today's leaderboard (1-indexed).

    Returns ``None`` if the user has no score today.
    """
    r = await get_redis()
    key = _today_key()
    member = _make_member(user_id, username)

    rank = await r.zrevrank(key, member)
    return (rank + 1) if rank is not None else None


async def get_user_score(user_id: str, username: str) -> int | None:
    """Get a user's score on today's leaderboard."""
    r = await get_redis()
    key = _today_key()
    member = _make_member(user_id, username)

    score = await r.zscore(key, member)
    return int(score) if score is not None else None
