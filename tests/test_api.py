import pytest
from conftest import at
from fastapi.testclient import TestClient

from voice_receptionist.api import create_app
from voice_receptionist.notifications import MockWhatsAppNotifier


@pytest.fixture
def notifier():
    return MockWhatsAppNotifier()


@pytest.fixture
def client(bookings, notifier):
    return TestClient(create_app(bookings=bookings, notifier=notifier))


def payload(**over):
    base = {
        "name": "Asha Rao",
        "phone": "9876543210",
        "service": "General Consultation",
        "requested_time": at(17, 11).isoformat(),
    }
    return {**base, **over}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "business": "Sample Wellness Clinic"}


def test_create_get_list_and_notify(client, notifier):
    created = client.post("/appointments", json=payload())
    assert created.status_code == 201
    body = created.json()
    assert body["phone"] == "+919876543210" and body["status"] == "booked"
    assert client.get(f"/appointments/{body['id']}").json() == body
    assert client.get("/appointments").json() == [body]
    assert client.get("/appointments", params={"day": "2026-11-18"}).json() == []
    assert len(notifier.sent) == 1


def test_error_mapping(client, notifier):
    assert client.post("/appointments", json=payload(phone="123")).status_code == 422  # shape
    assert (
        client.post("/appointments", json=payload(requested_time=at(22, 11).isoformat())).status_code == 422
    )
    assert client.post("/appointments", json=payload()).status_code == 201
    assert client.post("/appointments", json=payload()).status_code == 409  # slot taken
    assert client.get("/appointments/999").status_code == 404
    assert len(notifier.sent) == 1  # failures send nothing


def test_notifier_failure_does_not_lose_booking(bookings):
    class Broken:
        def send_booking_confirmation(self, *_):
            raise RuntimeError("twilio down")

    client = TestClient(create_app(bookings=bookings, notifier=Broken()))
    assert client.post("/appointments", json=payload()).status_code == 201
    assert len(bookings.list()) == 1
