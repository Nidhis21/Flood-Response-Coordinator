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
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate

from backend.database import engine, get_db, Base
from backend.models import Resource, Shelter, SOSEvent, FloodAlert, AuditLog, SMSLog, RegisteredCitizen, Donation
from backend.broadcast import connected_clients, broadcast, EVENT_SOS_CREATED
from backend.queues import sos_queue
from backend.queues import sos_queue
from backend.seed import seed
from backend.agents.orchestrator import orchestrator

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

    # Start all agents as background tasks via Orchestrator
    agent_tasks = orchestrator.start_all_agents()
    diagnostic_task = asyncio.create_task(orchestrator.run_diagnostics(), name="orchestrator_diagnostics")
    logger.info(f"Started {len(agent_tasks)} agent background tasks")

    yield

    # Shutdown: cancel all agent tasks
    await orchestrator.stop_all_agents()
    diagnostic_task.cancel()
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
            "address": s.address,
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

class ShelterCreate(BaseModel):
    name: str
    address: str
    capacity: int
    current_occupancy: int = 0
    lat: float
    lng: float

@app.post("/api/shelters")
async def create_shelter(shelter_data: ShelterCreate, db: Session = Depends(get_db)):
    """Create a new shelter, broadcast it, and send a mass SMS."""
    new_shelter = Shelter(
        name=shelter_data.name,
        address=shelter_data.address,
        capacity=shelter_data.capacity,
        lat=shelter_data.lat,
        lng=shelter_data.lng,
        current_occupancy=shelter_data.current_occupancy,
        food_stock=500,
        water_stock=3000,
        medicine_stock=100,
        status="open"
    )
    db.add(new_shelter)
    db.commit()
    db.refresh(new_shelter)

    shelter_dict = {
        "id": new_shelter.id,
        "name": new_shelter.name,
        "address": new_shelter.address,
        "lat": new_shelter.lat,
        "lng": new_shelter.lng,
        "capacity": new_shelter.capacity,
        "current_occupancy": new_shelter.current_occupancy,
        "food_stock": new_shelter.food_stock,
        "water_stock": new_shelter.water_stock,
        "medicine_stock": new_shelter.medicine_stock,
        "status": new_shelter.status,
    }

    # Broadcast new shelter to UI
    await broadcast("shelter_updated", shelter_dict)

    # Prepare list of all shelters for the broadcast
    all_shelters = db.query(Shelter).all()
    lines = ["EOC ALERT: New emergency shelter opened!\nCurrent Shelter Availability:"]
    for s in all_shelters:
        pct = int((s.current_occupancy / s.capacity) * 100) if s.capacity > 0 else 0
        lines.append(f"- {s.name} ({s.address}) - {pct}% Full")
    
    broadcast_msg = "\n".join(lines)

    # Save to SMS Log
    log_entry = SMSLog(
        phone="ALL_CITIZENS",
        direction="outbound",
        message=broadcast_msg,
        sms_type="broadcast",
        delivery_status="sent",
        related_sos_id=None,
        agent_name="liaison"
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    # Push SMS to Liaison console
    await broadcast("sms_sent", {
        "id": str(log_entry.id),
        "phone": log_entry.phone,
        "body": log_entry.message,
        "direction": log_entry.direction,
        "timestamp": log_entry.created_at.isoformat() if log_entry.created_at else datetime.now(timezone.utc).isoformat(),
        "classification": "Shelter Request",
        "confidence": 1.0,
        "status": log_entry.delivery_status,
        "sos_id": log_entry.related_sos_id,
    })

    return shelter_dict



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
            "disaster_phase": a.disaster_phase,
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


@app.get("/api/volunteers")
def get_volunteers(db: Session = Depends(get_db)):
    """Return all registered citizens / volunteers."""
    volunteers = db.query(RegisteredCitizen).order_by(RegisteredCitizen.created_at.desc()).all()
    return [
        {
            "id": v.id,
            "name": v.name,
            "phone": v.phone,
            "role": v.role,
            "district": v.district,
            "status": v.status,
            "resource_type": v.resource_type,
            "resource_description": v.resource_description,
            "created_at": str(v.created_at),
        }
        for v in volunteers
    ]


@app.get("/api/donations")
def get_donations(db: Session = Depends(get_db)):
    """Return all donations."""
    donations = db.query(Donation).order_by(Donation.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "donor_phone": d.donor_phone,
            "donor_name": d.donor_name,
            "donation_type": d.donation_type,
            "quantity": d.quantity,
            "description": d.description,
            "status": d.status,
            "assigned_truck_id": d.assigned_truck_id,
            "pickup_lat": d.pickup_lat,
            "pickup_lng": d.pickup_lng,
            "created_at": str(d.created_at),
        }
        for d in donations
    ]

