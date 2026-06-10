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
TODO — Implementation Checklist
=============================================================================
  1. Read OFFLINE_MODE from environment variables
  2. If online: poll Open-Meteo API for Lakhimpur district rainfall data
     - API endpoint: https://api.open-meteo.com/v1/forecast
     - Parameters: latitude=27.23, longitude=94.10, hourly=rain
  3. If offline: load backend/mock_rainfall.json and push its contents
  4. Parse rainfall intensity (mm/hr), water level, station data
  5. Push structured message to alert_queue (see MESSAGE_FORMATS.md § alert_queue)
  6. Run in a loop with configurable polling interval (e.g., every 60 seconds)
  7. Add error handling and retry logic for API failures
  8. Log all data ingestion events for debugging
=============================================================================
"""

import asyncio
import logging

logger = logging.getLogger("agent.perception")


async def run():
    """
    Main loop for the Perception Agent.
    Reads environmental data and pushes to alert_queue.
    """
    logger.info("Perception Agent started (stub — awaiting implementation)")
    while True:
        # TODO: Implement data ingestion loop
        await asyncio.sleep(60)
