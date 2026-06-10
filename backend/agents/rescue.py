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
