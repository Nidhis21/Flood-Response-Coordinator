import os
import json
import logging
import asyncio
from datetime import datetime, timezone

from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.database import SessionLocal
from backend.models import AuditLog, Resource, FloodAlert, SOSEvent, Mission
from backend.queues import conflict_queue, resolved_queue, dispatch_queue
from backend.broadcast import broadcast, EVENT_CONFLICT_RESOLVED

CURRENT_CONFLICT = {}
from backend.prompts import CONFLICT_RESOLUTION_SYSTEM_PROMPT
from backend.utils import run_priority_auction as auction_math

logger = logging.getLogger("agent.conflict")
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"


@tool
def run_priority_auction(request_a: dict, request_b: dict, disaster_phase: str = "peak") -> dict:
    """Run the mathematical priority auction to determine who gets the resource. MUST BE CALLED for every conflict."""
    return auction_math(request_a, request_b, disaster_phase)


@tool
def find_fallback_resource(resource_type: str, exclude_id: int, lat: float, lng: float) -> dict:
    """Find the nearest available resource of the same type."""
    db = SessionLocal()
    try:
        from backend.utils import haversine
        resources = db.query(Resource).filter(
            Resource.type == resource_type,
            Resource.status == "available",
            Resource.id != exclude_id
        ).all()
        if not resources:
            return {"error": "No available resources found. User must be added to a wait queue."}
            
        best = None
        min_dist = 999999.0
        for r in resources:
            d = haversine(r.lat, r.lng, lat, lng)
            if d < min_dist:
                min_dist = d
                best = r
        if best:
            return {"resource_id": best.id, "resource_name": best.name, "distance_km": round(min_dist, 1)}
        return {"error": "No fallback found."}
    finally:
        db.close()


@tool
async def send_resolution(
    winning_agent: str,
    winning_sos_id: int,
    loser_agent: str,
    losing_sos_id: int,
    resource_id: int,
    resource_name: str,
    reason: str,
    fallback_plan: str,
    score_winner: float,
    score_loser: float,
    sms_to_loser: str,
    sms_to_officer: str
) -> str:
    """Submit the final conflict resolution decision and trigger outbound SMS actions."""
    db = SessionLocal()
    try:
        log = AuditLog(
            event_type="conflict_resolved",
            agent_name="conflict_resolution",
            request_a=json.dumps(CURRENT_CONFLICT.get("req_a", {"sos_id": winning_sos_id, "agent": winning_agent})),
            request_b=json.dumps(CURRENT_CONFLICT.get("req_b", {"sos_id": losing_sos_id, "agent": loser_agent})),
            score_a=score_winner,
            score_b=score_loser,
            winner=winning_agent,
            fallback_assigned=fallback_plan,
            explanation=reason
        )
        db.add(log)
        db.commit()
    finally:
        db.close()

    payload = {
        "winning_agent": winning_agent,
        "winning_sos_id": winning_sos_id,
        "loser_agent": loser_agent,
        "losing_sos_id": losing_sos_id,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "reason": reason,
        "fallback_plan": fallback_plan,
        "sms_to_loser": sms_to_loser,
        "sms_to_officer": sms_to_officer,
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }
    logger.warning(f"send_resolution called! Winner: {winning_agent}, Fallback: {fallback_plan}")
    await resolved_queue.put(payload)
    await broadcast(EVENT_CONFLICT_RESOLVED, payload)
    
    # Push SMS to dispatch_queue for Liaison Agent
    if sms_to_loser:
        await dispatch_queue.put({
            "resource_type": "sms_notification",
            "phone": "+910000000000",  # We don't have losing phone handy here, so placeholder
            "message_template": sms_to_loser,
            "sos_id": losing_sos_id
        })
    if sms_to_officer:
        await dispatch_queue.put({
            "resource_type": "sms_notification",
            "phone": "+910000000001",  # Officer placeholder
            "message_template": sms_to_officer,
            "sos_id": -1
        })
    
    return "Resolution sent successfully. You can end your turn."


