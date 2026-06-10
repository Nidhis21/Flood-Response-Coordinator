"""
queues.py — Asyncio queues for inter-agent communication.

No Redis, no external dependencies. All queues are in-process asyncio.Queue
instances. Each queue has a single producer pattern and one or more consumers.

Architecture:
  Perception → alert_queue → Prediction
  Community Liaison → sos_queue → Rescue, Medical
  Rescue, Medical → dispatch_queue → Community Liaison (SMS confirmation)
  Logistics → resource_update_queue → (broadcast / DB update)
  Rescue, Medical, Logistics → conflict_queue → Conflict Resolution
  Conflict Resolution → resolved_queue → all other agents
"""

import asyncio

# ---------------------------------------------------------------------------
# alert_queue
# Producer: Perception Agent (pushes raw rainfall/water-level readings)
# Consumer: Prediction Agent (reads and computes flood forecasts)
# Message: see MESSAGE_FORMATS.md § alert_queue
# ---------------------------------------------------------------------------
alert_queue: asyncio.Queue = asyncio.Queue()

# ---------------------------------------------------------------------------
# sos_queue
# Producer: Community Liaison Agent (pushes parsed SOS from SMS/webhook)
# Consumer: Rescue Agent, Medical Agent (read and decide dispatch)
# Message: see MESSAGE_FORMATS.md § sos_queue
# ---------------------------------------------------------------------------
sos_queue: asyncio.Queue = asyncio.Queue()

# ---------------------------------------------------------------------------
# dispatch_queue
# Producer: Rescue Agent, Medical Agent (push dispatch assignments)
# Consumer: Community Liaison Agent (sends SMS confirmation to survivor)
# Message: see MESSAGE_FORMATS.md § dispatch_queue
# ---------------------------------------------------------------------------
dispatch_queue: asyncio.Queue = asyncio.Queue()

# ---------------------------------------------------------------------------
# resource_update_queue
# Producer: Logistics Agent (pushes resource position/status changes)
# Consumer: Dashboard broadcast, DB update
# Message: see MESSAGE_FORMATS.md § resource_update_queue
# ---------------------------------------------------------------------------
resource_update_queue: asyncio.Queue = asyncio.Queue()

# ---------------------------------------------------------------------------
# conflict_queue
# Producer: Rescue Agent, Medical Agent, Logistics Agent
#           (push when two+ agents want the same resource simultaneously)
# Consumer: Conflict Resolution Agent (runs priority auction)
# Message: see MESSAGE_FORMATS.md § conflict_queue
# ---------------------------------------------------------------------------
conflict_queue: asyncio.Queue = asyncio.Queue()

# ---------------------------------------------------------------------------
# resolved_queue
# Producer: Conflict Resolution Agent (pushes auction result + fallback)
# Consumer: All other agents (read resolution and act accordingly)
# Message: see MESSAGE_FORMATS.md § resolved_queue
# ---------------------------------------------------------------------------
resolved_queue: asyncio.Queue = asyncio.Queue()
