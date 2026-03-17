"""
Leaderboard — MongoDB-based operations for the all-time global leaderboard.

Queries the ``game_sessions`` collection directly.  Only sessions with
``status == "completed"`` are considered.  Scores are ranked by
``duration_ms`` (higher is better).  Per-user all-time best score is used.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.database import get_db
from app.schemas import LeaderboardEntry, LeaderboardResponse


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
    Retrieve the all-time top 100 scores.

    Uses a MongoDB aggregation pipeline to:
    1. Filter completed sessions
    2. Sort by duration descending (so $first picks the best session's date)
    3. Group by user → take max duration and the date of their best session
    4. Sort descending by duration
    5. Limit to 100
    """
    db = get_db()

    pipeline = [
        {"$match": {"status": "completed"}},
        # Sort so that when we group, $first gives us the best session's date
        {"$sort": {"duration_ms": -1}},
        {
            "$group": {
                "_id": "$user_id",
                "username": {"$first": "$username"},
                "duration_ms": {"$max": "$duration_ms"},
                "started_at": {"$first": "$started_at"},
            }
        },
        {"$sort": {"duration_ms": -1}},
        {"$limit": 100},
    ]

    results = await db.game_sessions.aggregate(pipeline).to_list(length=100)

    entries: list[LeaderboardEntry] = []
    for rank, doc in enumerate(results, start=1):
        # Format the date from the session's started_at
        recorded_at = doc.get("started_at")
        if isinstance(recorded_at, datetime):
            date_str = recorded_at.strftime("%Y-%m-%d")
        else:
            date_str = "—"

        entries.append(
            LeaderboardEntry(
                rank=rank,
                user_id=doc["_id"],
                username=doc["username"],
                duration_ms=doc["duration_ms"],
                date=date_str,
            )
        )

    # Total unique players (all-time)
    count_pipeline = [
        {"$match": {"status": "completed"}},
        {"$group": {"_id": "$user_id"}},
        {"$count": "total"},
    ]
    count_result = await db.game_sessions.aggregate(count_pipeline).to_list(length=1)
    total = count_result[0]["total"] if count_result else 0

    return LeaderboardResponse(
        entries=entries,
        total_players=total,
    )


async def get_user_rank(user_id: str, username: str) -> int | None:
    """
    Get a user's all-time rank on the leaderboard (1-indexed).

    Returns ``None`` if the user has no completed session.
    """
    db = get_db()

    pipeline = [
        {"$match": {"status": "completed"}},
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
    """Get a user's all-time best score."""
    db = get_db()

    pipeline = [
        {
            "$match": {
                "status": "completed",
                "user_id": user_id,
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
