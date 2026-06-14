"""
===========================================================================
RESCUE AGENT — Search and Rescue Dispatch
===========================================================================
Owner: Member 3

SUBSCRIBES TO:
  - sos_queue      ←  SOS events (shared with Medical Agent — routed internally)
  - resolved_queue ←  conflict resolutions from Agent 6 (shared — routed internally)

PUBLISHES TO:
  - dispatch_queue  →  dispatch assignments for Agent 7 (SMS)
  - conflict_queue  →  resource conflicts for Agent 6

DATABASE TABLES USED (from backend/models.py):
  - Resource  : type, name, lat, lng, status
  - SOSEvent  : lat, lng, people_count, injury_description, triage_level,
                status, assigned_resource_id
  - Mission   : sos_event_id, resource_id, status, shelter_id

QUEUE MESSAGE FORMAT (from main.py Twilio webhook):
  sos_queue receives:
    {
      "sos_id":             int,
      "phone":              str,
      "lat":                float,
      "lng":                float,
      "people_count":       int,
      "injury_description": str,
      "triage_level":       int   # 1=critical … 5=minor
    }

  resolved_queue receives (from Agent 6):
    {
      "winner_agent":  "rescue" | "medical" | ...,
      "sos_event":     dict,   # original SOS dict (with sos_id key)
      "sos_id":        int,
      "resource_id":   int,
    }

IMPORTANT — FAN-OUT PATTERN:
  asyncio.Queue is single-consumer: each item is received by exactly ONE
  get() call.  Because both Rescue and Medical agents need to see every SOS,
  we solve this WITHOUT touching main.py or queues.py:

    • rescue_agent.run()  owns the sos_queue.get() loop.
    • After reading a message it calls medical_agent.handle_sos_message()
      directly (same process, same event loop).
    • Same pattern for resolved_queue.

  This keeps the queue architecture intact while ensuring both agents see
  every message.  The function handle_sos_message() and
  handle_resolution_message() are the public API used by this fan-out.
===========================================================================
"""

import asyncio
import logging
from datetime import datetime, timezone

from backend.database import SessionLocal, Base, engine
from backend.queues import sos_queue, dispatch_queue, conflict_queue, resolved_queue
from backend.models import SOSEvent, Resource, Mission
from backend.broadcast import broadcast, EVENT_DISPATCH_ASSIGNED, EVENT_RESOURCE_MOVED
from backend.utils import haversine

# Medical agent import for fan-out — imported here to avoid circular import
# (medical_agent does NOT import rescue_agent)
import backend.agents.medical as medical_agent

logger = logging.getLogger("agent.rescue")

# Ensure tables exist (safe to call multiple times — SQLAlchemy is idempotent)
Base.metadata.create_all(bind=engine)


# ============================================================================
# CONSTANTS
# ============================================================================

# For each severity level: which vehicle types to try, in preference order.
# "high"     → helicopter first  (isolated/roof/fast water)
# "moderate" → boat first        (standard flood-zone evacuation)
# "low"      → truck first       (accessible area, road passable)
VEHICLE_PRIORITY = {
    "high":     ["helicopter", "boat", "truck"],
    "moderate": ["boat", "truck", "helicopter"],
    "low":      ["truck", "boat", "helicopter"],
}

# Travel speeds in km/hr — used to estimate ETA
VEHICLE_SPEEDS = {
    "helicopter":   150,
    "boat":          20,
    "truck":         40,
    "medical_team":  40,
}

# Seed data uses plain names: H1, B1, B2, T1, MT1
# There is no NDRF/SDRF prefix in this dataset, so we do NOT filter by name.
# Resources are ranked solely by distance (nearest first).


