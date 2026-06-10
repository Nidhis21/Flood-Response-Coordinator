"""
perception_data.py — Schemas and database models for the Perception agent data.
Defines additional data sources (river levels, dam discharge, citizen reports, etc.)
and their database structures without modifying the core foundation models.py.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime
from pydantic import BaseModel, Field

from backend.database import Base

# =============================================================================
# 1. DATABASE MODELS (SQLAlchemy)
# =============================================================================

class WeatherReading(Base):
    """Stores standardized weather data fetched from APIs or mock files."""
    __tablename__ = "weather_readings"

    id = Column(Integer, primary_key=True, index=True)
    river = Column(String(100), default="Ranganadi")
    district = Column(String(100), default="Lakhimpur")
    station = Column(String(100), default="Badatighat")
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    rainfall_intensity_mm_per_hr = Column(Float, nullable=False)
    watershed_area_hectares = Column(Float, default=134600.0)
    runoff_coefficient = Column(Float, default=0.233)
    current_water_level_m = Column(Float, nullable=True)
    danger_level_m = Column(Float, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    source = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RiverReading(Base):
    """Stores telemetry from water level monitoring stations."""
    __tablename__ = "river_readings"

    id = Column(Integer, primary_key=True, index=True)
    river = Column(String(100), nullable=False)
    station = Column(String(100), nullable=False)
    water_level_m = Column(Float, nullable=False)
    danger_level_m = Column(Float, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DamDischarge(Base):
    """Stores upstream reservoir discharge updates."""
    __tablename__ = "dam_discharges"

    id = Column(Integer, primary_key=True, index=True)
    dam_name = Column(String(100), nullable=False)
    river = Column(String(100), nullable=False)
    discharge_rate_cumecs = Column(Float, nullable=False)
    gate_status = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CitizenReport(Base):
    """Stores crowdsourced reports from affected citizens."""
    __tablename__ = "citizen_reports"

    id = Column(Integer, primary_key=True, index=True)
    reporter_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    water_level_description = Column(String(100), nullable=True)  # ankle, knee, waist, head-high, etc.
    water_level_m_est = Column(Float, nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RoadBlockage(Base):
    """Stores logistics-affecting road blocks and flooding updates."""
    __tablename__ = "road_blockages"

    id = Column(Integer, primary_key=True, index=True)
    road_name = Column(String(100), nullable=False)
    location_lat = Column(Float, nullable=False)
    location_lng = Column(Float, nullable=False)
    status = Column(String(50), nullable=False)  # clear, flooded, blocked
    severity = Column(String(50), nullable=False)  # low, medium, high
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# =============================================================================
# 2. INPUT SCHEMAS (Pydantic)
# =============================================================================

class RiverReadingInput(BaseModel):
    river: str = Field(..., example="Ranganadi")
    station: str = Field(..., example="Badatighat")
    water_level_m: float = Field(..., description="Current water level in meters")
    danger_level_m: float = Field(..., description="Official danger level mark in meters")
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class DamDischargeInput(BaseModel):
    dam_name: str = Field(..., example="Ranganadi Dam")
    river: str = Field(..., example="Ranganadi")
    discharge_rate_cumecs: float = Field(..., description="Discharge rate in cubic meters per second")
    gate_status: Optional[str] = Field("closed", description="e.g., closed, partially_open, open")


class CitizenReportInput(BaseModel):
    reporter_name: Optional[str] = None
    phone: Optional[str] = None
    lat: float = Field(..., description="Latitude of report")
    lng: float = Field(..., description="Longitude of report")
    water_level_description: Optional[str] = Field(None, description="e.g., ankle, knee, waist, flooded")
    water_level_m_est: Optional[float] = Field(None, description="Estimated water level in meters")


class ShelterStatusUpdate(BaseModel):
    current_occupancy: Optional[int] = None
    food_stock: Optional[int] = None
    water_stock: Optional[int] = None
    medicine_stock: Optional[int] = None
    status: Optional[str] = Field(None, description="open, full, closed")


class RoadBlockageInput(BaseModel):
    road_name: str = Field(..., example="NH-15 Bypass")
    location_lat: float
    location_lng: float
    status: str = Field(..., description="clear, flooded, blocked")
    severity: str = Field(..., description="low, medium, high")
