"""
database.py — SQLite connection and session setup via SQLAlchemy.

Database file: backend/floodresponse.db
This file provides:
  - engine: SQLAlchemy engine bound to SQLite
  - SessionLocal: session factory for DB operations
  - Base: declarative base for ORM models
  - get_db(): FastAPI dependency that yields a session
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Database lives alongside the backend code — single file, zero setup, works offline
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "floodresponse.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite + FastAPI
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a DB session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
