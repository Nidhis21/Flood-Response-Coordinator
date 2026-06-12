import os
import logging
import asyncio
from datetime import datetime, timezone
from twilio.rest import Client

from backend.database import SessionLocal
from backend.models import SMSLog
from backend.queues import dispatch_queue
from backend.broadcast import broadcast, EVENT_SMS_SENT

logger = logging.getLogger("agent.liaison")

OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "+1234567890")

twilio_client = None
if not OFFLINE_MODE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        logger.info("Twilio client initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize Twilio client: {e}")
        OFFLINE_MODE = True


async def send_sms(to_phone: str, message: str, sms_type: str, sos_id: int = None):
    """Send SMS via Twilio or print to console if offline."""
    status = "console_printed"
    if OFFLINE_MODE or not twilio_client:
        logger.info(f"\n[OFFLINE SMS] To: {to_phone}\nMessage: {message}\n")
    else:
        try:
            # Twilio's client is synchronous, so we run it in a thread
            def _send():
                return twilio_client.messages.create(
                    body=message,
                    from_=TWILIO_PHONE_NUMBER,
                    to=to_phone
                )
            msg = await asyncio.to_thread(_send)
            status = "sent"
            logger.info(f"Twilio SMS sent SID: {msg.sid}")
        except Exception as e:
            logger.error(f"Twilio SMS failed: {e}")
            status = "failed"

    # Log to DB
    db = SessionLocal()
    try:
        log_entry = SMSLog(
            direction="outbound",
            phone=to_phone,
            message=message,
            sms_type=sms_type,
            related_sos_id=sos_id if sos_id and sos_id > 0 else None,
            agent_name="liaison",
            delivery_status=status
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        log_id = log_entry.id
    except Exception as e:
        logger.error(f"Failed to write SMSLog: {e}")
        log_id = -1
    finally:
        db.close()

    # Broadcast to dashboard
    await broadcast(EVENT_SMS_SENT, {
        "id": log_id,
        "direction": "outbound",
        "phone": to_phone,
        "body": message,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


async def run():
    """Main loop for the Community Liaison Agent."""
    logger.info("Community Liaison Agent started")
    while True:
        try:
            dispatch = await dispatch_queue.get()
            
            phone = dispatch.get("phone", "+910000000000")
            msg_template = dispatch.get("message_template", "")
            resource_type = dispatch.get("resource_type", "resource")
            resource_name = dispatch.get("resource_name", "Unknown Unit")
            eta = dispatch.get("eta_minutes", 0)
            sos_id = dispatch.get("sos_id")
            
            # Safe replacement
            message = msg_template.replace("{resource_type}", str(resource_type)) \
                                  .replace("{resource_name}", str(resource_name)) \
                                  .replace("{eta_minutes}", str(eta))
            
            sms_type = "dispatch_confirm" if "mission_id" in dispatch else "notification"
            
            await send_sms(phone, message, sms_type, sos_id)
            
            dispatch_queue.task_done()
        except Exception as e:
            logger.error(f"Error processing dispatch: {e}", exc_info=True)
            await asyncio.sleep(5)
