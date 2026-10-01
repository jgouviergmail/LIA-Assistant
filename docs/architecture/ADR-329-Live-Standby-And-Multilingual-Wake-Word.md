# ADR-329 — Live standby and a multilingual wake word

**Status:** Accepted — 2026-10-01, owner request: « a standby after a delay of silence, and a
listening that wakes on a phrase in the person's language », in the three Live modes (Gemini,
OpenAI, ElevenLabs) and in the classic voice mode, under the project's hard constraints — a
Raspberry Pi hosts the server, the client is a PWA on iPhone and Android. The previous wake word
(« OK Guy ») was judged « unreliable, not optimal, English only » and is removed. Delivered in
lots: the bench (0), the detector (1), the classic voice mode and the removal (2), the live
standby (3). Spec: `docs/superpowers/specs/2026-10-01-live-standby-and-multilingual-wake-word-design.md`.

**Amends:** ADR-054 (the voice input's wake word), ADR-098 (the Sherpa glue loader of the CSP
context), ADR-136 (the isolation premise: the wake word no longer needs it), ADR-246 (the shells
no longer lose the wake word to isolation), ADR-299 / ADR-300 / ADR-301 (a live session sleeps
on silence instead of ending, and a direct session relays its words at each standby).

## Context

Read in the code before deciding (2026-10-01):

- The browser's wake word transcribed every speech segment with Whisper tiny.en compiled to WASM
  (`language: 'en'` forced) and matched « ok guy » in the text, synchronously on the main thread
  (200-400 ms stalls), over 104 MB of `.data` and 12 MB of WASM downloaded at build **without a
  checksum**. One English phrase served six interface languages.
- Its support predicate required `SharedArrayBuffer` and `crossOriginIsolated`, yet the WASM
  module declares a **non-shared** memory (read in the binary). That predicate, not the engine,
  is what lost the wake word on iOS (no `credentialless` COEP in WebKit, ADR-136) and in both
  native shells (never isolated, measured twice).
- No browser wake-word engine exists for the six phrases: the openWakeWord architecture (two
  shared stages — a melspectrogram and Google's `speech_embedding` — and a small classifier per
  phrase, Apache-2.0) is the one whose shared stages run anywhere ONNX runs and whose classifier
  trains offline on synthetic speech.

## Decision — one trained phrase per interface language

- The phrases are « Dis LIA » (fr), « Hey LIA » (en, de), « Oye LIA » (es), « Ehi LIA » (it),
  « 嗨 LIA » (zh). A phrase is a **trained model**, never a free entry; the interface language
  picks it. `lib/audio/wake-word/phrases.ts` names them for the screens (typed
  `Record<Language, string>`, so complete by construction) and the shipped-models guard holds
  every manifest's phrase equal to it.
- The models are trained **offline** in `scripts/wake-word/` (its own pinned requirements, two
  Docker images — CPU, and GPU for VoxCPM2 — never the API's interpreter nor the Pi): positives
  and near misses spoken by Piper voices (inside a sentence, cut on the phoneme alignment — a VITS
  voice asked for two words babbles) and by VoxCPM2 voices designed from descriptions or cloned
  from the corpora's speakers; negatives from FLEURS, Multilingual LibriSpeech and MUSAN; rooms,
  noise, band limits and levels synthesised. Every input that shapes a shipped model carries a
  permissive licence (CC0, CC-BY, public domain, Apache-2.0); a share-alike voice serves the
  held-out test set only. Every download is pinned to an immutable address and a SHA-256
  (`sources.lock.json`).
- The bench measures each candidate on held-out voices and corpora (recall clean and at 10 dB
  and 5 dB SNR, near-miss accepts, false accepts per hour on speech and on music, median
  latency) against thresholds published **before** training and never lowered to pass: recall
  ≥ 90 % clean and ≥ 80 % at 10 dB, ≤ 0.5 false accepts per hour on speech and ≤ 0.2 on music,
  latency ≤ 300 ms after the phrase. A model that fails them is not shipped.
- The models are **committed** under `apps/web/public/models/wake/v1/` (the spec first said
  release assets downloaded at build; measured, the two shared stages weigh 2.4 MB and a
  classifier — 213 889 float32 weights — about 0.86 MB, so under 8 MB for six languages, which
  does not justify a network dependency in every build): every file named
  after its SHA-256, one `manifest.json` per language stating the files with their size and
  hash, the detection policy, the measured figures and the provenance of every input with its
  licence. `shipped-models.test.ts` holds each file to its manifest, each model to an accepted
  bench, and refuses a file no manifest names.

## Decision — the browser engine

- `engine.ts` reproduces openWakeWord's **streaming** arithmetic exactly (melspectrogram of the
  last 1 760 samples per 80 ms chunk, a 76-frame mel window seeded with ones, a 16-embedding
  window), and `policy.ts` the toolbox's detection rule (warm-up, threshold, patience,
  refractory period); a differential test holds the policy to the toolbox's vectorised
  formulation on random streams. The toolbox's selfcheck proved its batch scorer equal to
  openWakeWord's streaming one; a golden fixture, regenerated from each exported model, holds
  the browser's scores to the toolbox's on the real models through ONNX Runtime Web
  (`parity.test.ts`).
