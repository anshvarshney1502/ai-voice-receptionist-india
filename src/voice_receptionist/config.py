"""Environment-driven settings and the business profile model."""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class Service(BaseModel):
    name: str = Field(min_length=1)
    duration_minutes: int = Field(default=30, gt=0)


class FAQ(BaseModel):
    question: str
    answer: str


class BusinessProfile(BaseModel):
    """Everything business-specific the receptionist needs to know."""

    name: str
    timezone: str = "Asia/Kolkata"
    services: list[Service] = Field(min_length=1)
    # weekday key -> (open, close); None or a missing key means closed that day.
    hours: dict[str, tuple[time, time] | None]
    faqs: list[FAQ] = []
    # Appointments that may overlap in time (e.g. number of practitioners/chairs).
    capacity: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _check(self) -> BusinessProfile:
        unknown = set(self.hours) - set(WEEKDAYS)
        if unknown:
            raise ValueError(f"unknown weekday keys: {sorted(unknown)}")
        for day, window in self.hours.items():
            if window and window[0] >= window[1]:
                raise ValueError(f"{day}: opening time must be before closing time")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {self.timezone}") from exc
        return self

    def find_service(self, name: str) -> Service | None:
        wanted = name.strip().casefold()
        return next((s for s in self.services if s.name.casefold() == wanted), None)

    def hours_on(self, day: date) -> tuple[time, time] | None:
        return self.hours.get(WEEKDAYS[day.weekday()])

    def hours_summary(self) -> str:
        parts = []
        for day in WEEKDAYS:
            window = self.hours.get(day)
            parts.append(
                f"{day.title()}: {window[0]:%H:%M}-{window[1]:%H:%M}" if window else f"{day.title()}: closed"
            )
        return "; ".join(parts)


# Sample data only: replace via VR_BUSINESS_PROFILE_PATH for a real business.
_open = (time(9, 0), time(19, 0))
DEFAULT_PROFILE = BusinessProfile(
    name="Sample Wellness Clinic",
    services=[
        Service(name="General Consultation", duration_minutes=30),
        Service(name="Dental Checkup", duration_minutes=45),
        Service(name="Follow-up Visit", duration_minutes=15),
    ],
    hours={"mon": _open, "tue": _open, "wed": _open, "thu": _open, "fri": _open, "sat": _open, "sun": None},
    faqs=[
        FAQ(
            question="Do you accept walk-ins?",
            answer="Walk-ins are accepted subject to availability; booking ahead is recommended.",
        ),
        FAQ(question="Which languages can I speak?", answer="Hindi, English or a mix of both."),
    ],
)


class Settings(BaseSettings):
    """Read from VR_* environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_prefix="VR_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/appointments.db")
    business_profile_path: Path | None = None  # JSON file; falls back to DEFAULT_PROFILE
    stt_provider: str = "openai"
    llm_provider: str = "openai"
    tts_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"

    def load_profile(self) -> BusinessProfile:
        if self.business_profile_path is None:
            return DEFAULT_PROFILE
        return BusinessProfile.model_validate_json(self.business_profile_path.read_text("utf-8"))
