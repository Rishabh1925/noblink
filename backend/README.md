# 👁️ The Global Staring Contest — Backend

A real-time multiplayer staring contest game where players compete to hold their eyes open the longest. The backend handles blink detection via **Eye Aspect Ratio (EAR)** analysis, anti-cheat validation, and a live global leaderboard.

## Architecture

```
┌─────────────────┐    WebSocket (30 FPS)     ┌──────────────────────┐
│   Browser        │ ──────────────────────── → │   FastAPI Server     │
│   (MediaPipe)    │ ← ─────────────────────── │                      │
│                  │    EAR updates / GAME_OVER │   ┌──────────────┐  │
└─────────────────┘                             │   │  ML Engine    │  │
                                                │   │  (EAR calc)   │  │
                                                │   └──────────────┘  │
                                                │   ┌──────────────┐  │
     ┌──────────────┐   REST (poll)             │   │  Anti-Cheat   │  │
     │  Leaderboard │ ← ────────────────────── │   └──────────────┘  │
     │  (Frontend)  │                           │                      │
     └──────────────┘                           │   ┌───────┐  ┌────┐ │
                                                │   │ Redis │  │ PG │ │
                                                │   └───────┘  └────┘ │
                                                └──────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + Uvicorn (async) |
| Blink Detection | Custom EAR algorithm on MediaPipe landmarks |
| Real-time | WebSockets |
| Leaderboard | Redis Sorted Sets |
| Database | PostgreSQL via Supabase |
| ORM | SQLAlchemy 2.0 (async) |

## Quick Start

### 1. Prerequisites

- **Python 3.11+**
- **Redis** — `brew install redis && redis-server` (or [Upstash](https://upstash.com) free tier)
- **Supabase** — Create a free project at [supabase.com](https://supabase.com)

### 2. Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase DATABASE_URL and Redis URL
```

### 3. Environment Variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Supabase PostgreSQL connection string | `postgresql+asyncpg://...localhost` |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` |
| `EAR_THRESHOLD` | Eye Aspect Ratio blink threshold | `0.21` |
| `EAR_CONSEC_FRAMES` | Consecutive low-EAR frames for blink | `2` |
| `CORS_ORIGINS` | Allowed frontend origins (comma-separated) | `http://localhost:3000,...` |
| `DEBUG` | Enable debug logging | `true` |

### 4. Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

- **Swagger UI**: http://localhost:8000/docs
- **Health check**: http://localhost:8000/api/health

### 5. Run Tests

```bash
python -m pytest tests/ -v
```

## API Reference

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check (DB + Redis status) |
| `POST` | `/api/users` | Register / get-or-create user |
| `GET` | `/api/users/{user_id}/stats` | User profile + session history |
| `GET` | `/api/leaderboard` | Top 100 longest stares today |
| `GET` | `/api/leaderboard/{user_id}/rank` | User's rank on today's board |

### WebSocket Endpoint

**URL**: `ws://localhost:8000/ws/staring-contest/{client_id}`

#### Session Flow

```
Client                          Server
  │                                │
  │──── connect ──────────────────→│
  │                                │
  │──── START_GAME ───────────────→│
  │←─── SESSION_READY ────────────│
  │←─── COUNTDOWN (3) ────────────│
  │←─── COUNTDOWN (2) ────────────│
  │←─── COUNTDOWN (1) ────────────│
  │←─── GAME_ACTIVE ──────────────│
  │                                │
  │──── FRAME (landmarks) ───────→│
  │←─── EAR_UPDATE ───────────────│
  │──── FRAME ────────────────────→│
  │──── FRAME ────────────────────→│
  │←─── EAR_UPDATE ───────────────│
  │     ... repeats at 30 FPS ...  │
  │                                │
  │←─── GAME_OVER ────────────────│  (blink detected!)
  │                                │
```

#### Client → Server Payloads

**START_GAME** (send once after connecting):
```json
{
  "type": "START_GAME",
  "user_id": "uuid-string",
  "username": "PlayerName"
}
```

**FRAME** (send at ~30 FPS during active game):
```json
{
  "type": "FRAME",
  "timestamp": 1709412345678,
  "landmarks": {
    "left_eye": [
      {"x": 0.52, "y": 0.34, "z": -0.02},
      {"x": 0.54, "y": 0.38, "z": -0.01},
      {"x": 0.58, "y": 0.38, "z": -0.01},
      {"x": 0.60, "y": 0.34, "z": -0.02},
      {"x": 0.58, "y": 0.30, "z": -0.01},
      {"x": 0.54, "y": 0.30, "z": -0.01}
    ],
    "right_eye": [
      {"x": 0.40, "y": 0.34, "z": -0.02},
      {"x": 0.42, "y": 0.38, "z": -0.01},
      {"x": 0.46, "y": 0.38, "z": -0.01},
      {"x": 0.48, "y": 0.34, "z": -0.02},
      {"x": 0.46, "y": 0.30, "z": -0.01},
      {"x": 0.42, "y": 0.30, "z": -0.01}
    ]
  }
}
```

**MediaPipe Face Mesh indices for the 6 eye landmarks:**
| Eye | p1 | p2 | p3 | p4 | p5 | p6 |
|---|---|---|---|---|---|---|
| Left | 362 | 385 | 387 | 263 | 373 | 380 |
| Right | 33 | 160 | 158 | 133 | 153 | 144 |

#### Server → Client Payloads

| Type | Fields | When |
|---|---|---|
| `SESSION_READY` | `session_id` | After START_GAME processed |
| `COUNTDOWN` | `count` (3→1) | Before game starts |
| `GAME_ACTIVE` | `started_at` (unix ms) | Game begins |
| `EAR_UPDATE` | `ear`, `elapsed_ms` | Every 3rd frame |
| `GAME_OVER` | `reason`, `duration_ms`, `final_ear` | Blink / cheat detected |
| `ERROR` | `detail` | On validation error |

**GAME_OVER reasons**: `blink_detected`, `cheating_detected`, `client_disconnect`, `server_error`

## Anti-Cheat System

The server validates every frame with these checks:

| Check | Failure Condition |
|---|---|
| **Landmark completeness** | Missing landmarks or x/y/z keys |
| **Coordinate range** | x/y values outside [-0.5, 1.5] |
| **EAR range** | EAR outside [0.05, 0.45] (physiologically impossible) |
| **Frame rate** | Below 10 FPS after initial frames (replay/tampering) |
| **Freeze detection** | Identical landmarks for 15+ frames (static image) |

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app + routes
│   ├── config.py               # Settings from .env
│   ├── ml_engine.py            # EAR calculation + BlinkDetector
│   ├── anti_cheat.py           # Frame validation + cheat detection
│   ├── websocket_manager.py    # WS session state machine
│   ├── leaderboard.py          # Redis sorted set operations
│   ├── database.py             # Async SQLAlchemy engine
│   ├── models.py               # User + GameSession ORM models
│   └── schemas.py              # Pydantic request/response models
├── tests/
│   ├── test_ml_engine.py       # EAR + blink detection tests
│   ├── test_leaderboard.py     # Redis leaderboard tests
│   └── test_websocket.py       # WebSocket integration tests
├── requirements.txt
├── .env.example
└── README.md
```
