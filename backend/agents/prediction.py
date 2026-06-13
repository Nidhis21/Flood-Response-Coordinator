"""
=============================================================================
PREDICTION AGENT — Flood Risk Forecasting (LangGraph + Gemini 1.5 Pro)
=============================================================================
Owner: Member 1

SUBSCRIBES TO:  alert_queue  (from Perception Agent)
PUBLISHES TO:   flood_alerts table (DB), EVENT_FLOOD_ALERT (WebSocket)
=============================================================================
"""

import os
import json
import math
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from backend.database import SessionLocal
from backend.models import FloodAlert, AuditLog, Shelter
from backend.queues import alert_queue, dispatch_queue
from backend.broadcast import broadcast, EVENT_FLOOD_ALERT
from backend.utils import rational_model, haversine
from backend.agents.perception_data import WeatherReading, RiverReading, DamDischarge, CitizenReport

from dotenv import load_dotenv
load_dotenv(override=True)

logger = logging.getLogger("agent.prediction")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# ── Static risk lookup tables for Lakhimpur revenue circles ──────────────────
ELEVATION_RISK = {
    "North Lakhimpur": 0.4,
    "Nowboicha":       0.7,
    "Dhakuakhana":     0.9,
    "Ghilamara":       0.8,
    "Gogamukh":        0.3,
    "Sisiborgaon":     0.3,
}
HISTORICAL_RISK = {
    "North Lakhimpur": 0.5,
    "Nowboicha":       0.8,
    "Dhakuakhana":     0.95,
    "Ghilamara":       0.75,
    "Gogamukh":        0.3,
    "Sisiborgaon":     0.4,
}

# =============================================================================
# LANGGRAPH TOOLS  — each tool is one step in the flood risk reasoning chain
# =============================================================================

@tool
def calculate_rainfall_risk(
    rainfall_mm_per_hr: float,
    watershed_area_ha: float,
    runoff_coefficient: float,
) -> dict:
    """
    Calculate flood risk from rainfall using the FLEWS rational model.
    Returns peak discharge Q (cumecs) and normalized rainfall_risk score (0-1).
    """
    Q = rational_model(runoff_coefficient, rainfall_mm_per_hr, watershed_area_ha)
    risk = min(1.0, Q / 4000.0)
    return {"discharge_q": round(Q, 2), "rainfall_risk": round(risk, 4)}


@tool
def calculate_river_risk(
    current_water_level_m: float,
    danger_level_m: float,
    river_name: str,
) -> dict:
    """
    Calculate river flood risk from current vs danger water levels.
    Also checks the latest upstream dam discharge from the database.
    Returns normalized river_risk score (0-1) and a dam discharge note.
    """
    level_diff = current_water_level_m - danger_level_m
    if level_diff < -2.0:
        river_risk = 0.0
    elif level_diff < 0.0:
        river_risk = 0.5 * (level_diff + 2.0) / 2.0
    elif level_diff < 1.0:
        river_risk = 0.5 + 0.4 * level_diff
    else:
        river_risk = min(1.0, 0.9 + 0.1 * (level_diff - 1.0))

    dam_note = "No upstream dam data."
    db = SessionLocal()
    try:
        dam = (
            db.query(DamDischarge)
            .filter(DamDischarge.river == river_name)
            .order_by(DamDischarge.timestamp.desc())
            .first()
        )
        if dam and dam.discharge_rate_cumecs > 500:
            factor = min(0.25, (dam.discharge_rate_cumecs - 500) / 1500.0)
            river_risk = min(1.0, river_risk + factor)
            dam_note = f"{dam.dam_name} releasing {dam.discharge_rate_cumecs} cumecs — added {factor:.2f} to river risk."
    finally:
        db.close()

    return {
        "river_risk": round(river_risk, 4),
        "level_diff_m": round(level_diff, 3),
        "dam_note": dam_note,
    }


