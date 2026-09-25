"""Business logic: intake with de-duplication, assignment, status changes, statistics.

Functions take a Session and never commit: the caller (API request, job, CLI) owns the transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from lead_hub.db import as_utc
from lead_hub.models import TRANSITIONS, Lead, LeadEvent, LeadStatus, Manager
from lead_hub.schemas import LeadIn, Stats


class ServiceError(ValueError):
    pass


@dataclass(frozen=True)
class IntakeOutcome:
    lead: Lead
    duplicate: bool


def find_recent_duplicate(session: Session, data: LeadIn, since: datetime) -> Lead | None:
    """The same person (phone or email) who already left a lead after `since`."""
    conditions = []
    if data.phone:
        conditions.append(Lead.phone == data.phone)
    if data.email:
        conditions.append(Lead.email == data.email)
    stmt = select(Lead).where(or_(*conditions), Lead.created_at >= since).order_by(Lead.created_at.desc()).limit(1)
    return session.scalars(stmt).first()


def pick_manager(session: Session) -> Manager | None:
    """Round-robin among active managers: the one who waited longest gets the next lead."""
    stmt = (
        select(Manager)
        .where(Manager.active.is_(True))
        .order_by(Manager.last_assigned_at.is_not(None), Manager.last_assigned_at, Manager.id)
        .limit(1)
    )
    return session.scalars(stmt).first()


def add_event(lead: Lead, kind: str, detail: str = "") -> None:
    lead.events.append(LeadEvent(kind=kind, detail=detail))


def intake(session: Session, data: LeadIn, now: datetime, duplicate_window: timedelta) -> IntakeOutcome:
    existing = find_recent_duplicate(session, data, now - duplicate_window)
    if existing is not None:
        existing.duplicates += 1
        extra = f" · {data.message}" if data.message else ""
        add_event(existing, "duplicate", f"повторная заявка ({data.source}){extra}")
        existing.updated_at = now
        return IntakeOutcome(existing, duplicate=True)

    lead = Lead(
        name=data.name,
        phone=data.phone,
        email=data.email,
        message=data.message,
        source=data.source,
        created_at=now,
        updated_at=now,
    )
    session.add(lead)
    add_event(lead, "created", f"источник: {data.source}")
    manager = pick_manager(session)
    if manager is not None:
        lead.manager = manager
        # Strictly after the latest assignment: leads arriving at the same instant must still rotate.
        latest = as_utc(session.scalar(select(func.max(Manager.last_assigned_at))))
        manager.last_assigned_at = now if latest is None or latest < now else latest + timedelta(microseconds=1)
        add_event(lead, "assigned", manager.name)
    session.flush()  # assigns lead.id
    return IntakeOutcome(lead, duplicate=False)


def update_lead(
    session: Session,
    lead: Lead,
    *,
    status: LeadStatus | None = None,
    manager_id: int | None = None,
    note: str | None = None,
) -> Lead:
    if status is not None and status != lead.status:
        if status not in TRANSITIONS[lead.status]:
            raise ServiceError(f"cannot change status from {lead.status.value} to {status.value}")
        add_event(lead, "status", f"{lead.status.value} → {status.value}")
        lead.status = status
    if manager_id is not None and manager_id != lead.manager_id:
        manager = session.get(Manager, manager_id)
        if manager is None or not manager.active:
            raise ServiceError(f"manager {manager_id} not found or inactive")
        lead.manager = manager
        add_event(lead, "assigned", manager.name)
    if note:
        add_event(lead, "note", note)
    session.flush()  # so lead.manager_id and events are consistent for the caller right away
    return lead


def list_leads(
    session: Session,
    *,
    status: LeadStatus | None = None,
    manager_id: int | None = None,
    source: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Lead], int]:
    stmt = select(Lead)
    if status is not None:
        stmt = stmt.where(Lead.status == status)
    if manager_id is not None:
        stmt = stmt.where(Lead.manager_id == manager_id)
    if source:
        stmt = stmt.where(Lead.source == source)
    if created_from is not None:
        stmt = stmt.where(Lead.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Lead.created_at < created_to)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = session.scalars(stmt.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit).offset(offset))
    return list(items), total


def overdue_new_leads(session: Session, now: datetime, sla: timedelta) -> list[Lead]:
    stmt = select(Lead).where(Lead.status == LeadStatus.NEW, Lead.created_at <= now - sla).order_by(Lead.created_at)
    return list(session.scalars(stmt))


def stats(session: Session, now: datetime, sla: timedelta, since: datetime | None = None) -> Stats:
    base = select(Lead)
    if since is not None:
        base = base.where(Lead.created_at >= since)
    sub = base.subquery()
    by_status = {s.value: 0 for s in LeadStatus}
    for status, count in session.execute(select(sub.c.status, func.count()).group_by(sub.c.status)):
        by_status[LeadStatus(status).value] = count
    by_source = dict(
        session.execute(select(sub.c.source, func.count()).group_by(sub.c.source).order_by(func.count().desc())).all()
    )
    won, lost = by_status["won"], by_status["lost"]
    overdue = sum(
        1 for lead in overdue_new_leads(session, now, sla) if since is None or as_utc(lead.created_at) >= since
    )
    return Stats(
        total=sum(by_status.values()),
        by_status=by_status,
        by_source=by_source,
        conversion=round(won / (won + lost), 3) if won + lost else 0.0,
        overdue=overdue,
    )