async def run():
    """Main loop for the Conflict Resolution Agent."""
    logger.info("Conflict Resolution Agent started")
    
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    if not GROQ_API_KEY or GROQ_API_KEY == "your-groq-api-key-here":
        logger.warning("No GROQ_API_KEY found. Conflict Agent will run in offline deterministic mode.")
        agent = None
    else:
        llm = ChatGroq(model="llama-3.1-8b-instant", temperature=0)
        tools = [run_priority_auction, find_fallback_resource, send_resolution]
        agent = create_react_agent(llm, tools, prompt=CONFLICT_RESOLUTION_SYSTEM_PROMPT)

    print("Conflict Agent started loop!")
    while True:
        try:
            conflict_data = await conflict_queue.get()
            print(f"Got conflict data: {conflict_data.get('resource_name')}")
            resource_id = conflict_data.get("resource_id", -1)
            resource_name = conflict_data.get("resource_name", "Unknown")
            req_a = conflict_data.get("request_a")
            req_b = conflict_data.get("request_b")

            if req_a is None:
                conflict_queue.task_done()
                continue
                
            db = SessionLocal()
            try:
                latest_alert = db.query(FloodAlert).order_by(FloodAlert.id.desc()).first()
                phase = latest_alert.disaster_phase if latest_alert else "peak"
            finally:
                db.close()

            # Handle resource exhaustion single-request fallback
            if req_b is None:
                logger.info(f"Handling single request exhaustion for SOS #{req_a.get('sos_id')}")
                fallback = find_fallback_resource.invoke({
                    "resource_type": "boat" if req_a.get("type")=="rescue" else "medical_team", 
                    "exclude_id": -1, 
                    "lat": 27.2, "lng": 94.1
                })
                reason = "No active mission found to challenge; assigning fallback directly."
                await send_resolution.ainvoke({
                    "winning_agent": req_a.get("agent"),
                    "winning_sos_id": req_a.get("sos_id"),
                    "loser_agent": "none",
                    "losing_sos_id": -1,
                    "resource_id": fallback.get("resource_id", -1),
                    "resource_name": fallback.get("resource_name", "Waitlist"),
                    "reason": reason,
                    "fallback_plan": "Waitlisted" if "error" in fallback else f"Assigned {fallback['resource_name']}",
                    "score_winner": 1.0,
                    "score_loser": 0.0,
                    "sms_to_loser": "Help is delayed. We will dispatch as soon as a unit frees up.",
                    "sms_to_officer": "Resource exhaustion event recorded."
                })
                conflict_queue.task_done()
                continue

            print(f"Evaluating conflict for resource {resource_name}: SOS #{req_a.get('sos_id')} vs SOS #{req_b.get('sos_id')}")

            CURRENT_CONFLICT["req_a"] = win_req if (agent is None and req_a.get("sos_id") == win_req.get("sos_id")) else req_a
            CURRENT_CONFLICT["req_b"] = lose_req if (agent is None and req_b.get("sos_id") == lose_req.get("sos_id")) else req_b

            # We will assign the correct winner/loser to req_a/req_b after LLM resolves it.
            # But the UI expects request_a to be the winner and request_b to be the loser.
            # Wait, the LLM sets winning_sos_id. We can swap them in send_resolution!
            
            if agent:
                message = (
                    f"Conflict over resource {resource_name} (ID {resource_id}).\n"
                    f"Disaster Phase: {phase}\n"
                    f"Request A: {json.dumps(req_a)}\n"
                    f"Request B: {json.dumps(req_b)}"
                )
                try:
                    logger.warning("Invoking LangGraph agent...")
                    for attempt in range(3):
                        try:
                            res = await agent.ainvoke({"messages": [("user", message)]})
                            logger.warning(f"LangGraph agent finished! Output: {res}")
                            break
                        except Exception as e:
                            if "429" in str(e) and attempt < 2:
                                logger.warning(f"Rate limit hit! Waiting 20 seconds before retry {attempt + 1}/3...")
                                await asyncio.sleep(20)
                            else:
                                raise e
                except Exception as e:
                    logger.error(f"LangGraph execution failed: {e}")
                    # Fallback to deterministic
                    agent = None

            # Deterministic fallback (offline mode or LangGraph failure)
            if not agent:
                res = auction_math(req_a, req_b, phase)
                winner_is_a = (res["winner"] == "a")
                win_req = req_a if winner_is_a else req_b
                lose_req = req_b if winner_is_a else req_a
                
                fallback = find_fallback_resource.invoke({
                    "resource_type": "boat", "exclude_id": resource_id, 
                    "lat": 27.2, "lng": 94.1
                })
                
                fallback_name = "Waitlisted" if "error" in fallback else f"Assigned {fallback.get('resource_name')}"
                
                reason = (
                    f"⚠️ [Deterministic Offline Mode] "
                    f"The {win_req.get('agent').capitalize()} Agent secured the resource over the {lose_req.get('agent').capitalize()} Agent. "
                    f"Using the mathematical priority auction (Score: {res['score_a']} vs {res['score_b']}), "
                    f"priority was granted to {win_req.get('agent').capitalize()} based on critical evaluation of lives at risk, "
                    f"time to irreversibility, and distance. The {lose_req.get('agent').capitalize()} Agent's request has been "
                    f"diverted to fallback plan: {fallback_name}."
                )

                await send_resolution.ainvoke({
                    "winning_agent": win_req.get("agent"),
                    "winning_sos_id": win_req.get("sos_id"),
                    "loser_agent": lose_req.get("agent"),
                    "losing_sos_id": lose_req.get("sos_id"),
                    "resource_id": resource_id,
                    "resource_name": resource_name,
                    "reason": reason,
                    "fallback_plan": fallback_name,
                    "score_winner": res["score_a"] if winner_is_a else res["score_b"],
                    "score_loser": res["score_b"] if winner_is_a else res["score_a"],
                    "sms_to_loser": "Your request is waitlisted. Help is delayed.",
                    "sms_to_officer": f"Conflict resolved offline. {win_req.get('agent')} won."
                })

            conflict_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in Conflict Resolution Agent: {e}", exc_info=True)
            await asyncio.sleep(5)
