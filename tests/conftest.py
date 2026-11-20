from datetime import datetime

import pytest

from voice_receptionist.booking import BookingService
from voice_receptionist.config import DEFAULT_PROFILE

# Monday 2026-11-16 10:00. Sample profile: Mon-Sat 09:00-19:00, Sunday closed.
NOW = datetime(2026, 11, 16, 10, 0)


@pytest.fixture
def bookings(tmp_path):
    return BookingService(tmp_path / "test.db", DEFAULT_PROFILE, now=lambda: NOW)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """A November 2026 datetime; day 17 is Tuesday, day 22 is Sunday."""
    return datetime(2026, 11, day, hour, minute)
