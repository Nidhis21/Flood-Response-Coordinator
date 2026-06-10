"""
=============================================================================
MEDICAL AGENT — Medical Triage and Emergency Health Response
=============================================================================
Owner: Member 3
=============================================================================

SUBSCRIBES TO:
  - sos_queue       ←  reads new SOS events from Community Liaison Agent
  - resolved_queue  ←  reads conflict resolutions from Conflict Resolution Agent

PUBLISHES TO:
  - dispatch_queue  →  pushes medical dispatch assignments for SMS confirmation
  - conflict_queue  →  pushes when resource conflict detected with another agent

BROADCAST EVENTS FIRED:
  - dispatch_assigned  →  fired when medical team is assigned to an SOS
    Payload: { mission_id, sos_id, resource_id, resource_name, eta_minutes }

=============================================================================
TODO — Implementation Checklist
=============================================================================
  1. Run as async loop reading from sos_queue
  2. For each SOS event, perform medical triage:
     - Re-assess triage_level based on injury_description using Gemini LLM
     - Triage levels: 1=critical, 2=severe, 3=moderate, 4=minor, 5=minimal
     - Update triage_level in sos_events table
  3. If triage_level <= 2 (critical/severe), dispatch MT1 medical team:
     - Find MT1 in resources table, check if available
     - If MT1 is dispatched, check if helicopter H1 can carry medical supplies
  4. If chosen resource is also being requested by Rescue Agent:
     - Push conflict to conflict_queue with medical urgency details
     - Medical cases with triage_level=1 should score high on irreversibility
     - Wait for resolution on resolved_queue
  5. If no conflict, assign medical resource:
     - Create Mission record linking SOS to MT1
     - Update SOS status to "assigned"
  6. Push dispatch info to dispatch_queue for SMS confirmation
  7. Broadcast EVENT_DISPATCH_ASSIGNED to dashboard
  8. Track medical supplies consumed per mission
  9. Alert Logistics Agent when medical supplies run low
  10. Log all triage decisions to audit_log for medical review
=============================================================================
"""

import asyncio
import logging

logger = logging.getLogger("agent.medical")


async def run():
    """
    Main loop for the Medical Agent.
    Reads SOS events, performs triage, dispatches medical resources.
    """
    logger.info("Medical Agent started (stub — awaiting implementation)")
    while True:
        # TODO: Implement medical triage and dispatch loop
        await asyncio.sleep(60)

"""
===========================================================================
MEDICAL AGENT — Medical Triage and Dispatch
===========================================================================
Owner: Member 3
===========================================================================

SUBSCRIBES TO:
  - sos_queue      ←  reads new SOS events from Community Liaison Agent
  - resolved_queue ←  reads conflict resolutions from Conflict Resolution Agent

PUBLISHES TO:
  - dispatch_queue  →  pushes dispatch assignments for SMS confirmation
  - conflict_queue  →  pushes when resource conflict detected with another agent

===========================================================================
"""

import asyncio
import logging
import math
from datetime import datetime, timezone

from backend.database import SessionLocal, Base, engine
from backend.queues import sos_queue, dispatch_queue, conflict_queue, resolved_queue
from backend.models import SOSEvent, Resource, Mission

logger = logging.getLogger("agent.medical")

# ── Make sure our tables exist in the database ──────────────────────────────
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Medical agent tables initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize medical tables: {e}")


# ============================================================================
# START TRIAGE CLASSIFICATION
# START = Simple Triage and Rapid Treatment
# Used by paramedics worldwide to sort casualties by urgency
# ============================================================================
def start_triage(sos_event: dict) -> str:
    """
    Classifies the medical urgency of an SOS event using START triage.

    Four levels (from most to least urgent):
      IMMEDIATE  — life-threatening, needs help within minutes
                   Examples: unconscious, not breathing, severe bleeding
      DELAYED    — serious but stable, can wait 30-60 mins
                   Examples: broken bones, moderate wounds
      MINOR      — walking wounded, can wait hours
                   Examples: small cuts, minor injuries
      DECEASED   — no signs of life

    Returns one of: "immediate", "delayed", "minor", "deceased"
    """
    injury = sos_event.get("injury_description", "").lower()
    triage_level = sos_event.get("triage_level", "").lower()
    people_count = sos_event.get("people_count", 1)
    is_breathing = sos_event.get("is_breathing", True)
    is_conscious = sos_event.get("is_conscious", True)

    # If triage level was already set by the community liaison agent, use it
    if triage_level in ["immediate", "delayed", "minor", "deceased"]:
        return triage_level

    # ── Check for DECEASED signs ────────────────────────────────────────
    if not is_breathing and not is_conscious:
        return "deceased"

    # ── Check for IMMEDIATE (life-threatening keywords) ─────────────────
    immediate_keywords = [
        "unconscious", "not breathing", "severe bleeding", "chest pain",
        "heart attack", "stroke", "drowning", "trapped underwater",
        "crush injury", "head injury", "not responding", "critical"
    ]
    if any(word in injury for word in immediate_keywords):
        return "immediate"

    # Not breathing is always immediate
    if not is_breathing:
        return "immediate"

    # Large groups in dangerous situations → treat as immediate
    if people_count >= 5 and not is_conscious:
        return "immediate"

    # ── Check for DELAYED (serious but stable keywords) ──────────────────
    delayed_keywords = [
        "broken", "fracture", "bleeding", "wound", "burn", "pain",
        "fever", "vomiting", "diabetic", "elderly", "pregnant",
        "cannot walk", "injured"
    ]
    if any(word in injury for word in delayed_keywords):
        return "delayed"

    # ── MINOR — everything else ──────────────────────────────────────────
    return "minor"


