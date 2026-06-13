"""
===========================================================================
MEDICAL AGENT — Medical Triage and Dispatch
===========================================================================
Owner: Member 3

SUBSCRIBES TO (via fan-out from rescue_agent.run()):
  - sos_queue      ←  every SOS is forwarded here by rescue_agent.run()
  - resolved_queue ←  every resolution is forwarded here by rescue_agent.run()

PUBLISHES TO:
  - dispatch_queue  →  medical dispatch assignments for Agent 7 (SMS)
  - conflict_queue  →  resource conflicts for Agent 6

DATABASE TABLES USED (from backend/models.py):
  - Resource  : type="medical_team" (or "helicopter"/"truck"), name, lat, lng, status
  - SOSEvent  : lat, lng, people_count, injury_description, triage_level,
                status, assigned_resource_id
  - Mission   : sos_event_id, resource_id, status, shelter_id

QUEUE MESSAGE FORMAT (from main.py Twilio webhook):
  sos_queue items have:
    {
      "sos_id":             int,
      "phone":              str,
      "lat":                float,
      "lng":                float,
      "people_count":       int,
      "injury_description": str,
      "triage_level":       int   # 1=critical … 5=minor (set by Agent 7)
    }

TRIAGE LEVELS (START system):
  1 → IMMEDIATE  (life-threatening — minutes matter)
  2 → IMMEDIATE  (serious — needs help soon)
  3 → DELAYED    (stable — can wait up to 60 min)
  4 → DELAYED    (minor injuries)
  5 → MINOR      (walking wounded)

NOTE — NO run() queue ownership:
  This agent does NOT call sos_queue.get() directly.
  rescue_agent.run() owns both sos_queue and resolved_queue and calls
  medical_agent.handle_sos_message() / handle_resolution_message()
  after reading each item.  This prevents the single-consumer problem
  where only one agent would see each message.
===========================================================================
"""

import asyncio
import logging
from datetime import datetime, timezone

from backend.database import SessionLocal, Base, engine
from backend.queues import dispatch_queue, conflict_queue
from backend.models import SOSEvent, Resource, Mission
from backend.broadcast import broadcast, EVENT_DISPATCH_ASSIGNED, EVENT_RESOURCE_MOVED
from backend.utils import haversine

logger = logging.getLogger("agent.medical")

Base.metadata.create_all(bind=engine)


# ============================================================================
# CONSTANTS
# ============================================================================

# Human-readable label for each triage level
TRIAGE_LABEL = {
    1: "IMMEDIATE",
    2: "IMMEDIATE",
    3: "DELAYED",
    4: "DELAYED",
    5: "MINOR",
}

# Vehicle type preference by triage level
# Critical (1-2): helicopter fastest, then dedicated medical_team, then truck
# Delayed  (3-4): medical_team first (best equipped), truck as backup
# Minor    (5):   truck sufficient
MEDICAL_VEHICLE_PRIORITY = {
    1: ["helicopter", "medical_team", "truck"],
    2: ["helicopter", "medical_team", "truck"],
    3: ["medical_team", "truck", "helicopter"],
    4: ["medical_team", "truck"],
    5: ["truck", "medical_team"],
}

# Travel speeds in km/hr — used for ETA
VEHICLE_SPEEDS = {
    "helicopter":   150,
    "medical_team":  40,
    "truck":         40,
    "boat":          20,
}

# Keywords that signal a medical component even in a "rescue" type SOS
MEDICAL_KEYWORDS = [
    "injured", "bleeding", "unconscious", "sick", "pain",
    "hurt", "wound", "medicine", "insulin", "breathing",
    "fracture", "burn", "seizure", "stroke", "cardiac",
]


# ============================================================================
# HELPER — ETA CALCULATION
# ============================================================================
def calculate_eta(distance_km: float, vehicle_type: str) -> int:
    """Return ETA in minutes. Minimum 2 minutes."""
    speed = VEHICLE_SPEEDS.get(vehicle_type, 40)
    return max(int((distance_km / speed) * 60), 2)


# ============================================================================
# STEP 1 — DOES THIS SOS NEED MEDICAL RESPONSE?
# ============================================================================
def needs_medical(sos_event: dict) -> bool:
    """
    Returns True if this SOS has a medical component.

    Rules:
      - event type is explicitly "medical" or "medical_only" → always True
      - triage_level ≤ 3 → serious enough to warrant medical attention
      - injury_description contains a medical keyword
      - people_count ≥ 5 (likely someone needs medical help in a large group)

    Called before any DB work — cheap filter.
    """
    event_type   = sos_event.get("type", "general").lower()
    triage       = sos_event.get("triage_level", 5)
    description  = sos_event.get("injury_description", "").lower()
    people_count = sos_event.get("people_count", 1)

    if event_type in ("medical", "medical_only"):
        return True
        
    # If it's a rescue event, ONLY dispatch medical if there are clear medical keywords
    if any(word in description for word in MEDICAL_KEYWORDS):
        return True

    return False