- The runtime is `onnxruntime-web/wasm`, **single-threaded, no proxy**, in a dedicated module
  worker: no `SharedArrayBuffer`, no cross-origin isolation, no main-thread stall. Its binary is
  served from `/ort/<version>/` (copied from the pinned package before `next dev` and `next
  build`; never a CDN). Every model file is fetched, checked against its manifest's size and
  SHA-256, and only then run.
- Caching: model files and the runtime binary are served `immutable` (a new content is a new
  URL); the manifest is revalidated.
- `WakeListener` owns the microphone of the wake word: the model loads **before** the
  microphone opens, so a language without a usable model never lights it; `pause()` releases
  the microphone and keeps the model; `handOff()` releases the capture but hands its **live
  stream** to the recording that follows a detection (`MicCapture.detach()`); calls are
  serialised, and a detection reaches the caller only while its latest call asked to listen. A
  runtime that fails while listening releases the microphone and reports `unavailable`.

## Decision — the classic voice mode and the removal

- `useVoiceMode` listens through `useWakeWord` while it waits for the person (`listening`), not
  while a meeting, a live session or the radio holds the microphone (ADR-258). The badge names
  the phrase while it listens and offers tap-to-speak otherwise — never a permanent
  « initializing »; the settings name the language's phrase. A tap while the phrase is listened
  for takes the same live stream.
- Removed: the Sherpa wake-word module and hook, `keywords.txt`, the three download scripts, the
  Dockerfile stage that fetched them, the setup step, the webpack `asyncWebAssembly` experiment,
  three dead constants (two read by nobody, the phrase now the model's), the store's three
  mirrored detector flags; the ratchets and baselines shrank accordingly. The backend STT
  (Sherpa-onnx Whisper Small) is untouched.

## Decision — the live standby

- A Live session — delegated or direct, on every provider — **sleeps** after its model's silence
  timeout, on a page hidden past its grace, or on the person's button: the browser closes the
  provider connection, so nothing of the provider runs or bills, then says so
  (`POST /live/sessions/{id}/standby`). The session itself stays: the record stays claimed,
  lives to `LIVE_STANDBY_MAX_SECONDS` instead of its frozen cap, and moves from the instance's
  active count to its standby set. **Only the person ends a session**; the silence and a hidden
  page no longer do. `idle_timeout` and `hidden` stay outcomes, because cards archived before
  carry them and a page hidden while a connection opens still ends it.
- **A wake opens a new connection** (`POST …/wake`), on the phrase or the button. The API refuses
  in order (awake already, cap spent, mint rate, instance cap), re-renders the setup at the
  wake's instant through the start's own function (`setup_render.render_setup_inputs`: the
  clock, LIA's inner state, the person's current switches), lets an agent-bound provider learn a
  tool set that changed, mints, and only then writes the record awake — a refused mint leaves the
  session asleep, exactly as it was. The cap is shifted by the length of the sleep: a session's
  « ten minutes » are ten minutes AWAKE. The browser connects on the kept resumption handle, then
  once more without it on a fresh credential (a stale handle must not end a session); refused
  twice, the session goes back to sleep under its own reason (`wake_failed`) and says so.
- **The memory is the application's, not the provider's** (owner decision): the setup is
  rendered from LIA's own context at every wake; a provider's resumed context is a bonus, never
  the source.
- **A direct session relays its words at each standby**, as a single session relayed them at its
  end (ADR-301): the kept turns are drained in one command and relayed off the request path; each
  fate goes to a list of its own (no read-modify-write of the record) and the closing card quotes
  the recap of every relay that could not run. A delegated session owes nothing: its exchanges
  were archived as they happened.
- **The figures are the awake ones**: the card's duration, the decision row, the histogram and
  the browser's meter count time awake; the card names the sleeps; the vendor's bill is read over
  every conversation the session's connections opened, all or nothing.
- Browser: `LiveStandby` (`lib/live/standby.ts`) owns the policy — the two requests and their
  refusals, the wake word, the bound — and the controller lends it its wire (close it, reopen it,
  arm the cap, end). The wake word of a sleeping session is the same `WakeListener` on a capture
  of its own (the spec first routed the session's microphone to the detector; each wire keeping
  its dedicated capture is simpler and is what some browsers require), listening on a visible
  page only and released before a wake. Every step after a wait checks that the session it began
  for is still the one the store holds, so a slow answer never sleeps or ends the next session.
  The banner says the session sleeps, what wakes it and that nothing bills; « standby » is closed
  while LIA works on a delegated request (its answer is what the voice waits for) and open while
  LIA speaks — the person's own act cuts the voice, only the silence clock waits for an answer's
  end (owner request 2026-10-01); one button changes role, so a keyboard user's focus survives the
  sleep and the wake; an iPhone is asked to keep its screen on.
- Metrics: `live_session_standby_total{provider,reason}`,
  `live_session_wakes_total{provider,reason,outcome}` and the `live_sessions_standby` gauge, on
  three panels of dashboard 30.

## Consequences

- The wake word speaks the person's language, costs one worker (natively, the three stages take
  ~0.8 ms per 80 ms chunk on one desktop core; the browser's WASM cost is measured by the mobile
  probe), and no longer depends on isolation; the shells and iOS lose the reason they had no
  wake word.
