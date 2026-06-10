# 🌊 Flood Response Coordinator

**7-agent autonomous flood response system for Lakhimpur, Assam**

Built for a 2-day hackathon. This system coordinates rescue, medical, logistics, and survivor communication during floods using AI agents that talk to each other, resolve conflicts, and push live updates to a dashboard.

---

## What We're Building

A multi-agent system where **7 AI agents** work together autonomously during a flood:

```
                    ┌─────────────┐
                    │  Perception │──── reads rainfall / water levels
                    └──────┬──────┘
                           │ alert_queue
                    ┌──────▼──────┐
                    │  Prediction │──── forecasts flood severity
                    └──────┬──────┘
                           │ broadcast: flood_alert
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────▼──────┐  ┌─────▼──────┐  ┌──────▼──────┐
   │   Rescue    │  │  Medical   │  │  Logistics  │
   │   Agent     │  │  Agent     │  │  Agent      │
   └──────┬──────┘  └─────┬──────┘  └──────┬──────┘
          │               │                │
          └───────┬───────┘                │
                  │ conflict_queue         │
          ┌───────▼────────┐               │
          │   Conflict     │◄──────────────┘
          │   Resolution   │──── runs priority auction
          └───────┬────────┘
                  │ resolved_queue + broadcast
          ┌───────▼────────┐
          │   Community    │──── sends SMS to survivors
          │   Liaison      │
          └────────────────┘
```

**The differentiator:** When two agents fight over the same helicopter, our Conflict Resolution Agent runs a priority auction using a weighted formula (lives at risk, urgency, irreversibility, distance) and picks the winner — with a fallback plan for the loser. Every decision is logged and explainable.

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | **FastAPI** + Uvicorn | Async-native, auto-generates API docs |
| Database | **SQLite** via SQLAlchemy | Single file, works offline, zero setup |
| Agent Framework | **LangGraph** + Gemini 1.5 Pro | ReAct agents with tool use |
| Agent Communication | **asyncio queues** | No Redis needed, no external deps |
| Live Updates | **FastAPI WebSocket** | Real-time dashboard push |
| SMS | **Twilio** | Survivor communication |
| Distance Calc | **Haversine** function | No PostGIS needed |
| Frontend | **React** + Mapbox GL | Map-based dashboard (separate) |

**No Docker. No containers. Everything runs directly.**

---

## Quick Start

```powershell
# 1. Clone and install
git clone <repo-url>
cd Flood-Response-Coordinator
pip install -r requirements.txt

# 2. Set up environment
copy .env.example .env
# Edit .env with your API keys (or leave OFFLINE_MODE=true for now)

# 3. Seed the database
python -m backend.seed
# → "Seeded Lakhimpur district data successfully"

# 4. Start the server
python -m uvicorn backend.main:app --reload --port 8000

# 5. Verify
# Open http://localhost:8000/docs        → Swagger UI with all endpoints
# Open http://localhost:8000/api/resources → 5 seeded resources as JSON
# Open http://localhost:8000/api/shelters  → 2 seeded shelters as JSON
```

**Postman:** Import `postman_collection.json` — all endpoints are pre-configured and ready to test.

---

## Team Assignments

| Member | Agent(s) | File(s) | Start Here |
|--------|----------|---------|------------|
| **Member 1** | Perception + Prediction | `backend/agents/perception.py`, `backend/agents/prediction.py` | Read `mock_rainfall.json` for input data format, implement rational model call |
| **Member 2** | Logistics | `backend/agents/logistics.py` | Query `resources` and `shelters` tables, implement pre-positioning logic |
| **Member 3** | Rescue + Medical | `backend/agents/rescue.py`, `backend/agents/medical.py` | Read from `sos_queue`, find nearest resource with `haversine()` |
| **Nidhi** | Conflict Resolution + Foundation | `backend/agents/conflict.py` | LangGraph + Gemini agent with priority auction |
| **Member 5** | Community Liaison + Frontend | `backend/agents/liaison.py`, `frontend/` | Read from `dispatch_queue`, send SMS via Twilio |

**Every stub file already has:** owner label, queue subscriptions, broadcast events, and a numbered TODO checklist. Open your file and start at TODO #1.

---

## What's Already Built (Foundation)

You don't need to build any of this — it's done and working:

- ✅ **Database** — 6 tables: `resources`, `shelters`, `sos_events`, `missions`, `flood_alerts`, `audit_log`
- ✅ **Seed Data** — 5 resources (H1 helicopter, B1/B2 boats, T1 truck, MT1 medical team) + 2 shelters in Lakhimpur
- ✅ **6 Async Queues** — `alert_queue`, `sos_queue`, `dispatch_queue`, `resource_update_queue`, `conflict_queue`, `resolved_queue`
- ✅ **WebSocket Broadcast** — 8 event types ready for the frontend
- ✅ **REST API** — 7 endpoints for dashboard data + Twilio webhook
- ✅ **Utility Functions** — `haversine()`, `rational_model()`, `priority_score()`
- ✅ **Offline Mode** — `OFFLINE_MODE=true` reads mock data, skips Twilio

