"""
=============================================================================
COMMUNITY LIAISON AGENT — Survivor Communication via SMS
=============================================================================
Owner: Member 5
=============================================================================

SUBSCRIBES TO:
  - dispatch_queue  ←  reads dispatch assignments from Rescue/Medical Agents

PUBLISHES TO:
  - sos_queue  →  pushes parsed SOS events received via SMS/webhook

BROADCAST EVENTS FIRED:
  - sms_sent  →  fired when outbound SMS confirmation is sent to survivor
    Payload: { phone, message, sos_id }

OFFLINE MODE:
  - When OFFLINE_MODE=true, prints SMS to console instead of sending via Twilio
  - When OFFLINE_MODE=false, sends SMS via Twilio API

=============================================================================
TODO — Implementation Checklist
=============================================================================
  1. Run as async loop reading from dispatch_queue
  2. For each dispatch assignment, compose confirmation SMS:
     - Include: resource type, ETA, shelter name, emergency contact
     - Example: "Help is on the way! Boat B1 arriving in ~15 min.
       Proceed to Gogamukh Community Hall if able. Stay safe."
  3. Check OFFLINE_MODE environment variable:
     - If true: print SMS content to console with phone number
     - If false: send via Twilio using TWILIO_ACCOUNT_SID, AUTH_TOKEN, PHONE_NUMBER
  4. Broadcast EVENT_SMS_SENT to dashboard
  5. Handle Twilio API errors gracefully (retry once, then log failure)
  6. Track all sent SMS for audit purposes
  7. Parse incoming SOS SMS from Twilio webhook (already handled in main.py,
     but may need enhancement for multi-format parsing):
     - Format 1: "lat,lng,people_count,injury_description"
     - Format 2: Free-text SOS — use Gemini to extract location/details
  8. Support multi-language SMS (Assamese, Hindi, English)
  9. Send periodic status updates to survivors already in queue
  10. Implement rate limiting to avoid Twilio cost overruns during mass events
=============================================================================
"""

import asyncio
import logging

logger = logging.getLogger("agent.liaison")


async def run():
    """
    Main loop for the Community Liaison Agent.
    Reads dispatch assignments and sends SMS confirmations to survivors.
    """
    logger.info("Community Liaison Agent started (stub — awaiting implementation)")
    while True:
        # TODO: Implement SMS communication loop
        await asyncio.sleep(60)
