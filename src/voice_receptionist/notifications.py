"""Notification interface. Only a MOCK WhatsApp implementation exists today.

A real Twilio WhatsApp sender should implement `Notifier`. Its HTTP client is blocking,
so call it via `asyncio.to_thread` from async code (the agent already does).
"""

from __future__ import annotations

import logging
from typing import Protocol

from .models import Appointment

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def send_booking_confirmation(self, appointment: Appointment, business_name: str) -> None: ...


def format_confirmation(appointment: Appointment, business_name: str) -> str:
    return (
        f"Hello {appointment.name}, your {appointment.service} at {business_name} is booked for "
        f"{appointment.requested_time:%A %d %B %Y, %I:%M %p}. "
        f"Booking ref: {appointment.id}."
    )


class MockWhatsAppNotifier:
    """Records messages in memory and logs them. Sends nothing."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    def send_booking_confirmation(self, appointment: Appointment, business_name: str) -> None:
        message = {
            "to": f"whatsapp:{appointment.phone}",
            "body": format_confirmation(appointment, business_name),
        }
        self.sent.append(message)
        logger.info("[MOCK WhatsApp] to=%s body=%s", message["to"], message["body"])
