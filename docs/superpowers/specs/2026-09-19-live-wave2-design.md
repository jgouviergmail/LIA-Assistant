# Live mode, wave 2 — conformity, a real duplex, and a second provider

**Date**: 2026-09-19 · **Status**: arbitrated with the owner, in execution · **Amends**: the
2026-09-18 live design (`2026-09-18-live-llm-connector-design.md`), ADR-299

## 1. Intent

The first wave shipped a speech-to-speech session that works. This wave makes it a
**real duplex** — reactive to a correction, never mute during a delegation, never
billed for nothing — and opens the **second provider (OpenAI GPT-Live-1)** without a
line of the bridge, the banner or the registers duplicated. Every decision below was
checked against the code or the providers' official documentation; what remains to be
measured is named as such and measured in its lot.

## 2. Arbitrated decisions

| # | Decision |
|---|---|
| A1 | **One header icon.** The voice-comments toggle (`VoiceToggle`, dashboard layout) is the entry: a plain toggle when the instance has no live capability or the account no live connector; a menu « Comments / Live » otherwise. The chat's `LiveButton` goes. Outside the chat page, « Live » navigates to the chat with `pendingStart` set in `liveStore` (never a URL parameter — `?intent=` is the auto-send of QW-24), consumed once by the chat page. |
| A2 | **A delegated turn produces no voice comment**: `user_voice_enabled` is false when `live_session_id` is set. The voice already speaks the answer; the TTS was platform spend for audio nobody heard. |
| A3 | **Opaque bands**: the live and the telephony banners sit in the sticky top block; both get a `bg-card` base under their `primary/10` tint. |
| A4 | **Voice sample** on every voice change, in the settings AND in the connector form: one door `POST /live/voices/sample {provider, voice, api_key?}` on the PERSON's key (the stored one, or the one the form holds — `discover` already posts it), never counted, rate-limited with the mint family; the client plays it through the PCM player. |
| A5 | **Extended Thinking opens**: the activation probe replays the REAL setup (thinking level, NON_BLOCKING tool) instead of `response_modalities` alone; `scheduling` is omitted where the model refuses it; `interactionStatus` is read and, where the model reports it, is the idle truth (a `turnComplete` per utterance archives nothing). |
| A6 | **Fillers**: the prompt takes the documented shape (language line, acknowledgement BEFORE the call, tool calls in distinct sentences) and is rendered per model CAPABILITY — a model without asynchronous delegation is not told to keep talking. Native fillers are a property of Extended Thinking; measured comparatively. |
| A7 | **Interruptions: the newest request wins.** A server cancellation (`toolCallCancellation`) stops the chat turn (`stopGeneration`) and frees the bridge; a new delegation while one runs stops the running turn, answers the old call SILENT « superseded » (unless the server cancelled it), then runs the new one. No `replaces_previous` parameter: GPT-Live's delegation carries no arguments at all, and the model (Gemini) or the transcript window (GPT-Live) already carries the correction. A prompt rule asks the model to merge an ADDITION into the new call. |
| A8 | **Idle 10 s** = no speech from the person, none from LIA, no delegation in flight, no provider processing; a countdown is shown for the last 5 s. **Cap 10 min**; at T−60 s an explicit dialog offers +10 min (unlimited, always explicit); no answer at T ends the session `expired`. All published by `/live/config`. |
| A9 | **GPT-Live-1 over WebRTC**: the browser's SDP offer is exchanged by OUR API with the person's key (`POST /live/sessions/{id}/offer` → `POST /v1/live/sessions {session, transport: {type: webrtc, sdp}}`); the SDP transits, the audio never does. Delegation `client` only — the `responses` mode is a second agent engine outside the graph. No ephemeral token exists for GPT-Live (documented). |
| A10 | **The `live` category is ADDITIVE**: both connectors may be active. The active provider is the account's choice (`users.live_preferences.provider`, JSONB, tolerant reader); each connector keeps its own model / voice / thinking level; a missing active provider falls back to the remaining connector. No migration. |
| A11 | **Seams**: `LiveTransport` speaks INTENTIONS (`onDelegation({id, request | null})`, `answerDelegation(id, text, delivery)`, `setInputActive(on)`, `close()` graceful), declares its audio (`ownership: pcm | native`, rates, chunk) and the controller reads CAPABILITIES published by `POST /live/sessions`, never a provider id. The microphone stays the controller's (`getUserMedia` once — ADR-258) and is HANDED to a native transport as a `MediaStream`. |

## 3. Provider facts the design rests on

