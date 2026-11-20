"""Appointment validation and SQLite persistence."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import BusinessProfile, Service
from .models import Appointment, AppointmentRequest

_FMT = "seconds"  # one fixed ISO precision so string comparison in SQL is chronological

_SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    service TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'booked',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_appointments_start ON appointments(start_time);
"""


class BookingError(Exception):
    """Base class; str(exc) is safe to read back to a caller."""


class ValidationFailure(BookingError):
    """The request can never be satisfied as given (unknown service, closed, past)."""


class SlotUnavailable(BookingError):
    """The requested interval is already full."""


class BookingService:
    def __init__(
        self,
        db_path: str | Path,
        profile: BusinessProfile,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.profile = profile
        self._tz = ZoneInfo(profile.timezone)
        # `now` returns naive local business time; injectable for tests.
        self._now = now or (lambda: datetime.now(self._tz).replace(tzinfo=None))
        self._db_path = str(db_path)
        if self._db_path != ":memory:":  # a new connection per call would lose an in-memory DB
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        # One short-lived connection per operation keeps this safe under FastAPI's threadpool.
        conn = sqlite3.connect(self._db_path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _localize(self, dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            dt = dt.astimezone(self._tz).replace(tzinfo=None)
        return dt.replace(second=0, microsecond=0)

    def validate(self, req: AppointmentRequest) -> tuple[Service, datetime, datetime]:
        """Check service, time and opening hours. Does not check slot availability."""
        service = self.profile.find_service(req.service)
        if service is None:
            names = ", ".join(s.name for s in self.profile.services)
            raise ValidationFailure(f"Unknown service '{req.service}'. Available: {names}.")
        start = self._localize(req.requested_time)
        if start <= self._now():
            raise ValidationFailure("That time is in the past.")
        end = start + timedelta(minutes=service.duration_minutes)
        window = self.profile.hours_on(start.date())
        if window is None:
            raise ValidationFailure(f"We are closed on {start:%A}.")
        if end.date() != start.date() or start.time() < window[0] or end.time() > window[1]:
            raise ValidationFailure(
                f"{service.name} takes {service.duration_minutes} min and must fit within "
                f"{window[0]:%H:%M}-{window[1]:%H:%M} on {start:%A}."
            )
        return service, start, end

    def create(self, req: AppointmentRequest) -> Appointment:
        _, start, end = self.validate(req)
        created = self._now()
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")  # serialise the check-then-insert
            try:
                (taken,) = conn.execute(
                    "SELECT COUNT(*) FROM appointments "
                    "WHERE status = 'booked' AND start_time < ? AND end_time > ?",
                    (end.isoformat(timespec=_FMT), start.isoformat(timespec=_FMT)),
                ).fetchone()
                if taken >= self.profile.capacity:
                    raise SlotUnavailable(f"{start:%A %d %b, %H:%M} is already booked.")
                cur = conn.execute(
                    "INSERT INTO appointments (name, phone, service, start_time, end_time, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        req.name,
                        req.phone,
                        self.profile.find_service(req.service).name,  # type: ignore[union-attr]
                        start.isoformat(timespec=_FMT),
                        end.isoformat(timespec=_FMT),
                        created.isoformat(timespec=_FMT),
                    ),
                )
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
        return self.get(cur.lastrowid)  # type: ignore[arg-type,return-value]

    @staticmethod
    def _row(row: sqlite3.Row) -> Appointment:
        return Appointment(
            id=row["id"],
            name=row["name"],
            phone=row["phone"],
            service=row["service"],
            requested_time=row["start_time"],
            end_time=row["end_time"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def get(self, appointment_id: int) -> Appointment | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, day: date | None = None) -> list[Appointment]:
        sql, args = "SELECT * FROM appointments", ()
        if day:
            sql += " WHERE start_time >= ? AND start_time < ?"
            args = (day.isoformat(), (day + timedelta(days=1)).isoformat())
        with self._conn() as conn:
            rows = conn.execute(sql + " ORDER BY start_time", args).fetchall()
        return [self._row(r) for r in rows]
