"""
=============================================================================
RESCUE AGENT — Search and Rescue Dispatch
=============================================================================
Owner: Member 3
=============================================================================

SUBSCRIBES TO:
  - sos_queue       ←  reads new SOS events from Community Liaison Agent
  - resolved_queue  ←  reads conflict resolutions from Conflict Resolution Agent

PUBLISHES TO:
  - dispatch_queue  →  pushes dispatch assignments for SMS confirmation
  - conflict_queue  →  pushes when resource conflict detected with another agent

BROADCAST EVENTS FIRED:
  - dispatch_assigned  →  fired when a resource is assigned to an SOS
    Payload: { mission_id, sos_id, resource_id, resource_name, eta_minutes }

=============================================================================
TODO — Implementation Checklist
=============================================================================
  1. Run as async loop reading from sos_queue
  2. For each SOS event, determine if it needs RESCUE (not medical-only):
     - Check people_count, injury_description, triage_level
     - If purely medical, skip (Medical Agent handles it)
  3. Find nearest available resource using haversine() from backend.utils:
     - Query resources table for status="available"
     - Prefer boats for flood zones, helicopter for isolated areas
  4. If chosen resource is also being requested by another agent:
     - Push conflict to conflict_queue with both SOS details
     - Wait for resolution on resolved_queue before proceeding
  5. If no conflict, assign resource directly:
     - Update resource status to "dispatched" in DB
     - Create Mission record with status="en_route"
     - Update SOS event status to "assigned"
  6. Calculate ETA based on haversine distance and resource speed:
     - Helicopter: ~150 km/hr
     - Boat: ~20 km/hr
     - Truck: ~40 km/hr (on flooded roads)
  7. Push dispatch info to dispatch_queue for SMS confirmation
  8. Broadcast EVENT_DISPATCH_ASSIGNED to dashboard
  9. Monitor mission lifecycle: en_route → on_site → evacuating → complete
  10. On mission complete, set resource back to "available"
=============================================================================
"""

import asyncio
import logging

logger = logging.getLogger("agent.rescue")


async def run():
    """
    Main loop for the Rescue Agent.
    Reads SOS events, dispatches nearest rescue resources.
    """
    logger.info("Rescue Agent started (stub — awaiting implementation)")
    while True:
        # TODO: Implement rescue dispatch loop
        await asyncio.sleep(60)

"""
===========================================================================
RESCUE AGENT — Search and Rescue Dispatch
===========================================================================
Owner: Member 3
===========================================================================

SUBSCRIBES TO:
  - sos_queue      ←  reads new SOS events from Community Liaison Agent
  - resolved_queue ←  reads conflict resolutions from Conflict Resolution Agent

PUBLISHES TO:
  - dispatch_queue  →  pushes dispatch assignments for SMS confirmation
  - conflict_queue  →  pushes when resource conflict detected with another agent

BROADCAST EVENTS FIRED:
  - dispatch_assigned →  fired when a resource is assigned to an SOS
    Payload: { mission_id, sos_id, resource_id, resource_name, eta_minutes }

===========================================================================
"""

import asyncio
import logging
import math
from datetime import datetime, timezone

from backend.database import SessionLocal, Base, engine
from backend.queues import sos_queue, dispatch_queue, conflict_queue, resolved_queue
from backend.models import SOSEvent, Resource, Mission

logger = logging.getLogger("agent.rescue")

# ── Make sure our tables exist in the database ──────────────────────────────
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Rescue agent tables initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize rescue tables: {e}")


