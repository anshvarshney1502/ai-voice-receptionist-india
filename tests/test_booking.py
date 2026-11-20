from datetime import UTC, datetime, timedelta

import pytest
from conftest import NOW, at
from pydantic import ValidationError

from voice_receptionist.booking import BookingService, SlotUnavailable, ValidationFailure
from voice_receptionist.config import DEFAULT_PROFILE
from voice_receptionist.models import AppointmentRequest, normalize_phone


def req(**over):
    base = {
        "name": "Asha Rao",
        "phone": "9876543210",
        "service": "General Consultation",
        "requested_time": at(17, 11),
    }
    return AppointmentRequest(**{**base, **over})


@pytest.mark.parametrize(
    "raw", ["9876543210", "+91 98765 43210", "919876543210", "09876543210", "98765-43210"]
)
def test_phone_normalisation(raw):
    assert normalize_phone(raw) == "+919876543210"


@pytest.mark.parametrize("raw", ["12345", "5876543210", "+1 415 555 0100", "abcdefghij"])
def test_bad_phone_rejected(raw):
    with pytest.raises(ValueError):
        normalize_phone(raw)


def test_request_rejects_short_name():
    with pytest.raises(ValidationError):
        req(name=" A ")


def test_create_persists_and_normalises(bookings):
    created = bookings.create(req(service="general consultation"))
    assert created.id == 1
    assert created.phone == "+919876543210"
    assert created.service == "General Consultation"  # canonical casing
    assert created.end_time == at(17, 11, 30)


def test_persistence_survives_new_service_instance(bookings, tmp_path):
    bookings.create(req())
    reopened = BookingService(tmp_path / "test.db", DEFAULT_PROFILE, now=lambda: NOW)
    assert [a.name for a in reopened.list()] == ["Asha Rao"]
    assert reopened.get(1).requested_time == at(17, 11)
    assert reopened.get(99) is None


def test_list_filters_by_day(bookings):
    bookings.create(req(requested_time=at(17, 11)))
    bookings.create(req(requested_time=at(18, 11)))
    assert len(bookings.list(at(17, 0).date())) == 1


@pytest.mark.parametrize(
    "when, reason",
    [
        (at(16, 9), "past"),  # Monday 09:00 is before NOW
        (at(22, 11), "closed"),  # Sunday
        (at(17, 8, 30), "must fit"),  # before opening
        (at(17, 18, 45), "must fit"),  # 30-minute visit would end after 19:00
    ],
)
def test_validation_failures(bookings, when, reason):
    with pytest.raises(ValidationFailure, match=reason):
        bookings.create(req(requested_time=when))
    assert bookings.list() == []


def test_unknown_service(bookings):
    with pytest.raises(ValidationFailure, match="Unknown service"):
        bookings.create(req(service="Haircut"))


def test_overlap_rejected_but_adjacent_allowed(bookings):
    bookings.create(req(requested_time=at(17, 11)))  # 11:00-11:30
    with pytest.raises(SlotUnavailable):
        bookings.create(req(requested_time=at(17, 11, 15)))
    bookings.create(req(requested_time=at(17, 11, 30)))  # starts exactly when the first ends
    assert len(bookings.list()) == 2


def test_capacity_two_allows_double_booking(tmp_path):
    profile = DEFAULT_PROFILE.model_copy(update={"capacity": 2})
    svc = BookingService(tmp_path / "c.db", profile, now=lambda: NOW)
    svc.create(req())
    svc.create(req())
    with pytest.raises(SlotUnavailable):
        svc.create(req())


def test_timezone_aware_input_converted_to_business_time(bookings):
    utc_time = datetime(2026, 11, 17, 5, 30, tzinfo=UTC)  # 11:00 IST
    assert bookings.create(req(requested_time=utc_time)).requested_time == at(17, 11)


def test_default_clock_rejects_past():
    svc = BookingService(":memory:", DEFAULT_PROFILE)
    with pytest.raises(ValidationFailure, match="past"):
        svc.validate(req(requested_time=datetime.now() - timedelta(days=1)))
