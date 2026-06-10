"""
=============================================================================
PREDICTION AGENT — Flood Risk Forecasting
=============================================================================
Owner: Member 1
=============================================================================

SUBSCRIBES TO:
  - alert_queue  ←  reads raw rainfall/water-level data from Perception Agent

PUBLISHES TO:
  - None (writes flood_alerts to DB directly)

BROADCAST EVENTS FIRED:
  - flood_alert  →  fired when a new severity update is generated
    Payload: { district, severity, discharge_q, fhi_score, affected_circles }

=============================================================================
"""

import os
import json
import math
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from backend.database import SessionLocal
from backend.models import FloodAlert, AuditLog, Shelter
from backend.queues import alert_queue
from backend.broadcast import broadcast, EVENT_FLOOD_ALERT
from backend.utils import rational_model, haversine
from backend.agents.perception_data import WeatherReading, RiverReading, DamDischarge, CitizenReport

logger = logging.getLogger("agent.prediction")

# Static lookups for Lakhimpur district revenue circles
ELEVATION_RISK = {
    "North Lakhimpur": 0.4,
    "Nowboicha": 0.7,
    "Dhakuakhana": 0.9,
    "Ghilamara": 0.8,
    "Gogamukh": 0.3,
    "Sisiborgaon": 0.3,
}

HISTORICAL_RISK = {
    "North Lakhimpur": 0.5,
    "Nowboicha": 0.8,
    "Dhakuakhana": 0.95,
    "Ghilamara": 0.75,
    "Gogamukh": 0.3,
    "Sisiborgaon": 0.4,
}


def compute_geojson_polygon(center_lat: float, center_lng: float, fhi: float, affected_circles: list) -> dict:
    """
    Generates a morphing GeoJSON polygon representation centered around the station
    with a radius proportional to the Flood Hazard Index (FHI).
    """
    # Scale radius by FHI
    radius = 0.05 * fhi
    if radius <= 0:
        radius = 0.005
        
    coordinates = []
    # Create an 8-sided polygon (octagon)
    for i in range(9):  # 9 points to close the loop
        angle = i * (360.0 / 8.0)
        angle_rad = angle * (math.pi / 180.0)
        
        # Morph shape based on which circles are affected
        lat_multiplier = 1.0
        lng_multiplier = 1.0
        if "Nowboicha" in affected_circles:
            lat_multiplier += 0.4
        if "Dhakuakhana" in affected_circles:
            lng_multiplier += 0.5
        if "Ghilamara" in affected_circles:
            lng_multiplier += 0.2
            
        lat = center_lat + radius * lat_multiplier * math.sin(angle_rad)
        lng = center_lng + radius * lng_multiplier * math.cos(angle_rad)
        coordinates.append([round(lng, 6), round(lat, 6)])
        
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coordinates]
        },
        "properties": {
            "name": f"Flood Zone - Lakhimpur (FHI: {fhi:.2f})",
            "fhi_score": round(fhi, 2),
            "affected_circles": affected_circles
        }
    }


