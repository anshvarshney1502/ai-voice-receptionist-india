# Roadmap

Ordered by what unlocks the most. Nothing below is promised or scheduled.

## Phase 1: Foundation (done)
- Business profile, appointment models, validation, SQLite booking, correction/confirmation logic
- FastAPI health and appointment endpoints, mock WhatsApp, offline demo, unit tests
- LiveKit agent skeleton with pluggable provider registry

## Phase 2: Make the live agent real
- Run the agent end to end with real LiveKit and OpenAI accounts; fix what breaks
- Real inbound calls: Twilio SIP trunk, LiveKit inbound trunk and dispatch rule, documented setup
- Latency instrumentation per [LATENCY.md](LATENCY.md); first real p50/p95 numbers
- Tune endpointing for phone-number dictation

## Phase 3: Hindi and Hinglish quality
- Build a small evaluation set of Hinglish booking dialogues and call-quality audio
- Compare STT and TTS providers; add them to the provider registry
- Evaluate relative-date resolution ("kal", "parso", "saade chaar")

## Phase 4: Notifications and product basics
- Twilio WhatsApp notifier using approved templates, with retries and delivery status
- Cancel and reschedule; reminders
- API authentication and rate limiting
- Per-business configuration via files or admin API; multiple staff calendars

## Phase 5: Hardening
- Postgres option, migrations, encryption at rest, retention policy and call-disclosure line
- Call transcripts and recordings with consent handling
- Observability, load testing, deployment guide