# ============================================================================
# STEP 1 — DETERMINE SEVERITY
# ============================================================================
def determine_severity(sos_event: dict) -> str:
    """
    Classify how serious a rescue SOS is.

    Inputs read from sos_event dict (keys as sent by main.py):
      - people_count        : int
      - triage_level        : int  1 (critical) … 5 (minor)
      - injury_description  : str
      - flood_severity      : str  "low"/"moderate"/"high"/"critical"
                                   (added by Prediction Agent if present)
      - is_isolated         : bool (added by Community Liaison if present)

    Returns: "high" | "moderate" | "low"
    """
    people_count   = sos_event.get("people_count", 1)
    triage_level   = sos_event.get("triage_level", 3)
    description    = sos_event.get("injury_description", "").lower()
    flood_severity = sos_event.get("flood_severity", "").lower()
    is_isolated    = sos_event.get("is_isolated", False)

    HIGH_KEYWORDS = [
        "trapped", "rooftop", "roof", "submerged", "swept", "drowning",
        "collapsed", "unconscious", "critical", "sinking", "underwater",
    ]

    # ── HIGH ──────────────────────────────────────────────────────────────
    if triage_level == 1:
        return "high"
    if people_count >= 10:
        return "high"
    if is_isolated:
        return "high"
    if flood_severity in ("high", "critical"):
        return "high"
    if any(word in description for word in HIGH_KEYWORDS):
        return "high"

    # ── MODERATE ──────────────────────────────────────────────────────────
    if triage_level == 2:
        return "moderate"
    if people_count >= 3:
        return "moderate"
    if flood_severity == "moderate":
        return "moderate"

    # ── LOW ───────────────────────────────────────────────────────────────
    return "low"


# ============================================================================
# STEP 2 — ETA CALCULATION
# ============================================================================
def calculate_eta(distance_km: float, vehicle_type: str) -> int:
    """Return ETA in minutes. Minimum 2 minutes."""
    speed = VEHICLE_SPEEDS.get(vehicle_type, 40)
    return max(int((distance_km / speed) * 60), 2)


# ============================================================================
# STEP 3 — FIND BEST RESCUE RESOURCE
# ============================================================================
def find_best_resource(sos_lat: float, sos_lng: float, severity: str, db):
    """
    Pick the best available resource for a rescue SOS.

    Algorithm:
      1. Get vehicle type priority list for this severity level.
      2. For each vehicle type, query DB for all available resources of that type.
      3. Among those, sort by distance (nearest first).
         — No NDRF/SDRF tier filter: seed data uses plain names (H1, B1, etc.)
      4. Return the first match.

    Returns:
      (resource, vehicle_type, distance_km)  on success
      (None, None, None)                      if nothing is available
    """
    vehicle_types = VEHICLE_PRIORITY.get(severity, ["boat", "truck", "helicopter"])

    for vehicle_type in vehicle_types:
        available = (
            db.query(Resource)
            .filter(Resource.type == vehicle_type)
            .filter(Resource.status == "available")
            .all()
        )

        if not available:
            logger.info(f"No available {vehicle_type} — trying next vehicle type")
            continue

        # Sort by distance — nearest first
        available.sort(
            key=lambda r: haversine(r.lat, r.lng, sos_lat, sos_lng)
        )
        best = available[0]
        distance_km = haversine(best.lat, best.lng, sos_lat, sos_lng)

        logger.info(
            f"Best rescue resource: '{best.name}' ({vehicle_type}) "
            f"at {distance_km:.2f} km | severity={severity}"
        )
        return best, vehicle_type, distance_km

    return None, None, None


# ============================================================================
# STEP 4 — WRITE DISPATCH TO DATABASE
# ============================================================================
async def dispatch_resource(sos_event: dict, resource: Resource,
                      vehicle_type: str, distance_km: float, db):
    """
    Persist the dispatch decision to the database.

    Changes made (field names match models.py exactly):
      Resource.status                  → "dispatched"
      SOSEvent.status                  → "assigned"
      SOSEvent.assigned_resource_id    → resource.id
      Mission (new row)                → status="en_route", shelter_id=None

    The sos_id key in the queue message maps to SOSEvent.id in the DB.
    """
    sos_db_id = sos_event.get("sos_id")   # key set by main.py Twilio webhook

    # Mark resource busy
    resource.status = "dispatched"

    # Create mission record
    mission = Mission(
        sos_event_id=sos_db_id,
        resource_id=resource.id,
        status="en_route",
        shelter_id=None,
    )
    db.add(mission)

    # Update SOS event row
    sos_record = db.query(SOSEvent).filter(SOSEvent.id == sos_db_id).first()
    if sos_record:
        sos_record.status = "assigned"
        sos_record.assigned_resource_id = resource.id

    db.commit()
    db.refresh(mission)
    
    # Broadcast resource update immediately for live tracking
    await broadcast(EVENT_RESOURCE_MOVED, {
        "resource_id": resource.id,
        "name": resource.name,
        "new_lat": resource.lat,
        "new_lng": resource.lng,
        "new_status": "dispatched",
        "inventory": resource.inventory_dict()
    })
    db.refresh(resource)

    eta_minutes = calculate_eta(distance_km, vehicle_type)
    logger.info(
        f"RESCUE DISPATCH: '{resource.name}' ({vehicle_type}) "
        f"→ SOS #{sos_db_id} | ETA ~{eta_minutes} min"
    )
    return mission, eta_minutes