# ============================================================================
# CHECK IF SOS NEEDS MEDICAL (has medical component)
# ============================================================================
def needs_medical(sos_event: dict) -> bool:
    """
    Returns True if this SOS has a medical component.
    Even rescue SOSes can have medical needs (injured trapped people).
    """
    sos_type = sos_event.get("type", "").lower()
    injury = sos_event.get("injury_description", "").lower()

    # Explicitly medical
    if sos_type in ["medical", "medical_only"]:
        return True

    # Has an injury description — medical help needed
    if injury and injury not in ["none", "no injury", ""]:
        return True

    # Rescue type but mentions injuries
    medical_keywords = [
        "injured", "hurt", "bleeding", "unconscious", "sick",
        "medicine", "insulin", "breathing", "pain", "wound"
    ]
    if any(word in injury for word in medical_keywords):
        return True

    return False


# ============================================================================
# HAVERSINE — same function as rescue agent (distance calculator)
# ============================================================================
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in kilometres between two GPS points."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def calculate_eta_minutes(distance_km: float, resource_type: str) -> int:
    """Estimate arrival time in minutes based on resource type."""
    speeds = {"ambulance": 60, "medical_team": 40, "helicopter": 150, "boat": 20}
    speed = speeds.get(resource_type.lower(), 40)
    return max(int((distance_km / speed) * 60), 2)


# ============================================================================
# FIND NEAREST MEDICAL RESOURCE
# Prioritises by triage level — Immediate gets helicopters/ambulances first
# ============================================================================
def find_nearest_medical_resource(
    sos_lat: float, sos_lon: float, triage: str, db
) -> Resource | None:
    """
    Finds the closest available medical resource.
    For IMMEDIATE cases: prefers ambulance or helicopter (fastest)
    For DELAYED/MINOR cases: any medical team will do
    """
    # Get all available medical resources
    available = (
        db.query(Resource)
        .filter(Resource.status == "available")
        .filter(Resource.resource_type.in_(["ambulance", "medical_team", "helicopter"]))
        .all()
    )

    if not available:
        return None

    nearest = None
    shortest_score = float("inf")

    for resource in available:
        distance = haversine(resource.latitude, resource.longitude, sos_lat, sos_lon)

        # For IMMEDIATE cases, strongly prefer ambulances/helicopters
        # Give them a big distance bonus to rank them first
        if triage == "immediate":
            if resource.resource_type in ["ambulance", "helicopter"]:
                distance = distance * 0.5  # Appears twice as close in ranking

        if distance < shortest_score:
            shortest_score = distance
            nearest = resource

    return nearest


# ============================================================================
# DISPATCH MEDICAL RESOURCE
# ============================================================================
def dispatch_medical_resource(sos_event: dict, resource: Resource, triage: str, db) -> Mission:
    """
    Assigns the medical resource to the SOS event.
    Updates database: resource → dispatched, creates Mission, updates SOS status.
    """
    now = datetime.now(timezone.utc)

    sos_lat = sos_event.get("latitude", 0.0)
    sos_lon = sos_event.get("longitude", 0.0)

    # Mark resource as dispatched
    resource.status = "dispatched"
    resource.updated_at = now

    distance_km = haversine(resource.latitude, resource.longitude, sos_lat, sos_lon)
    eta_minutes = calculate_eta_minutes(distance_km, resource.resource_type)

    # Create mission record
    mission = Mission(
        sos_event_id=sos_event.get("id"),
        resource_id=resource.id,
        status="en_route",
        assigned_at=now,
        eta_minutes=eta_minutes,
        destination_latitude=sos_lat,
        destination_longitude=sos_lon,
        notes=f"Triage: {triage.upper()}",  # Include triage level in mission notes
    )
    db.add(mission)

    # Update SOS status
    sos_db_record = db.query(SOSEvent).filter(SOSEvent.id == sos_event.get("id")).first()
    if sos_db_record:
        sos_db_record.status = "assigned"
        sos_db_record.triage_level = triage
        sos_db_record.updated_at = now

    db.commit()
    db.refresh(mission)
    db.refresh(resource)

    logger.info(
        f"Medical dispatch: {resource.resource_type} '{resource.name}' → "
        f"SOS {sos_event.get('id')} | Triage: {triage.upper()} | ETA: {eta_minutes} mins"
    )

    return mission


