# Latency engineering

> **No latency has been measured for this project.** Every number below is either a labelled hypothetical
> budget or a proposed target to be validated by benchmarking. Nothing here is a result.

## What we measure

For a voice agent, the number that matters is the time from the caller **finishing** a turn to the caller **hearing**
the first agent audio:

```
T_first_audio = T_ingress + T_endpointing + T_STT_remaining + T_LLM_TTFT + T_TTS_first_chunk + T_egress
```

| Term | Meaning |
|---|---|
| T_ingress | Caller audio travelling from the phone network through the SIP/media path to the agent |
| T_endpointing | Time VAD/turn detection waits to decide the caller has finished |
| T_STT_remaining | STT work left after the end of speech (final transcript lag) |
| T_LLM_TTFT | LLM time to first token (including any tool call before the spoken reply) |
| T_TTS_first_chunk | TTS time to the first playable audio chunk |
| T_egress | Agent audio travelling back to the caller |

## Why the sum is only an approximation

The stages are pipelined, not sequential:

- STT starts transcribing while the caller is still speaking, so most STT work overlaps with speech and
  only the tail ("remaining") counts.
- The LLM can begin on an interim or predicted transcript (speculative or "preemptive" generation) and the work is
  discarded if the final transcript differs. This hides latency when the guess is right and wastes cost when it is wrong.
- TTS can begin as soon as the LLM has produced the first sentence or clause, not the whole reply.
- Endpointing is a *policy* delay chosen to avoid cutting people off, not compute time. It often dominates and is
  tuned, not optimised.
- The terms are random variables; the sum of medians is not the median of the sum, and tails (p95) are driven by
  network jitter, provider queueing and cold connections.
- Tool calls (e.g. checking availability) insert an extra LLM round trip before speech when the reply depends on them.
- Telephony adds codec and jitter-buffer delay in both directions that is not visible to the agent.

## Illustrative 200 ms budget (NOT measured)

This is an engineering exercise showing how a budget could be allocated if every stage were extremely fast.
It is **not** measured performance and not a claim about any provider.

| Stage | Hypothetical allocation |
|---|---|
| Ingress | 20 ms |
| VAD / endpointing | 20 ms |
| Remaining STT | 40 ms |
| LLM TTFT | 50 ms |
| TTS first chunk | 50 ms |
| Egress | 20 ms |
| **Total** | **200 ms** |

## Why a reliable 200 ms is unrealistic over the phone

- **Endpointing**: 20 ms is shorter than ordinary pauses inside a sentence. Human turn gaps are often a few hundred
  milliseconds, and any endpointing that short will cut callers off constantly. Reliable end-of-turn detection costs time.
- **PSTN and SIP path**: a phone call crosses carrier networks, codecs and jitter buffers. Even before the cloud,
  one-way delay of tens of milliseconds per direction is normal, and it is outside the agent's control.
- **Hosted model APIs**: LLM time-to-first-token and TTS time-to-first-chunk over the public internet commonly cost
  more than 50 ms each once network round trips, queueing and connection setup are included, with variable tails.
- **Tool calls and reasoning** add a full extra model round trip.
- **Tails matter**: an average that meets budget but a p95 that doesn't still produces awkward calls.

## Proposed initial target (subject to benchmarking)

**Median under 800 ms** end-of-turn to first agent audio, measured at the agent. Treat it as a hypothesis to test, then
revise from data. Also track p95 (initial hypothesis: under ~1.5 s, equally unvalidated). A faster feel is possible later
through preemptive generation, regional deployment, streaming providers and filler acknowledgements, each
evaluated separately.

## Instrumentation strategy

1. **Timestamps per turn** at the agent: `t_user_speech_end` (VAD), `t_endpoint_decision`, `t_stt_final`,
   `t_llm_first_token`, `t_tts_first_chunk`, `t_first_audio_published`. LiveKit Agents emits per-component metrics
   events (STT, LLM time-to-first-token, TTS time-to-first-byte, end-of-utterance delay) that can be subscribed to; verify
   the exact field names in the installed SDK version before relying on them.
2. **Derive the stage terms** as differences, keeping the raw timestamps so overlaps are visible.
3. **Log a structured JSON line per turn** with a call id (no transcript text or phone numbers).
4. **Aggregate** p50/p95/p99 per stage and end to end, by provider, model, region and hour.
5. **Separate synthetic from real**: a scripted test caller (generated audio in a LiveKit room) for repeatable
   regression numbers; real PSTN calls through a test number for ingress/egress, which the agent cannot see directly
   (measure with a recorded round trip or a loopback tone).
6. **Dashboards and alerts** on p95 regressions after each model or provider change.

### Proposed metrics

| Metric | Report | Notes |
|---|---|---|
| End-of-turn → first audio | p50, p95 | headline metric |
| Endpointing delay | p50, p95 | policy-driven |
| STT final lag | p50, p95 | |
| LLM TTFT | p50, p95 | split by turns with and without tool calls |
| TTS first chunk | p50, p95 | |
| Interruption rate, false-interruption rate | rate | quality, not speed |
| Turns over 1.5 s | % | proposed threshold |
