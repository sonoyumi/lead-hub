"""API input/output models. Validation lives here, not in the handlers."""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from lead_hub.models import LeadStatus

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_phone(raw: str) -> str | None:
    """'+39 (333) 123-45-67' -> '+393331234567'. Too short/long numbers -> None."""
    digits = re.sub(r"\D", "", raw)
    if not 7 <= len(digits) <= 15:
        return None
    return f"+{digits}" if raw.strip().startswith("+") or len(digits) > 10 else digits


class LeadIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    message: str = Field(default="", max_length=5000)
    source: str = Field(default="website", min_length=1, max_length=100)

    @field_validator("name", "message", "source", mode="before")
    @classmethod
    def _strip(cls, value):
        return " ".join(value.split()) if isinstance(value, str) else value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        normalized = normalize_phone(value)
        if normalized is None:
            raise ValueError("phone must contain 7-15 digits")
        return normalized

    @field_validator("email")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("invalid email")
        return value

    @model_validator(mode="after")
    def _contact_required(self) -> LeadIn:
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        return self


class LeadUpdate(BaseModel):
    status: LeadStatus | None = None
    manager_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    detail: str
    created_at: datetime


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    email: str | None
    message: str
    source: str
    status: LeadStatus
    manager_id: int | None
    duplicates: int
    created_at: datetime
    updated_at: datetime


class LeadDetail(LeadOut):
    events: list[EventOut]


class IntakeResult(BaseModel):
    id: int
    duplicate: bool  # True: merged into an existing recent lead of the same person


class LeadPage(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int


class Stats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_source: dict[str, int]
    conversion: float  # won / (won + lost), 0..1
    overdue: int  # new leads older than the SLA
