"""
Leaderboard — MongoDB-based operations for the real-time global leaderboard.

Queries the ``game_sessions`` collection directly.  Only sessions with
``status == "completed"`` are considered.  Scores are ranked by
``duration_ms`` (higher is better).  Per-user best score for the day is
used.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from app.database import get_db
from app.schemas import LeaderboardEntry, LeaderboardResponse


# ── Helpers ──────────────────────────────────────────────────────────────────


def _today_range() -> tuple[datetime, datetime]:
    """Return (start, end) datetimes for today (UTC)."""
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


# ── Public API ───────────────────────────────────────────────────────────────


async def submit_score(
    user_id: str,
    username: str,
    duration_ms: int,
) -> None:
    """
    No-op — scores are already persisted in ``game_sessions`` by the
    WebSocket handler.  This function exists only to maintain the same
    call-sites; it does nothing.
    """
    pass


async def get_top_100() -> LeaderboardResponse:
    """
    Retrieve the top 100 scores for today.

    Uses a MongoDB aggregation pipeline to:
    1. Filter today's completed sessions
    2. Group by user → take max duration
    3. Sort descending by duration
    4. Limit to 100
    """
    db = get_db()
    start, end = _today_range()

    pipeline = [
        {
            "$match": {
                "status": "completed",
                "started_at": {"$gte": start, "$lt": end},
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "username": {"$first": "$username"},
                "duration_ms": {"$max": "$duration_ms"},
            }
        },
        {"$sort": {"duration_ms": -1}},
        {"$limit": 100},
    ]

    results = await db.game_sessions.aggregate(pipeline).to_list(length=100)

    entries: list[LeaderboardEntry] = []
    for rank, doc in enumerate(results, start=1):
        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=doc["_id"],
                username=doc["username"],
                duration_ms=doc["duration_ms"],
            )
        )

    # Total unique players today
    count_pipeline = [
        {
            "$match": {
                "status": "completed",
                "started_at": {"$gte": start, "$lt": end},
            }
        },
        {"$group": {"_id": "$user_id"}},
        {"$count": "total"},
    ]
    count_result = await db.game_sessions.aggregate(count_pipeline).to_list(length=1)
    total = count_result[0]["total"] if count_result else 0

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return LeaderboardResponse(
        date=today_str,
        entries=entries,
        total_players=total,
    )


async def get_user_rank(user_id: str, username: str) -> int | None:
    """
    Get a user's rank on today's leaderboard (1-indexed).

    Returns ``None`` if the user has no completed session today.
    """
    db = get_db()
    start, end = _today_range()

    pipeline = [
        {
            "$match": {
                "status": "completed",
                "started_at": {"$gte": start, "$lt": end},
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "duration_ms": {"$max": "$duration_ms"},
            }
        },
        {"$sort": {"duration_ms": -1}},
    ]

    results = await db.game_sessions.aggregate(pipeline).to_list(length=None)

    for rank, doc in enumerate(results, start=1):
        if doc["_id"] == user_id:
            return rank

    return None


async def get_user_score(user_id: str, username: str) -> int | None:
    """Get a user's best score on today's leaderboard."""
    db = get_db()
    start, end = _today_range()

    pipeline = [
        {
            "$match": {
                "status": "completed",
                "user_id": user_id,
                "started_at": {"$gte": start, "$lt": end},
            }
        },
        {
            "$group": {
                "_id": "$user_id",
                "duration_ms": {"$max": "$duration_ms"},
            }
        },
    ]

    results = await db.game_sessions.aggregate(pipeline).to_list(length=1)
    return results[0]["duration_ms"] if results else None