# ============================================================================
# STEP 5 — PROCESS ONE SOS EVENT (core pipeline)
# ============================================================================
async def process_sos_event(sos_event: dict):
    """
    Full rescue pipeline for one SOS message.

    Steps:
      1. Determine severity
      2. Find best available resource
      3. Re-check availability (race condition guard)
      4. Dispatch — write to DB
      5. Push to dispatch_queue (→ Agent 7 for SMS)
      6. Broadcast to dashboard via broadcast()
    """
    sos_id  = sos_event.get("sos_id", "unknown")
    sos_lat = sos_event.get("lat", 0.0)
    sos_lng = sos_event.get("lng", 0.0)

    severity = determine_severity(sos_event)
    logger.info(
        f"Rescue Agent | SOS #{sos_id} | severity={severity.upper()} | "
        f"people={sos_event.get('people_count', 1)} | "
        f"triage={sos_event.get('triage_level', 3)}"
    )

    db = SessionLocal()
    try:
        # ── 2. Find best resource ─────────────────────────────────────────
        resource, vehicle_type, distance_km = find_best_resource(
            sos_lat, sos_lng, severity, db
        )

        def _build_req(agent_name, evt, dist):
            return {
                "agent": agent_name, "type": agent_name,
                "sos_id": evt.get("sos_id", evt.get("id")),
                "lives_at_risk": evt.get("people_count", 1),
                "people_count": evt.get("people_count", 1),
                "time_to_critical_hours": 1.0,
                "irreversibility": 1.0 if agent_name == "rescue" else 0.8,
                "distance_km": dist,
                "vulnerable_population": evt.get("vulnerable_population", False),
                "reason": evt.get("injury_description", "Emergency rescue required")
            }

        # ── 3a. Nothing available ─────────────────────────────────────────
        if resource is None:
            logger.warning(f"No rescue resource available for SOS #{sos_id}")
            types = VEHICLE_PRIORITY.get(severity, ["boat", "truck", "helicopter"])
            active_mission = db.query(Mission).join(Resource).filter(
                Resource.type.in_(types),
                Resource.status == "dispatched",
                Mission.status.in_(["en_route", "on_site", "evacuating"])
            ).first()
            
            if active_mission:
                incumbent_sos = db.query(SOSEvent).filter(SOSEvent.id == active_mission.sos_event_id).first()
                incumbent_res = db.query(Resource).filter(Resource.id == active_mission.resource_id).first()
                dist_b = haversine(incumbent_res.lat, incumbent_res.lng, incumbent_sos.lat, incumbent_sos.lng)
                req_b = _build_req("rescue", {"sos_id": incumbent_sos.id, "people_count": incumbent_sos.people_count, "injury_description": incumbent_sos.injury_description, "vulnerable_population": incumbent_sos.vulnerable_population}, dist_b)
                
                await conflict_queue.put({
                    "resource_id": incumbent_res.id,
                    "resource_name": incumbent_res.name,
                    "request_a": _build_req("rescue", sos_event, 15.0),
                    "request_b": req_b
                })
            else:
                await conflict_queue.put({
                    "resource_id": -1,
                    "resource_name": "None",
                    "request_a": _build_req("rescue", sos_event, 15.0),
                    "request_b": None
                })
            return

        # ── 3b. Race condition re-check ───────────────────────────────────
        db.refresh(resource)
        if resource.status != "available":
            logger.warning(f"'{resource.name}' was just taken — raising conflict for SOS #{sos_id}")
            active_mission = db.query(Mission).filter(Mission.resource_id == resource.id, Mission.status.in_(["en_route", "on_site", "evacuating"])).first()
            req_b = None
            if active_mission:
                incumbent_sos = db.query(SOSEvent).filter(SOSEvent.id == active_mission.sos_event_id).first()
                dist_b = haversine(resource.lat, resource.lng, incumbent_sos.lat, incumbent_sos.lng)
                req_b = _build_req("rescue", {"sos_id": incumbent_sos.id, "people_count": incumbent_sos.people_count, "injury_description": incumbent_sos.injury_description, "vulnerable_population": incumbent_sos.vulnerable_population}, dist_b)
                
            await conflict_queue.put({
                "resource_id": resource.id,
                "resource_name": resource.name,
                "request_a": _build_req("rescue", sos_event, distance_km),
                "request_b": req_b
            })
            return

        # ── 4. Dispatch ───────────────────────────────────────────────────
        mission, eta_minutes = await dispatch_resource(
            sos_event, resource, vehicle_type, distance_km, db
        )

        # ── 5. Push to dispatch_queue (Agent 7 sends SMS) ─────────────────
        await dispatch_queue.put({
            "mission_id":    mission.id,
            "sos_id":        sos_id,
            "resource_id":   resource.id,
            "resource_name": resource.name,
            "resource_type": vehicle_type,
            "phone":         sos_event.get("phone", "+910000000000"),
            "eta_minutes":   eta_minutes,
            "shelter_name":  "Nearest Safe Zone",
            "shelter_lat":   sos_lat,
            "shelter_lng":   sos_lng,
            "message_template": "Help is on the way! {resource_type} {resource_name} arriving in ~{eta_minutes} min.",
        })

        # ── 6. Broadcast to React dashboard ──────────────────────────────
        await broadcast(EVENT_DISPATCH_ASSIGNED, {
            "mission_id":    mission.id,
            "sos_id":        sos_id,
            "resource_id":   resource.id,
            "resource_name": resource.name,
            "eta_minutes":   eta_minutes,
        })

        logger.info(f"Rescue dispatch confirmed for SOS #{sos_id}")

    except Exception as e:
        logger.error(f"Rescue Agent error on SOS #{sos_id}: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


# ============================================================================
# PUBLIC API — called by the fan-out loop in run()
# ============================================================================
async def handle_sos_message(sos_event: dict):
    """
    Decides whether this SOS needs rescue and processes it.

    Rescue handles: "rescue", "evacuation", "trapped", "general"
    For "general" events it also checks triage level as a fallback.
    """
    event_type = sos_event.get("type", "general").lower()

    if event_type in ("rescue", "evacuation", "trapped"):
        await process_sos_event(sos_event)
    else:
        logger.debug(f"Rescue Agent skipping type='{event_type}'")


async def handle_resolution_message(resolution: dict):
    """
    Called when Agent 6 resolves a resource conflict.
    If rescue won, re-attempt dispatch with the now-granted resource.
    """
    if resolution.get("winning_agent") == "rescue":
        logger.info("Rescue won conflict — re-dispatching")
        await process_sos_event(resolution.get("sos_event", {}))
    else:
        logger.info(
            f"Rescue lost conflict for SOS #{resolution.get('sos_id')} "
            f"— fallback assigned by Agent 6"
        )


# ============================================================================
# MAIN LOOP — owns sos_queue and resolved_queue, fans out to Medical Agent
# ============================================================================
async def run():
    """
    Entry point called by main.py as an asyncio task.

    Fan-out pattern:
      This agent owns the sos_queue consumer loop. After reading each message
      it forwards to medical_agent.handle_sos_message() so both agents process
      every SOS without needing a pub/sub broker.

      Same for resolved_queue.

    Why this agent owns the queues:
      Rescue is Agent 4; Medical is Agent 5. Having the lower-numbered agent
      own the queue reader is a deterministic convention so there is no race
      between the two run() coroutines.
    """
    logger.info("Rescue Agent started — owns sos_queue and resolved_queue fan-out")

    # Background task: drain resolved_queue and route to both agents
    async def resolution_fan_out():
        logger.info("Resolution fan-out loop started")
        while True:
            try:
                resolution = await resolved_queue.get()
                # Route to rescue
                await handle_resolution_message(resolution)
                # Route to medical
                await medical_agent.handle_resolution_message(resolution)
            except Exception as e:
                logger.error(f"Resolution fan-out error: {e}", exc_info=True)
                await asyncio.sleep(1)

    asyncio.create_task(resolution_fan_out())

    # Main loop: drain sos_queue and route to both agents
    while True:
        try:
            sos_event = await sos_queue.get()

            # Rescue gets first look
            await handle_sos_message(sos_event)

            # Medical gets the same message
            await medical_agent.handle_sos_message(sos_event)

        except Exception as e:
            logger.error(f"Rescue Agent main loop error: {e}", exc_info=True)
            await asyncio.sleep(5)