# ADR-258 — Meeting recording and structured minutes

- **Status**: Accepted
- **Date**: 2026-09-02
- **Related**: ADR-080 (remote speech-to-text), ADR-129 (entity-as-job
  durability), ADR-185 (exact counts), ADR-226 (document generation),
  ADR-229 (capability map), ADR-244 (model capability catalogue),
  ADR-246 (native shells), ADR-254 (shock absorbers)

## Context

The owner asked for one gesture — the composer's « + » button, where a file
was already attached — that turns a phone or a computer into a meeting recorder, and for LIA to hand back the
minutes: date, times, place, participants, a relevant title, a summary,
one entry per topic, actions with owners and deadlines, risks, and to offer
them by email and as a PDF while feeding a knowledge space called « Réunions ».
Two constraints were explicit: **it must work as a PWA, cleanly and fluidly**,
and **the STRUCTURE of the minutes must be the user's** (a per-user template,
with a library announced for later).

Every hypothesis was measured before design (probes in the session
scratchpad, summarised in the design spec):

1. **The local engine truncated everything past ~30 s.** Sherpa-onnx
   Whisper-small INT8 decodes one 30-second window: a 45 s buffer came back as
   its first 30 s, silently. Voice input never noticed (a spoken command is
   short); a meeting is hours.
2. **Both remote engines accept a whole file in one request and separate
   speakers.** ElevenLabs Scribe returned `speaker_id` per word on a two-voice
   Ogg/Opus dialogue and still accepted a WebM truncated at 60 % of its bytes
   (7/7 long-audio runs). OpenAI `gpt-4o-transcribe-diarize` returned speaker
   segments, `gpt-4o-mini-transcribe` plain text, both within the 25 MB cap
   (7/7).
3. **Browsers do not agree on a recording format.** Safari produced MP4/AAC
   before 18.4 and home-screen PWAs had a `MediaRecorder` defect through 18.x;
   `AudioEncoder` (WebCodecs) exists only from Safari 26. Both mobile
   platforms mute a backgrounded microphone (WKWebView suspends capture,
   Android 9+ blocks it), and the Wake Lock API is the only lever that keeps
   the screen — hence the capture — alive.
4. **Production runs four uvicorn workers**, so an upload may land on any of
   them; appending to one shared file would interleave.
5. **The ElevenLabs key stored in the dev instance is a key ID, not a key**
   (`api_key_id_used_as_api_key`): a remote engine must classify that answer
   as a configuration fault, never as something to retry.

## Decision

### Capture in the browser, minutes on the server

The client records in **segments of `MEETINGS_SEGMENT_SECONDS`** and uploads
each one as a raw-body `PUT /meetings/{id}/segments/{sequence}`. Two sources
share one interface (`lib/meetings/audio-source.ts`):

- **Opus through `MediaRecorder`** with a timeslice, first choice where the
  engine is trustworthy — a minute of speech is ~240 kB;
- **raw 16 kHz int16 PCM through the AudioWorklet** the voice input already
  uses (one worklet source, `lib/audio/pcm-worklet.ts`, cached per chunk
  size), the fallback and the ONLY path on Apple devices.

The decision is a pure function of the environment
(`chooseMeetingAudioFormat`), fixed at start for the whole recording. Segments
are files on disk, one per sequence, written to a temporary name then
`os.replace`d: atomic under four workers, idempotent on re-upload, and gap
detection is a directory listing. A segment is ordered, retried with backoff
that **never gives up while the recording lasts**, and waits — not fails —
while the browser is offline. The stop declares the uploader's own count;
sequences the server never received are refused with `segments_missing` and
the user chooses: finalize with the gaps stated, or discard.

The recorder lives in the dashboard layout (`MeetingRecorderProvider`), so a
recording survives navigation; a fixed banner says what is happening on every
page and carries the recoveries. The silence watchdog asks « still
recording ? » once after `MEETINGS_SILENCE_PROMPT_MINUTES` of silence; the
maximum duration finalizes by itself. A reload comes back as `interrupted` and
the server's `GET /meetings/active` is the truth the store is reconciled
against — the user can resume (sequence continues), finalize or discard.

### The meeting row is the durable job