---

## Project Structure

```
Flood-Response-Coordinator/
├── .env.example              ← copy to .env, fill in keys
├── requirements.txt          ← pip install -r requirements.txt
├── MESSAGE_FORMATS.md        ← JSON schema for every queue message
├── postman_collection.json   ← import into Postman for instant API testing
│
├── backend/
│   ├── database.py           ← SQLite engine + session setup
│   ├── models.py             ← 6 ORM tables
│   ├── queues.py             ← 6 asyncio queues (read the comments!)
│   ├── broadcast.py          ← WebSocket broadcast + event constants
│   ├── utils.py              ← haversine, rational_model, priority_score
│   ├── seed.py               ← pre-populates Lakhimpur data
│   ├── main.py               ← FastAPI app, all endpoints, agent startup
│   ├── mock_rainfall.json    ← real 2012 Lakhimpur flood numbers
│   │
│   └── agents/
│       ├── conflict.py       ← Conflict Resolution (Nidhi)
│       ├── perception.py     ← Perception (Member 1)
│       ├── prediction.py     ← Prediction (Member 1)
│       ├── logistics.py      ← Logistics (Member 2)
│       ├── rescue.py         ← Rescue (Member 3)
│       ├── medical.py        ← Medical (Member 3)
│       └── liaison.py        ← Community Liaison (Member 5)
│
└── frontend/                 ← React + Mapbox (Member 5)
```

---

## Key Files to Read First

1. **Your agent stub file** — has your TODO list
2. **[MESSAGE_FORMATS.md](MESSAGE_FORMATS.md)** — exact JSON format for every queue message
3. **[backend/queues.py](backend/queues.py)** — which queues you read from / write to
4. **[backend/broadcast.py](backend/broadcast.py)** — which WebSocket events you fire
5. **[backend/utils.py](backend/utils.py)** — haversine, rational model, priority score functions

---

## How Agents Communicate

Agents talk through **asyncio queues** (not HTTP, not Redis). Each agent runs as an async background task.

```python
# Example: Reading from a queue in your agent
from backend.queues import sos_queue

async def run():
    while True:
        message = await sos_queue.get()  # blocks until message arrives
        # process message...
```

```python
# Example: Broadcasting to the dashboard
from backend.broadcast import broadcast, EVENT_DISPATCH_ASSIGNED

await broadcast(EVENT_DISPATCH_ASSIGNED, {
    "mission_id": 1,
    "sos_id": 3,
    "resource_name": "B1",
})
```

```python
# Example: Writing to the database
from backend.database import SessionLocal
from backend.models import Resource

db = SessionLocal()
resource = db.query(Resource).filter(Resource.name == "B1").first()
resource.status = "dispatched"
db.commit()
db.close()
```

---

## Offline Mode

Set `OFFLINE_MODE=true` in `.env` (this is the default). When active:
- **Perception Agent** reads from `mock_rainfall.json` instead of calling Open-Meteo API
- **Community Liaison** prints SMS to console instead of sending via Twilio
- Everything else works identically

This is our safety net if the demo venue WiFi goes down.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/resources` | All resources with GPS + inventory |
| `GET` | `/api/shelters` | All shelters with capacity + stocks |
| `GET` | `/api/alerts` | Flood alerts, newest first |
| `GET` | `/api/sos` | All SOS events |
| `GET` | `/api/audit-log` | All agent decisions, newest first |
| `POST` | `/api/twilio/inbound` | Twilio SMS webhook (form data: `From`, `Body`) |
| `WS` | `/ws` | WebSocket for live dashboard updates |

Full interactive docs at **http://localhost:8000/docs** when server is running.

---

## Seed Data (Lakhimpur District)

**Resources:**
| Name | Type | Position |
|------|------|----------|
| H1 | Helicopter | 27.235, 94.105 |
| B1 | Boat | 27.228, 94.098 |
| B2 | Boat | 27.240, 94.112 |
| T1 | Supply Truck | 27.220, 94.090 |
| MT1 | Medical Team | 27.230, 94.100 |

**Shelters:**
| Name | Capacity | Stocks |
|------|----------|--------|
| Gogamukh Community Hall | 340 | Food: 500, Water: 3000L, Medicine: 100 |
| Sisiborgaon School | 180 | Food: 250, Water: 1500L, Medicine: 50 |

---

## Ground Rules

- **Never commit `.env`** — it's in `.gitignore`
- **Don't modify foundation files** (`database.py`, `models.py`, `queues.py`, `main.py`) without checking with Nidhi first
- **Always use the queue message formats** documented in `MESSAGE_FORMATS.md`
- **Always broadcast** relevant events so the dashboard stays live
- **Log decisions** to `audit_log` table for the demo narrative
