"""
Integration test for the WebSocket game flow and REST endpoints.

Uses FastAPI's TestClient with mocked Redis and SQLite in-memory DB
so no external services are required.
"""

import uuid
from unittest.mock import AsyncMock, patch

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app import leaderboard


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def mock_redis(monkeypatch):
    """Replace Redis with fakeredis for all tests."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _get_redis():
        return fake

    monkeypatch.setattr(leaderboard, "get_redis", _get_redis)
    # Also patch the leaderboard module import in main
    monkeypatch.setattr("app.leaderboard.get_redis", _get_redis)

    yield fake
    await fake.aclose()


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """
    Mock the database layer so we don't need a real PostgreSQL.
    The WebSocket handler and REST endpoints that need DB will use mocks.
    """
    from app import database

    # Mock init_db and close_db so lifespan doesn't fail
    monkeypatch.setattr(database, "init_db", AsyncMock())
    monkeypatch.setattr(database, "close_db", AsyncMock())

    # Mock close_redis in leaderboard
    monkeypatch.setattr(leaderboard, "close_redis", AsyncMock())


# ── Helpers ──────────────────────────────────────────────────────────────────


def _open_eye_landmarks() -> dict:
    return {
        "left_eye": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 0.2, "y": 0.15, "z": 0.0},
            {"x": 0.4, "y": 0.15, "z": 0.0},
            {"x": 0.6, "y": 0.0, "z": 0.0},
            {"x": 0.4, "y": -0.15, "z": 0.0},
            {"x": 0.2, "y": -0.15, "z": 0.0},
        ],
        "right_eye": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 0.2, "y": 0.15, "z": 0.0},
            {"x": 0.4, "y": 0.15, "z": 0.0},
            {"x": 0.6, "y": 0.0, "z": 0.0},
            {"x": 0.4, "y": -0.15, "z": 0.0},
            {"x": 0.2, "y": -0.15, "z": 0.0},
        ],
    }


def _closed_eye_landmarks() -> dict:
    return {
        "left_eye": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 0.2, "y": 0.02, "z": 0.0},
            {"x": 0.4, "y": 0.02, "z": 0.0},
            {"x": 0.6, "y": 0.0, "z": 0.0},
            {"x": 0.4, "y": -0.02, "z": 0.0},
            {"x": 0.2, "y": -0.02, "z": 0.0},
        ],
        "right_eye": [
            {"x": 0.0, "y": 0.0, "z": 0.0},
            {"x": 0.2, "y": 0.02, "z": 0.0},
            {"x": 0.4, "y": 0.02, "z": 0.0},
            {"x": 0.6, "y": 0.0, "z": 0.0},
            {"x": 0.4, "y": -0.02, "z": 0.0},
            {"x": 0.2, "y": -0.02, "z": 0.0},
        ],
    }


# ── REST Endpoint Tests ─────────────────────────────────────────────────────


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data


class TestLeaderboardEndpoint:
    @pytest.mark.asyncio
    async def test_leaderboard_returns_200(self):
        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/leaderboard")
            assert response.status_code == 200
            data = response.json()
            assert "entries" in data
            assert "total_players" in data

    @pytest.mark.asyncio
    async def test_leaderboard_with_data(self, mock_redis):
        """Test leaderboard returns data after scores are submitted."""
        await leaderboard.submit_score("user-1", "TestPlayer", 5000)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/leaderboard")
            assert response.status_code == 200
            data = response.json()
            assert len(data["entries"]) == 1
            assert data["entries"][0]["username"] == "TestPlayer"
            assert data["entries"][0]["duration_ms"] == 5000


# ── WebSocket Flow Test ──────────────────────────────────────────────────────


class TestWebSocketFlow:
    def test_full_game_session_blink_detected(self):
        """
        Simulate a complete game session with mocked DB:
        1. Connect
        2. Send START_GAME → receive SESSION_READY
        3. Receive 3x COUNTDOWN
        4. Receive GAME_ACTIVE
        5. Send open-eye frames
        6. Send closed-eye frames → receive GAME_OVER
        """
        from unittest.mock import MagicMock

        # Create a mock user and session for the DB layer
        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.username = "TestPlayer"
        mock_user.best_time_ms = 0
        mock_user.total_sessions = 0

        mock_session = MagicMock()
        mock_session.id = uuid.uuid4()

        # Mock the async session factory
        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.add = MagicMock()
        mock_db_session.flush = AsyncMock()
        mock_db_session.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, 'id', mock_session.id))
        mock_db_session.commit = AsyncMock()
        mock_db_session.close = AsyncMock()

        # Create an async context manager mock
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=False)

        with patch("app.websocket_manager.async_session_factory", return_value=mock_context):
            from app.main import app
            from fastapi.testclient import TestClient

            client = TestClient(app)
            client_id = str(uuid.uuid4())
            user_id = str(mock_user.id)

            with client.websocket_connect(f"/ws/staring-contest/{client_id}") as ws:
                # 1. START_GAME
                ws.send_json({
                    "type": "START_GAME",
                    "user_id": user_id,
                    "username": "TestPlayer",
                })

                # 2. SESSION_READY
                msg = ws.receive_json()
                assert msg["type"] == "SESSION_READY"
                assert "session_id" in msg

                # 3. COUNTDOWN (3, 2, 1)
                for expected_count in (3, 2, 1):
                    msg = ws.receive_json()
                    assert msg["type"] == "COUNTDOWN"
                    assert msg["count"] == expected_count

                # 4. GAME_ACTIVE
                msg = ws.receive_json()
                assert msg["type"] == "GAME_ACTIVE"

                # 5. Send a few open-eye frames
                for i in range(5):
                    ws.send_json({
                        "type": "FRAME",
                        "timestamp": 1700000000000 + i * 33,
                        "landmarks": _open_eye_landmarks(),
                    })

                # Receive EAR updates (sent every 3rd frame)
                msg = ws.receive_json()
                assert msg["type"] == "EAR_UPDATE"
                assert msg["ear"] > 0.20

                # 6. Send closed-eye frames to trigger blink
                for i in range(3):
                    ws.send_json({
                        "type": "FRAME",
                        "timestamp": 1700000000200 + i * 33,
                        "landmarks": _closed_eye_landmarks(),
                    })

                # Should receive GAME_OVER
                # Consume any pending EAR_UPDATE messages first
                game_over_received = False
                for _ in range(10):
                    msg = ws.receive_json()
                    if msg["type"] == "GAME_OVER":
                        game_over_received = True
                        assert msg["reason"] == "blink_detected"
                        assert msg["duration_ms"] >= 0
                        break

                assert game_over_received, "Expected GAME_OVER message"