async def run():
    """
    Main loop for the Prediction Agent.
    Reads from alert_queue, computes flood risk, writes alerts to DB.
    """
    logger.info("Prediction Agent started. Listening on alert_queue...")
    
    while True:
        try:
            # Blocks until a message is received from Perception Agent
            msg = await alert_queue.get()
            logger.info(f"Received alert_queue message from station {msg.get('station')}")
            
            # 1. Parse Perception inputs
            I = float(msg.get("rainfall_intensity_mm_per_hr", 0.0))
            A = float(msg.get("watershed_area_hectares", 134600.0))
            C = float(msg.get("runoff_coefficient", 0.233))
            WL = float(msg.get("current_water_level_m", 94.45))
            DL = float(msg.get("danger_level_m", 95.02))
            station_lat = float(msg.get("latitude", 27.23))
            station_lng = float(msg.get("longitude", 94.10))
            
            # 2. Compute peak discharge using FLEWS rational model
            Q = rational_model(C, I, A)
            
            # 3. Calculate Rainfall Risk Score (0-1)
            # Normalized based on typical maximum discharge rates in Ranganadi basin
            rainfall_risk = min(1.0, Q / 4000.0)
            
            # 4. Calculate River Level Risk Score (0-1)
            level_diff = WL - DL
            if level_diff < -2.0:
                river_risk = 0.0
            elif level_diff < 0.0:
                # scale from 0 to 0.5
                river_risk = 0.5 * (level_diff + 2.0) / 2.0
            elif level_diff < 1.0:
                # scale from 0.5 to 0.9
                river_risk = 0.5 + 0.4 * level_diff
            else:
                # scale from 0.9 to 1.0
                river_risk = min(1.0, 0.9 + 0.1 * (level_diff - 1.0))
                
            # Open DB session to fetch additional context
            db = SessionLocal()
            try:
                # Include Upstream Dam Discharge in River Risk
                latest_dam = (
                    db.query(DamDischarge)
                    .filter(DamDischarge.river == msg.get("river", "Ranganadi"))
                    .order_by(DamDischarge.timestamp.desc())
                    .first()
                )
                if latest_dam and latest_dam.discharge_rate_cumecs > 500:
                    dam_factor = min(0.25, (latest_dam.discharge_rate_cumecs - 500) / 1500.0)
                    river_risk = min(1.0, river_risk + dam_factor)
                    logger.info(f"Factored in dam discharge: +{dam_factor:.2f} river risk (Discharge: {latest_dam.discharge_rate_cumecs} cumecs)")
                
                # 5. Calculate Soil Saturation Risk (0-1)
                # Compute cumulative rainfall over the last 24 hours
                cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
                recent_readings = (
                    db.query(WeatherReading)
                    .filter(WeatherReading.timestamp >= cutoff_24h)
                    .all()
                )
                if recent_readings:
                    avg_intensity = sum(r.rainfall_intensity_mm_per_hr for r in recent_readings) / len(recent_readings)
                    cumulative_rain_est = avg_intensity * 24.0
                else:
                    cumulative_rain_est = I * 24.0  # fallback estimation
                
                # 150mm cumulative rain represents 100% soil saturation risk
                soil_saturation_risk = min(1.0, cumulative_rain_est / 150.0)
                
                # 6. Calculate Elevation and Historical Risk (averaged across the district circles)
                avg_elevation_risk = sum(ELEVATION_RISK.values()) / len(ELEVATION_RISK)
                avg_historical_risk = sum(HISTORICAL_RISK.values()) / len(HISTORICAL_RISK)
                
                # 7. Combine all factors into initial FHI score
                # Weights: Rainfall 30%, River 30%, Soil Saturation 15%, Elevation 10%, Historical 15%
                fhi = (
                    0.30 * rainfall_risk
                    + 0.30 * river_risk
                    + 0.15 * soil_saturation_risk
                    + 0.10 * avg_elevation_risk
                    + 0.15 * avg_historical_risk
                )
                
                # Adjust FHI using Citizen Reports (Ground truth verification)
                cutoff_2h = datetime.now(timezone.utc) - timedelta(hours=2)
                recent_citizen_reports = (
                    db.query(CitizenReport)
                    .filter(CitizenReport.timestamp >= cutoff_2h)
                    .all()
                )
                if recent_citizen_reports:
                    cit_count = len(recent_citizen_reports)
                    cit_levels = [r.water_level_m_est for r in recent_citizen_reports if r.water_level_m_est is not None]
                    cit_avg_level = sum(cit_levels) / len(cit_levels) if cit_levels else 0.5
                    
                    citizen_increment = min(0.15, (cit_count * 0.03) + (cit_avg_level * 0.05))
                    fhi = min(1.0, fhi + citizen_increment)
                    logger.info(f"Factored in {cit_count} citizen reports: +{citizen_increment:.2f} FHI score")
                
                # 8. Output Generation
                # Generate Severity Level
                if fhi < 0.3:
                    severity = "low"
                elif fhi < 0.6:
                    severity = "moderate"
                elif fhi < 0.8:
                    severity = "high"
                else:
                    severity = "critical"
                    
                # Generate Probability (1% - 99%)
                probability = min(99.0, max(1.0, fhi * 100.0))
                
                # Generate Affected Revenue Circles
                affected_circles = []
                for circle, elev_r in ELEVATION_RISK.items():
                    hist_r = HISTORICAL_RISK[circle]
                    # Compute circle-specific vulnerability
                    circle_score = 0.5 * fhi + 0.5 * ((elev_r + hist_r) / 2.0)
                    # Lower thresholds mean more circles affected as FHI rises
                    threshold = 0.4 if fhi > 0.5 else 0.3
                    if circle_score >= threshold:
                        affected_circles.append(circle)
                
                # Default to at least the closest circle if none matched but FHI is high
                if not affected_circles and fhi > 0.4:
                    affected_circles = ["North Lakhimpur"]
                    
                # Generate Flood Arrival Time Estimate (hours)
                # Shorter arrival time if water level is high/rising rapidly or discharge is extreme
                if level_diff > -1.5 or Q > 500:
                    arrival_hours = max(1.0, 12.0 - (Q / 400.0) - (level_diff * 4.0))
                    estimated_flood_time = datetime.now(timezone.utc) + timedelta(hours=arrival_hours)
                else:
                    estimated_flood_time = None
                    
                # Generate Shelter Risk Assessment
                # Fetch all shelters to evaluate
                shelters = db.query(Shelter).all()
                shelter_risk_assessment = {}
                for s in shelters:
                    dist = haversine(s.lat, s.lng, station_lat, station_lng)
                    # Determine risk level based on distance and FHI severity
                    if fhi < 0.3:
                        s_risk = "safe"
                    elif fhi < 0.6:
                        s_risk = "low" if dist < 8.0 else "safe"
                    elif fhi < 0.8:
                        if dist < 4.0:
                            s_risk = "high"
                        elif dist < 10.0:
                            s_risk = "moderate"
                        else:
                            s_risk = "low"
                    else:  # critical
                        if dist < 4.0:
                            s_risk = "critical"
                        elif dist < 8.0:
                            s_risk = "high"
                        elif dist < 15.0:
                            s_risk = "moderate"
                        else:
                            s_risk = "low"
                    shelter_risk_assessment[s.name] = s_risk
                    
                # Generate GeoJSON polygon
                geojson_dict = compute_geojson_polygon(station_lat, station_lng, fhi, affected_circles)
                # Store the extra prediction metrics inside the properties object
                geojson_dict["properties"]["probability"] = round(probability, 1)
                geojson_dict["properties"]["shelter_risk"] = shelter_risk_assessment
                geojson_dict["properties"]["arrival_time"] = estimated_flood_time.isoformat() + "Z" if estimated_flood_time else None
                
                # 9. Save FloodAlert record in database
                alert = FloodAlert(
                    district=msg.get("district", "Lakhimpur"),
                    severity=severity,
                    discharge_q=round(Q, 2),
                    estimated_flood_time=estimated_flood_time,
                    affected_circles=json.dumps(affected_circles),
                    geojson_polygon=json.dumps(geojson_dict),
                    fhi_score=round(fhi, 3),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(alert)
                db.commit()
                db.refresh(alert)
                
                # 10. Broadcast EVENT_FLOOD_ALERT via WebSocket
                broadcast_payload = {
                    "district": alert.district,
                    "severity": alert.severity,
                    "discharge_q": alert.discharge_q,
                    "fhi_score": alert.fhi_score,
                    "probability": round(probability, 1),
                    "affected_circles": affected_circles,
                    "estimated_flood_time": estimated_flood_time.isoformat() + "Z" if estimated_flood_time else None,
                    "shelter_risk": shelter_risk_assessment,
                    "geojson_polygon": geojson_dict,
                }
                await broadcast(EVENT_FLOOD_ALERT, broadcast_payload)
                
                # 11. Write Audit Log
                explanation_str = (
                    f"Generated FloodAlert #{alert.id} ({severity.upper()}) for Lakhimpur district. "
                    f"FHI score: {fhi:.2f}, Probability: {probability:.1f}%. "
                    f"Calculated peak discharge: {Q:.1f} cumecs. "
                    f"Current water level: {WL}m (danger: {DL}m). "
                    f"Estimated arrival: {f'{arrival_hours:.1f} hours' if estimated_flood_time else 'N/A'}. "
                    f"Affected Circles: {', '.join(affected_circles)}."
                )
                
                audit = AuditLog(
                    event_type="flood_alert_generated",
                    agent_name="prediction",
                    request_a=json.dumps({
                        "rainfall_intensity_mm_per_hr": I,
                        "water_level_m": WL,
                        "danger_level_m": DL,
                        "source": msg.get("source")
                    }),
                    request_b=json.dumps({
                        "rainfall_risk": rainfall_risk,
                        "river_risk": river_risk,
                        "soil_saturation_risk": soil_saturation_risk,
                        "avg_elevation_risk": avg_elevation_risk,
                        "avg_historical_risk": avg_historical_risk,
                    }),
                    score_a=fhi,
                    score_b=probability,
                    winner="N/A",
                    fallback_assigned="N/A",
                    explanation=explanation_str,
                    created_at=datetime.now(timezone.utc),
                )
                db.add(audit)
                db.commit()
                
                logger.info(f"Prediction Alert #{alert.id} processed successfully. Severity: {severity.upper()}, FHI: {fhi:.2f}")
                
            except Exception as dbe:
                logger.error(f"Database error in Prediction Agent: {dbe}")
                db.rollback()
            finally:
                db.close()
                
            # Signal queue task completion
            alert_queue.task_done()
            
        except Exception as e:
            logger.error(f"Unexpected error in Prediction Agent: {e}")
            await asyncio.sleep(5)  # Backoff if we hit an unexpected loop crash
