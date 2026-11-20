"""Per-call booking state: incremental extraction, corrections, read-back, confirmation.

Pure Python (no LiveKit imports) so it is unit-testable and reusable by any frontend.
The LLM extracts fields and calls `update`; this class is the source of truth for what
has been captured, what is missing and whether the booking is ready to confirm.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .booking import BookingError, BookingService
from .models import Appointment, AppointmentRequest, clean_name, normalize_phone, parse_time

FIELDS = ("name", "phone", "service", "requested_time")


@dataclass
class UpdateResult:
    changed: list[str] = field(default_factory=list)  # human-readable, e.g. "requested_time: A -> B"
    errors: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    readback: str | None = None  # set only when every field is present and valid

    @property
    def ready(self) -> bool:
        return self.readback is not None

    def message(self) -> str:
        """Text returned to the LLM as the tool result."""
        lines = [f"Updated {c}." for c in self.changed]
        lines += [f"Problem: {e}" for e in self.errors]
        if self.missing:
            lines.append(f"Still needed from caller: {', '.join(self.missing)}.")
        if self.readback:
            lines.append(f"Read these back and ask the caller to confirm: {self.readback}")
        return " ".join(lines) or "No change."


def _fmt_time(value: datetime) -> str:
    return f"{value:%A %d %B, %I:%M %p}"


class BookingConversation:
    def __init__(self, bookings: BookingService) -> None:
        self.bookings = bookings
        self.draft: dict[str, Any] = {}
        self.appointment: Appointment | None = None

    def _clean(self, key: str, value: Any) -> Any:
        if key == "name":
            return clean_name(value)
        if key == "phone":
            return normalize_phone(value)
        if key == "requested_time":
            return parse_time(value)
        service = self.bookings.profile.find_service(value)
        if service is None:
            names = ", ".join(s.name for s in self.bookings.profile.services)
            raise ValueError(f"unknown service '{value}'; available: {names}")
        return service.name

    def missing(self) -> list[str]:
        return [f for f in FIELDS if f not in self.draft]

    def update(self, **fields: Any) -> UpdateResult:
        """Merge new or corrected fields. Empty/None values are ignored."""
        result = UpdateResult()
        if self.appointment:
            result.errors.append("This booking is already confirmed.")
            return result
        for key, value in fields.items():
            if value is None or value == "":
                continue
            if key not in FIELDS:
                result.errors.append(f"unknown field '{key}'")
                continue
            try:
                cleaned = self._clean(key, value)
            except ValueError as exc:
                result.errors.append(f"{key}: {exc}")
                continue
            old = self.draft.get(key)
            if old != cleaned:
                self.draft[key] = cleaned
                result.changed.append(f"{key}: {old} -> {cleaned}" if old else f"{key}: {cleaned}")
        result.missing = self.missing()
        if not result.missing:
            try:
                self.bookings.validate(self._request())
                result.readback = self.summary()
            except BookingError as exc:
                result.errors.append(str(exc))
        return result

    def _request(self) -> AppointmentRequest:
        return AppointmentRequest(**self.draft)

    def summary(self) -> str:
        d = self.draft
        return f"{d['name']}, {d['phone']}, {d['service']}, {_fmt_time(d['requested_time'])}"

    def confirm(self) -> Appointment:
        """Persist the booking. Raises BookingError if incomplete, invalid or the slot is taken."""
        if self.appointment:
            return self.appointment
        if self.missing():
            raise BookingError(f"Cannot confirm yet; still missing: {', '.join(self.missing())}.")
        self.appointment = self.bookings.create(self._request())
        return self.appointment
