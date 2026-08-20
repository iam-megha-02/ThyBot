"""
Durable storage for extracted lab values.

Sits between utils/lab_extraction.py (which turns raw PDF text into
LabResult dataclasses, in memory, per upload) and a database (which
keeps those results across sessions). Nothing here ever updates or
deletes a row — see models/db_models.py for why.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models.db_models import Base, LabResultRecord, Patient


def get_engine(database_url: str):
    return create_engine(database_url)


def init_db(engine) -> None:
    """Create tables if they don't exist yet. No migrations — see the
    tutoring note on why Alembic isn't in scope for this MVP step."""
    Base.metadata.create_all(engine)


def get_session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine)


def get_or_create_default_patient(session: Session) -> Patient:
    """
    Stand-in for real patient identity/auth, which doesn't exist yet.
    Every lab result in this MVP belongs to one shared "default" patient
    row — fine for a single-user local demo, not fine for anything
    multi-user.
    """
    patient = session.query(Patient).filter_by(name="default").first()
    if patient is None:
        patient = Patient(name="default")
        session.add(patient)
        session.commit()
    return patient


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def save_lab_results(
    session: Session,
    patient_id: int,
    results: list,
    collection_date_str: Optional[str] = None,
) -> list:
    """
    Persist a batch of LabResult objects (from lab_extraction.py) for one
    upload. All results from the same upload share the same collection
    date, since they came off the same physical report.
    """
    collection_date = _parse_date(collection_date_str)
    records = []
    for result in results:
        record = LabResultRecord(
            patient_id=patient_id,
            test=result.test,
            variant=result.variant,
            value=result.value,
            unit=result.unit,
            reference_low=result.reference_low,
            reference_high=result.reference_high,
            reported_status=result.reported_status,
            raw_snippet=result.raw_snippet,
            collection_date=collection_date,
        )
        session.add(record)
        records.append(record)
    session.commit()
    return records


_TREND_KEYWORDS = (
    "tsh", "t3", "t4", "thyroid level", "thyroid levels",
    "trend", "improving", "improved", "getting better", "getting worse",
    "lab history", "lab result", "lab results", "my levels",
)


def looks_like_lab_trend_question(message: str) -> bool:
    """
    Crude keyword gate deciding whether a chat message is asking about
    lab trends — a stand-in for the real Router agent from the
    architecture blueprint. Deliberately cheap: no LLM call just to
    decide whether a handful of database rows are worth fetching.
    """
    lowered = message.lower()
    return any(keyword in lowered for keyword in _TREND_KEYWORDS)


def format_history_for_prompt(history: list) -> str:
    """
    Turn LabResultRecord rows into a compact, LLM-readable block,
    grouped by test — someone asking "is my TSH improving?" wants TSH's
    own trajectory, not an interleaved dump of every analyte.
    """
    if not history:
        return ""

    by_test: dict = {}
    for record in history:
        by_test.setdefault(record.test, []).append(record)

    lines = ["Patient's lab history (chronological, oldest first):"]
    for test_name, records in by_test.items():
        lines.append(f"\n{test_name}:")
        for record in records:
            date_str = str(record.collection_date) if record.collection_date else "date unknown"
            status = f" ({record.reported_status})" if record.reported_status else ""
            ref = (
                f", reference {record.reference_low}-{record.reference_high}"
                if record.reference_low is not None
                else ""
            )
            lines.append(f"  - {date_str}: {record.value} {record.unit or ''}{ref}{status}")
    return "\n".join(lines)


def get_lab_history(session: Session, patient_id: int, test: Optional[str] = None) -> list:
    """
    Full history for a patient, oldest first — the order a trend
    answer needs. Falls back to ingestion order (created_at) for
    records whose collection date wasn't parseable, rather than
    dropping them.
    """
    query = session.query(LabResultRecord).filter_by(patient_id=patient_id)
    if test:
        query = query.filter_by(test=test)
    return query.order_by(
        LabResultRecord.collection_date.is_(None),
        LabResultRecord.collection_date.asc(),
        LabResultRecord.created_at.asc(),
    ).all()
