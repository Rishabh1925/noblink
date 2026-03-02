"""
Unit tests for the Redis Leaderboard module.

Uses ``fakeredis`` so no real Redis instance is required.
"""

import pytest
import fakeredis.aioredis

from app import leaderboard
from app.schemas import LeaderboardResponse


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def mock_redis(monkeypatch):
    """Replace the real Redis connection with fakeredis."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _get_redis():
        return fake

    monkeypatch.setattr(leaderboard, "get_redis", _get_redis)
    yield fake
    await fake.aclose()


# ── Tests ────────────────────────────────────────────────────────────────────


class TestSubmitScore:
    @pytest.mark.asyncio
    async def test_submit_and_retrieve(self):
        await leaderboard.submit_score("user-1", "Alice", 5000)

        result = await leaderboard.get_top_100()
        assert isinstance(result, LeaderboardResponse)
        assert len(result.entries) == 1
        assert result.entries[0].username == "Alice"
        assert result.entries[0].duration_ms == 5000

    @pytest.mark.asyncio
    async def test_gt_flag_only_updates_higher(self):
        """Score should only increase, never decrease."""
        await leaderboard.submit_score("user-1", "Alice", 5000)
        await leaderboard.submit_score("user-1", "Alice", 3000)  # lower — ignored

        result = await leaderboard.get_top_100()
        assert result.entries[0].duration_ms == 5000

        await leaderboard.submit_score("user-1", "Alice", 8000)  # higher — accepted
        result = await leaderboard.get_top_100()
        assert result.entries[0].duration_ms == 8000

    @pytest.mark.asyncio
    async def test_multiple_users_sorted(self):
        await leaderboard.submit_score("user-1", "Alice", 5000)
        await leaderboard.submit_score("user-2", "Bob", 8000)
        await leaderboard.submit_score("user-3", "Charlie", 3000)

        result = await leaderboard.get_top_100()
        assert len(result.entries) == 3
        assert result.entries[0].username == "Bob"
        assert result.entries[1].username == "Alice"
        assert result.entries[2].username == "Charlie"


class TestGetUserRank:
    @pytest.mark.asyncio
    async def test_rank_exists(self):
        await leaderboard.submit_score("user-1", "Alice", 5000)
        await leaderboard.submit_score("user-2", "Bob", 8000)

        rank = await leaderboard.get_user_rank("user-2", "Bob")
        assert rank == 1  # Bob is #1

        rank = await leaderboard.get_user_rank("user-1", "Alice")
        assert rank == 2

    @pytest.mark.asyncio
    async def test_rank_not_found(self):
        rank = await leaderboard.get_user_rank("nonexistent", "Nobody")
        assert rank is None


class TestGetTop100:
    @pytest.mark.asyncio
    async def test_empty_leaderboard(self):
        result = await leaderboard.get_top_100()
        assert len(result.entries) == 0
        assert result.total_players == 0

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        # Add 105 users
        for i in range(105):
            await leaderboard.submit_score(f"user-{i}", f"Player{i}", 1000 + i)

        result = await leaderboard.get_top_100()
        assert len(result.entries) == 100
        # Highest score should be first
        assert result.entries[0].duration_ms == 1104
        assert result.total_players == 105
