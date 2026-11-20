"""Structured appointment models and field normalisers."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, field_validator

# Indian mobile numbers: optional +91 / 91 / 0 prefix, then 10 digits starting 6-9.
_PHONE_RE = re.compile(r"^(?:\+?91|0)?([6-9]\d{9})$")


def clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if len(name) < 2:
        raise ValueError("name must be at least 2 characters")
    return name


def normalize_phone(raw: str) -> str:
    """Return +91XXXXXXXXXX or raise ValueError."""
    match = _PHONE_RE.match(re.sub(r"[\s\-()]", "", raw))
    if not match:
        raise ValueError("expected a 10-digit Indian mobile number (optionally with +91)")
    return f"+91{match.group(1)}"


def parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("time must be ISO format, e.g. 2026-11-23T16:30") from exc


class BookingStatus(StrEnum):
    BOOKED = "booked"


class AppointmentRequest(BaseModel):
    """What the caller (or API client) asks for, validated for shape only."""

    name: str
    phone: str
    service: str
    requested_time: datetime

    _name = field_validator("name")(clean_name)
    _phone = field_validator("phone")(normalize_phone)


class Appointment(AppointmentRequest):
    """A persisted booking. `requested_time` is naive local time in the business timezone."""

    id: int
    end_time: datetime
    status: BookingStatus = BookingStatus.BOOKED
    created_at: datetime
