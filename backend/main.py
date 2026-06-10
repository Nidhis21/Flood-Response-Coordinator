"""
main.py — FastAPI application for the Flood Response Coordinator.

Endpoints:
  GET  /api/resources     — all resources from DB
  GET  /api/shelters      — all shelters from DB
  GET  /api/alerts        — flood alerts, newest first
  GET  /api/sos           — all SOS events
  GET  /api/audit-log     — audit log entries, newest first
  POST /api/twilio/inbound — Twilio SMS webhook
  WS   /ws                — WebSocket for live dashboard

On startup:
  - Creates all DB tables
  - Runs seed if DB is empty
  - Starts all 7 agents as background asyncio tasks
"""

import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from backend.database import engine, get_db, Base
from backend.models import Resource, Shelter, SOSEvent, FloodAlert, AuditLog
from backend.broadcast import connected_clients, broadcast, EVENT_SOS_CREATED
from backend.queues import sos_queue
from backend.seed import seed

# Agent imports (all stubs for now)
from backend.agents import perception, prediction, logistics, rescue, medical, liaison, conflict

load_dotenv()
logger = logging.getLogger("main")

OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"


# ── Lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables, seed data, launch agent tasks."""
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Seed if empty
    seed()

    # Start all agents as background tasks
    agent_tasks = [
        asyncio.create_task(perception.run(), name="perception_agent"),
        asyncio.create_task(prediction.run(), name="prediction_agent"),
        asyncio.create_task(logistics.run(), name="logistics_agent"),
        asyncio.create_task(rescue.run(), name="rescue_agent"),
        asyncio.create_task(medical.run(), name="medical_agent"),
        asyncio.create_task(liaison.run(), name="liaison_agent"),
        asyncio.create_task(conflict.run(), name="conflict_agent"),
    ]
    logger.info(f"Started {len(agent_tasks)} agent background tasks")

    yield

    # Shutdown: cancel all agent tasks
    for task in agent_tasks:
        task.cancel()
    await asyncio.gather(*agent_tasks, return_exceptions=True)
    logger.info("All agent tasks cancelled")


# ── App ───────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Flood Response Coordinator",
    description="7-agent autonomous flood response system for Lakhimpur, Assam",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ────────────────────────────────────────────────────────


@app.get("/api/resources")
def get_resources(db: Session = Depends(get_db)):
    """Return all resources from DB."""
    resources = db.query(Resource).all()
    return [
        {
            "id": r.id,
            "type": r.type,
            "name": r.name,
            "lat": r.lat,
            "lng": r.lng,
            "status": r.status,
            "inventory": json.loads(r.inventory) if r.inventory else {},
        }
        for r in resources
    ]


@app.get("/api/shelters")
def get_shelters(db: Session = Depends(get_db)):
    """Return all shelters from DB."""
    shelters = db.query(Shelter).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "lat": s.lat,
            "lng": s.lng,
            "capacity": s.capacity,
            "current_occupancy": s.current_occupancy,
            "food_stock": s.food_stock,
            "water_stock": s.water_stock,
            "medicine_stock": s.medicine_stock,
            "status": s.status,
        }
        for s in shelters
    ]


@app.get("/api/alerts")
def get_alerts(db: Session = Depends(get_db)):
    """Return flood alerts, newest first."""
    alerts = db.query(FloodAlert).order_by(FloodAlert.created_at.desc()).all()
    return [
        {
            "id": a.id,
            "district": a.district,
            "severity": a.severity,
            "discharge_q": a.discharge_q,
            "estimated_flood_time": str(a.estimated_flood_time) if a.estimated_flood_time else None,
            "affected_circles": json.loads(a.affected_circles) if a.affected_circles else [],
            "fhi_score": a.fhi_score,
            "created_at": str(a.created_at),
        }
        for a in alerts
    ]


@app.get("/api/sos")
def get_sos_events(db: Session = Depends(get_db)):
    """Return all SOS events."""
    events = db.query(SOSEvent).order_by(SOSEvent.created_at.desc()).all()
    return [
        {
            "id": e.id,
            "phone": e.phone,
            "lat": e.lat,
            "lng": e.lng,
            "district": e.district,
            "people_count": e.people_count,
            "injury_description": e.injury_description,
            "triage_level": e.triage_level,
            "status": e.status,
            "assigned_resource_id": e.assigned_resource_id,
            "created_at": str(e.created_at),
        }
        for e in events
    ]


@app.get("/api/audit-log")
def get_audit_log(db: Session = Depends(get_db)):
    """Return all audit log entries, newest first."""
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).all()
    return [
        {
            "id": l.id,
            "event_type": l.event_type,
            "agent_name": l.agent_name,
            "request_a": json.loads(l.request_a) if l.request_a else {},
            "request_b": json.loads(l.request_b) if l.request_b else {},
            "score_a": l.score_a,
            "score_b": l.score_b,
            "winner": l.winner,
            "fallback_assigned": l.fallback_assigned,
            "explanation": l.explanation,
            "created_at": str(l.created_at),
        }
        for l in logs
    ]


# ── Twilio Inbound SMS Webhook ────────────────────────────────────────────


@app.post("/api/twilio/inbound")
async def twilio_inbound(
    From: str = Form(...),
    Body: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Twilio webhook — receives inbound SMS from flood-affected people.

    Expected SMS format (simple): "<lat>,<lng>,<people_count>,<injury_info>"
    Example: "27.23,94.10,5,injured elderly person"

    In OFFLINE_MODE, Twilio verification is skipped.
    """
    try:
        parts = Body.strip().split(",", 3)
        lat = float(parts[0].strip())
        lng = float(parts[1].strip())
        people_count = int(parts[2].strip()) if len(parts) > 2 else 1
        injury = parts[3].strip() if len(parts) > 3 else ""
    except (ValueError, IndexError):
        # Default to Lakhimpur center if parsing fails
        lat, lng, people_count, injury = 27.23, 94.10, 1, Body

    # Create SOS event in DB
    sos = SOSEvent(
        phone=From,
        lat=lat,
        lng=lng,
        district="Lakhimpur",
        people_count=people_count,
        injury_description=injury,
        triage_level=3,  # Default; Medical Agent will re-triage
        status="pending",
    )
    db.add(sos)
    db.commit()
    db.refresh(sos)

    # Push to SOS queue for Rescue & Medical agents
    await sos_queue.put({
        "sos_id": sos.id,
        "phone": From,
        "lat": lat,
        "lng": lng,
        "people_count": people_count,
        "injury_description": injury,
        "triage_level": sos.triage_level,
    })

    # Broadcast to dashboard
    await broadcast(EVENT_SOS_CREATED, {
        "sos_id": sos.id,
        "phone": From,
        "lat": lat,
        "lng": lng,
        "people_count": people_count,
        "triage_level": sos.triage_level,
    })

    logger.info(f"SOS #{sos.id} created from {From}")

    # Twilio expects TwiML response
    return {"status": "received", "sos_id": sos.id}


# ── WebSocket ─────────────────────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.
    Frontend connects here and receives all broadcast events.
    """
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")

    try:
        while True:
            # Keep connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(connected_clients)}")