# ============================================================================
# PROCESS ONE MEDICAL SOS EVENT
# ============================================================================
async def process_medical_sos(sos_event: dict):
    """
    Full pipeline for one medical SOS event:
      1. Check if it has a medical component
      2. Run START triage to classify urgency
      3. Find nearest appropriate medical resource
      4. Dispatch or escalate conflict
      5. Push to dispatch_queue for SMS confirmation
    """
    sos_id = sos_event.get("id", "unknown")
    sos_lat = sos_event.get("latitude", 0.0)
    sos_lon = sos_event.get("longitude", 0.0)

    logger.info(f"Medical Agent processing SOS: {sos_id}")

    # ── Step 1: Does this need medical help? ─────────────────────────────
    if not needs_medical(sos_event):
        logger.info(f"SOS {sos_id} has no medical component — skipping")
        return

    # ── Step 2: Run START triage ─────────────────────────────────────────
    triage = start_triage(sos_event)
    logger.info(f"SOS {sos_id} triage classification: {triage.upper()}")

    # Do not dispatch for deceased (no medical help can be provided)
    if triage == "deceased":
        logger.info(f"SOS {sos_id} classified as DECEASED — no dispatch")
        return

    # ── Step 3: Open database and find nearest team ───────────────────────
    db = SessionLocal()
    try:
        resource = find_nearest_medical_resource(sos_lat, sos_lon, triage, db)

        # ── Step 4a: No resource available ───────────────────────────────
        if resource is None:
            logger.warning(f"No medical resource available for SOS {sos_id}")
            await conflict_queue.put({
                "type": "no_medical_resource",
                "sos_event": sos_event,
                "triage_level": triage,
                "agent": "medical",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            })
            return

        # ── Step 4b: Check if resource is still available (conflict check) ─
        db.refresh(resource)
        if resource.status != "available":
            logger.warning(f"Medical resource {resource.name} just taken — conflict for SOS {sos_id}")
            await conflict_queue.put({
                "type": "resource_conflict",
                "sos_event": sos_event,
                "triage_level": triage,
                "resource_id": resource.id,
                "resource_name": resource.name,
                "agent": "medical",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            })
            return

        # ── Step 5: Dispatch ──────────────────────────────────────────────
        mission = dispatch_medical_resource(sos_event, resource, triage, db)

        # ── Step 6: Push to dispatch_queue for SMS ────────────────────────
        dispatch_message = {
            "type": "medical_dispatch_assigned",
            "mission_id": mission.id,
            "sos_id": sos_id,
            "resource_id": resource.id,
            "resource_name": resource.name,
            "resource_type": resource.resource_type,
            "triage_level": triage,
            "eta_minutes": mission.eta_minutes,
            "destination_latitude": sos_lat,
            "destination_longitude": sos_lon,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        await dispatch_queue.put(dispatch_message)
        logger.info(f"Medical dispatch pushed to dispatch_queue for SOS {sos_id}")

    except Exception as e:
        logger.error(f"Error in Medical Agent processing SOS {sos_id}: {e}")
        db.rollback()
    finally:
        db.close()


# ============================================================================
# LISTEN FOR CONFLICT RESOLUTIONS
# ============================================================================
async def listen_for_resolutions():
    """
    Background task: watches resolved_queue for Agent 6 decisions.
    If medical agent wins the conflict, re-process the original SOS.
    """
    logger.info("Medical Agent: listening for conflict resolutions...")
    while True:
        try:
            resolution = await resolved_queue.get()

            if resolution.get("winner_agent") == "medical":
                logger.info(f"Conflict resolved — medical won: {resolution}")
                original_sos = resolution.get("sos_event")
                if original_sos:
                    await process_medical_sos(original_sos)
            else:
                logger.info(
                    f"Conflict resolved — medical lost SOS {resolution.get('sos_id')}. "
                    f"Fallback assigned by Agent 6."
                )
        except Exception as e:
            logger.error(f"Error reading resolved_queue in Medical Agent: {e}")
            await asyncio.sleep(1)


# ============================================================================
# MAIN RUN LOOP
# ============================================================================
async def run():
    """
    Main loop for the Medical Agent.
    Reads SOS events from sos_queue, runs triage, dispatches medical teams.

    Two tasks run concurrently:
      1. Main loop: reads sos_queue, handles medical SOSes
      2. Background: watches resolved_queue for conflict outcomes
    """
    logger.info("Medical Agent started — waiting for SOS events on sos_queue")

    # Start conflict resolution listener in background
    asyncio.create_task(listen_for_resolutions())

    while True:
        try:
            # Wait for next SOS event
            sos_event = await sos_queue.get()

            # Handle medical and general SOS types
            event_type = sos_event.get("type", "").lower()
            if event_type in ["medical", "medical_only", "general"]:
                await process_medical_sos(sos_event)
            elif event_type in ["rescue", "evacuation"] and sos_event.get("injury_description"):
                # Rescue SOS but has injuries — medical agent handles the medical side
                await process_medical_sos(sos_event)
            else:
                logger.debug(f"Medical Agent skipping SOS type '{event_type}'")

        except Exception as e:
            logger.error(f"Unexpected error in Medical Agent main loop: {e}")
            await asyncio.sleep(5)