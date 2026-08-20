"""
SQLAlchemy table definitions for durable patient/lab-history storage.

Deliberately append-only: this module defines no update or delete
helpers anywhere in the codebase. Every upload adds new rows; nothing
overwrites a prior lab result. That's what makes trend answers ("is my
TSH improving?") trustworthy — the full history is always intact — and
it's a real auditability property for health data, not just a style
choice.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, default="default")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    lab_results = relationship("LabResultRecord", back_populates="patient")


class LabResultRecord(Base):
    __tablename__ = "lab_results"

    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    test = Column(String, nullable=False)              # "TSH", "T3", "T4"
    variant = Column(String, nullable=False)            # "free" | "total" | "unspecified"
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=True)
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)
    reported_status = Column(String, nullable=True)     # "Normal" / "High" / "Low", as printed on the report
    raw_snippet = Column(Text, nullable=True)            # kept for audit — what text this was parsed from

    collection_date = Column(Date, nullable=True)        # when the blood was drawn (from the report)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # when we ingested it

    patient = relationship("Patient", back_populates="lab_results")
