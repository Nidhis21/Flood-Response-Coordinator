import os
import json
import logging
import asyncio
from datetime import datetime, timezone

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.database import SessionLocal
from backend.models import AuditLog, Resource, Shelter, FloodAlert
from backend.queues import conflict_queue, dispatch_queue
from backend.broadcast import broadcast, EVENT_RESOURCE_MOVED
from backend.prompts import LOGISTICS_SYSTEM_PROMPT

logger = logging.getLogger("agent.logistics")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"


@tool
def move_resource(resource_id: int, lat: float, lng: float, reason: str) -> str:
    """Pre-position or move a truck/resource to a new location based on flood risk."""
    db = SessionLocal()
    try:
        r = db.query(Resource).filter(Resource.id == resource_id).first()
        if not r: 
            return f"Resource {resource_id} not found."
        r.lat = lat
        r.lng = lng
        db.commit()
        
        # We need to broadcast the move (we use asyncio.run in a sync tool or a sync wrapper, but since it's a sync tool calling an async func... wait. Tool is sync. We should use a background task or run loop. Actually, better yet: just make the tool async!)
        return f"Moved resource '{r.name}' to {lat}, {lng}. Reason: {reason}"
    finally:
        db.close()

@tool
async def load_inventory(resource_id: int, item: str, quantity: int) -> str:
    """Load tools or rations into a resource/vehicle's inventory."""
    db = SessionLocal()
    try:
        r = db.query(Resource).filter(Resource.id == resource_id).first()
        if not r: 
            return f"Resource {resource_id} not found."
        
        inv = r.inventory or {}
        inv[item] = inv.get(item, 0) + quantity
        # SQLAlchemy JSON fields need to be reassigned to detect changes sometimes
        r.inventory = dict(inv)
        db.commit()
        db.refresh(r)
        
        # Broadcast resource update immediately for live tracking
        await broadcast(EVENT_RESOURCE_MOVED, {
            "resource_id": r.id,
            "name": r.name,
            "new_lat": r.lat,
            "new_lng": r.lng,
            "new_status": r.status,
            "inventory": r.inventory_dict()
        })
        return f"Loaded {quantity} {item} into {r.name}. Current inventory: {r.inventory}"
    finally:
        db.close()


@tool
def update_shelter_status(shelter_id: int, status: str, reason: str) -> str:
    """Update shelter status (open, full, closed, watch, active)."""
    db = SessionLocal()
    try:
        s = db.query(Shelter).filter(Shelter.id == shelter_id).first()
        if not s: 
            return f"Shelter {shelter_id} not found."
        s.status = status
        db.commit()
        return f"Updated shelter '{s.name}' to {status}. Reason: {reason}"
    finally:
        db.close()


@tool
async def escalate_conflict(resource_id: int, request_a: dict, request_b: dict) -> str:
    """Escalate a resource conflict to the Conflict Resolution Agent when multiple districts or shelters need the same truck.
    Format for request_a/b: {"type": "logistics", "sos_id": 999, "lives_at_risk": 50, "time_to_critical_hours": 2, "irreversibility": 0.4, "distance_km": 20, "agent": "logistics"}
    """
    await conflict_queue.put({
        "resource_id": resource_id,
        "resource_name": "Logistics Requested Resource",
        "request_a": request_a,
        "request_b": request_b
    })
    return "Conflict escalated to priority auction."


@tool
async def send_logistics_sms(phone: str, message: str, role: str) -> str:
    """Send SMS to a truck driver or shelter manager."""
    await dispatch_queue.put({
        "mission_id": -1,
        "sos_id": -1,
        "resource_id": -1,
        "resource_name": role,
        "resource_type": "logistics_info",
        "phone": phone,
        "eta_minutes": 0,
        "shelter_name": "Logistics Update",
        "shelter_lat": 0.0,
        "shelter_lng": 0.0,
        "message_template": message
    })
    return f"SMS queued for delivery to {role} at {phone}."


@tool
def write_logistics_audit(explanation: str, action_taken: str) -> str:
    """Write your decision to the official audit log for transparency."""
    db = SessionLocal()
    try:
        log = AuditLog(
            event_type="logistics_decision",
            agent_name="logistics",
            explanation=explanation,
            fallback_assigned=action_taken
        )
        db.add(log)
        db.commit()
        return "Audit log written successfully."
    finally:
        db.close()


async def run():
    """Main loop for the Logistics Agent."""
    logger.info("Logistics Agent started")
    
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    if not GEMINI_API_KEY or GEMINI_API_KEY == "your-gemini-api-key-here":
        logger.warning("No GEMINI_API_KEY found. Logistics Agent running in offline mode.")
        agent = None
    else:
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)
        tools = [move_resource, update_shelter_status, escalate_conflict, send_logistics_sms, write_logistics_audit, load_inventory]
        agent = create_react_agent(llm, tools, state_modifier=LOGISTICS_SYSTEM_PROMPT)

    last_alert_id = 0

    while True:
        try:
            db = SessionLocal()
            try:
                # 1. Process new flood alerts for pre-positioning
                new_alerts = db.query(FloodAlert).filter(FloodAlert.id > last_alert_id).order_by(FloodAlert.id.asc()).all()
                for alert in new_alerts:
                    last_alert_id = alert.id
                    msg = (
                        f"NEW FLOOD ALERT: {alert.district} District.\n"
                        f"Severity: {alert.severity}\n"
                        f"FHI Score: {alert.fhi_score}\n"
                        f"Phase: {alert.disaster_phase}\n"
                        f"Please evaluate pre-positioning needs. Use move_resource to move trucks closer to {alert.district} if severity is moderate or high. "
                        f"Log your decision via write_logistics_audit."
                    )
                    
                    if agent:
                        logger.info(f"Invoking Logistics Agent for flood alert #{alert.id}")
                        await agent.ainvoke({"messages": [("user", msg)]})
                    else:
                        logger.info(f"Offline mode: Auto-prepositioning simulated for {alert.district}")

                # 2. Monitor shelters for overcapacity
                shelters = db.query(Shelter).all()
                for s in shelters:
                    if s.capacity > 0:
                        occ_pct = s.current_occupancy / s.capacity
                        if occ_pct >= 0.85 and s.status not in ["full", "active", "closed"]:
                            msg = (
                                f"SHELTER CAPACITY ALERT: {s.name} (ID: {s.id}) is at {int(occ_pct*100)}% capacity "
                                f"({s.current_occupancy}/{s.capacity}). Consider updating status to 'full' or 'active' and "
                                f"sending an SMS to the shelter manager (+910000000000)."
                            )
                            if agent:
                                logger.info(f"Invoking Logistics Agent for shelter #{s.id} capacity alert")
                                await agent.ainvoke({"messages": [("user", msg)]})
                                
            finally:
                db.close()
                
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error in Logistics Agent: {e}", exc_info=True)
            await asyncio.sleep(10)
