"""
broadcast.py — WebSocket broadcast to connected frontend clients.

This module maintains a set of connected WebSocket clients and provides a
single `broadcast()` function that all agents call to push real-time updates
to the React + Mapbox dashboard.

Event Types (frontend should handle all of these):
─────────────────────────────────────────────────────────────────────────────
EVENT_FLOOD_ALERT      = "flood_alert"
  Fired when: Prediction Agent generates a new severity update.
  Payload: { district, severity, discharge_q, fhi_score, affected_circles }

EVENT_RESOURCE_MOVED   = "resource_moved"
  Fired when: Logistics Agent pre-positions a truck/boat/heli.
  Payload: { resource_id, name, old_lat, old_lng, new_lat, new_lng }

EVENT_SOS_CREATED      = "sos_created"
  Fired when: New SOS arrives via SMS or webhook.
  Payload: { sos_id, phone, lat, lng, people_count, triage_level }

EVENT_DISPATCH_ASSIGNED = "dispatch_assigned"
  Fired when: Rescue or Medical Agent assigns a resource to an SOS.
  Payload: { mission_id, sos_id, resource_id, resource_name, eta_minutes }

EVENT_CONFLICT_RAISED  = "conflict_raised"
  Fired when: Two agents compete for the same resource.
  Payload: { resource_id, agent_a, agent_b, sos_a_id, sos_b_id }

EVENT_CONFLICT_RESOLVED = "conflict_resolved"
  Fired when: Conflict Resolution Agent completes auction.
  Payload: { resource_id, winner, score_a, score_b, fallback, explanation }

EVENT_SHELTER_UPDATED  = "shelter_updated"
  Fired when: Shelter occupancy or supply stock changes.
  Payload: { shelter_id, name, current_occupancy, food_stock, water_stock }

EVENT_SMS_SENT         = "sms_sent"
  Fired when: Outbound SMS confirmation is sent to survivor.
  Payload: { phone, message, sos_id }
─────────────────────────────────────────────────────────────────────────────
"""

import json
import logging
from fastapi import WebSocket

logger = logging.getLogger("broadcast")

# ── Event type constants ──────────────────────────────────────────────────
EVENT_FLOOD_ALERT = "flood_alert"
EVENT_RESOURCE_MOVED = "resource_moved"
EVENT_SOS_CREATED = "sos_created"
EVENT_DISPATCH_ASSIGNED = "dispatch_assigned"
EVENT_CONFLICT_RAISED = "conflict_raised"
EVENT_CONFLICT_RESOLVED = "conflict_resolved"
EVENT_SHELTER_UPDATED = "shelter_updated"
EVENT_SMS_SENT = "sms_sent"
EVENT_DONATION_UPDATED = "donation_updated"

# ── Connected WebSocket clients ──────────────────────────────────────────
connected_clients: set[WebSocket] = set()


async def broadcast(event_type: str, data: dict) -> None:
    """
    Send a JSON message to every connected WebSocket client.

    Message format:
        { "event": "<event_type>", "data": { ... } }

    Disconnected clients are silently removed from the set.
    """
    if not connected_clients:
        return

    message = json.dumps({"event": event_type, "data": data})
    disconnected = set()

    for client in connected_clients:
        try:
            await client.send_text(message)
        except Exception:
            disconnected.add(client)

    # Clean up dead connections
    connected_clients.difference_update(disconnected)
    if disconnected:
        logger.info(f"Removed {len(disconnected)} disconnected client(s)")
