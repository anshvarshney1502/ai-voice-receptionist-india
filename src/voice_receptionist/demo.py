"""Scripted booking simulation. Needs no API keys, no network, no audio.

SIMULATED: there is no STT, LLM or TTS here. The "extracted" fields are hand-written
stand-ins for what the LLM would pass to the `update_booking_details` tool; the real
booking logic (validation, correction handling, SQLite, mock WhatsApp) does run.

Run: python -m voice_receptionist.demo
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from .booking import BookingService
from .config import DEFAULT_PROFILE
from .dialogue import BookingConversation
from .notifications import MockWhatsAppNotifier


def _next_open_day(bookings: BookingService) -> datetime:
    day = datetime.now() + timedelta(days=1)
    while bookings.profile.hours_on(day.date()) is None:
        day += timedelta(days=1)
    return day.replace(hour=16, minute=0, second=0, microsecond=0)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bookings = BookingService(Path(tmp) / "demo.db", DEFAULT_PROFILE)
        notifier = MockWhatsAppNotifier()
        convo = BookingConversation(bookings)
        day = _next_open_day(bookings)

        print(f"== {DEFAULT_PROFILE.name} | SIMULATED call (no STT/LLM/TTS) ==\n")
        turns = [
            (
                "Namaste, General Consultation ke liye appointment chahiye. Naam Rohan Mehta.",
                {"name": "Rohan Mehta", "service": "General Consultation"},
            ),
            ("Mera number 98765 43210 hai.", {"phone": "98765 43210"}),
            ("Kal shaam 4 baje.", {"requested_time": day.isoformat()}),
            ("Nahi nahi, 5 baje karo.", {"requested_time": (day + timedelta(hours=1)).isoformat()}),
        ]
        for caller, fields in turns:
            print(f"Caller : {caller}")
            print(f"  [simulated extraction] {fields}")
            print(f"  [tool result -> LLM]   {convo.update(**fields).message()}\n")

        print("Caller : Haan, theek hai.")
        appointment = convo.confirm()
        notifier.send_booking_confirmation(appointment, DEFAULT_PROFILE.name)
        print(f"  [saved to SQLite]      id={appointment.id} at {appointment.requested_time}")
        print(f"  [mock WhatsApp]        {notifier.sent[-1]['to']}: {notifier.sent[-1]['body']}")


if __name__ == "__main__":
    main()
