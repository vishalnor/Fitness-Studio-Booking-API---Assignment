"""Seed demo data: one user and a few upcoming classes.

Run from the project root:  python seed.py
Demo login: demo@example.com / password123
"""
from datetime import timedelta

from app.database import Base, SessionLocal, engine
from app.models import FitnessClass, User
from app.security import hash_password
from app.timeutils import now_ist


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).filter_by(email="demo@example.com").first():
            print("Already seeded.")
            return
        user = User(name="Demo User", email="demo@example.com", password_hash=hash_password("password123"))
        db.add(user)
        db.flush()
        base = now_ist().replace(minute=0, second=0, microsecond=0)
        samples = [
            ("Yoga Flow", 1, "John Doe", 20),
            ("HIIT Session", 2, "Jane Smith", 10),
            ("Zumba Party", 3, "Maria Garcia", 15),
            ("Pilates Core", 4, "Alex Kim", 8),
        ]
        for name, days, instructor, slots in samples:
            db.add(FitnessClass(
                name=name, date_time=base + timedelta(days=days, hours=1),
                instructor=instructor, available_slots=slots, created_by=user.id,
            ))
        db.commit()
        print("Seeded demo user and classes.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
