"""
seed.py — Pre-populate the database with Lakhimpur district data.

Resources and shelters are based on real FLEWS paper data for Lakhimpur
district, Assam. GPS coordinates are approximate positions around the
North Lakhimpur / Ranganadi basin area.

Run this script once after setting up the project:
    python -m backend.seed
    OR
    cd backend && python seed.py
"""

import sys
import os
import json

# Allow running as both `python seed.py` (from backend/) and `python -m backend.seed`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import engine, SessionLocal, Base
from backend.models import Resource, Shelter


def seed():
    """Create tables and insert Lakhimpur district seed data."""

    # Create all tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Check if already seeded
        if db.query(Resource).count() > 0:
            print("Database already seeded. Skipping.")
            return

        # ── Resources ─────────────────────────────────────────────────
        resources = [
            Resource(
                type="helicopter",
                name="H1",
                lat=27.2350,
                lng=94.1050,
                status="available",
                inventory=json.dumps({}),
            ),
            Resource(
                type="boat",
                name="B1",
                lat=27.2280,
                lng=94.0980,
                status="available",
                inventory=json.dumps({}),
            ),
            Resource(
                type="boat",
                name="B2",
                lat=27.2400,
                lng=94.1120,
                status="available",
                inventory=json.dumps({}),
            ),
            Resource(
                type="truck",
                name="T1",
                lat=27.2200,
                lng=94.0900,
                status="available",
                inventory=json.dumps({
                    "food_packets": 500,
                    "water_litres": 2000,
                    "medicine_kits": 50,
                }),
            ),
            Resource(
                type="medical_team",
                name="MT1",
                lat=27.2300,
                lng=94.1000,
                status="available",
                inventory=json.dumps({
                    "first_aid_kits": 20,
                    "stretchers": 5,
                    "oxygen_cylinders": 3,
                }),
            ),
        ]

        # ── Shelters ──────────────────────────────────────────────────
        shelters = [
            Shelter(
                name="Gogamukh Community Hall",
                lat=27.2700,
                lng=94.1300,
                capacity=340,
                current_occupancy=0,
                food_stock=500,
                water_stock=3000,
                medicine_stock=100,
                status="open",
                address="NH-15, Main Road, Gogamukh, Lakhimpur 787034"
            ),
            Shelter(
                name="Sisiborgaon School",
                lat=27.2100,
                lng=94.0700,
                capacity=180,
                current_occupancy=0,
                food_stock=250,
                water_stock=1500,
                medicine_stock=50,
                status="open",
                address="Near Sisiborgaon Block Office, Lakhimpur 787110"
            ),
        ]

        db.add_all(resources + shelters)
        db.commit()
        print("Seeded Lakhimpur district data successfully")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
