import asyncio
import logging
import math
from backend.database import SessionLocal
from backend.models import Resource, Mission, SOSEvent, Shelter
from backend.broadcast import broadcast, EVENT_RESOURCE_MOVED
from backend.utils import haversine

logger = logging.getLogger("agent.movement_simulator")

# Simulation speed factor. At 60km/h, a vehicle moves 1km per minute.
# We run this loop every 2 seconds. In real time, it would move very little.
# We'll speed up the simulation so a 10km trip takes ~30 seconds.
# 30 seconds = 15 ticks. 10km / 15 ticks = 0.66 km per tick.
KM_PER_TICK = 0.5 

async def run():
    """
    Background physics loop that animates vehicles towards their mission destinations.
    """
    logger.info("Movement Simulator started. Vehicles will animate over time.")
    
    while True:
        db = SessionLocal()
        try:
            # Get all active missions where the resource is dispatched or en_route
            active_missions = db.query(Mission).filter(Mission.status == "en_route").all()
            
            for mission in active_missions:
                resource = db.query(Resource).filter(Resource.id == mission.resource_id).first()
                if not resource or resource.status != "dispatched":
                    continue
                
                # Determine destination
                target_lat = None
                target_lng = None
                
                if mission.sos_event_id:
                    sos = db.query(SOSEvent).filter(SOSEvent.id == mission.sos_event_id).first()
                    if sos:
                        target_lat = sos.lat
                        target_lng = sos.lng
                elif mission.shelter_id:
                    shelter = db.query(Shelter).filter(Shelter.id == mission.shelter_id).first()
                    if shelter:
                        target_lat = shelter.lat
                        target_lng = shelter.lng
                        
                if target_lat is None or target_lng is None:
                    continue
                    
                # Calculate distance
                dist_km = haversine(resource.lat, resource.lng, target_lat, target_lng)
                
                if dist_km <= KM_PER_TICK:
                    # Arrived!
                    resource.lat = target_lat
                    resource.lng = target_lng
                    resource.status = "available" # Mission complete essentially (for demo purposes)
                    mission.status = "completed"
                    logger.info(f"Resource {resource.name} arrived at destination!")
                else:
                    # Move towards target using linear interpolation
                    ratio = KM_PER_TICK / dist_km
                    resource.lat = resource.lat + (target_lat - resource.lat) * ratio
                    resource.lng = resource.lng + (target_lng - resource.lng) * ratio
                
                db.commit()
                db.refresh(resource)
                
                # Broadcast the new position
                await broadcast(EVENT_RESOURCE_MOVED, {
                    "resource_id": resource.id,
                    "name": resource.name,
                    "new_lat": resource.lat,
                    "new_lng": resource.lng,
                    "new_status": resource.status,
                    "inventory": resource.inventory_dict()
                })
                
        except Exception as e:
            logger.error(f"Error in movement simulator: {e}")
            db.rollback()
        finally:
            db.close()
            
        await asyncio.sleep(2.0)