| | Gemini Live | GPT-Live-1 |
|---|---|---|
| Browser transport | WebSocket, token in the query (`…Constrained`) | WebRTC, offer exchanged server-side with the project key; no ephemeral token |
| Audio | 16 kHz in / 24 kHz out, PCM frames (binary) | media tracks (native); WebSocket variant is server-side only |
| Delegation | `toolCall` with the request written by the model | `session.delegation.created` = id + metadata, NO text — composed from `session.input_transcript.delta` |
| Result | `toolResponse` + `scheduling` (omitted on Extended Thinking) | `session.commentary.append` (spoken) / `session.thinking.append` (silent), ≤ 500 tokens, acknowledged |
| Interruption | cancels pending calls (`toolCallCancellation`) when the model is REPLYING; a new turn while it waits is a new call | implicit; « does not cancel your application's work » |
| Mute | `audioStreamEnd`; manual VAD needs `activityStart/End` | `session.input_audio.mute` → `…muted` (acknowledged) |
| Idle truth | `turnComplete`; `interactionStatus` on Extended Thinking | transcripts and delegation events (no turn events) |
| Resumption | handle + `goAway` | none (a fork is a new session) |
| Close | close the socket | `session.close` → wait `session.closed` (usage seconds, reason) |
| VAD config | `realtimeInputConfig` | none (« GPT-Live decides when to speak ») |
| Billing (the person's key) | tokens | duration, mute and waiting included |

Per-model capabilities (Gemini, measured listing on dev 2026-09-19: `gemini-2.5-flash-native-audio-*`,
`gemini-3.1-flash-live-preview`, `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`):
async delegation is unsupported on 3.1 Flash Live (documented), `scheduling` is refused on
Extended Thinking, `interactionStatus` is reported by Extended Thinking, thinking is required
there and refused on 3.8 Live.

## 4. Configuration (all published by `GET /live/config`)

`LIVE_SESSION_MAX_MINUTES` 30 → 10, `LIVE_IDLE_TIMEOUT_SECONDS` 300 → 10, new
`LIVE_EXTENSION_MINUTES` (10), `LIVE_EXTENSION_PROMPT_SECONDS` (60, validated below the cap),
`LIVE_VOICE_SAMPLE_MODEL` (the Gemini TTS model of the sample). The four demo `.env` files follow.

## 5. Lots

0 conformity (Gemini) · 1 seams · 2 idle / cap / extend · 3 interruptions · 4 TTS suppression +
opaque bands · 5 header icon · 6 voice sample · 7 Extended Thinking measured · 8 additive category
+ provider choice · 9 OpenAI provider (API) · 10 WebRTC transport + composer · 11 docs, ADR, cold
review, `ci:fast`. Each lot: red test → green → adversarial review → real proof on Docker dev.

## 6. Measured (lots 0–10, Docker dev, throwaway accounts deleted afterwards)

- **Gemini, lot 0**: the activation probe on the REAL setup accepts Extended Thinking with its
  level (the owner's 1007 « Thinking level must be specified » is gone); `scheduling` in the
  probe's tool response closes the socket with 1007 on that model — the probe honours the
  capability; `interactionStatus` arrives as the string `"IN_PROGRESS"`; the lot-0 prompt makes
  3.8-live say a sentence BEFORE the call.
- **Gemini, lot 2**: an OPEN socket dies at the token's expiry (1011 « auth token has expired »)
  — an extension re-mints to the new cap and the client reconnects on the handle at once; +10 min
  from the CURRENT cap, twice, the card carrying `extensions`, `end` ×2 = 404.
- **Gemini, lot 3**: a correction while a delegation is pending yields a SECOND `toolCall` with the
  complete request, never a `toolCallCancellation` — the newest request wins in the bridge.
- **Gemini, lot 6**: `gemini-3.1-flash-tts-preview` BLOCKS the sample sentence
  (`PROHIBITED_CONTENT`, no candidate); `gemini-2.5-flash-preview-tts` speaks it (~3 s, audio/L16
  24 kHz) — the default sample model.
- **Lot 5–7, browser**: the hermetic journey opens the session through the header's voice menu;
  Extended Thinking activates (201).
- **GPT-Live, lot 9 (WebSocket, the instance's key)**: `GET /v1/models` lists `gpt-live-1` and
  `gpt-live-transcribe` (dropped by the shared purpose-word filter); `session.start` →
  `session.started` in 1.2–1.7 s; an unknown voice → `error forbidden` BEFORE any start; an
  unknown model → `invalid_model`; `session.instructions.append` requires `delegation_id: null`
  and `content`; a greeting renders only while input audio flows (silence streamed at 40 ms pace:
  first audio delta 0.7 s after the append, the transcript exactly the sentence, `usage.seconds`
  = the input audio); the speech endpoint serves none of the twelve live voices. API proof on a
  throwaway account: discover, 12 voices, a 2.7 s sample WAV, activate 201, `connection: offer`
  with a 43-char nonce and an empty `setup`, a real SDP answer for a shaped offer, the same nonce
  again → 409 `credential_invalid`, renew → a fresh nonce, end 200.
- **GPT-Live, lot 10 (a real Chromium against dev, a microphone playing a spoken question)**:
  WebRTC `connected` in 480 ms, `oai-events` open at 640–710 ms, **`session.started` on the
  channel** 110 ms later; the question transcribed in fragments (`start_ms`/`end_ms`), the model
  DELEGATED BY ITSELF 6 ms after the last fragment and said « Une seconde, je regarde » (the
  mandate's language); our `session.commentary.append` on the delegation id ten seconds later,
  acknowledged and spoken back (the captions show it; remote-audio RMS 0.099); `session.close` →
  `session.closed` in 700 ms (usage 41 s, the person's own, read by nobody). A greeting or a
  delegation ask appended while the model is mid-speech is acknowledged and not acted on.
- **Not measured**: a WebRTC session in the mobile shells; the composer's grace against a
  provider that emits the delegation BEFORE the last fragment (measured the other way round).
- **Adjustments (owner, 2026-09-19, after the first sessions)**: per-model voice and durations
  remembered across switches (`0` = no limit, under a billing warning; a rolling cap's
  renewals never counted as extensions), the header entry named after the provider, the talk
  mode removed, LIA's inner state in the mandate and a delivery note per answer. Gemini's
  `enableAffectiveDialog` measured OUT on the browser's path: `setupComplete`, then 1007 at the
  first thing the model must answer (a text turn, a realtime text, a SPOKEN question —
  three runs, the flag in or out of the token constraint, v1beta and v1alpha); without it the
  same spoken question is delegated and a `{result, tone}` function response is restituted
  (384–545 kB of audio). API proof on a throwaway account: two models remembered side by
  side, the recalled voice on a switch back, idle 3 → 422, a start under cap 0 / idle 0 with
  the `<InnerVoice>` block and the tone rule in the mandate, extend → `extensions: 0`, end.