class DonationCreate(BaseModel):
    donor_name: str
    donor_phone: str
    donation_type: str
    quantity: int
    description: str
    pickup_lat: float
    pickup_lng: float

@app.post("/api/donations")
def create_donation(donation: DonationCreate, db: Session = Depends(get_db)):
    """Create manual donation and assign truck."""
    new_d = Donation(
        donor_phone=donation.donor_phone,
        donor_name=donation.donor_name,
        donation_type=donation.donation_type,
        quantity=donation.quantity,
        description=donation.description,
        pickup_lat=donation.pickup_lat,
        pickup_lng=donation.pickup_lng,
        status="confirmed"
    )
    
    # Auto assign truck
    truck = db.query(Resource).filter(Resource.type == "truck", Resource.status == "available").first()
    if truck:
        new_d.assigned_truck_id = truck.id
        new_d.status = "collected"
        truck.status = "dispatched"
    
    db.add(new_d)
    db.commit()
    db.refresh(new_d)
    
    # Notify donor
    if truck:
        from backend.queues import dispatch_queue
        import asyncio
        asyncio.create_task(dispatch_queue.put({
            "phone": new_d.donor_phone,
            "message_template": f"Confirmed! Truck {truck.name} is assigned to pick up your {new_d.quantity} {new_d.donation_type}.",
            "resource_type": "Truck",
            "resource_name": truck.name,
            "eta_minutes": 15,
            "sos_id": None
        }))
    
    return {
        "id": new_d.id,
        "donor_phone": new_d.donor_phone,
        "donor_name": new_d.donor_name,
        "donation_type": new_d.donation_type,
        "quantity": new_d.quantity,
        "description": new_d.description,
        "status": new_d.status,
        "assigned_truck_id": new_d.assigned_truck_id,
        "pickup_lat": new_d.pickup_lat,
        "pickup_lng": new_d.pickup_lng,
        "created_at": str(new_d.created_at),
    }


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
        if len(parts) < 2:
            raise ValueError("Not enough parts")
        lat = float(parts[0].strip())
        lng = float(parts[1].strip())
        people_count = int(parts[2].strip()) if len(parts) > 2 else 1
        injury = parts[3].strip() if len(parts) > 3 else ""
        classification = "SOS Rescue" if "blood" not in injury.lower() and "sick" not in injury.lower() else "SOS Medical"
    except (ValueError, IndexError):
        try:
            class SMSParseResult(BaseModel):
                lat: float = Field(description="Latitude, default to 27.23 if unknown")
                lng: float = Field(description="Longitude, default to 94.10 if unknown")
                people_count: int = Field(description="Number of people affected, default 1")
                injury: str = Field(description="Description of emergency, donation details, or injury")
                classification: str = Field(description="One of: SOS Rescue, SOS Medical, Shelter Request, Supply Request, Blockage Report, Water Level, Donation Offer")
            
            llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
            parser = PydanticOutputParser(pydantic_object=SMSParseResult)
            prompt = PromptTemplate(
                template="Parse the following flood emergency SMS.\n{format_instructions}\nSMS: {sms}",
                input_variables=["sms"],
                partial_variables={"format_instructions": parser.get_format_instructions()},
            )
            chain = prompt | llm | parser
            parsed = await chain.ainvoke({"sms": Body})
            lat = parsed.lat
            lng = parsed.lng
            people_count = parsed.people_count
            injury = parsed.injury
            classification = parsed.classification
            logger.info(f"Gemini parsed free-text SMS: {classification} with {people_count} people")
        except Exception as e:
            logger.error(f"NLP fallback failed: {e}")
            classification = "general"
            if "donate" in Body.lower() or "donation" in Body.lower():
                classification = "Donation Offer"
            else:
                # Check if there is a pending donation for this number
                pending = db.query(Donation).filter(
                    Donation.donor_phone == From, 
                    Donation.status.in_(["offered", "pending_details"])
                ).first()
                if pending:
                    classification = "Donation Offer"
            
            lat, lng, people_count, injury = 27.23, 94.10, 1, Body

    # Multi-turn Donation Logic
    if classification == "Donation Offer":
        from backend.queues import dispatch_queue
        
        existing_donation = db.query(Donation).filter(
            Donation.donor_phone == From, 
            Donation.status.in_(["offered", "pending_details"])
        ).first()
        
        if not existing_donation:
            # First turn: create pending donation
            new_d = Donation(
                donor_phone=From,
                donor_name="Unknown SMS Donor",
                donation_type="supplies",
                quantity=1,
                description=injury if injury else Body,
                status="pending_details"
            )
            db.add(new_d)
            db.commit()
            
            await dispatch_queue.put({
                "phone": From,
                "message_template": "Thank you for your offer! Community Liaison Agent 7 here. What exactly are you donating (item and quantity), and what is your location?",
                "resource_type": "Liaison",
                "resource_name": "Agent 7",
                "eta_minutes": 0,
                "sos_id": None
            })
            return {"status": "donation_pending", "classification": classification}
        else:
            # Second turn: update donation with details and assign truck
            existing_donation.description = f"{existing_donation.description} | Update: {Body}"
            existing_donation.pickup_lat = lat
            existing_donation.pickup_lng = lng
            
            truck = db.query(Resource).filter(Resource.type == "truck", Resource.status == "available").first()
            if truck:
                existing_donation.assigned_truck_id = truck.id
                existing_donation.status = "collected"
                truck.status = "dispatched"
                msg = f"Confirmed! Truck {truck.name} is assigned for pickup at your location."
            else:
                existing_donation.status = "confirmed"
                msg = "Confirmed! We have logged your donation but all trucks are currently busy. We will contact you soon."
                
            db.commit()
            
            await dispatch_queue.put({
                "phone": From,
                "message_template": msg,
                "resource_type": "Truck",
                "resource_name": truck.name if truck else "Pending",
                "eta_minutes": 15,
                "sos_id": None
            })
            return {"status": "donation_confirmed", "classification": classification}

    # Create SOS event in DB
    sos = SOSEvent(
        phone=From,
        lat=lat,
        lng=lng,
        district="Lakhimpur",
        people_count=people_count,
        injury_description=injury,
        triage_level=3,  # Default; Medical Agent will re-triage
        sms_classification=classification,
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
        "sms_classification": classification,
        "type": "medical" if classification == "SOS Medical" else "rescue" if classification == "SOS Rescue" else "general"
    })

    # Broadcast to dashboard
    await broadcast(EVENT_SOS_CREATED, {
        "sos_id": sos.id,
        "phone": From,
        "lat": lat,
        "lng": lng,
        "district": sos.district,
        "people_count": people_count,
        "triage_level": sos.triage_level,
    })

    logger.info(f"SOS #{sos.id} created from {From}")

    # Twilio expects TwiML response, but we return JSON for the simulator
    return {"status": "received", "sos_id": sos.id, "classification": classification}


class OutboundSMSRequest(BaseModel):
    phone: str
    message: str

@app.post("/api/twilio/outbound")
async def twilio_outbound(req: OutboundSMSRequest):
    """
    Manual outbound SMS from the frontend dashboard.
    Pushes to dispatch_queue to be sent by Liaison Agent.
    """
    from backend.queues import dispatch_queue
    await dispatch_queue.put({
        "phone": req.phone,
        "message_template": req.message,
        "resource_type": "Operator",
        "resource_name": "EOC Manual Response",
        "eta_minutes": 0,
        "sos_id": -1,
    })
    return {"status": "queued"}

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
