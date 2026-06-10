"""
models.py — All six database tables for the Flood Response Coordinator.

Tables:
  1. resources   — boats, helicopters, trucks, medical teams with GPS + inventory
  2. shelters    — evacuation shelters with capacity and supply stocks
  3. sos_events  — incoming SOS requests from flood-affected people
  4. missions    — links an SOS event to a dispatched resource, tracks lifecycle
  5. flood_alerts — flood severity predictions per district
  6. audit_log   — every agent decision logged for transparency and review
"""

import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, Enum
)
from backend.database import Base


# ---------------------------------------------------------------------------
# 1. RESOURCES — boats, helicopters, trucks, medical teams
# ---------------------------------------------------------------------------
class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(
        Enum("helicopter", "boat", "truck", "medical_team", name="resource_type"),
        nullable=False,
    )
    name = Column(String(50), unique=True, nullable=False)       # e.g. "H1", "B1"
    lat = Column(Float, nullable=False)                          # GPS latitude
    lng = Column(Float, nullable=False)                          # GPS longitude
    status = Column(
        Enum("available", "dispatched", "maintenance", name="resource_status"),
        default="available",
        nullable=False,
    )
    inventory = Column(Text, default="{}")                       # JSON: {"food": 100, ...}

    def inventory_dict(self):
        return json.loads(self.inventory) if self.inventory else {}


# ---------------------------------------------------------------------------
# 2. SHELTERS — evacuation points with capacity and supply stocks
# ---------------------------------------------------------------------------
class Shelter(Base):
    __tablename__ = "shelters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    capacity = Column(Integer, nullable=False)                   # max people
    current_occupancy = Column(Integer, default=0)
    food_stock = Column(Integer, default=0)                      # units
    water_stock = Column(Integer, default=0)                     # litres
    medicine_stock = Column(Integer, default=0)                  # kits
    status = Column(
        Enum("open", "full", "closed", name="shelter_status"),
        default="open",
        nullable=False,
    )


# ---------------------------------------------------------------------------
# 3. SOS_EVENTS — incoming distress calls from flood-affected people
# ---------------------------------------------------------------------------
class SOSEvent(Base):
    __tablename__ = "sos_events"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(20), nullable=False)                   # caller phone
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    district = Column(String(100), default="Lakhimpur")
    people_count = Column(Integer, default=1)
    injury_description = Column(Text, default="")
    triage_level = Column(Integer, default=3)                    # 1 (critical) – 5 (minor)
    status = Column(
        Enum("pending", "assigned", "rescued", name="sos_status"),
        default="pending",
        nullable=False,
    )
    assigned_resource_id = Column(Integer, ForeignKey("resources.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 4. MISSIONS — lifecycle tracking: en_route → on_site → evacuating → complete
# ---------------------------------------------------------------------------
class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    sos_event_id = Column(Integer, ForeignKey("sos_events.id"), nullable=False)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    status = Column(
        Enum("en_route", "on_site", "evacuating", "complete", name="mission_status"),
        default="en_route",
        nullable=False,
    )
    shelter_id = Column(Integer, ForeignKey("shelters.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# 5. FLOOD_ALERTS — severity predictions per district / river basin
# ---------------------------------------------------------------------------
class FloodAlert(Base):
    __tablename__ = "flood_alerts"

    id = Column(Integer, primary_key=True, index=True)
    district = Column(String(100), nullable=False)
    severity = Column(
        Enum("low", "moderate", "high", "critical", name="alert_severity"),
        default="low",
        nullable=False,
    )
    discharge_q = Column(Float, nullable=True)                   # peak discharge (cumecs)
    estimated_flood_time = Column(DateTime, nullable=True)
    affected_circles = Column(Text, default="[]")                # JSON array of revenue circles
    geojson_polygon = Column(Text, default="{}")                 # GeoJSON for map overlay
    fhi_score = Column(Float, nullable=True)                     # Flood Hazard Index 0–1
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 6. AUDIT_LOG — every agent decision for transparency
# ---------------------------------------------------------------------------
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False)              # e.g. "conflict_resolved"
    agent_name = Column(String(50), nullable=False)              # e.g. "conflict_resolution"
    request_a = Column(Text, default="{}")                       # JSON: first competing request
    request_b = Column(Text, default="{}")                       # JSON: second competing request
    score_a = Column(Float, nullable=True)
    score_b = Column(Float, nullable=True)
    winner = Column(String(10), nullable=True)                   # "a" or "b"
    fallback_assigned = Column(Text, default="")                 # what the loser gets
    explanation = Column(Text, default="")                       # plain English reasoning
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
