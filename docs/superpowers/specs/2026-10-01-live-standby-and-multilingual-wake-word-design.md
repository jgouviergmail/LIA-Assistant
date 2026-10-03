# Live standby and a multilingual wake word — systemic analysis and design

**Date:** 2026-10-01
**Status:** analysis written against the code at `fcfb8a89` (every claim below names the file it
was read in); approved by the owner on 2026-10-01. Lots 1-3 are implemented (the engine, the
classic voice mode and the removal, the live standby on both sides); lot 0 — the trained
models — is in progress, so no model ships yet. What changed from this design while it was built
is in section 12; the decision record is ADR-329.
**Scope:** the three live wires (Gemini Live, GPT-Live, ElevenLabs Agents) in both modes
(delegated « Live », direct « Live direct »), the classic voice mode (wake word → STT), the
wake-word engine shipped to the browser, and the removal of the Sherpa-onnx wake-word stack.
**Out of scope:** the phone channel (ADR-290/301), the radio, the backend Sherpa STT service
(`domains/voice/stt/sherpa_stt.py`, which stays the local transcription engine), any change to
the delegation bridge or to the mandate's content.

---

## 1. The need, deconstructed

### 1.1 What the owner asked (facts)

1. A live session must be able to go to **standby** after a silence: LIA reacts to nothing and,
   above all, **bills nothing**, for as long as it lasts. The session **ends only on the person's
   explicit act** (the banner's « End » button), as today — there is no longer an end on silence.
2. Standby ends on a **wake word in the person's language**; French: **« Dis LIA »**.
3. The wake word serves **three consumers** with one engine: Live delegated, Live direct (the
   session stays open, no stop/restart), and the classic voice mode where the word only starts
   the STT capture.
4. **Everything technical about the current wake word is removed** (Sherpa-onnx WASM, its scripts,
   the Dockerfile stage, `keywords.txt`, the isolation predicate).
5. Hard constraints: the API runs on a Raspberry Pi 5; the clients are PWAs on iPhone and
   Android.
6. « The memory is the application's, not the provider's »: nothing the provider keeps in its
   connection has a value of its own.

### 1.2 What is deduced (assumptions the owner can correct, none blocking)

| # | Assumption | Why |
|---|---|---|
| A1 | In standby the **provider connection is closed on the three wires**. | « Bills nothing » cannot depend on what a muted socket costs at each vendor: ElevenLabs bills the conversation's minutes (`vendor_billed`), Gemini and GPT-Live bill tokens, and all three have connection lifetimes of their own. No socket is the only state with no doubt. |
| A2 | The cap (`session_max_minutes`) and the extensions count **awake time only**. | They bound a spend; standby spends nothing. |
| A3 | A **hidden page** no longer ends the session: hidden while awake → standby after the grace; hidden while in standby → nothing. | The end is manual. The hidden grace existed to stop paying for a session nobody attends; standby costs nothing. |
| A4 | A **manual standby** button exists beside the automatic one, and a **manual wake** button beside the wake word. | A mechanism the person can drive is a mechanism they can test; the wake word is then an accelerator, never the only door (the detector may be unavailable: no WebAssembly, a refused microphone). |
| A5 | **A standby on a DIRECT session relays the exchanges kept since the last wake**, exactly as the end of a single-connection session did (ADR-301): synthesis, then the person's own turn in the chat. The end relays what is left. A delegated session relays nothing at standby (its turns are archived as they happen). **The wake re-renders the setup** at the wake's instant for both modes — the spoken clock, the psyche block and, for a direct session, the context block (which carries the last exchanges of the conversation, relayed turns included). | Owner correction 2026-10-01: the recap belongs to the closing of the connection, as before; the memory is the application's, so the wake reads it back through the mandate's own context. A setup rendered hours earlier would also carry a wrong clock. |
| A6 | The other five phrases: « Hey LIA » (en), « Hey LIA » (de), « Oye LIA » (es), « Ehi LIA » (it), « 嗨 LIA » (zh). Each phrase is a trained model, never a free entry. | Proposed on 2026-10-01, accepted in the same exchange; written here so the training set is explicit. |
| A7 | The standby has a **bounded duration** (`LIVE_STANDBY_MAX_SECONDS`, default 8 h, bounds 60 s – 24 h): past it the session ends `expired`, books closed. | A Redis key with no TTL is never written (Persistence rule); the record must outlive the cap in standby and still die. |
| A8 | The trained models are **committed** under `apps/web/public/models/wake/v1/`, each file named after its SHA-256 and checked against the manifest by the browser and by a guard test (`shipped-models.test.ts`). *Amended during lot 1: the first decision was release assets downloaded at build.* | Measured: the shared stages weigh 2.4 MB and a classifier (213 889 float32 weights) about 0.86 MB, so six languages weigh under 8 MB, not 24; the radio's committed music library is the precedent; a download stage is one more network dependency of every build and of every fresh dev environment, and a committed model brings its manifest (hashes, measured figures, provenance) into the diff a reviewer reads. |
| A9 | The per-model key `idle_timeout_seconds` **keeps its name and changes its meaning** (silence before standby, `0` = never automatically). | It is stored per model in `connector_metadata` (`live/model_settings.py`); a rename is a migration of a JSONB nobody else reads; the UI label and the API descriptions change. |

### 1.3 Business intent, stated once

A live session becomes a **presence** the person opens once and keeps for the day: it costs
nothing while nobody speaks, and it answers the moment it is called by name. The classic voice
mode gets the same name, in the person's language, without the 116 MB download and without the
English-only limitation.

---

## 2. Facts verified in the code (no extrapolation)

Every hypothesis the design rests on was read in the source. Line numbers are those of `fcfb8a89`.

| # | Fact | Where |
|---|---|---|
| F1 | The live silence clock **ends** the session: `onIdle: () => void this.end('idle_timeout')`. There is no standby state in the machine (`idle → minting → connecting → live ⇄ reconnecting → ending → ended`). | `apps/web/src/lib/live/session-controller.ts:901`, `session-machine.ts:12-62` |
| F2 | The clock runs only while nobody is busy: holds `speaking`, `delegating`, `provider`. A standby entered by the clock therefore never interrupts a delegation or LIA's speech. | `activity-clock.ts:66-71`, `session-controller.ts:415,453,586,615` |
| F3 | Mute exists and tells the provider its own way: Gemini `audioStreamEnd`, GPT-Live `session.input_audio.mute`, ElevenLabs `setMicMuted`. It keeps the connection open — it is **not** a standby. | `transports/gemini-ws.ts:292`, `openai-webrtc.ts:357`, `elevenlabs-webrtc.ts:154` |
| F4 | Microphone ownership differs by wire: `pcm` (Gemini: our worklet at 16 kHz, 40 ms chunks), `native` (GPT-Live: our stream, the track carried by WebRTC, 48 kHz), `managed` (ElevenLabs: the SDK opens the microphone itself; the controller holds no stream). | `transports/*.ts:12-46`, `mic-capture.ts:49-116`, `session-controller.ts:216-219` |
| F5 | ElevenLabs is `vendor_billed=True`, `configurable_vad=False`, `reports_idle=False`; Gemini `configurable_vad=True`; GPT-Live `configurable_vad=False`. | `domains/live/providers/elevenlabs_live.py:100-107`, `gemini.py:104-144`, `openai_live.py:98-100` |
| F6 | The record lives `expires_at − now + 120 s` (`remaining_life_seconds`); the claim, the record, the direct turns list and the tool budget counter all carry that TTL. `extend` refreshes claim, record and turns — **not** the tool budget key. | `domains/live/session_store.py:96-100,207-230,289-301` |
| F7 | The end computes `duration = now − started_at`, observed in `live_session_duration_seconds` and written on the card. | `domains/live/service.py:672-676,713` |
| F8 | The instance cap is a sorted set scored by `expires_at`; `count_active` prunes by expiry. A session in standby would keep a slot it does not use. | `session_store.py:303-316` |
| F9 | `renew_credential`/`_remint` mint to **the record's own `expires_at`**; Gemini closes an open connection at its credential's expiry (measured 2026-09-19). A wake must therefore move `expires_at` before minting. | `service.py:505-540`, docstring of `extend` at `service.py:588-604` |
| F10 | `extend` refuses when `now >= expires_at` (`session_expired`) and re-mints only on a `token` connection that is not WebRTC. | `service.py:606-616` |
| F11 | For an `offer` connection the credential endpoint keeps a fresh nonce on the record (`_keep_nonce`); the exchange consumes it before the provider is asked; « a WebRTC reconnection is a NEW provider session, its context lost ». | `service.py:324-338,541-586` |
| F12 | `hidden_grace_seconds` ends the session (`end('hidden')`), after a grace that starts only once the iOS permission sheet returned a stream. | `session-controller.ts:332-342` |
| F13 | The Gemini transport sends `sessionResumption.handle` when the controller holds one and keeps the latest `newHandle`; `goAway` triggers a reconnection with a margin. | `transports/gemini-ws.ts:149-153,277-283`, `session-controller.ts:560-575` |
| F14 | The closing is carrier-neutral: `close_voice_session(duration_seconds, extensions=0, …)` is shared with the phone's post-call path; new figures must be optional with defaults. | `infrastructure/scheduler/voice_session_closing.py:487-517` |
| F15 | The card reads `duration_seconds`, `extensions`, `relay` from `live_summary` metadata; the e2e journey asserts the card's words. | `apps/web/src/lib/live/live-message.ts:17-28`, `e2e/smoke/chat-live-session.spec.ts:371-373` |
| F16 | `useLiveHoldsMicrophone()` is `isSessionOpen(status)`: the classic voice loop pauses while a session is open. | `stores/liveStore.ts:201-203` |
| F17 | The Sherpa WASM module declares a **non-shared** memory (flags `0x1`); its glue holds zero `SharedArrayBuffer` reference. `isSherpaKwsSupported()` nevertheless requires `SharedArrayBuffer` and `crossOriginIsolated`. ADR-136, VOICE_MODE.md, both mobile guides and the mobile probe README state « no isolation → no wake word » on the strength of that predicate, not of the engine. | binary read of `public/models/sherpa-wasm/*.wasm`, `lib/audio/sherpaKws.ts:1052-1081`, `ADR-136:24-25,66-70` |
| F18 | The current engine transcribes every VAD segment with a complete Whisper (`whisper_tiny.en`, `language: 'en'` forced), synchronously on the main thread (200-400 ms, a `TODO` in the file), over 104 MB of `.data` + 12 MB of wasm. The Dockerfile stage downloads it **without a checksum**. | `sherpaKws.ts:560-574,877-882`, `apps/web/Dockerfile.prod:8-35` |
| F19 | The classic voice mode feeds the detector from its own inline worklet (`KwsProcessor`, 1 600-sample Float32 chunks) while push-to-talk and the live mode share `pcm-worklet.ts` (int16, one source). The ready chime is already a module (`lib/audio/ready-chime.ts`). | `hooks/useVoiceMode.ts:310-345`, `lib/audio/pcm-worklet.ts` |
| F20 | `VOICE_MODE_IDLE_TIMEOUT_SECONDS` (300) is declared and read by nobody. `VOICE_MODE_KWS_THRESHOLD` (0.25) is declared and read by nobody but the docs. | `lib/constants.ts:393,426`; `grep` over `src/` |
| F21 | The i18n names the phrase in prose: `chat.voice_mode.hint_listening` (« Say "OK Guy" or tap to speak »), `settings.voice_mode.enable_description`, `settings.voice_mode.experimental_note`; six locales. | `apps/web/locales/en/translation.json:768,1403-1408` |
| F22 | The Sherpa stack is named by three ratchets/baselines (`.cc-baseline.json` `sherpaKws.ts` max 16; `.react-hooks-baseline.json` `useSherpaKws.ts: 1`; `source-ratchets.guard.test.ts` ALLOWED `lib/audio/sherpaKws.ts`), by `vitest.config.ts:350` (a jsdom exclusion), by three CSP tests, by `Dockerfile.dev:5`, `scripts/setup-dev.sh:78-105`, `scripts/download-sherpa-wasm.sh`, `scripts/download-whisper-wasm-model.sh`, `apps/web/scripts/download-kws-model.sh`, `.gitignore` (both), `CLAUDE.md:1080`, `apps/web/CLAUDE.md:58`, ADR-054/098/136, VOICE_MODE.md, both mobile guides, the probe README and `page.html`. | `grep` inventory, section 7 of this document |
| F23 | The mint rate limit is 12 per 60 s per account; a reconnection mints one. The instance cap defaults to 8. | `.env.example:2616-2618`, `core/constants.py:6850-6852` |
| F24 | The live settings are composed in `core/config/live.py` (`live_idle_timeout_seconds` described as « the client ends the session »); the per-model durations are validated « within bounds or unlimited » in `model_settings.py:67-83`; the settings UI labels the field « Silence avant la fin de la session ». | `core/config/live.py:89-98`, `locales/fr/translation.json:4500-4501` |
| F25 | Dashboard 30 draws every live metric (sessions, mints, duration, turns, extensions, samples, offers, lookups, relays): a new metric must join it (metric coverage ratchet). | `infrastructure/observability/grafana/dashboards/30-live.json` |
| F26 | The direct session's turns are kept in a Redis list bounded at 400 rows for the whole session; the relay at the end reads them. | `session_store.py:139-162`, `core/constants.py:6873` |
| F27 | The end's vendor bill is fetched for ONE `provider_conversation_id` (the last one the wire named). | `service.py:689-691`, `schemas.py:587` |
| F28 | `test_vocabulary_crosses_the_stack.py` pins outcomes, refusal codes and provider rows between the API and the browser; `get_live_phrases(language)` must hold six sentences per code. | `apps/api/tests/unit/domains/live/test_vocabulary_crosses_the_stack.py:71-122` |
| F29 | The e2e journeys play the provider with `page.routeWebSocket` and mock `/live/config`, `/live/sessions`, the turns and the end; the fixture publishes `idle_timeout_seconds: 300`. | `apps/web/e2e/fixtures/live.ts`, `e2e/smoke/chat-live-session.spec.ts:284` |
| F30 | The mobile probe measures `crossOriginIsolated`, `has_SharedArrayBuffer`, `has_WebAssembly`, `has_AudioWorklet`, a WebRTC offer and a `blob:` worklet — not WebAssembly SIMD. | `scripts/mobile-probe/page.html:37-40,129-160` |
| F31 | The direct closing is two steps: `_relay_direct(session, transcript)` synthesises and relays (no card, no session held, every failure a named `RelayOutcome`), and `_settle_direct_relay` adds the card rewrite and the notice. The relay core is reusable without a card. | `infrastructure/scheduler/voice_session_closing.py:216-340` |
| F32 | The direct mandate's context block (`build_owner_context`, `SECTION_ORDER`) includes « the last few exchanges of the conversation » read from the conversation repository (`_RECENT_EXCHANGES_MAX`); the mandate renders the clock from `inputs.now`. | `domains/telephony/self_call_context.py:7,57,160-170`, `domains/live/mandate.py:49,99`, `direct_mandate.py:165,221` |

### 2.1 External facts, verified on 2026-10-01

- **openWakeWord** (Apache-2.0 code; its pre-trained models CC-BY-NC, which we do not ship):
  three ONNX stages — melspectrogram, a shared Google speech-embedding backbone (Apache-2.0),
  a per-phrase classifier — on 16 kHz int16 audio in 1 280-sample (80 ms) chunks, 76-frame mel
  windows slid by 8, 16 embeddings per decision; the mel and embedding stages run on the WASM
  backend of ONNX Runtime Web (custom audio operators). Its own training notebook supports
  English only because its TTS generator is English; the acoustic pipeline is not.
- **livekit-wakeword** (Apache-2.0): trains an openWakeWord-compatible classifier from synthetic
  TTS data with augmentation in one command, exports ONNX; reports 0.08 false positives per hour
  against openWakeWord's 8.50 on its own benchmark. Python/Rust/Swift runtimes; no browser
  runtime, but the exported classifier drops into the same three-stage pipeline.
- **voicute/onnx-wakeword**: claims fr/de/zh/en/ja, < 130 KB models, a web runtime on ONNX
  Runtime Web; training on the vendor's platform; licence not stated. Kept as a fallback to
  evaluate, not as the plan.
- **sherpa-onnx KWS**: pre-trained models exist for Chinese and English only
  (`sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20`); no French/German/Spanish/Italian.
- **Picovoice Porcupine Web**: fr/de/it/es/zh supported, custom phrases trained on their console,
  an AccessKey validated online, proprietary. Rejected (open-source, self-hosted product).
- **Gemini Live API**: a connection lives about 10 minutes (GoAway first); a session can be
  resumed on its handle after a termination (the documentation states both « within 24 hours »
  and « 2 hours after the last termination » — to be measured, section 9); audio-only sessions
  are bounded by context unless context compression is on (LIA sets it).
- **GPT-Live**: a session lasts at most 60 minutes; a WebRTC reconnection is a new session.
- **iOS Safari / PWA**: the microphone stops transmitting when the page leaves the foreground
  or the screen locks (WebKit, documented and reported); `AudioContext` suspension on background
  was fixed in iOS 17.5 for playback, not capture. Standby therefore listens **screen on** only.

---

## 3. False positives and false negatives hunted

| Kind | Claim | Verdict |
|---|---|---|
| False positive | « Mute is a standby. » | No (F3): the connection stays open, the clock still ends the session, ElevenLabs keeps billing. |
| False positive | « The credential endpoint is enough to wake. » | No (F9): it mints to a frozen, possibly past `expires_at`; the record's cap, the active set and the TTL must move first. A dedicated `wake` door does both. |
| False positive | « `extend` re-mints, so a wake can ride on it. » | No (F10): it refuses an expired cap, re-mints only on `token` connections, and would count an extension nobody asked for. |
| False positive | « The wake word needs cross-origin isolation. » | No (F17): the engine never did; the predicate did. The real mobile obstacle was weight and a synchronous decode (F18). |
| False positive | « The `.data` bundle is multilingual. » | No (F18): `whisper_tiny.en`, language forced to `en`. |
| False negative | « A new worklet is needed for the detector. » | No (F19): `pcm-worklet.ts` is the one int16 source, parametrised by chunk size; the inline `KwsProcessor` is the drift the removal fixes. |
| False negative | « A new chime is needed at wake. » | No: `lib/audio/ready-chime.ts`. |
| False negative | « A new claim/TTL primitive is needed. » | No: `refresh_claim` is owner-checked (`infrastructure/locks/redis_claim.py:106`); `LiveSessionStore.extend` already refreshes claim, record and turns under it. |
| False negative | « A new silence clock is needed. » | No (F1-F2): `ActivityClock` with `onIdle` → standby instead of end. |
| False negative | « The provider conversation id covers the vendor bill. » | Partly (F27): with several wakes an ElevenLabs session has several conversations; the bill must be summed over their ids. |
| False negative | « The tool budget follows the record's life. » | Not through `extend` (F6): a long standby would expire the counter and reset a direct session's lookup budget. The standby rewrite must refresh it. |
| False negative | « A recap must be injected at wake. » | No: the closing already turns a direct session's words into the person's own turn (F31), and the direct mandate already reads the last exchanges of the conversation (F32). Relaying at every standby and re-rendering the setup at wake gives the wake its memory through the application, with no new mechanism. |
| False positive | « Replaying the stored `setup_inputs` at wake is harmless. » | No (F32): the mandate carries the clock of its rendering; after hours of standby the voice would state a wrong time. The wake re-renders. |

---

## 4. Target design

### 4.1 Vocabulary and invariants

- **Awake**: the provider connection is open or being (re)opened; the clock, the cap, the
  budget and the meter run.
- **Standby**: the session record exists and is claimed; **no provider connection, no
  microphone chunk leaves the device, no token or minute is billed**; the wake-word detector
  listens; the cap is frozen; the person's own buttons work. Bounded by
  `LIVE_STANDBY_MAX_SECONDS`.
- **Wake**: a transition from standby to awake on a wake word or a click; one credential mint
  (+ one offer exchange on GPT-Live); the setup **re-rendered** at the wake's instant and kept
  on the record for the connection's later renewals.
- **Closing of a connection**: on a direct session, the words kept since the last wake become
  the person's own turn (synthesis + relay, ADR-301) — at every standby and at the end. On a
  delegated session nothing is owed: every exchange was archived as it happened.
- **Awake time**: the sum of awake stretches; it is what the cap, the extensions, the card's
  duration, the histogram and the decision row measure.
- **Invariant 1 — nothing is billed in standby**: by construction (no connection), on every wire.
- **Invariant 2 — one session, many connections**: the session id, run id, meter, captions,
  extensions and card survive every standby; provider connections come and go beneath them.
- **Invariant 3 — the end is explicit**: `ended` (the button), plus the pre-existing involuntary
  ends (`expired` at the standby bound or the awake cap declined, `budget_reached`, `mic_denied`,
  `superseded`, `error`). `idle_timeout` and `hidden` **leave the outcome vocabulary**: nothing
  produces them any more (ADR-303: a status nobody produces is removed, not kept).
- **Invariant 4 — the detector listens only in standby** (Live) or in `listening` (classic
  mode): never while LIA converses, so « Dis LIA » said to LIA mid-conversation triggers nothing.

### 4.2 The wake-word engine (`apps/web/src/lib/audio/wake-word/`)

**Pipeline** (openWakeWord's, re-implemented in TypeScript; no third-party browser wrapper is
pinned, the two surveyed are a blog package and a vendor CDN script):

1. `engine.ts` — openWakeWord's streaming arithmetic over a `WakeWordRuntime` interface
   (`melspectrogram(samples)`, `embed(window)`, `classify(features)` → score): int16 samples
   rebuffered into 1 280-sample chunks; per chunk, the melspectrogram of the last 1 760 samples
   (`x / 10 + 2`), a 76-frame mel window seeded with ones, a 16-embedding window seeded with
   zeros, the detection policy (`policy.ts`: warm-up, threshold, patience, refractory — all
   from the manifest). Pushes are serialised (a stage call is asynchronous). Tested with a fake
   runtime over exact window arithmetic, and held to the toolbox's reference by a golden
   fixture with the real models (`parity.test.ts`, `task wake:golden -- <lang>`).
2. `ort-runtime.ts` — the `WakeWordRuntime` on `onnxruntime-web/wasm` (pinned), WASM execution
   provider, `numThreads = 1`, no proxy (no `SharedArrayBuffer`, no isolation); the binary is
   served from `/ort/<version>/`, copied there from the package by `scripts/copy-ort-runtime.mjs`
   before `next dev` and `next build` (gitignored), the version in the path so it is cached as
   immutable. Every model file is checked against the manifest's size and SHA-256 before it is
   handed to the runtime (`IntegrityError`).
3. `worker.ts` + `worker-core.ts` — the engine runs in a dedicated module Worker; the page posts
   int16 chunks as transferables and receives `ready {phrase}`, `detected {score}` or
   `failed {reason: manifest | integrity | runtime}`; a newer `load` supersedes one in flight.
4. `manifest.ts` — `/models/wake/v1/<lang>/manifest.json`: `{version, language, phrase,
   sample_rate, chunk_samples, threshold, patience, refractory_chunks, warmup_chunks, files:
   {melspectrogram, embedding, classifier: {url, sha256, bytes}}, measured, provenance}`, parsed
   strictly (a file outside `/models/wake/`, a malformed hash, another language: refused). Model
   files are named after their SHA-256 (immutable); the manifest keeps its name and is
   revalidated (`next.config.ts` cache rules).
5. `detector.ts` — the page's side of the worker: `load(language)` resolving `ready |
   unavailable | idle`, `push(pcm16)`, `reset()`, `dispose()`, `onDetected`, `onStateChange`.
   It holds no microphone. `listener.ts` — `WakeListener`, the detector plus its own capture
   (`startMicCapture`, 16 kHz, 1 280 samples): the model loads BEFORE the microphone opens, a
   language without a usable model never lights it, `pause()` releases the microphone and keeps
   the model, `handOff()` gives the live stream to the recording that follows a detection
   (`MicCapture.detach()`), calls are serialised and a detection reaches the caller only while
   its latest call asked to listen. `useWakeWord.ts` wraps it for a component (classic mode).
6. `support.ts` — `isWakeWordSupported()`: `Worker`, `WebAssembly`, `AudioContext`,
   `AudioWorkletNode`, `crypto.subtle.digest`, `navigator.mediaDevices.getUserMedia`.
   **No `SharedArrayBuffer`, no `crossOriginIsolated`.**

**Audio sources** — *simplified during lot 1*: in standby every wire RELEASES its own capture
and the `WakeListener` opens its own (16 kHz, 80 ms). One path for three wires instead of three
(a routed worklet, a cloned track, a dedicated capture), and the provider's capture is never kept
open in standby — the person sees the microphone indicator only while LIA can actually hear the
phrase. The cost is one `getUserMedia` at each standby and at each wake (a few hundred
milliseconds, measured in the browser proofs). The classic voice mode listens through the same
`WakeListener` and hands its stream to the recording after a detection (`handOff`), as the
previous engine did.

**Models and languages.** One classifier per language for the phrases of A6; the shared
stages identical for all. Training is **offline**, in `scripts/wake-word/` (Python, its own
pinned requirements and lock, a Dockerfile so it never runs on the Pi nor on the API's
interpreter): synthetic positives from open multilingual TTS voices (Piper has fr/de/es/it/zh/en
voices; the phrase is spelled phonetically per language so « LIA » is read /li.a/, never as
letters), augmentation (noise, reverberation, gain, speed), negatives from a speech corpus of the
language (Common Voice, CC-0) plus music and noise. Export: the classifier ONNX + the manifest
with the measured threshold, written by `task wake:train -- <lang>` into
`apps/web/public/models/wake/v1/` (A8, amended): committed, every file named after its SHA-256,
the provenance of every input with its licence in the manifest.

**Measurement** (`task wake:measure -- <lang>`), reported in the ADR and on the settings page's
provenance line: recall on a held-out synthetic set and on a **real** set (≥ 5 speakers × 20
utterances, recorded by the team, kept out of the repository — « never personal usage in the
code » applies to voices too), false accepts per hour on ≥ 10 h of speech of the language and
≥ 5 h of music/noise, CPU share and detection latency on one Android mid-range phone and one
iPhone. Acceptance for lot 0, French: recall ≥ 90 % clean and ≥ 80 % at 10 dB SNR; ≤ 0.5
false accepts/hour on speech and ≤ 0.2 on music; latency ≤ 300 ms after the phrase; ≤ 10 % of
one core on the phones; and no written form of the phrase — separated (« Dis Lia »), fused
(« Dilia »), with a pause (« Dis, Lia ») — under 85 % clean, since a person says it either way
(owner on dev, 2026-10-01: « dis … Lia » woke LIA, « dilia » did not). Every language's banks
say each form, and its natural voices are told it plainly, fused and once with a pause. The
stop command (amendment 2026-10-01; « LIA, stop » since 2026-10-02, `--keyword stop`) has its own grid: the same recalls and
per-form floor, latency ≤ 300 ms, ≤ 2 false accepts/hour on speech and ≤ 1 on music — a false
stop only cuts a reading, where a false wake opens the microphone. The thresholds are published
in the spec of lot 0 and never lowered to pass.

### 4.3 Live standby — server side (`apps/api/src/domains/live/`)

**Record** (`LiveSessionRecord`, round-trip test extended field by field, the rule):
`standby_since: datetime | None = None`, `awake_since: datetime` (defaults to `started_at`),
`awake_seconds: int = 0` (completed stretches), `standbys: int = 0`,
`provider_conversation_ids: list[str] = []` (every conversation the wires named — F27).

**Arithmetic.** Awake duration = `awake_seconds + (now − awake_since)` when awake, else
`awake_seconds`. Standby seconds = `(now − started_at) − awake duration`, derived, never stored.
At standby: `awake_seconds += now − awake_since; standby_since = now; standbys += 1`. At wake:
`expires_at += now − standby_since; awake_since = now; standby_since = None`. The cap is thus
**shifted by the standby's length**, one field, and `extend` keeps its arithmetic; in standby
`extend` compares `now` with the shifted value and re-mints nothing (no connection).

**Store.** `LiveSessionStore.extend` becomes the one « rewrite under the claim with a new life »
and refreshes **every** key of the session: claim, record, turns, and the tool budget counter
(F6's gap). `standby(record)` writes with `LIVE_STANDBY_MAX_SECONDS + grace` and
`unregister_active`; `wake(record)` writes with `remaining_life_seconds` and `register_active`
after the instance-cap check.

**Routes** (`router.py`, `get_current_active_session`, the record owned):

- `POST /live/sessions/{id}/standby` → `LiveStandbyResponse {standby_since, awake_seconds,
  standby_deadline_at, relay}`. Idempotent: already in standby answers the same figures. Counts
  `live_session_standby_total{provider, reason}` (`idle | manual | hidden`, the body's reason).
  **On a direct session it drains the kept turns atomically** (one `LRANGE` + `DEL` under the
  claim — a `MULTI`, so a second standby racing a wake never relays a row twice) and schedules
  `_relay_direct` in a task the API owns (the closing's envelope: the background-task set,
  drained at shutdown), answering `relay: scheduled | empty` at once like `end` does. The task
  settles its fate on the record (`relays: list[{at, outcome, recap}]`, a rewrite under the
  claim; a lost claim leaves the fate logged and counted only), counted in the existing
  `live_direct_relay_total{outcome}`, and the thread shows the relayed turn through the
  ordinary `conversation_updated` signal. No card exists yet: nothing is rewritten. A standby
  while a relay task is still running leaves it alone (it owns its rows); the end's relay covers
  only the rows kept after it.
- `POST /live/sessions/{id}/wake` body `{reason: wake_word | manual}` →
  `LiveWakeResponse {credential: LiveCredentialResponse, expires_at, extensions}`. Refusals in
  order: 404 `session_not_found` (gone), 409 `session_awake` (not in standby), 429
  `mint_rate_limited`, 503 `instance_busy` (re-checked: the slot was released at standby), 409
  `session_expired` (the shifted cap is behind `now` — the client offers the extension, then
  wakes again). Then the setup is **re-rendered** exactly as `start` renders it (the same
  builders, `now` = the wake's instant, the account's current personality, psyche block,
  `phone_disabled_domains` and language; the route passes `timezone` and `display_name` like
  `start`), written on the record as the new `setup_inputs`, and — on an agent-bound provider
  — `_sync_agent` runs again so a tool set that changed meanwhile reaches the agent before the
  credential is minted (a vendor refusal leaves the session in standby, named). Counts
  `live_session_wakes_total{provider, reason, outcome}`.
- `extend` in standby: allowed, no mint. `end`: duration = awake duration; `standbys`,
  `standby_seconds` and the list of the standby relays' fates join `LiveEndResponse`, the
  card's metadata and `close_voice_session` as optional keyword arguments (F14: the phone
  passes none); the end's own relay covers the rows kept since the last wake and the card's
  `relay` keeps its meaning (the LAST relay's fate), the earlier fates drawn as a count with
  their outcomes. The vendor bill is summed over `provider_conversation_ids`
  (`fetch_vendor_bill` takes the list; the old single field stays readable).
- `LiveSessionStartResponse` and `LiveConfigResponse` publish `standby_max_seconds` (enforced,
  therefore published — ADR-184). `idle_timeout_seconds` keeps its name; every description and
  label says « standby ».

**Settings and constants.** `LIVE_STANDBY_MAX_SECONDS` (`core/config/live.py`, default
`LIVE_STANDBY_MAX_SECONDS_DEFAULT = 28_800`, bounds `60 – 86_400` in `core/constants.py`), the
line added to `.env.example`, `.env.prod.example`, `.env.min.prod.example` and the four
demonstrator files (`.env.demo-instance*`, `.env.public-demo`). `LIVE_HIDDEN_GRACE_SECONDS` and
`LIVE_IDLE_TIMEOUT_SECONDS` keep their names; their comments change (« enters standby »).

**Service size.** `service.py` is at 763 physical lines; standby and wake live in
`domains/live/standby.py` (functions over the store and the service's thin doors), the service
only routes to them — the 600-SLOC rule, applied before it bites. The setup rendering of
`start` is extracted into one function both `start` and `wake` call (today it is inline in
`start`, `service.py:356-383`), so the two cannot drift.

**The relay at standby, precisely.** `_relay_direct` (F31) is promoted to a public door of
`voice_session_closing` (`relay_direct_transcript`), called by the end's settle and by the
standby task alike; the card rewrite stays the end's. The relayed turn runs under the session's
run id as today, so the card's total at the end covers every relay; it is the person's own turn
(`spoken_by_person`), it may ask a question (the chat's own HITL rule), and its spend is the
platform's bookkeeping of the closing, exactly what a single-connection session paid at its
end — **standby itself still bills nothing**.

**i18n.** `get_live_phrases` gains `session_awake` and the wake-refusal sentences in six
languages (`test_every_backend_code_has_its_six_sentences`, F28); `LIVE_OUTCOMES` loses
`idle_timeout` and `hidden` on both sides (F28 pins the equality).

**Metrics and dashboard.** The two counters above, plus `live_sessions_standby` (gauge, the
sessions whose record is in standby — read from the active set's complement is not possible, so
the gauge is set from `standby`/`wake`/`end` like `live_sessions_active`); three panels on
dashboard 30 (`or vector(0)`, `"noValue": "0"`). The coverage ratchet refuses a blind metric.

### 4.4 Live standby — browser side (`apps/web/src/lib/live/`)

**Machine** (`session-machine.ts`): status `standby`; events `standby: {live: 'standby'}`,
`wake: {standby: 'connecting'}`; `isSessionOpen` includes `standby` (the record exists, the
microphone is held, the end button works — F16 keeps the classic loop paused).

**`standby.ts`** — a collaborator the controller delegates to, tested without React:

- `enter(reason)`: stop the clock, clear the expiry/extension/goAway/budget timers, bump the
  generation, `POST standby`, close the transport (awaited on `managed`), route the audio to the
  detector per the table of 4.2, start the detector with the account's language (the chat's
  language prop, normalised to the frontend's `zh`), arm one local timer at
  `standby_deadline_at − grace` → `end('expired')`, store `apply('standby')`,
  `setVoiceState('idle')`.
- `wake(reason)`: stop the detector (release its own capture first on `managed`), `POST wake`;
  on 404 → `end('superseded')`; on 409 `session_expired` → `offerExtension(true)` and, once
  extended, wake again; on 429/503/5xx/network → **stay in standby**, toast
  `live.wake.refused.<code>`, detector restarted; on success `apply('wake')`, `connect` with the
  kept resumption handle; a connection refused **with** a handle is retried once **without** it
  (a stale handle must not end a session); a second refusal returns to standby with a toast.
  `onReady`: `armExpiry`, `startClock`, `startBudgetClock`, the ready chime when the reason is
  the wake word (the chime says « I can hear you now », so it plays once the provider is ready,
  never before).
- The hidden page: `pageHidden(true)` while `live` → after the grace → `enter('hidden')`; while
  `standby` → nothing; `pageHidden(false)` while `standby` → `detector.resume()`.
- A late delegated result arriving in standby (`late:` in the bridge) is dropped for the voice —
  the chat holds it — as it is today when the transport is closed.

**Controller** (`session-controller.ts`): `onIdle` → `standby.enter('idle')`; the hidden timer
→ `standby.enter('hidden')`; `end()` from standby closes the books (no transport to close, the
detector stopped, the kept stream released); `toggleMute` is disabled in standby; two public
methods `standby()` and `wake()` for the banner; `onChunk` routes to the detector in standby.

**Store** (`liveStore.ts`): `standbySince`, `standbys`, `wakePhrase`, `detectorState`;
`effectiveVoiceState` unchanged (idle in standby).

**Banner** (`LiveBanner.tsx`): the status line `live.status.standby` with the phrase
(« En veille — dites « Dis LIA » ») as `role="status"`; a « Mettre en veille » button while
`live` (disabled while `delegating`, read from the store; open while LIA speaks — the person's
own act cuts the voice, owner request 2026-10-01); a
« Réveiller » button in standby; the microphone button hidden in standby; a one-line hint on iOS
(« gardez l'écran allumé », the user-agent test the controller already uses for the audio
transport). Every button keeps a translated `aria-label`, the existing `size="sm"` icon pattern,
keyboard reachable, no colour-only state.

**Meter**: unchanged folding; `checkBudget` reads awake elapsed (the store keeps `awakeMs`
accumulated at standby, instead of `liveSince` alone) for duration-billed models.

**Card** (`LiveSessionSummaryCard.tsx`, `live-message.ts`): « · 3 mises en veille » when
`standbys > 0`, six languages, `_one/_other` keys duplicated for zh.

### 4.5 The classic voice mode

`useVoiceMode.ts` replaces `useSherpaKws` by `useWakeWord({language, enabled, onDetected})`;
the KWS capture uses `pcm-worklet` at 1 280 samples; `isKwsSupported` becomes
`isWakeWordSupported()`; the badge and the settings show the phrase from the manifest
(`hint_listening` with `{{phrase}}`); the « experimental on mobile » note is replaced by the
measured sentence (or removed) after lot 0; `recordWakeWord`, the ready chime and the stream
steal are unchanged. On iOS and in the shells the wake word becomes **available** (F17), which
amends ADR-136's compromise sentence, both mobile guides, the probe README, `CLAUDE.md:1080`
and `apps/web/CLAUDE.md:58`.

### 4.6 Removal of the Sherpa wake-word stack

Deleted: `lib/audio/sherpaKws.ts`, `hooks/useSherpaKws.ts`, `public/models/keywords.txt`,
`scripts/download-sherpa-wasm.sh`, `scripts/download-whisper-wasm-model.sh`,
`apps/web/scripts/download-kws-model.sh`, the Dockerfile.prod stage 0 and the `setup-dev.sh`
step 3 (nothing replaces them: the models are committed, A8 amended), the `.gitignore` entries
(replaced by `/public/ort/` alone), `VOICE_MODE_KWS_THRESHOLD`,
`VOICE_MODE_IDLE_TIMEOUT_SECONDS` (F20), `VOICE_MODE_DEFAULT_WAKE_WORD` (the phrase is the
manifest's). Shrunk: `.cc-baseline.json` (the `sherpaKws.ts` entry removed; `useVoiceMode.ts`
re-measured, lowered if the removal lowers it), `.react-hooks-baseline.json` (`useSherpaKws.ts`
removed), `source-ratchets` ALLOWED (the Sherpa entry replaced by the manifest/model fetch of
`lib/audio/wake-word/manifest.ts`, same reason: static assets, not the API), `vitest.config.ts`
exclusion (the ORT runtime module replaces the Sherpa one; the engine itself is covered). The
CSP keeps `wasm-unsafe-eval`, `blob:` in `script-src` (worklets) and `worker-src 'self' blob:`;
the three CSP tests are reworded to name the wake-word engine.

### 4.7 Documentation and maps

ADR-329 « Live standby and a multilingual wake word » (amending ADR-299/300/301 for the session
lifecycle, ADR-136/246 for the isolation premise, ADR-054 for the voice input architecture);
`docs/technical/LIVE_MODE.md` (states, routes, settings, the measured provider behaviours);
`docs/technical/VOICE_MODE.md` (the engine section rewritten, the troubleshooting section);
`docs/guides/GUIDE_MOBILE_{ANDROID,IOS}.md` (the wake word is available; standby listens
screen on); `scripts/mobile-probe/README.md` and `page.html` (a `wasm_simd` measure);
`CLAUDE.md` (one short entry pointing at the ADR, per the owner's rule on additions);
`apps/web/src/data/maps/` (the ADR entry and its words in six languages, `task docs:maps`);
`docs/INDEX.md`, `ADR_INDEX.md`; the CHANGELOG at release time.

---

## 5. Impact map and risk matrix

### 5.1 Impacts

| Layer | Direct | Indirect |
|---|---|---|
| API | 2 routes, 3 schemas, 5 record fields, 2 store methods + 1 refresh, `standby.py`, `end`/`extend` arithmetic, 1 setting + constants, 6-language phrases, 3 metrics + 3 panels | `close_voice_session` signature (optional kwargs, phone unchanged), `fetch_vendor_bill` over a list, `LIVE_OUTCOMES` shrink, the e2e fixture's mocked responses |
| Web (live) | machine, `standby.ts`, controller wiring, store, banner, hook, i18n (≈ 12 keys × 6), tests | `useLiveHoldsMicrophone` semantics unchanged by inclusion of `standby`; the eyes unchanged |
| Web (voice) | `useVoiceMode` detector swap and worklet unification, badge, settings, i18n | push-to-talk untouched; meeting recorder untouched (shares `pcm-worklet`) |
| Web (build) | `onnxruntime-web` dependency, ORT wasm copy script, model download stage with checksums, `.gitignore`, ratchets/baselines shrink | the dev-container lockfile trap; `pnpm install --frozen-lockfile` in the prod build |
| Database | none (Redis record only; no migration) | — |
| LLM / providers | one mint per wake (+ one offer exchange on GPT-Live); the setup re-billed at the first turn of a fresh provider session; nothing recorded by the platform (the person's key) | the mint rate limit bounds a flapping wake; the instance cap is re-checked |
| Registers | the decision row's duration = awake time; the card gains two figures; no new register, no new consultation | Article-12 export: additive metadata |
| Mobile | wake word available on iOS/shells; standby screen-on only; the probe gains a measure | the native shells need no change (web origin) |
| Docs | ADR-329 + 4 amendments, 2 technical docs, 2 guides, maps in 6 languages | `lint:docs` facts (figures quoted from code) |

### 5.2 Risks and mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | A non-English phrase trained on synthetic voices under-performs (recall, false accepts). | medium-high | blocks the feature | **Lot 0 first**, go/no-go on published thresholds; fallbacks evaluated in the same lot (onnx-wakeword; a different embedding) before any product code. |
| R2 | ONNX Runtime Web's single-thread binary or SIMD on iOS Safari/WebView misbehaves. | low-medium | wake word unavailable on iOS | Measured in lot 0 on a real iPhone (probe page + the engine); the UI degrades to the wake button / tap-to-speak through `detectorState`. |
| R3 | A stale Gemini resumption handle makes the wake fail. | medium | a wake that ends the session | One retry without the handle; the handle's validity after a termination measured on a proof account (`task live:probe`). |
| R4 | Safari refuses two simultaneous captures (ElevenLabs SDK + our detector). | medium | wake fails on iOS + ElevenLabs | The detector releases its capture before `startSession`; measured in lot 0; the order is a pinned test. |
| R5 | Standby bypasses the direct session's lookup budget (TTL reset). | certain without the fix | a ceiling that lies | `extend` refreshes the tool budget key; a store test with FakeRedis TTLs. |
| R6 | A tab in standby for hours is superseded by another start and does not know. | medium | a confusing wake failure | The wake's 404 ends it `superseded` with its toast; optional: the chat merge recognises a `live_session_summary` row of its own session id and closes the tab (kept as a follow-up). |
| R7 | The cap arithmetic drifts (shift, extension in standby, expiry). | medium | wrong card, wrong refusals | Pure functions over a frozen clock, property tests on sequences of standby/wake/extend; the record round-trip test. |
| R8 | The hidden-page rule change leaves a session open for hours on a locked phone. | low | none billed, a stale banner | By design (A3): nothing is billed; the standby bound ends it; the toast at `expired` says so. |
| R9 | The removal leaves a dangling reference (docs, ratchets, CSP tests, scripts). | medium | red build | The inventory of F22 is the checklist of lot 2; `task lint` + `lint:docs` + the ratchets refuse a leftover. |
| R10 | `session-controller.ts` and `useVoiceMode.ts` grow past their complexity baselines. | medium | ratchet red | Standby in its own module; the voice mode loses the inline worklet and the Sherpa hook; the baselines are re-measured, never raised. |
| R11 | The vendor bill shown at the end covers one conversation of several. | certain without the fix | a wrong figure shown | Sum over `provider_conversation_ids`; a unit test with two ids. |
| R12 | A model download at build fails or is tampered. | low | red build / wrong model | SHA-256 pinned in the Dockerfile and the manifest; a failed check fails the build, never a silent fallback. |

---

## 6. Edge cases to prove

| Scenario | Expected behaviour |
|---|---|
| Nominal: silence → standby → « Dis LIA » → chime → question → answer | one session, one card with 1 standby, duration = awake time |
| Silence while LIA speaks / delegates / provider processes | no standby (the clock's holds); manual standby button disabled while LIA delegates, open while LIA speaks (it cuts the voice) |
| Manual standby mid-turn | refused in the UI (disabled); the API accepts a standby whenever asked (idempotent) |
| Wake word while awake | ignored (detector stopped) |
| Wake on 429 / 503 / 5xx / network down | stays in standby, toast, detector restarted |
| Wake on 404 | `superseded` |
| Wake with the awake cap exhausted | 409 `session_expired` → extension dialog → extend (no mint) → wake |
| Wake refused by the provider with a handle | retry once without the handle; then standby + toast |
| Gemini standby longer than the handle's validity | fresh session, same setup, context from the mandate alone |
| GPT-Live wake | new nonce, new offer, new provider session; the kept track re-added |
| ElevenLabs wake | detector capture released, new signed URL, new conversation id appended |
| Standby reaches `LIVE_STANDBY_MAX_SECONDS` | client ends `expired` before the record's grace; books closed |
| Record gone during standby (Redis flush) | the local deadline or the wake's 404 ends the tab honestly |
| Page hidden while awake (desktop) | standby after the grace; the detector keeps hearing on desktop |
| Page hidden / screen locked (iOS) in standby | nothing heard until visible; `resume()` on return |
| Microphone revoked in standby | the track ends; the wake fails `mic_denied` |
| Device change in standby | ignored; the wake re-opens on the default device |
| Direct session, 400 kept rows reached within one awake stretch | rows past the bound dropped and counted (existing); the bound now applies per stretch since every standby drains the list |
| Direct session: standby with nothing said since the last wake | `relay: empty`, no task, no turn |
| Direct session: standby, then wake before the relay task settled | the task finishes on its own rows; the new stretch starts with an empty list; the fate lands on the record whenever it settles |
| Direct session: the relay fails or is quota-blocked at a standby | the fate and the recap are kept on the record and drawn on the final card; the words are never lost in silence |
| Wake on ElevenLabs after `phone_disabled_domains` changed in standby | the re-rendered tool set re-syncs the agent (fingerprint); a vendor refusal leaves the session in standby with a toast |
| Wake after hours: the mandate's clock | re-rendered at the wake's instant, never the start's |
| Direct session, lookup budget across a long standby | the counter's TTL follows the record (R5) |
| Budget reached while awake | `budget_reached` ends (unchanged) |
| Two starts of one account, one in standby | the second supersedes; the first learns at its next request |
| Detector unavailable (no WASM, bad checksum, worker refused) | standby still works with the wake button; the banner says the word is unavailable |
| Classic mode on iOS Safari | wake word available; tap-to-speak remains |
| Classic mode: live session open | the loop stays paused (`useLiveHoldsMicrophone`) |
| Language switched mid-session | the detector loads the new language at the next standby; never mid-listen |
| Malformed `wake` body / unknown reason | 422 (closed vocabulary) |

---

## 7. LLM, cost and quota analysis

- **Standby**: zero tokens, zero minutes, zero Pi CPU beyond two cheap Redis rewrites. The
  record's Redis footprint is unchanged (a few hundred bytes).
- **Wake**: one credential mint (Gemini: a token; ElevenLabs: a signed URL; GPT-Live: a nonce
  plus one SDP exchange on the person's key), bounded by the mint rate limit (12/min/account).
  A fresh provider session re-bills its setup at the first turn: ≈ 1.2 K prompt tokens on a
  delegated Gemini session, ≈ 11 K on a direct one (ADR-300 wave 4 measurement); within the
  handle's validity Gemini resumes with its context and re-bills nothing of the setup. GPT-Live
  always starts fresh (60-minute sessions anyway). ElevenLabs starts a new conversation on the
  vendor's per-minute grid.
- **Platform spend**: the provider side runs on the person's own key (ADR-299); the meter
  shows the folded total across wakes; nothing of it is recorded (feedback: never record a
  person's own key spend). What the platform DOES pay is unchanged in nature and moves in time:
  a direct session's synthesis and relayed turn, once per standby and once at the end instead
  of once at the end — filed under the session's run id, shown on the card, bounded by the
  account's and the instance's ceilings like any chat turn (ADR-272). A delegated session's
  standby costs the platform nothing.
- **Instance**: the cap counts awake sessions; a standby session frees its slot and asks again
  at wake. The API does one Redis round trip per standby/wake plus one provider call per wake.
- **Prompt sizing**: unchanged — the mandate is rendered once at start and replayed.
- **The Pi**: serves ~5 MB of static model files per language once (immutable cache headers on
  the versioned path), nothing else.

---

## 8. Test master plan (TDD basis)

### 8.1 Coverage matrix

| Unit under test | Level | What is proven |
|---|---|---|
| `engine.ts` | web TU (vitest, fake runtime) | frame rebuffering 40/20 ms → 80 ms, mel window 76/8, 16-embedding decision, threshold and refractory, int16 → float exactness, no detection on silence, detection on a scripted score sequence |
| `manifest.ts` | web TU | shape validation, SHA-256 mismatch → `unavailable`, unknown language → `unavailable` |
| `detector.ts` | web TU (fake worker) | start/stop/resume lifecycle, events, one active source, release order on `managed` |
| `useWakeWord` | web TU | loading → listening → detected → callback; unsupported → inert |
| `session-machine.ts` | web TU | the two transitions; `isSessionOpen` includes standby; outcomes without `idle_timeout`/`hidden` |
| `standby.ts` | web TU (fake api/transport/mic/detector/clock) | enter per wire (close awaited on managed, chunk routing on pcm, clone on native), wake happy path, the refusal matrix of section 6, handle retry, chime on wake-word only, deadline timer |
| `session-controller.ts` | web TU | idle → standby not end; hidden → standby; end from standby; mute disabled; `awakeMs` for the budget |
| `liveStore`, `live-message` | web TU | new fields, card figures, zh plural duplicates |
| `LiveBanner` | web TU (RTL) | standby line as `status`, buttons with translated names, disabled while busy, keyboard |
| `useVoiceMode` | web TU (existing 775-line suite rewired) | wake → recording with the new hook; unsupported → tap-to-speak; worklet unification |
| CSP, source ratchets, baselines | web TU | reworded tests pass; the ALLOWED entry replaced, not added |
| `session_store.py` | API TU (FakeRedis) | standby/wake rewrites and TTLs on claim, record, turns, tool budget; active set unregister/register; round-trip over every field |
| `standby.py` / `service.py` | API TU (frozen clock) | arithmetic sequences (standby → wake → extend → standby → end), refusal order, idempotence, `extend` in standby without mint, `end` duration and figures, vendor bill summed, the setup re-rendered at wake with the wake's `now` (one rendering function for `start` and `wake`), agent re-sync at wake on an agent-bound provider |
| direct relay at standby | API TU (fake store, fake relay door) | an atomic drain (no row relayed twice across a standby/wake race), `relay: empty` on nothing kept, the fate written on the record, a lost claim leaves it logged, the end relays only the later rows, the card lists the fates |
| `router.py`, `schemas.py` | API TU | routes wired with the session dependency, closed `reason` vocabulary (422), bounds published |
| config/constants | API TU | `LIVE_STANDBY_MAX_SECONDS` bounds; the `.env*` files carry the line (existing env guard) |
| i18n phrases | API TU | six sentences per code (`test_vocabulary_crosses_the_stack.py`) |
| metrics | API TU | the coverage ratchet sees the three panels |
| session store on **real Redis** | API integration | two independent actors: a successor's claim refuses the owner's standby/wake; expiry of a standby record; TTL of the tool budget after a standby |
| closing with figures | API integration (PostgreSQL, extends `test_live_trace_db.py`) | the card row carries `standbys`/`standby_seconds`; the decision row's duration is awake time |
| live journey | e2e (Playwright, `routeWebSocket`) | start → silence (mocked `idle_timeout_seconds: 5`) → standby line → socket closed → « Réveiller » → `POST wake` observed → setup replayed on a new socket → captions → end → card « 1 mise en veille » |
| classic mode journey | e2e | the badge names the phrase; tap-to-speak unchanged |
| mobile probe | measurement (`task mobile:probe:*`) | `wasm_simd`, the engine's load and one detection on both shells |

### 8.2 Simulations and measurements before and during development

1. **Lot 0 bench** (before any product code): French model trained; recall/false-accept/latency/CPU
   figures on the sets of 4.2; ORT single-thread on iOS Safari; Safari double-capture behaviour.
2. **Provider wakes on a proof account** (never the owner's — a start supersedes the account's
   session): Gemini resume inside and outside the handle's validity; GPT-Live fresh offer after a
   closed peer connection; ElevenLabs new conversation and the summed bill.
3. **Clock sequences** as property tests (random sequences of standby/wake/extend over a frozen
   clock; the invariant: awake + standby = wall time, cap − awake = remaining).
4. **A long standby on dev Docker**: 1 h in standby, Redis TTLs read every 10 min, zero provider
   traffic observed on the browser's network panel, then a wake.

---

## 9. Action plan — lots, ordered, atomic

Each lot ends with `task lint`, the fast unit gates of both apps, the relevant e2e, and an
exhaustive cold adversarial review (file by file). Nothing is committed by the agent.

**Lot 0 — the bench (no product code).** `scripts/wake-word/` (Dockerfile, pinned requirements
+ lock, `train.py`, `measure.py`, `task wake:train`, `task wake:measure`); the French model;
the measurement table in `docs/superpowers/specs/2026-10-01-wake-word-bench.md`; the ORT/iOS
and Safari-capture probes. **Go/no-go against the published thresholds.** Estimated 2-4 days.

**Lot 1 — the detector.** TDD order: `engine.ts` → `manifest.ts` → `detector.ts` (fake worker)
→ `worker.ts` + `ort-runtime.ts` → `support.ts` → `listener.ts` → `useWakeWord.ts`;
`onnxruntime-web` pinned, the ORT copy script (`/ort/<version>/`, gitignored), `.gitignore`,
cache rules for `/models/wake/` (immutable files, revalidated manifest) and `/ort/<version>/`;
the shipped-models guard; CSP tests reworded with the removal (lot 2); the mobile probe
measure. 2-3 days.

**Lot 2 — the classic voice mode and the removal.** `useVoiceMode` on `useWakeWord` and
`pcm-worklet`; badge and settings on the manifest's phrase; i18n in six languages; the F22
inventory deleted or reworded; ratchets and baselines shrunk; ADR-136 amendment, guides,
`CLAUDE.md` lines; the 775-line suite green. 2 days.

**Lot 3a — API standby/wake.** Record fields + round-trip test → store methods + FakeRedis TTL
tests + the atomic drain → `standby.py` arithmetic (frozen clock) → the setup rendering
extracted from `start` → the relay door promoted from the closing and the standby relay task →
routes/schemas → `end`/`extend` changes → vendor bill list → settings/constants/env files (all
seven) → phrases ×6 → metrics + dashboard 30 → real-Redis integration test (two actors) →
PostgreSQL closing test with the relay fates on the card. 4-5 days.

**Lot 3b — browser standby/wake.** `session-machine` → `standby.ts` (fakes) → controller
wiring → store → banner + i18n → `useLiveSession` → `live-message`/card → e2e journey; the
`LIVE_OUTCOMES` shrink on both sides. 3-4 days.

**Lot 3c — proofs and documentation.** Provider wakes on a proof account (figures into the
ADR); ADR-329 and the four amendments; LIVE_MODE.md, VOICE_MODE.md, the mobile guides and probe
README; maps data in six languages + `task docs:maps`; `lint:docs`. 1-2 days.

Ratchets touched, all in the shrinking direction: `.cc-baseline.json`, `.react-hooks-baseline.json`,
`source-ratchets` ALLOWED (one entry replaced), `vitest.config.ts` exclusion (one module
replaced), `metric_coverage_baseline.json` (nothing added: the panels ship with the metrics),
`file_size_baseline.json` (nothing added: new modules under the cap).

---

## 10. Residual arbitrations (none blocks lot 0)

1. A1-A9 of section 1.2, each with its reason — a « no » on any of them changes one lot, not the
   plan.
2. The acceptance thresholds of lot 0 (section 4.2) — the owner may tighten them; they are not
   lowered to pass.
3. Follow-ups deliberately left out of v1: a standby tab closing itself when superseded (R6);
   an « asleep » expression of the eyes in standby; a per-language phrase chosen among several
   trained ones.

---

## 11. Self-evaluation

- **Complete, robust, viable, no blur that blocks implementation?** Yes for the engineering of
  every lot: each hypothesis names its file and line (section 2), every refusal, TTL, arithmetic
  and audio path is specified, the edge cases are enumerated with their expected behaviour. One
  empirical question remains by nature — whether a French phrase trained on synthetic voices
  reaches the published thresholds — and the plan puts it **first**, with a go/no-go, so no
  product code is written on a guess.
- **Every hypothesis confronted with the code?** Yes (F1-F30), and three of the first reading's
  claims were corrected by it: the tool budget's TTL does not follow `extend` (R5), the vendor
  bill reads one conversation (R11), and the wake word never needed shared memory (F17). The
  external claims are dated and marked « to be measured » where the documentation is ambiguous
  (the Gemini handle's validity, ORT on iOS, Safari's capture rule).
- **Tokens/costs, registers, mobile fully framed?** Yes: section 7 (nothing billed in standby,
  the per-wake setup cost named with its measured orders of magnitude, the platform records
  nothing), section 4.3 (the decision row and the card measure awake time; no new register),
  sections 2.1/4.2/6 (screen-on standby on iOS, the detector's degradation path, the probe
  measures).
- **Plans precise enough to start now?** Lot 0 can start immediately; lots 1-3 are ordered in
  TDD steps with their test files named, and each is bounded by a ratchet it must not raise.

---

## 12. What changed while it was built

Each change below is the smaller or the measured choice; none widens the scope.

- **The models are committed, not downloaded at build** (A8): measured, the two shared stages
  weigh 2.4 MB and a classifier about 0.86 MB — under 8 MB for six languages, which does not
  justify a network dependency in every build. Every file is named after its SHA-256 and held
  to its manifest by `shipped-models.test.ts`.
- **`idle_timeout` and `hidden` stay outcomes** (4.3 said `LIVE_OUTCOMES` would lose them):
  cards archived before carry them, and a page hidden while a connection is still OPENING has
  nothing to keep asleep, so it still ends as `hidden`.
- **The fates of a direct session's standby relays live in a list of their own**, appended by
  the relay task, read by the end — never a read-modify-write of the record, which the wake
  rewrites concurrently.
- **Each wire keeps its dedicated capture** (4.2 and 4.4 routed the session's microphone to the
  detector per wire): the wake word opens its own capture at 16 kHz through the same
  `WakeListener` as the classic voice mode, and releases it before the wake's connection opens
  — simpler, the same code path for every provider, and what a browser refusing two captures
  needs.
- **A wake the provider refuses twice goes back to sleep under its own reason**,
  `wake_failed` (the API's `LiveStandbyReason` and the browser's type, held equal by
  `test_vocabulary_crosses_the_stack.py`), so the dashboard tells it from a silence.
- **`session_awake` on a wake ends the session, named**: the API holds the record awake while
  this tab believes it asleep — a lost answer, never a state to repair by guessing.
- **The browser's policy is a class, `LiveStandby`**, over a five-door wire the controller lends
  it; every step after a wait checks that the session it began for is still the store's (found
  by the lot's review: a slow standby answer for an ended session could otherwise sleep or end
  the NEXT one).
- **The band's door is one button that changes role**, so a keyboard user's focus survives the
  sleep, the connection and the wake.
- **The composer stays closed while a session sleeps**, as while it talks; opening it would let
  a phrase wake the session in the middle of a typed turn. Kept as a follow-up for the owner.
- **Lot 0's first French run** (Piper voices only, 40 000 steps) held no threshold under the dev
  false-accept target by step 14 000; the training now logs how far the strictest threshold
  stands (`dev_fa_per_hour_strictest`), and the next run trains on Piper and VoxCPM2 banks
  together. That first run then froze inside the WSL kernel (the per-VMA lock defect already met
  on 2026-09-03), which also stopped every new container: the retraining waits for the host.