# ============================================================================
# HAVERSINE FUNCTION
# Give it two GPS coordinates → returns distance in kilometres
# Formula works because Earth is a sphere, not flat
# ============================================================================
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate straight-line distance between two GPS points in kilometres.
    lat1, lon1 = starting point (e.g. rescue team's current location)
    lat2, lon2 = destination point (e.g. SOS location)
    """
    R = 6371  # Earth's radius in kilometres

    # Convert degrees to radians (math functions need radians)
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # The actual haversine formula
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))

    return R * c  # returns kilometres


# ============================================================================
# CALCULATE ETA
# Given distance and resource type → returns estimated minutes to arrive
# ============================================================================
def calculate_eta_minutes(distance_km: float, resource_type: str) -> int:
    """
    Estimate travel time based on resource type and distance.
    Speeds are realistic for flood conditions:
      - Helicopter: ~150 km/hr (fastest, can fly over water)
      - Boat:       ~20 km/hr  (fast on water, slow approach)
      - Truck:      ~40 km/hr  (on flooded roads, very slow)
    """
    speeds = {
        "helicopter": 150,
        "boat": 20,
        "truck": 40,
        "ambulance": 40,
    }
    # Default to boat speed if unknown type
    speed = speeds.get(resource_type.lower(), 20)

    # time = distance / speed, then convert hours to minutes
    eta_minutes = int((distance_km / speed) * 60)

    # Minimum 2 minutes ETA (preparation time)
    return max(eta_minutes, 2)


# ============================================================================
# CHECK IF SOS NEEDS RESCUE (not purely medical)
# Purely medical cases (like "need medicine") go to Medical Agent only
# ============================================================================
def needs_rescue(sos_event: dict) -> bool:
    """
    Returns True if this SOS needs a rescue team dispatched.
    Purely medical SOSes (no physical rescue needed) return False.
    Examples:
      - "4 people trapped on rooftop" → True  (physical rescue needed)
      - "need insulin for diabetic patient" → False (medical only)
    """
    sos_type = sos_event.get("type", "").lower()
    injury = sos_event.get("injury_description", "").lower()
    people_count = sos_event.get("people_count", 0)

    # If explicitly marked as medical-only, skip rescue
    if sos_type == "medical_only":
        return False

    # If there are people trapped or needing evacuation, rescue is needed
    if sos_type in ["rescue", "evacuation", "trapped"]:
        return True

    # If people count > 0 and no specific medical type, assume rescue needed
    if people_count > 0 and sos_type != "medical_only":
        return True

    return True  # Default: handle it, better safe than sorry


# ============================================================================
# FIND NEAREST AVAILABLE RESOURCE
# Queries the database, calculates distance to each available team,
# returns the closest one
# ============================================================================
def find_nearest_resource(sos_lat: float, sos_lon: float, db) -> Resource | None:
    """
    Looks at ALL available rescue resources in the database.
    Calculates distance from each one to the SOS location.
    Returns the closest available resource.

    Preference order:
      - Boats preferred for flood zones (water rescue)
      - Helicopters preferred for isolated/unreachable areas
      - Trucks as last resort
    """
    # Get all resources that are currently available
    available_resources = (
        db.query(Resource)
        .filter(Resource.status == "available")
        .filter(Resource.resource_type.in_(["boat", "helicopter", "truck", "ambulance"]))
        .all()
    )

    if not available_resources:
        return None  # No one is free right now

    # Calculate distance from each resource to the SOS location
    nearest = None
    shortest_distance = float("inf")  # Start with "infinitely far"

    for resource in available_resources:
        distance = haversine(
            resource.latitude, resource.longitude,
            sos_lat, sos_lon
        )

        # Prefer boats for flood rescue (give them a 20% distance bonus)
        if resource.resource_type == "boat":
            distance = distance * 0.8  # Makes boats seem closer in ranking

        if distance < shortest_distance:
            shortest_distance = distance
            nearest = resource

    return nearest


# ============================================================================
# DISPATCH RESOURCE
# Updates database: resource → "dispatched", creates Mission record,
# updates SOS status → "assigned"
# ============================================================================
def dispatch_resource(sos_event: dict, resource: Resource, db) -> Mission:
    """
    Officially assigns the rescue resource to the SOS.
    Updates three things in the database:
      1. Resource status: "available" → "dispatched"
      2. Creates a new Mission record with status "en_route"
      3. Updates the SOS event status to "assigned"
    Returns the newly created Mission object.
    """
    now = datetime.now(timezone.utc)

    # 1. Mark resource as dispatched (no longer available)
    resource.status = "dispatched"
    resource.updated_at = now

    # 2. Calculate ETA
    sos_lat = sos_event.get("latitude", 0.0)
    sos_lon = sos_event.get("longitude", 0.0)
    distance_km = haversine(resource.latitude, resource.longitude, sos_lat, sos_lon)
    eta_minutes = calculate_eta_minutes(distance_km, resource.resource_type)

    # 3. Create a Mission record to track this rescue operation
    mission = Mission(
        sos_event_id=sos_event.get("id"),
        resource_id=resource.id,
        status="en_route",           # First status in the lifecycle
        assigned_at=now,
        eta_minutes=eta_minutes,
        destination_latitude=sos_lat,
        destination_longitude=sos_lon,
    )
    db.add(mission)

    # 4. Update SOS event status to "assigned"
    sos_db_record = db.query(SOSEvent).filter(SOSEvent.id == sos_event.get("id")).first()
    if sos_db_record:
        sos_db_record.status = "assigned"
        sos_db_record.updated_at = now

    # Save all changes to the database in one go
    db.commit()
    db.refresh(mission)
    db.refresh(resource)

    logger.info(
        f"Dispatched {resource.resource_type} '{resource.name}' "
        f"to SOS {sos_event.get('id')} — ETA: {eta_minutes} mins"
    )

    return mission


# ============================================================================
# PROCESS ONE SOS EVENT
# This is the brain of the rescue agent — handles one SOS at a time
# ============================================================================
async def process_sos_event(sos_event: dict):
    """
    Full pipeline for handling one SOS event:
      1. Check if rescue is needed
      2. Find nearest available resource
      3. Check for conflicts with other agents
      4. Dispatch if no conflict, or escalate if conflict
      5. Push dispatch info to dispatch_queue for SMS
    """
    sos_id = sos_event.get("id", "unknown")
    sos_lat = sos_event.get("latitude", 0.0)
    sos_lon = sos_event.get("longitude", 0.0)

    logger.info(f"Processing SOS event: {sos_id} at ({sos_lat}, {sos_lon})")

    # ── Step 1: Should rescue handle this? ────────────────────────────────
    if not needs_rescue(sos_event):
        logger.info(f"SOS {sos_id} is medical-only — skipping (Medical Agent will handle)")
        return

    # ── Step 2: Open database and find nearest team ────────────────────────
    db = SessionLocal()
    try:
        nearest_resource = find_nearest_resource(sos_lat, sos_lon, db)

        # ── Step 3: No resource available at all ──────────────────────────
        if nearest_resource is None:
            logger.warning(f"No available rescue resource for SOS {sos_id} — pushing to conflict queue")
            await conflict_queue.put({
                "type": "no_resource_available",
                "sos_event": sos_event,
                "agent": "rescue",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            })
            return

        # ── Step 4: Check if this resource is also being claimed by another agent ──
        # We do this by seeing if the resource is still "available" right now
        # If another agent just grabbed it between our query and now, conflict
        db.refresh(nearest_resource)  # Get latest status from DB
        if nearest_resource.status != "available":
            logger.warning(
                f"Resource {nearest_resource.name} was just taken — pushing conflict for SOS {sos_id}"
            )
            await conflict_queue.put({
                "type": "resource_conflict",
                "sos_event": sos_event,
                "resource_id": nearest_resource.id,
                "resource_name": nearest_resource.name,
                "agent": "rescue",
                "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            })
            return

        # ── Step 5: No conflict — dispatch the resource ───────────────────
        mission = dispatch_resource(sos_event, nearest_resource, db)

        # ── Step 6: Push to dispatch_queue so Agent 7 can SMS the survivor ─
        dispatch_message = {
            "type": "dispatch_assigned",
            "mission_id": mission.id,
            "sos_id": sos_id,
            "resource_id": nearest_resource.id,
            "resource_name": nearest_resource.name,
            "resource_type": nearest_resource.resource_type,
            "eta_minutes": mission.eta_minutes,
            "destination_latitude": sos_lat,
            "destination_longitude": sos_lon,
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        }

        await dispatch_queue.put(dispatch_message)
        logger.info(f"Dispatch message pushed to dispatch_queue for SOS {sos_id}")

    except Exception as e:
        logger.error(f"Error processing SOS {sos_id}: {e}")
        db.rollback()
    finally:
        db.close()  # Always close DB connection, even if error happened


# ============================================================================
# LISTEN FOR CONFLICT RESOLUTIONS
# Agent 6 (Conflict Resolution) posts decisions on resolved_queue
# We pick them up and act on the winning assignment
# ============================================================================
async def listen_for_resolutions():
    """
    Runs in background, watching the resolved_queue.
    When Agent 6 resolves a conflict and rescue wins, we dispatch.
    When rescue loses, we log it (Agent 6 already assigned fallback).
    """
    logger.info("Rescue Agent: listening for conflict resolutions...")
    while True:
        try:
            resolution = await resolved_queue.get()

            if resolution.get("winner_agent") == "rescue":
                logger.info(f"Conflict resolved — rescue won: {resolution}")
                # Re-process the original SOS now that we have the resource
                original_sos = resolution.get("sos_event")
                if original_sos:
                    await process_sos_event(original_sos)
            else:
                logger.info(
                    f"Conflict resolved — rescue lost SOS {resolution.get('sos_id')}. "
                    f"Fallback assigned by Agent 6."
                )
        except Exception as e:
            logger.error(f"Error reading resolved_queue: {e}")
            await asyncio.sleep(1)


# ============================================================================
# MAIN RUN LOOP
# This is what starts the agent — keeps running forever
# ============================================================================
async def run():
    """
    Main loop for the Rescue Agent.
    Reads SOS events from sos_queue and dispatches nearest rescue resources.

    Two tasks run at the same time (asyncio runs them concurrently):
      1. Main loop: reads from sos_queue, processes each SOS
      2. Background task: watches resolved_queue for conflict outcomes
    """
    logger.info("Rescue Agent started — waiting for SOS events on sos_queue")

    # Start the conflict resolution listener as a background task
    # This runs alongside the main loop without blocking it
    asyncio.create_task(listen_for_resolutions())

    # Main loop — reads SOS events one by one
    while True:
        try:
            # Wait for the next SOS event to arrive in the queue
            # If queue is empty, this line just waits (doesn't waste CPU)
            sos_event = await sos_queue.get()

            # Only handle rescue-type SOS events
            # Medical-only events go to Agent 5
            event_type = sos_event.get("type", "")
            if event_type in ["rescue", "evacuation", "trapped", "general"]:
                await process_sos_event(sos_event)
            else:
                logger.debug(f"Rescue Agent skipping SOS type '{event_type}' — not a rescue event")

        except Exception as e:
            logger.error(f"Unexpected error in Rescue Agent main loop: {e}")
            await asyncio.sleep(5)  # Brief pause before retrying after an error