"""HTTP API (FastAPI) + background scheduler for the automation jobs.

No `from __future__ import annotations` here: FastAPI reads the handler annotations at runtime,
and string annotations could not see the dependency aliases defined inside create_app().
"""

import hmac
import logging
from collections.abc import Iterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Response, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from lead_hub.config import Settings
from lead_hub.db import make_engine, make_session_factory, session_scope
from lead_hub.jobs import check_sla, notify_new_lead, send_digest
from lead_hub.models import Lead, LeadStatus, Manager
from lead_hub.notify import LogNotifier, Notifier, TelegramNotifier
from lead_hub.schemas import IntakeResult, LeadDetail, LeadIn, LeadOut, LeadPage, LeadUpdate, Stats
from lead_hub.services import ServiceError, intake, list_leads, stats, update_lead

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Declared as a security scheme: the /docs page shows an "Authorize" button for the key.
API_KEY_HEADER = APIKeyHeader(name="X-Api-Key", auto_error=False)


class ManagerIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    telegram_chat_id: str | None = Field(default=None, max_length=32)


class ManagerPatch(BaseModel):
    active: bool | None = None
    telegram_chat_id: str | None = Field(default=None, max_length=32)


class ManagerOut(BaseModel):
    id: int
    name: str
    telegram_chat_id: str | None
    active: bool

    model_config = {"from_attributes": True}


def build_notifier(settings: Settings) -> Notifier:
    if settings.telegram_enabled:
        return TelegramNotifier(settings.bot_token.get_secret_value())
    return LogNotifier()


def start_scheduler(settings: Settings, factory: sessionmaker[Session], notifier: Notifier) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=settings.tz)

    def sla_job() -> None:
        with session_scope(factory) as session:
            check_sla(session, notifier, settings, datetime.now(UTC))

    def digest_job() -> None:
        with session_scope(factory) as session:
            send_digest(session, notifier, settings, datetime.now(UTC), PROJECT_ROOT / "data" / "exports")

    scheduler.add_job(sla_job, "interval", minutes=1, id="sla", max_instances=1, coalesce=True)
    scheduler.add_job(digest_job, "cron", hour=settings.digest_hour, minute=0, id="digest", coalesce=True)
    scheduler.start()
    return scheduler


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    notifier: Notifier | None = None,
    run_scheduler: bool = True,
) -> FastAPI:
    settings = settings or Settings()
    factory = session_factory or make_session_factory(make_engine(settings.database_url))
    notifier = notifier or build_notifier(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = start_scheduler(settings, factory, notifier) if run_scheduler else None
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Lead Hub", version="0.1.0", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["POST"], allow_headers=["*"]
        )

    # --- dependencies ---

    def get_session() -> Iterator[Session]:
        with session_scope(factory) as session:
            yield session

    def _key_ok(given: str | None, allowed: list[str]) -> bool:
        # compare_digest: the check takes the same time whether the key is almost right or totally wrong
        return bool(given) and any(hmac.compare_digest(given.encode(), k.encode()) for k in allowed if k)

    def require_intake(x_api_key: Annotated[str | None, Security(API_KEY_HEADER)] = None) -> None:
        keys = [k.get_secret_value() for k in settings.intake_keys]
        if not _key_ok(x_api_key, keys):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing X-Api-Key")

    def require_admin(x_api_key: Annotated[str | None, Security(API_KEY_HEADER)] = None) -> None:
        admin = settings.admin_key.get_secret_value()
        if not admin:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "admin API is disabled: set ADMIN_KEY")
        if not _key_ok(x_api_key, [admin]):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing X-Api-Key")

    SessionDep = Annotated[Session, Depends(get_session)]
    admin_only = [Depends(require_admin)]

    def get_lead(session: Session, lead_id: int) -> Lead:
        lead = session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "lead not found")
        return lead

    # --- routes ---

    @app.get("/health")
    def health(session: SessionDep) -> dict:
        session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/api/leads", response_model=IntakeResult, status_code=201, dependencies=[Depends(require_intake)])
    def create_lead(data: LeadIn, session: SessionDep, background: BackgroundTasks, response: Response):
        outcome = intake(session, data, datetime.now(UTC), timedelta(hours=settings.duplicate_window_hours))
        if outcome.duplicate:
            response.status_code = status.HTTP_200_OK
        else:
            session.commit()  # the notification must not describe a lead that could still be rolled back
            background.add_task(notify_new_lead, outcome.lead, notifier, settings)
        return IntakeResult(id=outcome.lead.id, duplicate=outcome.duplicate)

    @app.get("/api/leads", response_model=LeadPage, dependencies=admin_only)
    def leads(
        session: SessionDep,
        status_: Annotated[LeadStatus | None, Query(alias="status")] = None,
        manager_id: int | None = None,
        source: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> LeadPage:
        def local_midnight(day: date) -> datetime:
            return datetime.combine(day, datetime.min.time(), tzinfo=settings.tz).astimezone(UTC)

        items, total = list_leads(
            session,
            status=status_,
            manager_id=manager_id,
            source=source,
            created_from=local_midnight(date_from) if date_from else None,
            created_to=local_midnight(date_to) + timedelta(days=1) if date_to else None,
            limit=limit,
            offset=offset,
        )
        return LeadPage(items=[LeadOut.model_validate(i) for i in items], total=total, limit=limit, offset=offset)

    @app.get("/api/leads/{lead_id}", response_model=LeadDetail, dependencies=admin_only)
    def lead_detail(lead_id: int, session: SessionDep) -> Lead:
        return get_lead(session, lead_id)

    @app.patch("/api/leads/{lead_id}", response_model=LeadOut, dependencies=admin_only)
    def patch_lead(lead_id: int, data: LeadUpdate, session: SessionDep) -> Lead:
        lead = get_lead(session, lead_id)
        try:
            update_lead(session, lead, status=data.status, manager_id=data.manager_id, note=data.note)
        except ServiceError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
        session.flush()
        return lead

    @app.get("/api/stats", response_model=Stats, dependencies=admin_only)
    def get_stats(session: SessionDep, days: Annotated[int, Query(ge=1, le=3650)] = 30) -> Stats:
        now = datetime.now(UTC)
        return stats(session, now, timedelta(minutes=settings.sla_minutes), since=now - timedelta(days=days))

    @app.get("/api/managers", response_model=list[ManagerOut], dependencies=admin_only)
    def managers(session: SessionDep) -> list[Manager]:
        return list(session.scalars(select(Manager).order_by(Manager.id)))

    @app.post("/api/managers", response_model=ManagerOut, status_code=201, dependencies=admin_only)
    def add_manager(data: ManagerIn, session: SessionDep) -> Manager:
        manager = Manager(name=data.name, telegram_chat_id=data.telegram_chat_id, active=True)
        session.add(manager)
        session.flush()
        return manager

    @app.patch("/api/managers/{manager_id}", response_model=ManagerOut, dependencies=admin_only)
    def patch_manager(manager_id: int, data: ManagerPatch, session: SessionDep) -> Manager:
        manager = session.get(Manager, manager_id)
        if manager is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "manager not found")
        if data.active is not None:
            manager.active = data.active
        if data.telegram_chat_id is not None:
            manager.telegram_chat_id = data.telegram_chat_id or None
        return manager

    return app
