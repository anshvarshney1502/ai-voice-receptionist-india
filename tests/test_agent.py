"""Smoke test that our code still matches the installed livekit-agents API (no network/keys)."""

import pytest
from conftest import NOW

pytest.importorskip("livekit.agents")

from voice_receptionist.agent import Receptionist, build_component, build_instructions  # noqa: E402
from voice_receptionist.config import DEFAULT_PROFILE, Settings  # noqa: E402
from voice_receptionist.notifications import MockWhatsAppNotifier  # noqa: E402


def test_receptionist_registers_both_tools(bookings):
    agent = Receptionist(bookings, MockWhatsAppNotifier(), now=NOW)
    names = {t.id for t in agent.tools}
    assert names == {"update_booking_details", "confirm_booking"}


def test_instructions_contain_profile_facts():
    text = build_instructions(DEFAULT_PROFILE, NOW)
    assert "Sample Wellness Clinic" in text and "Dental Checkup (45 min)" in text
    assert "Sun: closed" in text and "Monday 16 November 2026" in text


def test_unknown_provider_is_a_clear_error():
    with pytest.raises(ValueError, match="No stt provider 'nope'"):
        build_component("stt", "nope", Settings())
