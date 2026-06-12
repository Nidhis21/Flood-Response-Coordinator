import sys
import os
import asyncio
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import SMSLog

def inject():
    db = SessionLocal()
    try:
        phones = ["+919876543211", "+919876543212", "+919876543213"]
        message = "EOC FLOOD ALERT (CRITICAL): Immediate danger in North Lakhimpur, Nowboicha. Move to higher ground or assigned shelters now. ETA: 1.5 hours."
        
        for phone in phones:
            log_entry = SMSLog(
                direction="outbound",
                phone=phone,
                message=message,
                sms_type="broadcast",
                related_sos_id=None,
                agent_name="liaison",
                delivery_status="console_printed"
            )
            db.add(log_entry)
        db.commit()
        print("Injected 3 mock outbound broadcast SMS messages.")
    except Exception as e:
        print(f"Error injecting: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inject()
