"""FastAPI app: health check and a basic appointment API.

No authentication yet: do not expose this to the public internet as-is.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import FastAPI, HTTPException

from .booking import BookingService, SlotUnavailable, ValidationFailure
from .config import Settings
from .models import Appointment, AppointmentRequest
from .notifications import MockWhatsAppNotifier, Notifier

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    bookings: BookingService | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    settings = settings or Settings()
    if bookings is None:
        bookings = BookingService(settings.db_path, settings.load_profile())
    notifier = notifier or MockWhatsAppNotifier()
    app = FastAPI(title="AI Voice Receptionist API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "business": bookings.profile.name}

    @app.post("/appointments", response_model=Appointment, status_code=201)
    def create_appointment(req: AppointmentRequest) -> Appointment:
        try:
            appointment = bookings.create(req)
        except ValidationFailure as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SlotUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        try:
            notifier.send_booking_confirmation(appointment, bookings.profile.name)
        except Exception:  # a failed notification must not undo a saved booking
            logger.exception("notification failed for appointment %s", appointment.id)
        return appointment

    @app.get("/appointments", response_model=list[Appointment])
    def list_appointments(day: date | None = None) -> list[Appointment]:
        return bookings.list(day)

    @app.get("/appointments/{appointment_id}", response_model=Appointment)
    def get_appointment(appointment_id: int) -> Appointment:
        appointment = bookings.get(appointment_id)
        if appointment is None:
            raise HTTPException(status_code=404, detail="Appointment not found")
        return appointment

    return app
