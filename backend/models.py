"""SQLAlchemy ORM models for 拾光 · Lumen data schema."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime. Stored in SQLite as naive UTC for
    compatibility, but the tzinfo ensures FastAPI serializes with +00:00 suffix
    so JavaScript can parse it correctly across all browsers."""
    return datetime.now(timezone.utc)


# ── Core entities ──────────────────────────────────────────────────────────


class Record(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    type = Column(String(20), nullable=False, default="text")  # text | voice
    status = Column(String(20), nullable=False, default="unprocessed")
    # unprocessed → processing → processed | archived
    meta_json = Column(Text, default="{}")  # JSON blob for extensibility
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    events = relationship("Event", secondary="record_events", back_populates="records")
    tasks = relationship("Task", secondary="record_tasks", back_populates="records")
    contexts = relationship("Context", secondary="record_contexts", back_populates="records")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    confidence = Column(Float, default=0.5)  # 0.0 – 1.0
    status = Column(String(20), nullable=False, default="inferred")
    # inferred → confirmed → modified | deleted
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    records = relationship("Record", secondary="record_events", back_populates="events")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(20), nullable=False, default="pending")
    # pending → in_progress → done | deleted
    priority = Column(String(10), default="medium")  # low | medium | high
    due_date = Column(DateTime)
    confidence = Column(Float, default=0.5)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    completed_at = Column(DateTime)

    records = relationship("Record", secondary="record_tasks", back_populates="tasks")


class Context(Base):
    __tablename__ = "contexts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    summary = Column(Text, nullable=False)
    valid_from = Column(DateTime, nullable=False, default=_utcnow)
    valid_until = Column(DateTime)
    created_at = Column(DateTime, default=_utcnow)

    records = relationship("Record", secondary="record_contexts", back_populates="contexts")


# ── Junction tables (traceability) ──────────────────────────────────────────


class RecordEvent(Base):
    __tablename__ = "record_events"
    record_id = Column(Integer, ForeignKey("records.id"), primary_key=True)
    event_id = Column(Integer, ForeignKey("events.id"), primary_key=True)


class RecordTask(Base):
    __tablename__ = "record_tasks"
    record_id = Column(Integer, ForeignKey("records.id"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), primary_key=True)


class RecordContext(Base):
    __tablename__ = "record_contexts"
    record_id = Column(Integer, ForeignKey("records.id"), primary_key=True)
    context_id = Column(Integer, ForeignKey("contexts.id"), primary_key=True)


# ── 情绪指数 ─────────────────────────────────────────────────────────────────


class Mood(Base):
    """User mood snapshot computed from recent records."""

    __tablename__ = "moods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score = Column(Float, nullable=False)  # 1.0 – 10.0
    label = Column(String(20), nullable=False)  # 低落 / 平稳 / 良好
    summary = Column(Text, nullable=False)  # 1-2 sentence interpretation
    key_factors = Column(Text, default="[]")  # JSON array of key emotional factors
    created_at = Column(DateTime, default=_utcnow)
