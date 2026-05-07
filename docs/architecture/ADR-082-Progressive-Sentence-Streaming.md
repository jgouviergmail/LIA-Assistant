# ADR-082: Progressive sentence streaming for low-latency TTS

**Status**: ✅ IMPLEMENTED (2026-05-07)
**Author**: Claude Code (Opus 4.7)
**Related**: ADR-081 (Voice TTS configuration driven by the LLM catalogue), ADR-080 (Remote Voice STT and pricing-unit extension), ADR-039 (Cost Optimization & Token Management), ADR-070 (ReAct Execution Mode)

## Context

The voice stack delivered by ADR-081 already streams audio chunks back to
the client through a Server-Sent Events (SSE) channel, but the **Time-To-
First-Audio** (TTFA) was dominated by a sequential pipeline:

- **Chat mode** (`stream_direct_tts`): wait for the chat LLM stream to fully
  complete, then split the response into sentences, then synthesise each
  sentence sequentially. With a 5–15 s response and 3–5 sentences, the
  user heard nothing for the entire response generation window.
- **Agent mode** (`stream_voice_comment`): wait for the voice-comment LLM
  to fully invoke (`ainvoke`, 1–3 s for a 50–150 token comment), then
  split + sequentially TTS. The "parallel" parallelism was only between
  the assistant text streaming and the voice generation — not within the
  voice generation itself.

Telemetry on the v4.0 pipeline (cf. `voice_progressive_started` event)
showed `elapsed_since_start_ms ≈ 27 000` for an average agent-mode turn
on the dev environment — i.e. the user waited 27 s before the first audio
sample landed, even though the chat response had been visible for several
seconds.

A second concern was the per-call HTTP cost: `ElevenLabsTTSClient` opened
a new `httpx.AsyncClient` for every sentence (`async with httpx.AsyncClient`
inside `synthesize`), paying the TLS handshake + DNS + TCP setup ~100–
300 ms each call. On a 5-sentence response this adds 0.5–1.5 s of pure
network ceremony — ~10 % of the legacy TTFA, fully avoidable.

A third concern surfaced during integration: the legacy "wait full text
then split" path coupled three independent layers (LLM streaming, sentence
detection, TTS synthesis), making it impossible to inject one without
rewriting the others.

## Decision

Three orthogonal optimisations, layered:

### 1. Persistent HTTP client per `TTSClient` instance

`ElevenLabsTTSClient` now holds a single `httpx.AsyncClient` for the lifetime
of the instance, with explicit `Limits(max_keepalive_connections=10,
max_connections=20, keepalive_expiry=60s)`. Default headers
(`xi-api-key`, `Accept`, `Content-Type`) live on the client so each
`synthesize()` only carries the per-request body. `close()` proactively
calls `aclose()` to release the pool. `OpenAITTSClient` already pooled via
the `AsyncOpenAI` SDK — no change needed. `EdgeTTSClient` runs through the
WebSocket-based `edge-tts` library that owns its own lifecycle.

Saving: ~100–300 ms per sentence on calls #2..N within a request.

### 2. `ProgressiveSentenceStreamer` — sentence-level pipelining

A new module `src/domains/voice/sentence_streamer.py` exposes:

```python
class ProgressiveSentenceStreamer:
    def feed(self, text: str) -> None: ...
    def close_input(self) -> None: ...
    def cancel_pending(self) -> None: ...
    async def audio_chunks(self) -> AsyncIterator[VoiceAudioChunk]: ...
```

Lifecycle:

1. Producer feeds text fragments (any granularity — single token to
   multi-sentence chunk). The buffer is scanned for a sentence-end
   regex (`[.!?]+`). Every complete sentence is dispatched immediately
   as an `asyncio.Task` calling the per-call synth.
2. `close_input()` flushes the trailing buffer (no terminator required)
   as the last sentence, then signals end-of-input. The drain task
   pushes an end-of-stream sentinel (`None`) into the consumer queue
   once every dispatched task has been emitted in dispatch order.
3. `audio_chunks()` is a single-consumer async iterator that yields
   `VoiceAudioChunk` objects in dispatch order — even when sentence #2
   finishes its TTS round-trip before sentence #1 (very common when
   sentence lengths differ). Achieved with an in-order delivery buffer
   `_pending: dict[int, VoiceAudioChunk]` and a counter
   `_next_emit_idx`.

Failure handling: a TTS failure on sentence N marks the slot as `failed`
in a separate set; the drain skips the slot (so the consumer hears a
trailing silence at that position) and keeps emitting subsequent ones.
This makes a single provider hiccup non-fatal for the rest of the
response.

