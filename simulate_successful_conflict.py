import sys
import os
import asyncio
import json
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models import AuditLog

def inject_mock_conflict():
    db = SessionLocal()
    try:
        req_a = {
            "sos_id": 1042,
            "agent": "medical",
            "lives_at_risk": 1,
            "time_to_critical_hours": 0.5,
            "irreversibility": 0.9,
            "distance_km": 12.4,
            "reason": "Severe heart attack, patient requires immediate airlift to hospital within 30 minutes. High irreversibility."
        }
        req_b = {
            "sos_id": 1043,
            "agent": "rescue",
            "lives_at_risk": 5,
            "time_to_critical_hours": 1.5,
            "irreversibility": 0.7,
            "distance_km": 18.2,
            "reason": "Five people trapped on a sinking roof. Water rising fast, but they have approximately 90 minutes before structure collapses."
        }
        
        explanation = (
            "The Medical Agent bid for Helicopter H1 to transport a heart attack victim (1 life, 30m critical window). "
            "The Rescue Agent bid for Helicopter H1 to save 5 people on a sinking roof (5 lives, 90m critical window). "
            "Although Rescue has more lives at risk, the Medical Agent wins the auction because the heart attack has a significantly "
            "shorter critical time window and a higher irreversibility score. The helicopter will transport the medical patient first, "
            "and Logistics Agent will reroute Boat B2 (ETA 45m) to the sinking roof as a fallback."
        )

        log = AuditLog(
            event_type="conflict_resolved",
            agent_name="conflict_resolution",
            request_a=json.dumps(req_a),
            request_b=json.dumps(req_b),
            score_a=85.4,
            score_b=72.1,
            winner="a",
            fallback_assigned=json.dumps({"type": "boat", "resource_name": "B2", "eta_minutes": 45, "explanation": "Boat B2 dispatched to roof"}),
            explanation=explanation,
            created_at=datetime.now(timezone.utc)
        )
        db.add(log)
        db.commit()
        print("Successfully injected a realistic AI conflict resolution into the database!")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    inject_mock_conflict()
