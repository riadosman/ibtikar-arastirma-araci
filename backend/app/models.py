from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.expression import false as sa_false

from app.core.db import Base


def now():
    return datetime.now(timezone.utc)


def as_utc(value):
    """SQLite returns naive UTC values; PostgreSQL returns aware values in the session zone."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    created_by: Mapped[str | None] = mapped_column(String(36))
    updated_by: Mapped[str | None] = mapped_column(String(36))


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text)
    # ADMIN manages users; USER researches and reviews; VIEWER reads and exports.
    role: Mapped[str] = mapped_column(String(20), default="USER")
    active: Mapped[bool] = mapped_column(default=True)


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ResearchRequest(Identity, Base):
    __tablename__ = "research_requests"
    search_language: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto")
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    field: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(200))
    target_type: Mapped[str] = mapped_column(String(100))
    requested_quantity: Mapped[int]
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="CREATED", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list["ResearchKeyword"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        cascade="all, delete-orphan", back_populates="research", passive_deletes=True
    )


class ResearchKeyword(Base):
    __tablename__ = "research_keywords"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    research_request_id: Mapped[str] = mapped_column(
        ForeignKey("research_requests.id", ondelete="CASCADE"), index=True
    )
    value: Mapped[str] = mapped_column(String(200))


class Candidate(Identity, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidate_request_status", "research_request_id", "status"),
        CheckConstraint("relevance_score >= 0 AND relevance_score <= 100"),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 100"),
    )
    research_request_id: Mapped[str] = mapped_column(
        ForeignKey("research_requests.id", ondelete="CASCADE")
    )
    full_name: Mapped[str] = mapped_column(String(200), index=True)
    headline: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(String(200))
    organization: Mapped[str | None] = mapped_column(String(200))
    organization_type: Mapped[str | None] = mapped_column(String(100))
    field: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    website: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    twitter_url: Mapped[str | None] = mapped_column(Text)
    instagram_url: Mapped[str | None] = mapped_column(Text)
    public_email: Mapped[str | None] = mapped_column(String(320))
    public_phone: Mapped[str | None] = mapped_column(String(100))
    bio: Mapped[str | None] = mapped_column(Text)
    expertise: Mapped[list] = mapped_column(JSON, default=list)
    relevance_score: Mapped[int] = mapped_column(default=0)
    confidence_score: Mapped[int] = mapped_column(default=0)
    relevance_reason: Mapped[str] = mapped_column(Text, default="Not analyzed yet.")
    status: Mapped[str] = mapped_column(String(20), default="NEW")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo: Mapped[bool] = mapped_column(default=False)
    # Per-requirement decisions (role, topic, place, keywords) behind relevance_score.
    match_details: Mapped[dict] = mapped_column(JSON, default=dict)
    research: Mapped[ResearchRequest] = relationship(back_populates="candidates")
    sources: Mapped[list["CandidateSource"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class CandidateSource(Identity, Base):
    __tablename__ = "candidate_sources"
    __table_args__ = (UniqueConstraint("candidate_id", "url"),)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(100), default="website")
    source_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Short quote from the source that supports the candidate; created_at is when it was seen.
    evidence: Mapped[str | None] = mapped_column(Text)


class ExportJob(Identity, Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_export_jobs_idempotency_key"),
    )
    research_request_id: Mapped[str] = mapped_column(
        ForeignKey("research_requests.id", ondelete="CASCADE"), index=True
    )
    format: Mapped[str] = mapped_column(String(20))
    candidate_count: Mapped[int]
    include_all: Mapped[bool] = mapped_column(default=False)
    # PENDING -> COMPLETED | FAILED. MOCK marks a Sheets preview without Google credentials.
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    detail: Mapped[str | None] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(200))
    external_url: Mapped[str | None] = mapped_column(Text)
    # "<actor scope>:<Idempotency-Key>": a retried Sheets export resumes the same sheet.
    idempotency_key: Mapped[str | None] = mapped_column(String(200))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class CollectionJob(Identity, Base):
    """QUEUED -> RUNNING -> COMPLETED | PARTIAL | NO_RESULTS | FAILED | CANCELLED."""

    __tablename__ = "collection_jobs"
    search_language: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto")
    research_request_id: Mapped[str] = mapped_column(
        ForeignKey("research_requests.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)
    query: Mapped[str] = mapped_column(Text)
    processed: Mapped[int] = mapped_column(default=0)
    discovered: Mapped[int] = mapped_column(default=0)
    created_count: Mapped[int] = mapped_column(default=0)
    merged_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Pipeline counters: search results, duplicates removed, extracted/qualified people.
    stats: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceDocument(Identity, Base):
    __tablename__ = "source_documents"
    collection_job_id: Mapped[str] = mapped_column(
        ForeignKey("collection_jobs.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="DISCOVERED")
    error: Mapped[str | None] = mapped_column(String(200))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # Where the source came from and how it was ranked before fetching (search yield stats).
    query: Mapped[str | None] = mapped_column(Text)
    engine: Mapped[str | None] = mapped_column(String(30))
    rank: Mapped[int | None]
    page_kind: Mapped[str | None] = mapped_column(String(30))
    priority: Mapped[int] = mapped_column(default=0, server_default="0")


class IdempotencyRecord(Base):
    """Stored outcome of a POST sent with an Idempotency-Key, replayed on retries."""

    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("scope", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    scope: Mapped[str] = mapped_column(String(64))
    key: Mapped[str] = mapped_column(String(128))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status_code: Mapped[int | None]
    response: Mapped[dict | list | None] = mapped_column(JSON)