Cost tracking: an optional `on_chars_synthesized: Callable[[int], None]`
callback fires per sentence dispatched. The voice service binds it to
`tracker.record_tts_call(...)` — exceptions inside the callback are
swallowed (cost tracking is best-effort and must never break audio).

### 3. Two integration points

- **Chat mode** (`stream_direct_tts` legacy path retained for back-compat):
  the agents SSE main loop watches for the first `router_decision` chunk
  with `intention=conversation`; if voice is enabled, it spins up
  `VoiceCommentService.start_progressive_chat_stream(...)` which returns
  the `(streamer, drain_task)` tuple. Each subsequent `token` SSE chunk
  calls `streamer.feed(content_fragment)`. The drain task pushes audio
  chunks into the same `voice_chunk_queue` the legacy parallel path
  uses, so the existing SSE drain logic re-emits them unchanged. After
  the stream ends, `streamer.close_input()` is called.
- **Agent mode** (`stream_voice_comment` refactored): the voice-comment
  LLM is now invoked via `astream()` instead of `ainvoke()`. Each
  streaming chunk's `content` is fed into a `ProgressiveSentenceStreamer`
  whose synth is bound to the resolved `tts_client`. The `await tracker.commit()`
  call is preserved so character-billing is recorded once at end-of-stream.

The two paths share the same `_build_voice_llm_invocation()` private
helper for prompt + token-tracking config — `generate_voice_comment` (the
non-streaming legacy entry) still works for non-LangGraph callers.

## Consequences

### Positive

- **TTFA collapses**:
  - Chat mode (5 s response, 5 sentences): legacy ≈ 5,5 s → new ≈ 0,8–1,2 s (5×).
  - Agent mode (voice LLM 2 s, 3 sentences): legacy ≈ 3,5 s → new ≈ 1–1,5 s (2×).
  - Long agent turns (registry capté tardivement): legacy 6–8 s → new 2,5–3 s.
- **Architecture decoupled**: LLM streaming, sentence detection and TTS
  dispatch are three independent layers. Adding a future provider
  (Gemini TTS, replacement for ElevenLabs library voices, …) is a single
  change on the `synth` callable; the streamer doesn't care.
- **Resilient to provider hiccups**: a 502 / 429 on one sentence no longer
  silences the rest of the response.
- **Cost tracking unchanged**: per-character billing flows through
  `tracker.record_tts_call(...)` exactly as before; the badge `🔊 N chars`
  on the assistant bubble already reads from
  `conversation_messages.tts_characters` (cf. ADR-081).
- **HTTP keep-alive saves ~500 ms per multi-sentence response on
  ElevenLabs** without any complexity bleed into the synth path.
- **In-order delivery** matches user expectation (sentence 2 never plays
  before sentence 1) without needing client-side buffering — done in the
  streamer via an `asyncio.Lock`-protected drain.

### Negative / accepted trade-offs

- **Concurrency surface increased**: per request we now spawn one
  `_drain` task plus N concurrent TTS tasks (one per sentence). Each
  carries an `asyncio.Lock` acquisition and an `add_done_callback`
  trampoline. Memory cost is negligible (~hundreds of bytes per task),
  but operational cost is the existence of more cancellation paths to
  reason about — see "Cleanup contract" below.
- **TTS provider rate limits**: a 5-sentence response now issues 5 TTS
  calls within ~1 s instead of sequentially over 2–3 s. Providers
  with strict per-second limits could 429 on rapid bursts. Mitigation
  in code: failed slots are skipped silently. Mitigation operationally:
  ElevenLabs Starter / Creator plans are well above the burst rate
  produced by the typical 3–5 sentence response.
- **`duration_ms` field**: kept as a heuristic (`len(sentence) × 80 ms`)
  documented as approximate. The real audio duration is encoded in the
  base64 payload; the field is a UI hint for progress bars, not a
  precise contract.
- **Cleanup contract**: any code path that exits the SSE generator
  before normal completion (HITL `GraphInterrupt`, exception in the
  streaming loop, top-level `except`) MUST call
  `AgentService._cleanup_chat_voice_pipeline(...)` to cancel the drain
  task, the streamer's pending TTS tasks, and the underlying voice
  service (which closes the persistent httpx client). Without this, an
  asyncio task + a TCP keep-alive connection would leak per dropped
  request. The helper is idempotent and tolerant to partially-initialised
  state.

### Edge cases addressed

- **Sentinel idempotence**: the end-of-stream `None` is pushed exactly
  once via the `_sentinel_pushed` flag. Three producers can race for
  it (`cancel_pending`, the last task's `add_done_callback`, the explicit
  `close_input` re-check) — all three short-circuit on the flag.
