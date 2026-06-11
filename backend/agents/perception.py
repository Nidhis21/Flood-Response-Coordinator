"""
=============================================================================
PERCEPTION AGENT — Environmental Data Ingestion
=============================================================================
Owner: Member 1
=============================================================================

SUBSCRIBES TO:
  - None (this is the data source — entry point of the pipeline)

PUBLISHES TO:
  - alert_queue  →  pushes raw rainfall/water-level readings for Prediction Agent

BROADCAST EVENTS FIRED:
  - None (Perception collects data; Prediction interprets and broadcasts)

OFFLINE MODE:
  - When OFFLINE_MODE=true, reads from backend/mock_rainfall.json
  - When OFFLINE_MODE=false, calls Open-Meteo API for real-time rainfall data

=============================================================================
"""

import os
import json
import asyncio
import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from backend.database import SessionLocal, Base, engine
from backend.queues import alert_queue
from backend.agents.perception_data import WeatherReading, RiverReading

logger = logging.getLogger("agent.perception")

# Read OFFLINE_MODE from environment variables
OFFLINE_MODE = os.getenv("OFFLINE_MODE", "true").lower() == "true"
POLL_INTERVAL = int(os.getenv("PERCEPTION_POLL_INTERVAL", "60"))

# Ensure perception tables are created
try:
    Base.metadata.create_all(bind=engine)
    logger.info("Perception data tables initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize perception data tables: {e}")


def _fetch_open_meteo_api() -> dict:
    """Synchronous fetch helper for Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast?latitude=27.23&longitude=94.10&hourly=rain"
    req = urllib.request.Request(url, headers={'User-Agent': 'Flood-Response-Coordinator'})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode())


async def fetch_weather_online() -> float:
    """
    Fetches real-time rainfall data from Open-Meteo API.
    Returns rainfall intensity in mm/hr for the current hour.
    """
    try:
        data = await asyncio.to_thread(_fetch_open_meteo_api)
        
        current_utc_dt = datetime.now(timezone.utc)
        times = data.get("hourly", {}).get("time", [])
        rains = data.get("hourly", {}).get("rain", [])
        
        rain_mm = 0.0
        found = False
        
        # Try to find the matching hourly slot
        for t, r in zip(times, rains):
            try:
                t_dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
                if abs((current_utc_dt - t_dt).total_seconds()) < 1800:
                    rain_mm = r
                    found = True
                    break
            except ValueError:
                continue
                
        if not found and times:
            # Fallback to the closest time index
            min_diff = float('inf')
            for t, r in zip(times, rains):
                try:
                    t_dt = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
                    diff = abs((current_utc_dt - t_dt).total_seconds())
                    if diff < min_diff:
                        min_diff = diff
                        rain_mm = r
                except ValueError:
                    continue
                    
        logger.info(f"Fetched online rainfall from Open-Meteo: {rain_mm} mm/hr")
        return float(rain_mm)
        
    except Exception as e:
        logger.error(f"Error fetching from Open-Meteo: {e}. Falling back to offline mock data.")
        raise e


def load_mock_rainfall() -> dict:
    """Loads backend/mock_rainfall.json."""
    mock_path = Path(__file__).parent.parent / "mock_rainfall.json"
    if not mock_path.exists():
        # absolute fallback in case seed/repo path issues
        return {
            "river": "Ranganadi",
            "district": "Lakhimpur",
            "station": "Badatighat",
            "rainfall_intensity_mm_per_hr": 42.5,
            "watershed_area_hectares": 134600,
            "runoff_coefficient": 0.233,
            "current_water_level_m": 94.45,
            "danger_level_m": 95.02,
            "latitude": 27.23,
            "longitude": 94.10,
        }
    with open(mock_path, "r") as f:
        return json.load(f)

async def run():
    """
    Main loop for the Perception Agent.
    Reads environmental data and pushes to alert_queue.
    """
    logger.info(f"Perception Agent started. Mode: {'OFFLINE' if OFFLINE_MODE else 'ONLINE'}, Poll Interval: {POLL_INTERVAL}s")
    
    while True:
        try:
            # Fetch data based on mode
            rain_mm = None
            source_label = ""
            
            mock_data = load_mock_rainfall()
            
            if not OFFLINE_MODE:
                try:
                    rain_mm = await fetch_weather_online()
                    source_label = "open_meteo"
                except Exception:
                    # Fallback to mock if online call fails
                    rain_mm = mock_data.get("rainfall_intensity_mm_per_hr", 0.0)
                    source_label = "mock_rainfall.json (fallback)"
            else:
                rain_mm = mock_data.get("rainfall_intensity_mm_per_hr", 0.0)
                source_label = "mock_rainfall.json"
            
            # Open DB session to check latest river readings and save weather
            db = SessionLocal()
            try:
                # Query latest RiverReading if available to get actual river levels
                latest_river = (
                    db.query(RiverReading)
                    .filter(RiverReading.river == mock_data.get("river", "Ranganadi"))
                    .order_by(RiverReading.timestamp.desc())
                    .first()
                )
                
                current_water_level = latest_river.water_level_m if latest_river else mock_data.get("current_water_level_m", 94.45)
                danger_level = latest_river.danger_level_m if latest_river else mock_data.get("danger_level_m", 95.02)
                
                # Create and save weather reading record
                reading = WeatherReading(
                    river=mock_data.get("river", "Ranganadi"),
                    district=mock_data.get("district", "Lakhimpur"),
                    station=mock_data.get("station", "Badatighat"),
                    timestamp=datetime.now(timezone.utc),
                    rainfall_intensity_mm_per_hr=rain_mm,
                    watershed_area_hectares=float(mock_data.get("watershed_area_hectares", 134600)),
                    runoff_coefficient=float(mock_data.get("runoff_coefficient", 0.233)),
                    current_water_level_m=float(current_water_level),
                    danger_level_m=float(danger_level),
                    latitude=float(mock_data.get("latitude", 27.23)),
                    longitude=float(mock_data.get("longitude", 94.10)),
                    source=source_label,
                )
                db.add(reading)
                db.commit()
                db.refresh(reading)
                
                # Format queue message
                timestamp_str = reading.timestamp.isoformat()
                if not timestamp_str.endswith("Z"):
                    timestamp_str += "Z"
                    
                message = {
                    "river": reading.river,
                    "district": reading.district,
                    "station": reading.station,
                    "timestamp": timestamp_str,
                    "rainfall_intensity_mm_per_hr": reading.rainfall_intensity_mm_per_hr,
                    "watershed_area_hectares": reading.watershed_area_hectares,
                    "runoff_coefficient": reading.runoff_coefficient,
                    "current_water_level_m": reading.current_water_level_m,
                    "danger_level_m": reading.danger_level_m,
                    "latitude": reading.latitude,
                    "longitude": reading.longitude,
                    "source": reading.source,
                }
                
                # Push message to alert_queue
                await alert_queue.put(message)
                logger.info(f"Ingested weather reading from {reading.source}: {reading.rainfall_intensity_mm_per_hr}mm/hr rain, {reading.current_water_level_m}m water level. Pushed to alert_queue.")
                
            except Exception as dbe:
                logger.error(f"Database error in Perception Agent: {dbe}")
                db.rollback()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Unexpected error in Perception Agent: {e}")
            
        await asyncio.sleep(POLL_INTERVAL)