@tool
def calculate_soil_saturation_risk(current_rainfall_mm_per_hr: float) -> dict:
    """
    Calculate soil saturation risk from cumulative 24-hour rainfall in the database.
    Returns normalized soil_saturation_risk (0-1) and estimated cumulative rain (mm).
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        readings = db.query(WeatherReading).filter(WeatherReading.timestamp >= cutoff).all()
        if readings:
            avg = sum(r.rainfall_intensity_mm_per_hr for r in readings) / len(readings)
            cumulative = avg * 24.0
        else:
            cumulative = current_rainfall_mm_per_hr * 24.0
        risk = min(1.0, cumulative / 150.0)
    finally:
        db.close()

    return {
        "soil_saturation_risk": round(risk, 4),
        "cumulative_rain_mm": round(cumulative, 1),
    }


@tool
def get_elevation_and_historical_risk() -> dict:
    """
    Get per-circle and average elevation and historical flood risk scores
    for all Lakhimpur revenue circles.
    """
    avg_elev = sum(ELEVATION_RISK.values()) / len(ELEVATION_RISK)
    avg_hist = sum(HISTORICAL_RISK.values()) / len(HISTORICAL_RISK)
    return {
        "elevation_risk_per_circle": ELEVATION_RISK,
        "historical_risk_per_circle": HISTORICAL_RISK,
        "avg_elevation_risk": round(avg_elev, 4),
        "avg_historical_risk": round(avg_hist, 4),
    }


@tool
def get_citizen_report_factor() -> dict:
    """
    Compute FHI adjustment from citizen water-level reports in the last 2 hours.
    Returns citizen_increment (0-0.15) and report count.
    """
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        reports = db.query(CitizenReport).filter(CitizenReport.timestamp >= cutoff).all()
        if not reports:
            return {"citizen_increment": 0.0, "report_count": 0}
        levels = [r.water_level_m_est for r in reports if r.water_level_m_est is not None]
        avg_level = sum(levels) / len(levels) if levels else 0.5
        increment = min(0.15, (len(reports) * 0.03) + (avg_level * 0.05))
        return {
            "citizen_increment": round(increment, 4),
            "report_count": len(reports),
            "avg_water_level_m": round(avg_level, 2),
        }
    finally:
        db.close()


@tool
def compute_fhi_and_outputs(
    rainfall_risk: float,
    river_risk: float,
    soil_saturation_risk: float,
    avg_elevation_risk: float,
    avg_historical_risk: float,
    citizen_increment: float,
    current_water_level_m: float,
    danger_level_m: float,
    discharge_q: float,
    station_lat: float,
    station_lng: float,
) -> dict:
    """
    Combine all risk factors into the Flood Hazard Index (FHI) and generate
    all 6 required outputs: severity, probability, affected circles, arrival
    time, shelter risk assessment, and GeoJSON flood polygon.
    """
    # Weighted FHI
    fhi = (
        0.30 * rainfall_risk
        + 0.30 * river_risk
        + 0.15 * soil_saturation_risk
        + 0.10 * avg_elevation_risk
        + 0.15 * avg_historical_risk
    )
    fhi = min(1.0, fhi + citizen_increment)

    # 1. Severity
    if fhi < 0.3:   severity = "low"
    elif fhi < 0.6: severity = "moderate"
    elif fhi < 0.8: severity = "high"
    else:           severity = "critical"

    # 2. Probability
    probability = round(min(99.0, max(1.0, fhi * 100.0)), 1)

    # 3. Affected circles
    affected_circles = []
    threshold = 0.4 if fhi > 0.5 else 0.3
    for circle, elev_r in ELEVATION_RISK.items():
        hist_r = HISTORICAL_RISK[circle]
        if (0.5 * fhi + 0.5 * ((elev_r + hist_r) / 2.0)) >= threshold:
            affected_circles.append(circle)
    if not affected_circles and fhi > 0.4:
        affected_circles = ["North Lakhimpur"]

    # 4. Flood arrival time
    level_diff = current_water_level_m - danger_level_m
    if level_diff > -1.5 or discharge_q > 500:
        arrival_hours = max(1.0, 12.0 - (discharge_q / 400.0) - (level_diff * 4.0))
        estimated_flood_time = (
            datetime.now(timezone.utc) + timedelta(hours=arrival_hours)
        ).isoformat() + "Z"
    else:
        arrival_hours = None
        estimated_flood_time = None

    # 5. Shelter risk assessment
    db = SessionLocal()
    try:
        shelter_risk = {}
        for s in db.query(Shelter).all():
            dist = haversine(s.lat, s.lng, station_lat, station_lng)
            if fhi < 0.3:   s_risk = "safe"
            elif fhi < 0.6: s_risk = "low" if dist < 8.0 else "safe"
            elif fhi < 0.8:
                s_risk = "high" if dist < 4.0 else ("moderate" if dist < 10.0 else "low")
            else:
                s_risk = "critical" if dist < 4.0 else (
                    "high" if dist < 8.0 else ("moderate" if dist < 15.0 else "low")
                )
            shelter_risk[s.name] = s_risk
    finally:
        db.close()

    # 6. GeoJSON flood polygon (morphs by affected circles)
    radius = max(0.005, 0.05 * fhi)
    lat_m = 1.0 + (0.4 if "Nowboicha" in affected_circles else 0)
    lng_m = 1.0 + (0.5 if "Dhakuakhana" in affected_circles else 0) + (
        0.2 if "Ghilamara" in affected_circles else 0
    )
    coords = []
    for i in range(9):
        a = i * (360.0 / 8.0) * (math.pi / 180.0)
        coords.append([
            round(station_lng + radius * lng_m * math.cos(a), 6),
            round(station_lat + radius * lat_m * math.sin(a), 6),
        ])
    geojson = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coords]},
        "properties": {
            "fhi_score": round(fhi, 3),
            "probability": probability,
            "shelter_risk": shelter_risk,
            "arrival_time": estimated_flood_time,
            "affected_circles": affected_circles,
        },
    }

    return {
        "fhi_score": round(fhi, 3),
        "severity": severity,
        "probability": probability,
        "affected_circles": affected_circles,
        "estimated_flood_time": estimated_flood_time,
        "arrival_hours": arrival_hours,
        "shelter_risk": shelter_risk,
        "geojson": geojson,
    }


# =============================================================================
# LANGGRAPH STATEGRAPH ORCHESTRATION
# =============================================================================
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END

class PredictionState(TypedDict):
    msg: dict
    
    # Intermediate risk values
    rainfall_risk: float
    discharge_q: float
    river_risk: float
    level_diff_m: float
    dam_note: str
    soil_saturation_risk: float
    cumulative_rain_mm: float
    elevation_risk_per_circle: Dict[str, float]
    historical_risk_per_circle: Dict[str, float]
    avg_elevation_risk: float
    avg_historical_risk: float
    citizen_increment: float
    report_count: int
    avg_water_level_m: float
    
    # Outputs
    fhi_score: float
    severity: str
    probability: float
    affected_circles: List[str]
    estimated_flood_time: Optional[str]
    arrival_hours: Optional[float]
    shelter_risk: Dict[str, str]
    geojson: dict
    explanation: str


def rainfall_risk_node(state: PredictionState) -> dict:
    msg = state["msg"]
    I = float(msg["rainfall_intensity_mm_per_hr"])
    A = float(msg["watershed_area_hectares"])
    C = float(msg["runoff_coefficient"])
    res = calculate_rainfall_risk.func(I, A, C)
    return {
        "discharge_q": res["discharge_q"],
        "rainfall_risk": res["rainfall_risk"]
    }


def river_risk_node(state: PredictionState) -> dict:
    msg = state["msg"]
    WL = float(msg["current_water_level_m"])
    DL = float(msg["danger_level_m"])
    res = calculate_river_risk.func(WL, DL, msg["river"])
    return {
        "river_risk": res["river_risk"],
        "level_diff_m": res["level_diff_m"],
        "dam_note": res["dam_note"]
    }


def soil_saturation_node(state: PredictionState) -> dict:
    msg = state["msg"]
    I = float(msg["rainfall_intensity_mm_per_hr"])
    res = calculate_soil_saturation_risk.func(I)
    return {
        "soil_saturation_risk": res["soil_saturation_risk"],
        "cumulative_rain_mm": res["cumulative_rain_mm"]
    }


def vulnerability_node(state: PredictionState) -> dict:
    res = get_elevation_and_historical_risk.func()
    return {
        "elevation_risk_per_circle": res["elevation_risk_per_circle"],
        "historical_risk_per_circle": res["historical_risk_per_circle"],
        "avg_elevation_risk": res["avg_elevation_risk"],
        "avg_historical_risk": res["avg_historical_risk"]
    }


def citizen_reports_node(state: PredictionState) -> dict:
    res = get_citizen_report_factor.func()
    return {
        "citizen_increment": res["citizen_increment"],
        "report_count": res["report_count"],
        "avg_water_level_m": res.get("avg_water_level_m", 0.0)
    }


def fhi_outputs_node(state: PredictionState) -> dict:
    msg = state["msg"]
    WL = float(msg["current_water_level_m"])
    DL = float(msg["danger_level_m"])
    lat = float(msg["latitude"])
    lng = float(msg["longitude"])
    
    res = compute_fhi_and_outputs.func(
        rainfall_risk=state["rainfall_risk"],
        river_risk=state["river_risk"],
        soil_saturation_risk=state["soil_saturation_risk"],
        avg_elevation_risk=state["avg_elevation_risk"],
        avg_historical_risk=state["avg_historical_risk"],
        citizen_increment=state["citizen_increment"],
        current_water_level_m=WL,
        danger_level_m=DL,
        discharge_q=state["discharge_q"],
        station_lat=lat,
        station_lng=lng,
    )
    return {
        "fhi_score": res["fhi_score"],
        "severity": res["severity"],
        "probability": res["probability"],
        "affected_circles": res["affected_circles"],
        "estimated_flood_time": res["estimated_flood_time"],
        "arrival_hours": res["arrival_hours"],
        "shelter_risk": res["shelter_risk"],
        "geojson": res["geojson"],
    }


def explanation_node(state: PredictionState) -> dict:
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    use_llm = True
    if not GROQ_API_KEY or GROQ_API_KEY == "your-groq-api-key-here":
        logger.warning("No GROQ_API_KEY found. Prediction Agent will run in fast offline math mode.")
        use_llm = False
    
    if use_llm:
        try:
            llm = ChatGroq(
                model="llama-3.1-8b-instant",
                temperature=0,
            )
            
            prompt = (
                f"You are the Flood Prediction Agent for Lakhimpur district, Assam.\n"
                f"Write a brief, plain-English summary of the flood risk for district administrators explaining what is happening and why.\n"
                f"Target audience: non-technical government officials.\n\n"
                f"Here is the risk assessment telemetry:\n"
                f"- River: {state['msg']['river']} at {state['msg']['station']}\n"
                f"- Severity: {state['severity'].upper()} (FHI Score: {state['fhi_score']:.2f}, Probability: {state['probability']}%)\n"
                f"- Peak Discharge: {state['discharge_q']} cumecs (Rainfall Risk: {state['rainfall_risk']})\n"
                f"- Water Level: {state['msg']['current_water_level_m']}m (danger: {state['msg']['danger_level_m']}m, River Risk: {state['river_risk']})\n"
                f"- Upstream Dam telemetry: {state['dam_note']}\n"
                f"- Soil Saturation: {state['soil_saturation_risk']} (24h cumulative rain: {state['cumulative_rain_mm']}mm)\n"
                f"- Vulnerability: Avg Elevation Risk {state['avg_elevation_risk']}, Avg Historical Risk {state['avg_historical_risk']}\n"
                f"- Citizen Ground Truth: {state['report_count']} reports in last 2h (increment added: {state['citizen_increment']})\n"
                f"- Affected Revenue Circles: {', '.join(state['affected_circles'])}\n"
                f"- Estimated Flood Arrival Time: {state['estimated_flood_time'] or 'N/A'}\n"
                f"- Shelters Risk: {json.dumps(state['shelter_risk'])}"
            )
            
            response = llm.invoke(prompt)
            explanation = response.content
        except Exception as e:
            logger.warning(f"Error calling Gemini in explanation_node: {e}. Falling back to structured explanation.")
            explanation = _get_fallback_explanation(state)
    else:
        explanation = _get_fallback_explanation(state)
        
    return {"explanation": explanation}


def _get_fallback_explanation(state: PredictionState) -> str:
    msg = state["msg"]
    return (
        f"[OFFLINE STATEGRAPH] FloodAlert ({state['severity'].upper()}) for Lakhimpur. "
        f"FHI: {state['fhi_score']:.2f}, Probability: {state['probability']}%, "
        f"Discharge: {state['discharge_q']} cumecs, "
        f"Water: {msg['current_water_level_m']}m (danger: {msg['danger_level_m']}m). "
        f"Circles: {', '.join(state['affected_circles'])}."
    )


# Compile the StateGraph workflow
workflow = StateGraph(PredictionState)
workflow.add_node("rainfall_risk", rainfall_risk_node)
workflow.add_node("river_risk", river_risk_node)
workflow.add_node("soil_saturation", soil_saturation_node)
workflow.add_node("vulnerability", vulnerability_node)
workflow.add_node("citizen_reports", citizen_reports_node)
workflow.add_node("fhi_outputs", fhi_outputs_node)
workflow.add_node("explanation", explanation_node)

workflow.set_entry_point("rainfall_risk")
workflow.add_edge("rainfall_risk", "river_risk")
workflow.add_edge("river_risk", "soil_saturation")
workflow.add_edge("soil_saturation", "vulnerability")
workflow.add_edge("vulnerability", "citizen_reports")
workflow.add_edge("citizen_reports", "fhi_outputs")
workflow.add_edge("fhi_outputs", "explanation")
workflow.add_edge("explanation", END)

prediction_graph = workflow.compile()


def _invoke_graph_agent(msg: dict) -> tuple[dict, str]:
    """Invoke the LangGraph StateGraph prediction agent (synchronously)."""
    initial_state = {"msg": msg}
    final_state = prediction_graph.invoke(initial_state)
    
    prediction = {
        "fhi_score": final_state["fhi_score"],
        "severity": final_state["severity"],
        "probability": final_state["probability"],
        "affected_circles": final_state["affected_circles"],
        "estimated_flood_time": final_state["estimated_flood_time"],
        "arrival_hours": final_state["arrival_hours"],
        "shelter_risk": final_state["shelter_risk"],
        "geojson": final_state["geojson"],
        "discharge_q": final_state["discharge_q"]
    }
    explanation = final_state["explanation"]
    return prediction, explanation


# =============================================================================
# MAIN AGENT LOOP
# =============================================================================

async def run():
    """
    Main loop for the Prediction Agent.
    Reads from alert_queue, runs LangGraph StateGraph agent,
    saves FloodAlert to DB, broadcasts EVENT_FLOOD_ALERT, writes audit_log.
    """
    logger.info("Prediction Agent started. Mode: LangGraph StateGraph workflow")

    while True:
        try:
            msg = await alert_queue.get()
            logger.info(f"Processing alert from {msg.get('station')} via {msg.get('source')}")

            # ── Run prediction via LangGraph StateGraph ────────────────────
            try:
                prediction, explanation = await asyncio.to_thread(_invoke_graph_agent, msg)
            except Exception as agent_err:
                logger.error(f"StateGraph Agent error: {agent_err}")
                await asyncio.sleep(5)
                alert_queue.task_done()
                continue

            # ── Save FloodAlert to database ───────────────────────────────
            db = SessionLocal()
            try:
                alert = FloodAlert(
                    district=msg.get("district", "Lakhimpur"),
                    severity=prediction["severity"],
                    discharge_q=round(float(prediction.get("discharge_q", 0)), 2),
                    estimated_flood_time=(
                        datetime.fromisoformat(
                            prediction["estimated_flood_time"].rstrip("Z")
                        ).replace(tzinfo=timezone.utc)
                        if prediction.get("estimated_flood_time")
                        else None
                    ),
                    affected_circles=json.dumps(prediction["affected_circles"]),
                    geojson_polygon=json.dumps(prediction["geojson"]),
                    fhi_score=round(prediction["fhi_score"], 3),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(alert)

                # Audit log
                audit = AuditLog(
                    event_type="flood_alert_generated",
                    agent_name="prediction",
                    request_a=json.dumps({
                        "rainfall_mm_per_hr": msg.get("rainfall_intensity_mm_per_hr"),
                        "water_level_m": msg.get("current_water_level_m"),
                        "danger_level_m": msg.get("danger_level_m"),
                        "source": msg.get("source"),
                    }),
                    request_b=json.dumps({
                        "fhi_score": prediction["fhi_score"],
                        "severity": prediction["severity"],
                        "affected_circles": prediction["affected_circles"],
                    }),
                    score_a=prediction["fhi_score"],
                    score_b=prediction["probability"],
                    winner="N/A",
                    fallback_assigned="N/A",
                    explanation=explanation,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(audit)
                db.commit()
                db.refresh(alert)

                # ── Broadcast EVENT_FLOOD_ALERT ───────────────────────────
                await broadcast(EVENT_FLOOD_ALERT, {
                    "district": alert.district,
                    "severity": alert.severity,
                    "discharge_q": alert.discharge_q,
                    "fhi_score": alert.fhi_score,
                    "probability": prediction["probability"],
                    "affected_circles": prediction["affected_circles"],
                    "estimated_flood_time": prediction.get("estimated_flood_time"),
                    "shelter_risk": prediction["shelter_risk"],
                    "geojson_polygon": prediction["geojson"],
                })

                logger.info(
                    f"Alert #{alert.id} saved — "
                    f"Severity: {alert.severity.upper()}, FHI: {alert.fhi_score}"
                )

                # ── Automated Mass Broadcast for Severe Alerts ─────────────────
                if alert.severity in ["high", "critical"]:
                    dummy_phones = ["+919876543211", "+919876543212", "+919876543213"]
                    circles_str = ", ".join(prediction["affected_circles"])
                    arrival_val = prediction.get('arrival_hours', 'N/A')
                    arrival_str = f"{arrival_val:.1f}" if isinstance(arrival_val, (int, float)) else str(arrival_val)
                    broadcast_msg = f"EOC FLOOD ALERT ({alert.severity.upper()}): Immediate danger in {circles_str}. Move to higher ground or assigned shelters now. ETA: {arrival_str} hours."
                    
                    for phone in dummy_phones:
                        await dispatch_queue.put({
                            "phone": phone,
                            "message_template": broadcast_msg,
                            "resource_type": "broadcast",
                            "resource_name": "EOC",
                            "eta_minutes": 0,
                            "sos_id": -1
                        })
                    logger.info(f"Pushed mass broadcast for {len(dummy_phones)} citizens to dispatch_queue.")

            except Exception as db_err:
                logger.error(f"DB error in Prediction Agent: {db_err}")
                db.rollback()
            finally:
                db.close()

            alert_queue.task_done()

        except Exception as e:
            logger.error(f"Unexpected error in Prediction Agent: {e}")
            await asyncio.sleep(5)