- Changing a phrase or a threshold is a retraining, never a setting.
- A live session can stay open for hours at no provider cost; what it costs is the time awake,
  and that is what every figure shows. The composer stays closed while a session sleeps, as while
  it talks: typing means ending it.

**Not measured yet, and said so:** the recall on real voices recorded by people (the bench's
real set needs recordings the agent cannot make), the engine on a physical iPhone, the CPU share
and latency on a mid-range phone; on a real provider, how long Gemini honours a resumption handle
after a long sleep (the retry without it covers the refusal); on a physical iPhone, whether the
answer of a session woken by the phrase plays without a fresh gesture, and whether the chime does.

## Amendment — 2026-10-01: the owner's first tests on dev

The training procedure, end to end, and the measurements behind it:
[WAKE_WORD_TRAINING.md](../technical/WAKE_WORD_TRAINING.md).

- **The runtime's loader ships with its binary.** ONNX Runtime Web 1.30 loads
  `ort-wasm-simd-threaded.mjs` beside the `.wasm` from `wasmPaths`; only the binary was copied, the
  loader answered 404 and the badge offered tap-to-speak alone.
  `apps/web/scripts/copy-ort-runtime.mjs` copies both.
- **The phrase is said quickly.** « dis … Lia » woke LIA, « dilia » did not: the natural voices
  said the phrase slowly (median 0.85 s, a third with a pause). Every language now trains its
  phrase plainly, FUSED and once with a pause (« Dis Lia », « Dilia », « Dis, Lia »), Piper's rate
  and the speed augmentation reach faster, and the bench reports the recall of each written form
  and refuses a model leaving one under 85 % clean (`recall_each_form`). VoxCPM2 keeps its first
  plan, on ONE process: measured, a process peaks at 11.3 GB of RAM while it loads and commits
  about 8.6 GB on a Windows host under WSL — three at once froze the WSL machine.
- **Talking over LIA cuts her voice.** The phrase heard while she reads an answer aloud stops her
  before the recording opens (`useVoiceMode.onInterrupt` → `useChat.stopVoice`); before, she kept
  speaking over the person until the transcription was sent.
- **A stop word, per language** (owner choice: « Stop » in French, English and Italian, « Stopp »
  in German, « 停下 » in Chinese; Spanish delegated: « Detente », the word Spanish speakers already
  tell a voice assistant — « para » is also the preposition in almost every sentence and
  « bastante » begins with « basta », and a detector that decides as the word ends cannot tell
  them apart). It is a SECOND classifier over the same
  embeddings, declared by the language's manifest under `commands` (its word, policy, classifier
  and measured figures, exported by `--keyword stop` into the phrase's manifest), posted by the
  worker as a `command` and relayed by the listener under the same gate as the phrase. It cuts
  LIA's voice and nothing else: no recording, no transcription, no message. It is not armed: a
  stop heard while nothing plays stops nothing. Its own grid allows more false accepts — ≤ 2 per
  hour on speech, ≤ 1 on music, recall as the phrase's — since a false one only cuts a reading,
  where a false wake opens the microphone. `shipped-models.test.ts` requires it in every
  language, its word equal to `STOP_WORDS`. In a live session the provider hears « stop » itself.
- **The standby door stays open while LIA speaks**: the person's own act cuts the voice; it closes
  only while a delegated request is in flight, whose answer the voice waits for.

## Amendment — 2026-10-02: French only, in beta

Owner decision for the release: « the wake word works only in French and is still in BETA (its
recognition is being improved) ». The French model was rebuilt (fused forms, faster voices) and
its bench says so honestly — clean recall 88 %, 50 % at 10 dB, false accepts per hour 0.50 on
French speech, 0.41 on music, 1.52 on noise: `no-go` against the thresholds above, which were
not lowered. The other five languages have no model yet.

- **What ships is declared, with its status.** `WAKE_MODEL_STATUS` (`lib/audio/wake-word/
  manifest.ts`) names the languages a model ships for — `{ fr: 'beta' }` — and
  `wakeLanguageOf` answers null for every other interface language, so the listener stays
  `unavailable`, never fetches a manifest the server does not hold, and the person keeps the
  badge's tap and the long press. The settings say « beta », say why, and in a language without
  a model say that the phrase is not offered there yet — never an empty « {{phrase}} ».
- **The decision « a model that fails the bench is not shipped » is amended, not dropped**: a
  model below the thresholds may ship only as `beta`, and the guard holds the status to the
  verdict BOTH ways — `stable` requires `go` for the phrase and the stop word, and a `beta`
  model whose bench says `go` fails until the table says `stable`. The guard also refuses a
  manifest for a language the table does not declare.
- The stop word ships with the phrase, beta too (its own bench: 83 % clean, `no-go`).
- The phrases of the five other languages stay declared in `phrases.ts` — they are what the
  toolbox trains next — but nothing names them to a person until their model ships.
