from backend.database import SessionLocal
from backend.models import RegisteredCitizen, Donation

def seed_mock_data():
    db = SessionLocal()
    try:
        # Seed Citizens
        if db.query(RegisteredCitizen).count() == 0:
            c1 = RegisteredCitizen(
                name="Rohan Bora", phone="+919876543210", role="volunteer", district="Lakhimpur",
                status="available", resource_type="boat", resource_description="Personal motorboat, 4 capacity"
            )
            c2 = RegisteredCitizen(
                name="Aisha Ali", phone="+919876543211", role="driver", district="Lakhimpur",
                status="active", resource_type="truck", resource_description="Can drive heavy rescue trucks"
            )
            c3 = RegisteredCitizen(
                name="Vikram Singh", phone="+919876543212", role="citizen", district="Lakhimpur",
                status="standby"
            )
            db.add_all([c1, c2, c3])
            
        # Seed Donations
        if db.query(Donation).count() == 0:
            d1 = Donation(
                donor_phone="+919998887776", donor_name="Local Gurudwara", donation_type="food",
                quantity=1000, description="1000 packed dal-chawal meals", status="confirmed",
                pickup_lat=27.2345, pickup_lng=94.1032
            )
            d2 = Donation(
                donor_phone="+919998887777", donor_name="Rotary Club", donation_type="medicine",
                quantity=50, description="50 first aid kits and water purifiers", status="collected",
                assigned_truck_id=4, pickup_lat=27.2355, pickup_lng=94.1042
            )
            db.add_all([d1, d2])

        db.commit()
        print("Successfully seeded mock volunteers and donations!")
    except Exception as e:
        db.rollback()
        print("Error:", e)
    finally:
        db.close()

if __name__ == "__main__":
    seed_mock_data()