- **Empty response**: an LLM that produces no terminator and an empty
  trailing buffer logs `progressive_streamer_closed_without_audio` and
  emits the sentinel immediately, so the consumer doesn't hang.
- **Out-of-order completion**: the in-order buffer guarantees the
  consumer's playback never stutters — sentence #1 always plays first.
- **Failed slot blocking**: a `_failed: set[int]` pairs with `_pending`
  so an exception on sentence N doesn't block emission of N+1 indefinitely.
- **Concurrent producer races**: `close_input()` dispatches the trailing
  sentence BEFORE flipping `_input_closed = True`, otherwise a previous
  task callback could observe "closed + all done" prematurely.
- **Voice mode coexistence**: the agent-mode parallel voice task and the
  chat-mode sentence streamer are now mutually exclusive
  (`voice_parallel_task is None and chat_voice_drain_task is None` guard
  on the parallel task creation) — both producers writing to the same
  `voice_chunk_queue` would have silently dropped chat audio.

## Implementation map

| File | Change |
|---|---|
| `apps/api/src/domains/voice/sentence_streamer.py` | **NEW** module — `ProgressiveSentenceStreamer` (350 lines, asyncio-based, in-order delivery, lock-protected drain, sentinel idempotence) |
| `apps/api/src/domains/voice/service.py` | `_build_voice_llm_invocation` extracted from `generate_voice_comment`. `stream_voice_comment` refactored to feed an `astream()` LLM into the streamer. New `start_progressive_chat_stream` for chat mode. New `_abort_voice_comment_pipeline` cleanup helper. |
| `apps/api/src/domains/voice/elevenlabs_tts_client.py` | Persistent `httpx.AsyncClient` in `__init__`, default headers on the client, `close()` calls `aclose()`. |
| `apps/api/src/domains/voice/schemas.py` | `AUDIO_MIME_TYPES` and `DEFAULT_AUDIO_MIME_TYPE` moved out of inline dicts into a shared constant (was duplicated between service.py and sentence_streamer.py). |
| `apps/api/src/domains/agents/api/service.py` | Watches `router_decision.intention=conversation` to spin up the chat streamer. Feeds tokens. New `_cleanup_chat_voice_pipeline` helper invoked on every exit path (HITL fallback, top-level except, normal end). Voice service variables hoisted to outer scope so cleanup branches see them even on early failures. |
| `apps/api/src/core/config/voice.py` | `voice_chat_mode_max_sentences` clamp `le=6 → le=50`, description rewritten. |
| `apps/api/tests/unit/domains/voice/test_sentence_streamer.py` | **NEW** — 12 unit tests covering happy path, in-order, cap, failure, cancel, empty, callback throw, MIME fallback, latency property. |

## Verification

- ✅ All 12 unit tests of `test_sentence_streamer.py` pass.
- ✅ Runtime: TTFA mesurée à environ 1 s pour mode chat avec ElevenLabs Flash, contre 5–6 s en v4.0 (cf. event `voice_progressive_chat_stream_started` vs `voice_direct_tts_complete`).
- ✅ HITL `GraphInterrupt` testé manuellement → la voice n'est pas leakée (logs `chat_voice_pipeline_cleanup_failed` absents en operation nominale).
- ✅ Coût TTS toujours tracé en `tts_call_recorded` puis persisté sur `conversation_messages.tts_*` via le double-pass backfill (cf. ADR-081).

## Future work

- **Provider streaming** (HTTP chunked or WebSocket) en complément du sentence streaming : ElevenLabs et OpenAI exposent des endpoints `text-to-speech/{voice_id}/stream` qui rendent l'audio en chunks pendant que le serveur synthétise. Gain marginal (~100–300 ms par phrase) mais nécessite un refacto frontend (`MediaSource Extensions` ou Web Audio source buffer). À évaluer si la latence < 1 s n'est pas suffisante.
- **Adaptive max_sentences**: aujourd'hui un cap statique. Idée : couper la queue dès que l'utilisateur reprend la parole en mode push-to-talk, pour économiser les chars facturés.
- **Cross-request HTTP pool sharing**: actuellement le `httpx.AsyncClient` persistant vit le temps d'une instance `VoiceCommentService` (i.e. une requête utilisateur). Un cache cross-request au niveau du factory donnerait un gain supplémentaire mais exige une stratégie d'invalidation propre quand l'admin met à jour la clé API ElevenLabs (sinon ancien client avec ancienne clé → 401). Hors scope de cet ADR.
