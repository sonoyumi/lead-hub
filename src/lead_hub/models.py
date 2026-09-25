"""Database models (SQLAlchemy 2.0). Schema changes go through Alembic migrations in migrations/."""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class LeadStatus(enum.StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    WON = "won"
    LOST = "lost"


# Allowed status changes: a closed lead can be reopened, but "new" is only the starting point.
TRANSITIONS: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.NEW: {LeadStatus.IN_PROGRESS, LeadStatus.LOST},
    LeadStatus.IN_PROGRESS: {LeadStatus.WON, LeadStatus.LOST},
    LeadStatus.WON: {LeadStatus.IN_PROGRESS},
    LeadStatus.LOST: {LeadStatus.IN_PROGRESS},
}


class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    leads: Mapped[list[Lead]] = relationship(back_populates="manager")


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_status_created", "status", "created_at"),
        Index("ix_leads_phone", "phone"),
        Index("ix_leads_email", "email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(254))
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="website", nullable=False)
    status: Mapped[LeadStatus] = mapped_column(
        # values_callable: store "new"/"won" (readable in SQL), not the Python names "NEW"/"WON"
        Enum(LeadStatus, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        default=LeadStatus.NEW,
        nullable=False,
    )
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("managers.id"))
    duplicates: Mapped[int] = mapped_column(default=0, nullable=False)  # repeated submissions merged here
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # SLA reminder sent
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # sent to the admin

    manager: Mapped[Manager | None] = relationship(back_populates="leads")
    events: Mapped[list[LeadEvent]] = relationship(
        back_populates="lead", cascade="all, delete-orphan", order_by="LeadEvent.id"
    )


class LeadEvent(Base):
    """Audit trail: every change of a lead is recorded."""

    __tablename__ = "lead_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_id: Mapped[int] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # created | duplicate | assigned | status | note
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="events")
