# ADR-300 — A second live provider: one seam, two wires

**Date**: 2026-09-19
**Status**: Accepted
**Amends**: ADR-299 (the live voice mode: the seam holds, the wire is now a provider's), ADR-070 (the delegated turn stays an ordinary chat turn under a delegation the model performs itself), ADR-245 (a provider family with no ladder resolves to no level, and says so), ADR-184 (every bound the provider enforces is published: the append budget, the extension, the idle silence), ADR-185 (the closing card's figures stay the server's), ADR-263 (a session is one decision row on either provider), ADR-272 (nothing of the provider's is RECORDED — a WebRTC session's seconds included; wave 3 shows them on the band, priced by the declared tariff, and records nothing), ADR-260 (two more key families: the voice sample's limiter, the nonce on the session record)

## Context

The first wave shipped a speech-to-speech session on Gemini Live. The owner's
feedback after a day of use named seven things, and one direction: « n'oublie
pas qu'après nous allons intégrer OpenAI GPT-Live-1, attention à bien faire du
code générique ou encapsulé » — then « cela pourrait être pertinent de
l'intégrer dès maintenant … cumulatif avec Gemini ». The second provider is
different on every count the first one was measured on: the browser speaks
**WebRTC**, not a WebSocket; **no ephemeral token exists** — the SDP offer is
exchanged by a server holding the key; the model **delegates by its own act**
and the delegation event **carries no text**; a result is **appended** as
spoken commentary or silent thinking under a **500-token** bound; there is no
VAD setting, no turn event, no resumption, and the voices are **not** the
speech endpoint's. If the seam of ADR-299 was worth its name, none of the
bridge, the banner, the registers or the closing card would move.

Every provider fact below was **measured before it was trusted** — on the dev
instance's key from inside the API container (a WebSocket session), then in a
real Chromium against Docker dev with a microphone playing a spoken question
(a WebRTC session end to end), the throwaway accounts deleted afterwards:

- `session.start` answers `session.started` in 1.2–1.7 s; an unknown voice is
  refused BEFORE any start (`forbidden`), an unknown model with
  `invalid_model` — so, unlike Gemini, the provider judges the voice itself;
- `session.instructions.append` requires an explicit `delegation_id: null`
  and a `content` field (the reference shows `instructions`), and a greeting
  is rendered only while INPUT audio flows: the session clock advances with it;
- over WebRTC the connection is `connected` in 480 ms, the `oai-events`
  channel open at 640–710 ms, and **`session.started` follows on the channel
  itself** (undocumented for WebRTC) 110 ms later;
- a spoken « What is on my agenda tomorrow? » is transcribed in fragments
  (`start_ms` / `end_ms`), the model **delegates by itself 6 ms after the
  last fragment** and says « Une seconde, je regarde » in the mandate's
  language; ten seconds later our `session.commentary.append` on the
  delegation's id is spoken back, acknowledged, and its words land in the
  captions; `session.close` answers `session.closed` in 700 ms with the
  seconds the person's key paid — read by nobody;
- the speech endpoint serves **none** of the twelve live voices (measured
  against its own list), and the listing carries a transcription model under
  the live prefix (`gpt-live-transcribe`).

## Decision

**One seam, two wires.** `LiveProvider` (API) and `LiveTransport` (browser)
keep their shape; each provider says how it differs through two declarations
the seam reads, never through a branch on its name:

- **`connection`: `token` or `offer`** (`providers/protocol.py`). On a `token`
  connection the browser opens the socket itself with the provider's
  credential (Gemini). On an `offer` connection the API mints **its own
  single-use nonce** as the credential — the session record keeps it
  (`nonce`, `nonce_until`) and consumes it under its claim — and the browser
  hands the nonce back with its SDP offer to `POST /live/sessions/{id}/offer`,
  which exchanges it on the person's key (`POST /v1/live/sessions {session,
  transport: {type: webrtc, sdp}}`) and returns the answer. « One credential
  opens one connection » therefore holds on both wires (a second exchange on
  the same nonce is `409 credential_invalid`; a refused exchange burns it, and
  a reconnection mints a fresh one). An extension re-mints only on a `token`
  connection: the WebRTC session outlives the cap on its own, and a
  reconnection there would be a NEW provider session, its context lost.
- **`delegation_wire`: `tool` or `native`** (`providers/protocol.py`). The
  mandate is rendered with ONE verb (`delegate_by_call` → « call
  send_to_lia », `delegate_native` → « delegate to LIA ») and a delegation
  block per wire and capability (`delegation_async`, `delegation_blocking`,
  `delegation_native` — the last carrying the documented rules: delegate
  before answering, never guess while waiting, stopping speech is not
  cancelling work). No function declaration travels on a native wire.
- **The request of a native delegation is COMPOSED** in the browser
  (`lib/live/request-composer.ts`): the input-transcript fragments since the
  previous delegation, up to the event's `offset_ms`, after a short grace for
  the fragments still in flight. Short replies go as they are — the thread
  already holds the earlier turns, and the newest-request rule (ADR-299 wave 2
  A7) applies unchanged.
- **The transport speaks the provider's own signals** and derives what the
  seam needs from them (`lib/live/transports/openai-webrtc.ts`): the
  assistant's transcript IS its speech (its quiet ends the utterance and
  completes the turn), a person's words meanwhile are an interruption, a
  result is split into appends under the documented bound, the microphone is
  told with `mute` / `unmute`, the session is ready when the provider SAYS
  `session.started` (bounded), and `close()` waits for `session.closed`,
  bounded. `session.usage.updated` is read by nobody.
- **A voice the speech endpoint does not serve is sampled by the live model
  itself**: a short server-side WebSocket session on the person's key
  (`providers/openai_live_socket.py`), input silence streamed at real-time
  pace, the sentence asked through an instruction append, the continuous
  output trimmed of its silence (`infrastructure/media/pcm.py`). The same
  socket is the activation PROBE, which therefore validates model AND voice.
- **The `live` category is ADDITIVE** (`CONNECTOR_ADDITIVE_CATEGORIES`): both
  keys may be active; the sessions open on the account's choice
  (`users.live_preferences.provider`, tolerant reader; saving a connector's
  settings makes it the one), each connector keeping its own model, voice and
  thinking level; the settings list the UNION of the models the active keys
  discover, grouped by brand, and choosing a model IS choosing its provider;
  the reflexes a provider decides itself (VAD) are not offered on it. The
  connector form is told which provider it sets up; the brand is a parameter
  of its wording, never a second set of keys.
- **What the seam still refuses to know**: a provider id. The controller
  branches on `LiveSessionStart.capabilities` and `connection`, the mandate on
  `delegation_wire` and `async_delegation`, the settings on
  `configurable_vad` — a third provider is one `LiveProvider`, one transport,
  one row in `LIVE_PROVIDERS`, and, for a `token` wire, one CSP host. A WebRTC
  wire needs no CSP host: no directive governs a peer connection.

## Consequences

- Nothing of the bridge, the banner, the store, the registers, the summary
  card or the learning pass changed for the second provider — the proof is
  the hermetic journey `chat-live-session-openai.spec.ts`, which plays the
  provider through a fake `RTCPeerConnection` and asserts the same thread,
  the same card, the same `end`.
- The nonce is a small price for a property that would otherwise be false on
  one wire: a client bug double-connecting would open two provider sessions
  billed to the person under one LIA record.
- The voice sample of GPT-Live costs the person a few seconds of a live
  session (their own key, never counted): the alternative — a speech-endpoint
  voice that is not the one chosen — would have been a false claim.
- Two provider readings are pinned by the fakes: the transport's unit test and
  the hermetic journey emit `session.started` after the channel opens, the
  documented delegation event with NO text, and the acknowledgements — the
  same shapes the real browser measured, never a convenient one (ADR-299's
  lesson, applied before the first click this time).
- Left open, in writing: the mobile shells have not measured a WebRTC session
  (desktop Chromium only); the `session.started` reading over WebRTC is a
  measurement, not a documented promise, and is bounded for that reason; no
  `task live:probe` variant replays the GPT-Live facts yet — they live in the
  provider's docstrings with their dates.

## Amendments — 2026-09-19, five owner adjustments after the first sessions, then wave 2 (items 6–8) and wave 3 (items 9–12)

1. **The voice chosen for a model survives a switch.** The connector used to hold
   ONE voice, ONE level: choosing another model overwrote them. A connector now
   remembers every model it was set up on (`connector_metadata.models`,
   `domains/live/model_settings.py`, read through one reader, the previous
   top-level shape still read and never written); the form recalls a model's
   own settings on the switch and shows them (`model_settings` on the wire).
2. **The two durations are the MODEL's, `0` meaning no limit.** Some providers
   bill the whole session second by second, waiting included; others only the
   exchanges — only the person knows their model's billing, so the silence
   before the session closes (default 60 s) and the longest session (default
   10 min) are per model, under a warning that says exactly that. The bounds
   are one declaration shared with the instance settings and published
   (ADR-184); the gap between « no limit » and the minimum is refused by the
   schema and withheld by the form. An unlimited cap ROLLS by extension slices
   the client renews in silence — a provider token cannot outlive its expiry
   and a key with no TTL is never written — and a renewal is never counted as
   the person's extension (`unlimited_cap` on the record, `kind` on the
   metric). `0` for the silence means no clock at all.
3. **The header entry is named after the provider the sessions open on**:
   « Live session (Gemini) », drawn like « Spoken replies », an icon before
   each; `useLiveAvailability` answers `{ available, provider }`.
4. **No talk mode.** A live session is always automatic; the hold-to-talk
   button, the preference, its locale keys and its manual VAD went.
5. **Emotion in the voice — three levers asked, two kept, one measured out.**
   (a) LIA's inner state reaches the mandate at the session's start through the
   psyche engine's own block, the one every secondary generation point carries
   (nothing said when the engine is off for the instance or the person).
   (b) The register the answering model declared for each answer (ADR-253)
   reaches the voice as a DELIVERY NOTE beside the result — one line per
   register in `live_tone_lines.txt`, published by `/live/config`, read off
   the live bubble (the reducer now keeps `expressivity` on the message, live
   only), on each wire's own shape: a `tone` field in Gemini's function
   response, a silent `thinking.append` before the spoken one on GPT-Live —
   the mandate says what the note is and never to read it aloud. Measured on
   the real endpoint: the note-bearing response is accepted and restituted.
   (c) Gemini's `enableAffectiveDialog` was measured OUT: a `setupComplete`,
   then 1007 at the first thing the model must answer — text, realtime text
   or a spoken question alike — on v1beta and v1alpha; a negative test pins
   the measurement where the documentation invites the flag. What the audio
   SOUNDS like under (a) and (b) has no oracle and is not claimed.
6. **The « biiiip » is Chrome 152's, and the player no longer gives it a
   chunk to start.** The owner's build (152.0.7977.83) is the one the
   community measured replacing the start of a scheduled
   `AudioBufferSourceNode` with one 128-sample render block repeated ~100
   times (a quarter-second « MEEP »); the raw provider audio is clean, a
   Chromium 148 rendering is clean. `PcmStreamPlayer` is now ONE
   `AudioWorkletNode` reading a queue continuously — no scheduling, no
   per-chunk resampling, an exact `drained` report instead of a tail timer.
   The repository's own tap could not reproduce the defect on that build in
   four sessions; the fix rests on the community measurement and on
   removing the shape it needs (LIVE_MODE.md § Measured).
7. **The two voices are exclusive, and the session greets its own start.**
   Asking for a session switches the spoken replies off without a word
   (`disableQuietly`), the checkbox is refused while a session is open, the
   icon shows the live waveform, and the toast comes on the session's `live`
   status (once per session id) — a click is a request, the session opens a
   second later or not at all.
8. **A provider close names itself in the log — and on the screen.** `LiveEndRequest.detail`
   (the close code and reason, bounded) — two sessions closed by the
   provider within five seconds had left nothing but `provider_closed`; the
   banner's toast now carries the same word (wave 3, owner request).
9. **The session's cost is SHOWN, never recorded** (wave 3, 2026-09-19; the
   « never count a personal key's spend » rule amended by the owner the same
   day: a live display is not an accounting). The provider's own usage
   reports — Gemini's `usageMetadata` per model turn, by modality, the whole
   context re-billed each turn; GPT-Live's `session.usage.updated` seconds —
   are folded in the browser and priced by the tariff the API published at
   the start (`LiveRates`), drawn under the last caption, set off by a lateral
   bar, in the chat meter's vocabulary with the context size. A
   cost needing a rate nobody declared reads as unavailable, never partial
   (ADR-185). Nothing of it is persisted or on the closing card.
10. **A live model is a row of the tariff table, or it is not offered** (owner
   rule 2026-09-19). The table gained the audio pair
   (`audio_input_unit_price` / `audio_output_unit_price`, both or neither,
   token-billed only; migration `f1a3c5e7b9d2` prices the discovered live models
   the way `e9b5d7f3a2c4` priced deepseek-flash, a guard holding migration and seed
   equal), the Live settings offer the discovered models the table declares and
   NAME the rest, a session on an undeclared model is refused (`model_unpriced`).
   The captions stay: Gemini bills them at the text output rate and GPT-Live in its
   minute, and both wires need them (the delegation, the archive, the composed
   request) — an option to switch them off would save nothing and break the seam.
11. **An optional spend ceiling per session, the connector's** (provider
   granularity, owner decision): `session_budget_eur` under
   `LIVE_SESSION_BUDGET_EUR_MAX`, published at the start, enforced by the
   browser's meter — outcome `budget_reached`, told as a toast and on the card.
12. **Rejected, for now**: Gemini's `enableAffectiveDialog` and
   `proactiveAudio` as settings (the first kills the session on the browser's
   path, the second exists on `v1alpha` alone — owner: « on attend que ce soit
   stabilisé »).

## Amendments — 2026-09-19, wave 4 (items 13–14): a direct session, and a third provider on the first wire

13. **A DIRECT session is the phone's line, in the browser** (owner decision
    2026-09-19: « le live direct sans mutable, comme pour le téléphone
    personnel »; spec `docs/superpowers/specs/2026-09-19-live-wave4-design.md`).
    The header's voice menu offers « Direct live session (<brand>) » where
    the chosen model's wire carries a tool schema
    (`LiveModelCapabilities.direct_tools` — never a provider id); in it the
    voice model holds LIA's READ-ONLY tools itself — the phone's derived set
    (ADR-290 lot 8) minus the person's switches, voice-projected — the
    phone's context block, and never delegates. The mode is a column of the
    session RECORD (`LiveSessionRecord.mode`), chosen at
    `POST /live/sessions {mode}`, refused `mode_unsupported` (409) elsewhere.
    ONE tool door for every tool wire, `POST /live/sessions/{id}/tools`, on
    the person's own cookie; the phone's `run_live_tool` generalised to a
    `VoiceToolHost` (surface `live_session`, the session's run id, node
    `live_session_tool`), so the phone stays on `phone_call` and the two
    never disagree; a per-session lookup budget (`LIVE_DIRECT_TOOL_CALLS_MAX`)
    because a model in a loop must not spend for ever; every refusal a
    sentence the voice says. **The owner's premises were corrected before the
    design was frozen, then measured**: a direct session gains latency and
    nothing else — Gemini re-bills the whole context every turn, and the 55
    declarations are 35 864 of the setup's 40 312 characters: **10 983 prompt
    tokens on the first turn against 1 227 delegated** (dev, a real session);
    transcription is a rounding error; HITL, mutations, extractions and
    registers all come free with delegation. Hence read-only, and the
    extractions by the EXISTING end-of-session learning pass over the
    archived `live_turn` rows (a relay turn was designed and rejected: one
    paid graph turn per session for no fact the pass does not extract).
    Found on the way: the record's `from_json` did not read `mode` — the
    first real proof answered every lookup « not a direct session » — so the
    round-trip is now equality over every field, the setup inputs' pair too
    (a DIRECT session keeps `direct_tools` and no declaration).

14. **A third provider on the first wire: ElevenLabs Agents** (owner decision
    2026-09-19: the person picks an AGENT of their workspace and everything
    but the prompt stays on the ElevenLabs portal). It joined without a line
    of the bridge, the banner, the registers or the card moving; two seams
    grew, both provider-neutral. **A provider DECLARES who bills its
    sessions** (`LiveProvider.billing`, owner rule 2026-09-20): `tariff` —
    the platform's own table prices the model (Gemini Live, GPT-Live: the
    start publishes `LiveRates`, the meter counts) — or `vendor` — the
    session runs on the PERSON's own key under the vendor's own grid and the
    platform prices NOTHING of it: `rates` is null at the start, the meter
    shows the clock alone, no spend ceiling can be set
    (`LiveModelCapabilities.vendor_billed`), the listing offers the model
    whatever the tariff table holds, and the choice is never refused as
    « unpriced ». ElevenLabs has TWO price grids and the table knows ONE:
    the simple API (speech to text, text to speech — what the STT and TTS
    slots run on the deployment's key; `eleven_v3_conversational` joins the
    table THERE, a `tts` row at 0.05 USD per 1 000 characters, migration
    `a4c8e1f7b3d5` + seed, the guard holding them equal) and the agents API
    (telephony and the live mode, per conversation minute plus the LLM on
    top — never on a key of ours). Two versions were written and retired
    before this one: a flat row `elevenlabs-agents` at 0.10 USD a minute
    (migration `b7d1e3f5a9c2`, kept as inactive history and taken OUT of
    the catalogue, `RETIRED_CATALOGUE`) — a guess at a price the platform
    never pays —, then a `tariff_for(api_key, model)` pricing an agent
    under its voice model's minute with the meter as a floor — a price
    from the wrong grid, the simple API's per-character figure read as a
    per-minute one. The agent's configuration is still read at the listing
    (`LiveModel.voice_model`, `LiveModel.llm`, from
    `conversation_config`) for INFORMATION, drawn beside the agent's name.
    At the end the vendor's own bill is read on the key
    (**`VendorBilling`**: `GET /v1/convai/conversations/{id}` — `cost_fiat`,
    the LLM and call charges in credits, the models it charged for, the
    duration — under the conversation id the metadata frame named) and
    SHOWN once by the banner, recorded nowhere: nothing of a session on
    the person's own key reaches a ledger (measured on the owner's agent:
    0.0383 USD, 193 credits, 57 LLM, 136 call, for a 20-second session).
    **The vendor settles the bill AFTER the close handshake** (measured
    2026-09-20: the conversation reads `in-progress` with no cost while the
    browser's close frame lands, the bill is stated 0.3 s after the
    handshake, `done` at 1.4 s) — the first version posted `/end` tens of
    milliseconds after `socket.close()` and two sessions in a row showed
    the person nothing. The transport's `close()` now waits for the socket's
    close event (bounded, `ELEVENLABS_CLOSE_WAIT_MS`, the shape of
    `openai-webrtc`'s wait for `session.closed`), and `fetch_vendor_bill`
    asks again a bounded number of times
    (`LIVE_VENDOR_BILL_SETTLE_ATTEMPTS` × `LIVE_VENDOR_BILL_SETTLE_INTERVAL_SECONDS`)
    while the vendor states no bill — never longer, because the closing
    card must not wait on a vendor.
    **`AgentSyncing`**: a session's tools are attached to the AGENT, never
    named per session (measured on the phone: the vendor refuses `tool_ids`
    inside an override), and a per-session prompt needs the agent's
    permission — so before the mint the provider grants the prompt override
    MERGED into the agent's own overrides block (the vendor replaces omitted
    booleans with false), creates LIA's client tools once per fingerprint of
    the declarations, and sets `tool_ids` to the person's own plus THIS
    session's set (a delegated session never sees the read-only tools, and
    vice versa); what LIA holds is kept on the connector's metadata, a NEW
    dict. **`portal_voice`**: the voice, the language and the turn-taking are
    the agent's — the form names the step « Agent », offers no voice and no
    sample, stores the sentinel `agent` (held equal across the stack). The
    credential is a signed URL (one conversation, 15 minutes to open it),
    the wire the `convai` subprotocol, the delegation a blocking CLIENT tool
    (`async_delegation: false`), the note beside the result in one JSON
    string, no resumption, the meter on the clock. **Measured on the owner's
    agent the same evening**, after a first draft read from the official
    `@elevenlabs/client` 1.25.0 source: `source_info.source` is validated
    against the vendor's SDK names and any other word closes 1008 AFTER the
    metadata (the frame carries none now, and the probe waits
    `ELEVENLABS_LIVE_PROBE_SETTLE_SECONDS` past the metadata, which is not the
    verdict); a client tool's array items need a `description` (422 — the
    phone's own measurement, now in the one neutral projection); a refused
    creation cancels its siblings before the rollback (`TaskGroup`, never
    `gather`: 99 orphan tools measured). The probe still refuses in words an
    agent whose input format is not `pcm_16000` or whose output is not PCM.

15. **A DIRECT session records nothing, and says so** (owner request
    2026-09-19: a band in the direct session's window telling the person that
    what is exchanged is not recorded by LIA — memory, interests, and so on).
    Wave 4 had kept the direct exchanges as `live_turn` rows and handed them
    to the learning pass at the end (13, « the EXISTING learning pass
    extracts from them »), so the sentence the owner asked for was FALSE as
    written, twice over: the rows sat in the thread, and the next written turn
    injects them into the graph state (`out_of_graph.py`), whose own memory
    extractor reads every message but a proactive notification — a detour no
    « skip the learning pass » alone would close. A banner states what the
    code enforces (ADR-284's rule, pointed at a notice), so the code changed
    rather than the wording: `archive_turn` refuses a direct record (409
    `direct_not_archived`, named rather than dropped in silence — no client
    can write what the banner denies), the browser never posts one, the
    session's end skips `schedule_live_learning` on `mode == "direct"` as an
    explicit rule, and the card's body counts no exchange
    (`summary_body_direct`), because a count it does not hold is not shown
    (ADR-185). What remains recorded is what the registers owe (ADR-263): the
    decision row and the consultation rows name the session and the
    capability read, never a word said. On the way, the card's cost now adds
    what the tool host files under the session's OWN run id — a direct
    session's lookups were billed to it and shown as nothing. **The header's
    voice menu follows the Live settings** (same request): the toggle lives
    in the dashboard layout and never remounts on the way back from the
    settings, so its one read of `GET /live/connectors` kept the old brand
    and the old `direct_tools` on the entries until a reload. The query hook
    holds no cache shared between mounts, so the seam is a REVISION
    (`stores/revisionStore.ts`, a closed vocabulary): a writer bumps the
    resource it changed — a saved connector, an activation, a live
    disconnect — and the reader hands the revision to its query's `deps`.
    Measured by a journey on one page (red without the bump).

## Amendment — 2026-09-24: the audio transport is a property of the session, and iOS takes WebRTC

The wire a provider declares (`connection`, `delegation_wire`) says how a
session is credentialed and how it delegates; it did not say how the AUDIO
travels, and on iPhone and iPad the raw WebSocket PCM of an ElevenLabs agent
arrived unevenly enough to be heard. The start now names the audio transport
(`LiveSessionStartRequest.audio_transport`: `websocket` by default, `webrtc`
from an iOS browser), the setup inputs carry it and round-trip it with the
record, and the provider mints what that transport opens — a signed URL for the
WebSocket, a LiveKit conversation token for WebRTC. The browser's
`createLiveTransport(provider, audioTransport)` returns
`transports/elevenlabs-webrtc.ts`, which drives the vendor's own SDK
(`@elevenlabs/client`, pinned) and declares its audio `managed`: the SDK holds
the microphone and the speaker, so the controller disposes of its PCM player
and opens no PCM microphone. LIA's tools are the SDK's client tools, all routed
through the same tool door; a name only the person's agent declares reaches that
door too, which refuses what it does not know. A WebRTC session holds no
expiring credential, so an extension moves the cap without re-minting — the rule
GPT-Live already followed — and the CSP names the one host the SDK opens
(`wss://livekit.rtc.elevenlabs.io`).

Three measures travel with it: the PCM player keeps a rebuffer headroom after an
underrun (120 ms on iOS) and a short attack after a gap, and reports aggregate
counts at the session's end (`LiveAudioDiagnostics` on `POST …/end`: chunks,
drains, gaps, rates — never audio, never text); the hidden-page grace starts
only once iOS's microphone permission sheet has returned a stream; and a Gemini
key restricted to the API server's IP address — which mints the token, then
sees the browser's socket refused (1008) — is named as such
(`live.error.key_ip_restricted`) instead of a generic start failure.

## References

- Spec: `docs/superpowers/specs/2026-09-19-live-wave2-design.md` (A1–A11, § 6 measured)
- Technical: `docs/technical/LIVE_MODE.md`
- Provider reference read on 2026-09-19: `developers.openai.com/api/docs/guides/live-*`,
  `voice-webrtc?api=live`, `voice-websockets?api=live`, `models/gpt-live-1`