# ============================================================================
# STEP 2 — FIND BEST MEDICAL RESOURCE
# ============================================================================
def find_best_medical_resource(sos_lat: float, sos_lng: float,
                                triage_level: int, db):
    """
    Find the best available resource for a medical dispatch.

    Algorithm:
      1. Get vehicle priority list for this triage level.
      2. For each type, query DB for available resources.
      3. Sort by distance (nearest first).
         — No NDRF/SDRF name prefix in seed data, so distance is the sole
           tiebreaker within a vehicle type.
      4. Return first match.

    Returns:
      (resource, vehicle_type, distance_km)  on success
      (None, None, None)                      if nothing available
    """
    vehicle_types = MEDICAL_VEHICLE_PRIORITY.get(triage_level, ["medical_team", "truck"])

    for vehicle_type in vehicle_types:
        available = (
            db.query(Resource)
            .filter(Resource.type == vehicle_type)
            .filter(Resource.status == "available")
            .all()
        )

        if not available:
            logger.info(f"No available {vehicle_type} — trying next type")
            continue

        available.sort(
            key=lambda r: haversine(r.lat, r.lng, sos_lat, sos_lng)
        )
        best = available[0]
        distance_km = haversine(best.lat, best.lng, sos_lat, sos_lng)

        logger.info(
            f"Medical resource match: '{best.name}' ({vehicle_type}) "
            f"at {distance_km:.2f} km | "
            f"triage={TRIAGE_LABEL.get(triage_level, 'DELAYED')}"
        )
        return best, vehicle_type, distance_km

    return None, None, None


# ============================================================================
# STEP 3 — WRITE MEDICAL DISPATCH TO DATABASE
# ============================================================================
async def dispatch_medical_resource(sos_event: dict, resource: Resource,
                               vehicle_type: str, distance_km: float, db):
    """
    Persist the medical dispatch to the database.

    Field names match models.py exactly:
      Resource.status                  → "dispatched"
      SOSEvent.status                  → "assigned"
      SOSEvent.assigned_resource_id    → resource.id
      Mission (new row)                → status="en_route", shelter_id=None

    Key mapping: sos_event["sos_id"] → SOSEvent.id (FK in Mission and SOSEvent)
    """
    sos_db_id = sos_event.get("sos_id")   # set by main.py Twilio webhook

    resource.status = "dispatched"

    mission = Mission(
        sos_event_id=sos_db_id,
        resource_id=resource.id,
        status="en_route",
        shelter_id=None,
    )
    db.add(mission)

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
    triage_label = TRIAGE_LABEL.get(sos_event.get("triage_level", 3), "DELAYED")

    logger.info(
        f"MEDICAL DISPATCH: '{resource.name}' ({vehicle_type}) "
        f"→ SOS #{sos_db_id} | Triage={triage_label} | ETA ~{eta_minutes} min"
    )
    return mission, eta_minutes


