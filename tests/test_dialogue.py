import pytest
from conftest import at

from voice_receptionist.booking import BookingError, SlotUnavailable
from voice_receptionist.dialogue import BookingConversation
from voice_receptionist.models import AppointmentRequest
from voice_receptionist.notifications import MockWhatsAppNotifier


def full(convo, **over):
    fields = {
        "name": "Rohan Mehta",
        "phone": "98765 43210",
        "service": "dental checkup",
        "requested_time": at(17, 16).isoformat(),
    }
    return convo.update(**{**fields, **over})


def test_incremental_collection_tracks_missing(bookings):
    convo = BookingConversation(bookings)
    result = convo.update(name="Rohan Mehta")
    assert result.missing == ["phone", "service", "requested_time"]
    assert not result.ready
    result = convo.update(phone="9876543210", service="Dental Checkup")
    assert result.missing == ["requested_time"]


def test_ready_result_contains_readback(bookings):
    result = full(BookingConversation(bookings))
    assert result.ready
    assert "Rohan Mehta" in result.readback and "+919876543210" in result.readback
    assert "Dental Checkup" in result.readback


def test_correction_replaces_value_and_reports_change(bookings):
    convo = BookingConversation(bookings)
    full(convo)
    result = convo.update(requested_time=at(17, 17).isoformat())
    assert result.changed and "requested_time" in result.changed[0]
    assert result.ready and "05:00 PM" in result.readback
    assert convo.draft["requested_time"] == at(17, 17)


def test_repeating_same_value_is_not_a_change(bookings):
    convo = BookingConversation(bookings)
    full(convo)
    assert convo.update(name="Rohan Mehta").changed == []


def test_invalid_correction_keeps_previous_value(bookings):
    convo = BookingConversation(bookings)
    full(convo)
    result = convo.update(phone="12345")
    assert result.errors and convo.draft["phone"] == "+919876543210"
    assert result.ready  # draft is still valid


def test_unavailable_time_blocks_readback(bookings):
    convo = BookingConversation(bookings)
    result = full(convo, requested_time=at(22, 11).isoformat())  # Sunday
    assert not result.ready and "closed" in result.errors[0]


def test_confirm_requires_all_fields(bookings):
    convo = BookingConversation(bookings)
    convo.update(name="Rohan Mehta")
    with pytest.raises(BookingError, match="missing"):
        convo.confirm()


def test_confirm_persists_and_locks_the_draft(bookings):
    convo = BookingConversation(bookings)
    full(convo)
    appointment = convo.confirm()
    assert bookings.get(appointment.id).name == "Rohan Mehta"
    assert convo.confirm() is appointment  # idempotent: no duplicate row
    assert len(bookings.list()) == 1
    assert convo.update(name="Someone Else").errors  # cannot edit after confirmation


def test_confirm_surfaces_slot_conflict(bookings):
    bookings.create(
        AppointmentRequest(
            name="Other Person", phone="9123456789", service="Dental Checkup", requested_time=at(17, 16)
        )
    )
    convo = BookingConversation(bookings)
    result = full(convo)
    assert result.ready  # validate() does not check availability...
    with pytest.raises(SlotUnavailable):  # ...confirm() does, atomically
        convo.confirm()


def test_mock_notifier_records_message(bookings):
    convo = BookingConversation(bookings)
    full(convo)
    notifier = MockWhatsAppNotifier()
    notifier.send_booking_confirmation(convo.confirm(), "Sample Wellness Clinic")
    assert notifier.sent[0]["to"] == "whatsapp:+919876543210"
    assert "Booking ref: 1" in notifier.sent[0]["body"]
