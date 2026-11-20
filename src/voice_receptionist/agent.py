"""LiveKit voice agent (LIVE integration: needs LiveKit + OpenAI credentials to run).

Pipeline: Silero VAD -> STT -> LLM (with tools) -> TTS, orchestrated by AgentSession.
All booking logic lives in `dialogue.py` / `booking.py`; the tools here are thin wrappers.

Dev run:   python -m voice_receptionist.agent console   (local mic/speaker, still needs OpenAI key)
Worker:    python -m voice_receptionist.agent dev        (connects to LiveKit; needs LIVEKIT_* vars)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
)
from livekit.plugins import openai, silero

from .booking import BookingError, BookingService
from .config import BusinessProfile, Settings
from .dialogue import BookingConversation
from .notifications import MockWhatsAppNotifier, Notifier

logger = logging.getLogger(__name__)

# Pluggable providers: add an entry here (e.g. a Deepgram STT or ElevenLabs TTS plugin) and
# select it with VR_STT_PROVIDER / VR_LLM_PROVIDER / VR_TTS_PROVIDER. Only "openai" is wired today.
PROVIDERS: dict[str, dict[str, Callable[[Settings], Any]]] = {
    # shortcut: language="hi" is a starting point for Hindi/Hinglish, not a tuned setting.
    "stt": {"openai": lambda s: openai.STT(language="hi")},
    "llm": {"openai": lambda s: openai.LLM(model=s.llm_model)},
    "tts": {"openai": lambda s: openai.TTS()},
}


def build_component(kind: str, name: str, settings: Settings) -> Any:
    try:
        return PROVIDERS[kind][name](settings)
    except KeyError:
        raise ValueError(f"No {kind} provider '{name}'. Available: {sorted(PROVIDERS[kind])}") from None


def build_instructions(profile: BusinessProfile, now: datetime) -> str:
    services = "\n".join(f"- {s.name} ({s.duration_minutes} min)" for s in profile.services)
    faqs = "\n".join(f"Q: {f.question}\nA: {f.answer}" for f in profile.faqs) or "(none)"
    return f"""You are the phone receptionist for {profile.name}. Today is {now:%A %d %B %Y}, \
{now:%H:%M} ({profile.timezone}).

Language: callers speak Hindi, English or Hinglish. Reply in the language the caller uses. Keep \
every reply to one or two short sentences, because this is a phone call. Ask one question at a time.

Services:
{services}
Opening hours: {profile.hours_summary()}

FAQs:
{faqs}

Booking rules:
- Collect name, phone number, service and preferred date/time. Call update_booking_details every \
time the caller gives or corrects any of them; pass only the fields that changed.
- Convert relative dates ("kal", "next Monday") to a concrete local time like 2026-11-23T16:30.
- When the tool says the details are ready, read them back and wait for an explicit yes. If the \
caller corrects anything, call update_booking_details again and read the new details back.
- Only after an explicit yes, call confirm_booking. Never claim a booking exists before it succeeds.
- Never guess availability or business facts. If the tool reports a problem, explain it and offer \
another time. If you cannot help, say so politely.
"""


class Receptionist(Agent):
    def __init__(
        self,
        bookings: BookingService,
        notifier: Notifier,
        now: datetime | None = None,
    ) -> None:
        now = now or datetime.now(bookings._tz).replace(tzinfo=None)  # noqa: SLF001
        super().__init__(instructions=build_instructions(bookings.profile, now))
        self._convo = BookingConversation(bookings)
        self._notifier = notifier

    @function_tool
    async def update_booking_details(
        self,
        context: RunContext,
        name: str | None = None,
        phone: str | None = None,
        service: str | None = None,
        requested_time: str | None = None,
    ) -> str:
        """Record or correct the caller's booking details. Pass only fields that were just given or changed.

        Args:
            name: Caller's full name.
            phone: Caller's 10-digit Indian mobile number.
            service: One of the business's services, exactly as listed.
            requested_time: Local date and time in ISO format, e.g. 2026-11-23T16:30.
        """
        return self._convo.update(
            name=name, phone=phone, service=service, requested_time=requested_time
        ).message()

    @function_tool
    async def confirm_booking(self, context: RunContext) -> str:
        """Save the booking. Call only after the caller explicitly confirmed the read-back details."""
        try:
            appointment = await asyncio.to_thread(self._convo.confirm)
        except BookingError as exc:
            return f"Booking not saved: {exc} Ask the caller for a different time."
        try:
            await asyncio.to_thread(
                self._notifier.send_booking_confirmation,
                appointment,
                self._convo.bookings.profile.name,
            )
        except Exception:  # the booking is saved; a failed message must not fail the call
            logger.exception("confirmation message failed for appointment %s", appointment.id)
        return (
            f"Booked. Reference number {appointment.id}. "
            "Tell the caller a confirmation message is on its way."
        )


server = AgentServer()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()  # load once per worker process, not per call


server.setup_fnc = prewarm


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    settings = Settings()
    bookings = BookingService(settings.db_path, settings.load_profile())
    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=build_component("stt", settings.stt_provider, settings),
        llm=build_component("llm", settings.llm_provider, settings),
        tts=build_component("tts", settings.tts_provider, settings),
        allow_interruptions=True,  # barge-in; endpointing/VAD thresholds are left at SDK defaults
    )
    # MockWhatsAppNotifier only logs; swap in a real Twilio notifier once one exists.
    await session.start(agent=Receptionist(bookings, MockWhatsAppNotifier()), room=ctx.room)
    await session.generate_reply(
        instructions=f"Greet the caller on behalf of {bookings.profile.name} and ask how you can help."
    )


if __name__ == "__main__":
    load_dotenv()  # make OPENAI_API_KEY / LIVEKIT_* from .env visible to the SDK
    cli.run_app(server)