# ============================================================================
# STEP 4 — PROCESS ONE MEDICAL SOS (core pipeline)
# ============================================================================
async def process_medical_sos(sos_event: dict):
    """
    Full medical pipeline for one SOS message.

    Steps:
      1. Check if medical response is needed (needs_medical filter)
      2. Find best available medical resource for this triage level
      3. Re-check resource availability (race condition guard)
      4. Dispatch — write to DB
      5. Push to dispatch_queue (→ Agent 7 for SMS)
      6. Broadcast to dashboard via broadcast()
    """
    sos_id       = sos_event.get("sos_id", "unknown")
    sos_lat      = sos_event.get("lat", 0.0)
    sos_lng      = sos_event.get("lng", 0.0)
    triage_level = sos_event.get("triage_level", 3)
    triage_label = TRIAGE_LABEL.get(triage_level, "DELAYED")

    # ── 1. Quick filter ───────────────────────────────────────────────────
    if not needs_medical(sos_event):
        logger.debug(f"SOS #{sos_id} has no medical component — skipping")
        return

    logger.info(
        f"Medical Agent | SOS #{sos_id} | "
        f"triage={triage_label} (level {triage_level}) | "
        f"people={sos_event.get('people_count', 1)}"
    )

    db = SessionLocal()
    try:
        # ── 2. Find best medical resource ─────────────────────────────────
        resource, vehicle_type, distance_km = find_best_medical_resource(
            sos_lat, sos_lng, triage_level, db
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
                "reason": evt.get("injury_description", "Medical emergency")
            }

        # ── 3a. Nothing available ─────────────────────────────────────────
        if resource is None:
            logger.warning(f"No medical resource available for SOS #{sos_id}")
            types = MEDICAL_VEHICLE_PRIORITY.get(triage_level, ["medical_team", "truck"])
            active_mission = db.query(Mission).join(Resource).filter(
                Resource.type.in_(types),
                Resource.status == "dispatched",
                Mission.status.in_(["en_route", "on_site", "evacuating"])
            ).first()
            
            if active_mission:
                incumbent_sos = db.query(SOSEvent).filter(SOSEvent.id == active_mission.sos_event_id).first()
                incumbent_res = db.query(Resource).filter(Resource.id == active_mission.resource_id).first()
                dist_b = haversine(incumbent_res.lat, incumbent_res.lng, incumbent_sos.lat, incumbent_sos.lng)
                req_b = _build_req("medical", {"sos_id": incumbent_sos.id, "people_count": incumbent_sos.people_count, "injury_description": incumbent_sos.injury_description, "vulnerable_population": incumbent_sos.vulnerable_population}, dist_b)
                
                await conflict_queue.put({
                    "resource_id": incumbent_res.id,
                    "resource_name": incumbent_res.name,
                    "request_a": _build_req("medical", sos_event, 15.0),
                    "request_b": req_b
                })
            else:
                await conflict_queue.put({
                    "resource_id": -1,
                    "resource_name": "None",
                    "request_a": _build_req("medical", sos_event, 15.0),
                    "request_b": None
                })
            return

        # ── 3b. Race condition re-check ───────────────────────────────────
        db.refresh(resource)
        if resource.status != "available":
            logger.warning(f"Medical resource '{resource.name}' just taken — raising conflict for SOS #{sos_id}")
            active_mission = db.query(Mission).filter(Mission.resource_id == resource.id, Mission.status.in_(["en_route", "on_site", "evacuating"])).first()
            req_b = None
            if active_mission:
                incumbent_sos = db.query(SOSEvent).filter(SOSEvent.id == active_mission.sos_event_id).first()
                dist_b = haversine(resource.lat, resource.lng, incumbent_sos.lat, incumbent_sos.lng)
                req_b = _build_req("medical", {"sos_id": incumbent_sos.id, "people_count": incumbent_sos.people_count, "injury_description": incumbent_sos.injury_description, "vulnerable_population": incumbent_sos.vulnerable_population}, dist_b)
                
            await conflict_queue.put({
                "resource_id": resource.id,
                "resource_name": resource.name,
                "request_a": _build_req("medical", sos_event, distance_km),
                "request_b": req_b
            })
            return

        # ── 4. Dispatch ───────────────────────────────────────────────────
        mission, eta_minutes = await dispatch_medical_resource(
            sos_event, resource, vehicle_type, distance_km, db
        )

        # ── 5. Push to dispatch_queue (Agent 7 SMS) ───────────────────────
        await dispatch_queue.put({
            "mission_id":    mission.id,
            "sos_id":        sos_id,
            "resource_id":   resource.id,
            "resource_name": resource.name,
            "resource_type": vehicle_type,
            "phone":         sos_event.get("phone", "+910000000000"),
            "eta_minutes":   eta_minutes,
            "shelter_name":  "Nearest Medical Center",
            "shelter_lat":   sos_lat,
            "shelter_lng":   sos_lng,
            "message_template": "Medical help is on the way! {resource_type} {resource_name} arriving in ~{eta_minutes} min.",
        })

        # ── 6. Broadcast to React dashboard ───────────────────────────────
        await broadcast(EVENT_DISPATCH_ASSIGNED, {
            "mission_id":    mission.id,
            "sos_id":        sos_id,
            "resource_id":   resource.id,
            "resource_name": resource.name,
            "eta_minutes":   eta_minutes,
        })

        logger.info(f"Medical dispatch confirmed for SOS #{sos_id}")

    except Exception as e:
        logger.error(f"Medical Agent error on SOS #{sos_id}: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


# ============================================================================
# PUBLIC API — called by rescue_agent fan-out loop
# ============================================================================
async def handle_sos_message(sos_event: dict):
    """
    Public entry point called by rescue_agent.run() for every SOS message.
    Filters and dispatches if medical response is warranted.
    """
    await process_medical_sos(sos_event)


async def handle_resolution_message(resolution: dict):
    """
    Called by rescue_agent's resolution fan-out when Agent 6 resolves a conflict.
    If medical won, re-attempt dispatch with the now-granted resource.
    """
    if resolution.get("winning_agent") == "medical":
        logger.info("Medical won conflict — re-dispatching")
        await process_medical_sos(resolution.get("sos_event", {}))
    else:
        logger.info(
            f"Medical lost conflict for SOS #{resolution.get('sos_id')} "
            f"— fallback assigned by Agent 6"
        )


# ============================================================================
# run() — required by main.py but queue ownership is in rescue_agent
# ============================================================================
async def run():
    """
    Called by main.py as an asyncio background task.

    This agent does NOT own sos_queue or resolved_queue — rescue_agent.run()
    handles the fan-out.  This coroutine simply stays alive so main.py's task
    list remains consistent (all 7 agents have a run() coroutine).
    """
    logger.info(
        "Medical Agent started — queue fan-out handled by Rescue Agent. "
        "Waiting for forwarded events."
    )
    # Keep the task alive so main.py doesn't see it as crashed.
    while True:
        await asyncio.sleep(3600)