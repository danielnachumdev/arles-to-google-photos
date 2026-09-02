"""SQLAlchemy declarative models — schema source of truth for Alembic.

Table shapes must stay in sync with ``SqlAlchemyStateStore`` read/write paths.
New columns belong in a new Alembic revision, not ad-hoc ALTER TABLE.
"""
from __future__ import annotations

from sqlalchemy import (
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData()


class JobRow(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    error = Column(Text)
    error_code = Column(String)
    product_url = Column(Text)
    created_at = Column(String, nullable=False)
    started_at = Column(String)
    running_started_at = Column(String)
    run_seconds = Column(Float)
    folder_label = Column(Text)
    preview_json = Column(Text)
    source_job_id = Column(String)
    parent_job_id = Column(String)
    scrape_url = Column(Text)
    scrape_headers_json = Column(Text)
    job_number = Column(Integer)
    auto_publish = Column(Integer, nullable=False, server_default=text("0"))
    warnings_json = Column(Text)
    import_origin = Column(String)
    extra_json = Column(Text)
    user_edited = Column(Integer, nullable=False, server_default=text("0"))
    archived_at = Column(String)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (Index("idx_events_job_id", "job_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        String,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    stage = Column(String, nullable=False)
    message = Column(Text, nullable=False, server_default=text("''"))
    current = Column(Integer, nullable=False, server_default=text("0"))
    total = Column(Integer, nullable=False, server_default=text("0"))
    extra_json = Column(Text)
    occurred_at = Column(String, nullable=False)
    kind = Column(String)
    audience = Column(String)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)


class MetaRow(Base):
    __tablename__ = "meta"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class UserRow(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(String, nullable=False)


JOBS_TABLE = JobRow.__table__
EVENTS_TABLE = EventRow.__table__
META_TABLE = MetaRow.__table__
USERS_TABLE = UserRow.__table__
METADATA = Base.metadata