`meetings.status` carries `recording → stopped → processing → ready | failed`
(`interrupted` when no segment arrives for `MEETINGS_RECORDING_STALE_MINUTES`).
Every transition is one conditional UPDATE (ADR-129) — and every read that
follows one **expires the session first** (`MeetingService._fresh`), because a
bulk UPDATE leaves the identity map stale (measured 2026-09-03: a stop
answered `status: recording`); the segment ack reads its counters from
`RETURNING`. The claim takes a
lease, heartbeats renew it and publish the **stage** the page shows
(normalizing, transcribing, synthesizing, indexing), a lost heartbeat aborts
every later effect, and the reaper re-drives stopped orphans and expired
leases within a bounded attempt budget. Refusals that are not pipeline
failures — usage limit, no engine — release the job **without consuming an
attempt**.

### Engine chain, decided before the first second

`resolve_engine` reads the provider-key cache only: the admin
`voice_transcription` slot's provider when it has a key, then
`STT_PROVIDER_FALLBACK_ORDER` (ElevenLabs, OpenAI), then the local Whisper
engine when speech-to-text is enabled. The user's preference can force
`remote` or `local`; `auto` shows the engine and its price per audio hour
before recording. The local path is **unbounded**: the recording is decoded
in 600 s blocks and each block runs through **Silero VAD windows ≤ 20 s**
(`voice/stt/long_audio.py`, fixed windows when the VAD model is absent,
never truncation) — the same fix closes the 30 s defect for voice input. A remote failure is classified structurally (`PERMANENT_STT_CODES`: an invalid
key, a file over the cap). **The chain is walked again at processing time**
(`transcribe_with_fallback`): a permanent fault of ONE provider hands over to
the next engine within the user's preference — measured 2026-09-03, the dev
instance's ElevenLabs key ID would otherwise have dead-lettered every meeting
while an OpenAI key sat one step down the chain. Only a fault that says
something about the AUDIO (`no_speech`) or a transient one (rate limit,
timeout — the job's retry budget) stops the walk.

### Minutes are structured data with the user's template as contract

One structured-output call on the dedicated `meeting_synthesis` slot fills the
template (`meeting_synthesis_prompt.txt`); when the transcript overflows the
model's window it is condensed part by part first (`meeting_condense_prompt`).
The model answers a permissive shape and `repair_report` folds it into the
strict `MeetingReport`: sections the model skipped come back empty, invented
sections are dropped, a payload in the wrong shape for its kind is converted,
participants are restricted to speaker labels that actually spoke. The
transcript rests Fernet-encrypted; `report_generated` is immutable and
`report_current` is what the user edits — « restore » is a copy, « rebuild »
re-runs the synthesis on the stored transcript with the current template.

ONE serializer (`render.py`) produces the Markdown the knowledge space
indexes, the sectioned content the PDF renderer (ADR-226) turns into a file,
and the HTML body the email carries. The « Réunions » space is found by
**role** (`rag_spaces.kind = 'meetings'`, unique per user), created in the
user's language on first use, exempt from the per-user space cap, and each
meeting owns one RAG document rewritten in place on edit (the durable
reindex requeues it — nothing is deleted first) and deleted with the meeting
(chunks, row and file: the space is a projection of the minutes, never a copy
that outlives them — the third runtime proof found three orphaned projections
behind three deleted meetings).

### Published bounds, exact counts, one vocabulary

Every bound the server enforces travels in the start response (`limits`);
the list carries the exact total (ADR-185); the notification card, the list
and the minutes share the speaker labels `S1…Sn`, stable across providers.
`MEETINGS` is a platform capability (route-enforced, ADR-229 node, settings
section paired) and `meetings_enabled` an instance flag the composer and the
header read: « Meetings » is a dashboard destination between Relations and
Alerts, present only where the instance offers the feature. Seven labels cost
the header its slack, and the row paid on the controls side — the language
control shows its flag alone at every width, the personality title waits for
`2xl` — rather than on the destinations. The composer's control became a « + »
because it opens actions, of which a file is one; it is 44 px wide on a phone
and 40 px beyond, so the typing area keeps the width.

### Every paid unit is accounted, and shown

A meeting spends two priced units — audio at the transcription engine and
tokens at the synthesis model, the condense passes and every rebuild included.
Both reach the platform's books the way every other exchange does: the audio
through the remote-STT statistics, the tokens through `track_proactive_tokens`
under a `run_id` the archived chat message carries, so history queries join the
token log exactly as they do for any proactive notification. The meeting row
keeps the minutes' own spend (model, tokens, cost) so the page can state the
exact total, and the chat card states the two units and their sum whenever the
user displays costs. A model without an administered price yields `null`,
never a zero: an unknown price is not a free one (ADR-185).

## Consequences

- A meeting reaches its minutes whatever the browser, at PCM cost on Apple
  devices — a three-hour meeting is 345 MB of segments there, encoded to Opus
  server-side once, under the 25 MB remote cap.
- The local engine now transcribes any length; the trade-off is time (RTF
  ≈ 1.5 on the production board) and no speaker separation, both stated in
  the settings.
- A recording that dies with segments in flight loses those segments; the
  minutes say so (`audio_gaps`) and the model is told never to bridge a gap.
- Two prompts, one LLM slot, one Grafana dashboard (`27-meetings.json`) and
  seven metrics join the surfaces the ratchets guard.
- Deliberately NOT done: live streaming transcription (an hour of speech is
  one request, not a socket), a second sandbox or a second worklet, per-meeting
  template choice (the announced library — the schema already carries
  `template_snapshot` and `is_default` for it).

## Amendment 2026-09-05 — a meeting is never lost, its owner never blocked

A 33-second production meeting was transcribed, its synthesis failed, and the
row stayed `processing` for two hours, re-driven every fifteen minutes. Three
defects hid behind one symptom, and the amendment closes each with a rule:

- **Every transition persists, and is proven on a real database.** A bare enum
  member as a `case()` result is bound as `NullType`: the VALUE reaches a column
  that stores the NAME, `RETURNING` cannot read it back, the transaction rolls
  back. Literals carry the column's type, an AST guard refuses a bare `case()`
  under `src/`, and every repository transition now runs against PostgreSQL in
  `tests/integration/domains/meetings/`. The unit tests mocked the repository;
  the statement had never been executed.
- **The job resumes from what it acquired.** Each stage checkpoints its result
  on the claimed row inside the lease-renewal statement (normalized audio, then
  the encrypted transcript with its `stt_*` facts); a claim reads the
  checkpoints before spending anything again, and a meeting with no audio
  anywhere is dead-lettered as `audio_unavailable` instead of burning its retry
  budget on ffmpeg. Retention purges the audio of `ready` meetings only: a
  `failed` meeting keeps its audio until its owner deletes it — the retry needs
  it.
- **Nobody is blocked on a dead worker.** A `processing` row under no live
  lease is requeued by the reaper, or dead-lettered as `worker_lost` when its
  budget is spent, and can be deleted meanwhile (`delete_unless_leased`, the
  database clock decides). The detail publishes `attempts`, `max_attempts` and
  `worker_stale`; the page shows the attempt of the budget, the previous
  attempt's reason, and a delete when the worker is gone.
- **A valid answer is never thrown away.** The trigger was a model writing
  `null` on a defaulted list; the model-facing shapes accept it, the native
  structured-output path defaults nulls generically before giving up on a tool
  call (`llm/tool_call_rescue.py`), reads the `parsing_error` it discarded and
  names the real reason. A background task that fails now logs its traceback.

## Verification

`tests/unit/domains/meetings/` (models, templates and i18n parity, audio
store, engine resolution and exclusion walk, service guards, reapers,
transcription and its fallback, synthesis repair and condensation, render,
enrichment, indexing, delivery, the job's failure classification and the
regeneration), `tests/unit/domains/voice/` (VAD windowing, long-audio routing,
both file transcribers under `httpx.MockTransport`), the frontend suites under
`lib/meetings/__tests__/` (silence watchdog, uploader order/retry/offline and
its settled count after a fatal refusal, format choice, template keys, the
whole recorder lifecycle under fakes including the server-side cap and the
cross-device resume) and the component tests of the banner, the composer
entry, the provider's coarse context, the editors, the read-only minutes
view, the settings section, the list and detail pages and the minutes card.

The 2026-09-05 amendment adds `tests/integration/domains/meetings/test_repository_jobs.py`
(every transition on real PostgreSQL, the incident replayed), the resume suite
(`test_processing_resume.py`), the statement-level binds (`test_repository_statements.py`),
the AST guard, the null-tolerance and tool-call rescue suites, and the processing
panel's attempt/stale states in the frontend.

The feature was then driven end to end against the dev containers through its
HTTP contract (design spec §8.1): PCM and Opus sources, the OpenAI engine
reached by fallback from a refused ElevenLabs key and the local engine, down to
the indexed document, the PDF, the edit/reset/regenerate cycle and the delete.
Three defects invisible to the unit suites came out of it — the stale
identity-map read, the missing processing-time fallback, the zero cost for an
unpriced model — and are fixed with a test each. Live probes against both
remote providers and the local engine are recorded in the same spec.
