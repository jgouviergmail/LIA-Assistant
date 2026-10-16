# ADR-345 — Fish Audio, served whole: one synthesis door, one allowance per account, cues each engine reads

- **Status**: Accepted
- **Date**: 2026-10-14
- **Amends**: ADR-080 (the remote dictation engine is the slot's, no longer
  ElevenLabs by construction), ADR-081 (a TTS slot names a fifth provider and
  its own tuning), ADR-082 (the streamer's cost callback is gone, and so are the
  uncalled non-streaming comment and its metric), ADR-184 (every
  bound the voice library enforces is published), ADR-244 (a vendor's announced
  retirement is a catalogue fact the speaking path reads), ADR-258 (the meeting
  engine chain gains a third remote engine and a per-request duration cap),
  ADR-260 (three key families), ADR-272 (a flat-priced act reaches the instance's
  ledger), ADR-304 (no session is held while the vendor answers, the voice admin
  routes included), ADR-317 (a vendor's refusal travels by its facts, in every
  voice client), ADR-324 (the radio voices a dialogue take and one cue per line;
  its voice catalogue and language rule become the voice domain's), ADR-326 (the
  cue grammars are linear flatteners)
- **Scope**: `domains/voice/` — `fishaudio/` (client, socket, dialogue, voices,
  library, design store, library service, errors, schemas), `spoken.py`,
  `provider_capacity.py`, `families.py`, `factory.py`, `expressive_cues.py`,
  `cue_prompt.py`, `egress.py`, `library_router.py`, `stt/fishaudio_stt.py`,
  `stt/factory.py`, `vendor_refusal.py` and the clients that read it
  (`stt/elevenlabs_stt.py`, `stt/openai_stt.py`, `elevenlabs_tts_client.py`,
  `openai_tts_client.py`, `gemini_tts_client.py`, `voices_catalog.py`), the
  voice comment (`service.py`, `metrics_voice.py`, dashboard 11); the shared
  pins and the person's voices (`engine_voices.py`, `fishaudio/pins.py`,
  `fishaudio/models.py`, `lia_voices.py`, `lia_voices_router.py`,
  `admin_router.py`, `schemas.py`, `users/voice_preferences_columns.py`);
  `core/remote_stt.py`; the meetings' engine and
  transcription; the radio's takes, audio plan, delivery and production; the
  instance ledger (`usage_limits/instance_spend.py`); migrations `cec87eda4868`,
  `a9326a120b55`, `8ba7655b548b` and `4c2e8a6f1d3b` and the seed bundle; the
  admin voice slot form, the voice library section and the voice mode settings;
  six locales

## Context

The owner asked, on 2026-10-13, for Fish Audio — an instance key — to join the
speech providers with `s2.1-pro` and `s2.1-pro-free`, « integrated exactly like
the other TTS providers ». The scope was then widened, not reduced (owner,
2026-10-14): Fish Audio's speech-to-text (`transcribe-1`, `transcribe-1-pro`),
voice cloning and voice design, its real-time WebSocket, multi-voice dialogue,
the models `s1`, `s2-pro` and `drama-3`, and expressive cues written by LIA for
every engine that performs them, with a vocabulary per provider and model.
Offered voices: the vendor's licensed ones and the account's own. Fish Audio's
agents are left for later. No paid request was to be run (owner decision), so
every live measurement below is on `s2.1-pro-free`.

Integrating a fifth engine « like the others » exposed that the others were not
alike:

- each speaking surface recorded its own spend, and a surface whose configured
  engine could not be served spoke through Edge while recording the configured
  engine's tariff — a cost for a voice nobody paid for;
- the voice mode's remote dictation was ElevenLabs whatever the
  `voice_transcription` slot named: the factory read the slot's model and
  ignored its provider, « remote available » meant « an ElevenLabs key exists »,
  and the privacy notice named ElevenLabs whatever engine received the audio;
- only ElevenLabs had an allowance pool, so nothing kept a burst of radio lines
  from taking every slot of a vendor account a dictation needed;
- a bracketed word in a read answer became a cue on an engine that reads tags,
  while nothing wrote a cue on purpose.

What the vendor does was measured before the design was fixed, or read from its
documentation (dates 2026-10-13 and 2026-10-14):

| Fact | Source |
|---|---|
| A missing or unknown `model` header is served AND billed as the vendor's default model | measured |
| Synthesis is billed per UTF-8 BYTE of the text (a Chinese character is three) | pricing page |
| One account holds `ratelimit-limit-concurrency: 5` requests in flight, synthesis, transcription and design together; a 429 carries no `Retry-After` | measured |
| A refusal is `{status, message}` with, on some, an `x-fish-error-code` header; the message may quote the request | measured |
| The WebSocket (`/v1/tts/live`, msgpack) connects in 0.6-1.3 s and streams: the first audio frame comes 0.6-1.0 s after the text whatever its length (135-1631 bytes), then one at least every 1.7 s; a sentence returned whole finishes no sooner than over HTTP on the free model | measured |
| Several voices in one request (`<|speaker:N|>` + a list of references); the timestamped stream aligns every word, so each turn can be placed | measured |
| `s1` retires on 2026-12-31 and is served as `s2.1-pro` afterwards, where its parenthesised cues are read as text | deprecations page |
| `s2.1-pro-free` costs nothing « through November 30, 2026 » | changelog |
| The licensed library holds 113 voices, one language each; the public library is mostly unlicensed clones | measured |
| `/v1/asr` refuses raw PCM, bills the duration rounded up to the second, takes up to 60 minutes; its pro model writes speaker markers inside its text | documentation |
| Voice design answers 1 to 4 base64 WAV candidates and is billed once per SUCCESSFUL request; creating a voice model has no published price | documentation |

## Decision

1. **One provider vocabulary.** `fishaudio` joins the seven hand-maintained
   provider lists, held equal by the parity guard, and the database enum
   (`cec87eda4868`). Its key is the instance's, like every speech engine's.

2. **One door per voice act, billed as the engine that spoke bills.** A heard
   synthesis goes through `voice/spoken.speak` (a dialogue through
   `speak_dialogue`): recorded ONCE, only when served, in the billing unit of the
   engine that actually spoke — characters, UTF-8 bytes, or the tokens a vendor
   reports (`families.TtsBilling`, `billed_text_units`). Edge standing in for an
   unservable engine speaks with its own voices and costs nothing. The streamer's
   per-sentence callback (ADR-082) is gone: the synth it is handed records itself.

3. **One allowance per vendor account.** `provider_capacity.provider_slot` takes
   a Redis lease per in-flight request, keyed by the account's key digest
   (`fishaudio:capacity`, `FISHAUDIO_MAX_CONCURRENCY`), for EVERY request of that
   account — synthesis, transcription, design, the voice listing. The wait for a
   slot and the request share one bound, so a lease always outlives what it covers.

4. **The client names its model and reads a refusal by its facts.** HTTP
   `/v1/tts` by default; a slot may choose the WebSocket (`provider_config.
   transport`): one session per synthesis, falling back to HTTP on a transient
   failure — never on a rate limit, which a replay would only deepen. Silence is
   one: a session that answers nothing for `FISHAUDIO_SOCKET_STALL_SECONDS`, six
   times the longest gap a healthy one left between two frames, has stalled; its
   finish disarms the silence bound. If the whole-request deadline expires
   during the subsequent close, the completed audio is retained and that cleanup
   timeout is logged; it never buys a second synthesis. Explicit cancellation
   still cancels the call without an HTTP replay. A refusal is
   its status and its bounded vendor code; its message never travels (ADR-317).

5. **The catalogue states the vendor's facts, and the speaking path reads them.**
   Five speech and two transcription models travel by migration `a9326a120b55`
   AND by seed, held equal by a guard; synthesis rows count bytes. `s1`'s
   announced retirement is a catalogue date and a `VENDOR_SHUTDOWNS` entry: past
   it, LIA writes for the engine that will actually speak. The free model's
   window is a PRICE, not a retirement, and is stored as none.

6. **The voices offered are the account's own, the attested pins, the licensed
   ones** (amended 2026-10-14). An administrator pins a public voice by id after
   attesting the right to use it — ONE list for every voice slot (decision 14);
   a voice that cannot speak, or that the vendor took down, is not offered. The
   merged list is cached per account and pin set (`fishaudio:voices`), and
   forgotten when the library changes.

7. **One cue vocabulary, a dialect per engine, and cues only where LIA writes for
   speech.** `expressive_cues.Cue` is canonical; each engine declares the
   spellings it performs (`CueDialect`: ElevenLabs v3/v4 tags, Fish S2 `[…]`, `s1`
   parentheses, `drama-3` brackets and paired `<…>`, Gemini's point-in-time
   events) and the syntax it reads is DERIVED from them. LIA writes cues only in
   text written to be spoken — the voice comment, under one budget
   (`VOICE_EXPRESSIVE_CUES_MAX`), and one cue per radio line from its tone, else
   its energy —
   while literal text (a read answer, a readout, a quoted headline) is
   neutralised for the engine that will speak it. A `<|speaker:N|>` marker is
   removed from every text: in a third party's words it would make another voice
   speak.

8. **A dialogue is one request, placed exactly or not at all.** On the engines
   that voice several speakers (`families.voices_dialogue`), the radio voices a
   take — consecutive lines of one programme part, under the same controls,
   bounded by `RADIO_DIALOGUE_MAX_BYTES` — through the timestamped stream, which
   places each turn by its letters and digits. A take the stream cannot place, or
   that fails, is voiced line by line; the mixer cuts each line out of the take
   with no pause inside it. Counted (`radio_dialogue_takes_total`).

9. **The remote dictation engine is the slot's, decided once.** `core/
   remote_stt.py` reads the `voice_transcription` slot (who receives the audio),
   the provider's own switch and its key, for the dictation socket, the voice
   preference and the meetings alike; the cost is filed under that provider.
   `FishAudioSttService` wraps PCM in WAV, sends the pro model's fields to it
   alone, keeps the words without the speaker markers and reports the billed
   duration. A meeting on Fish Audio always runs `transcribe-1-pro`, and a
   recording longer than one request takes moves to the next engine BEFORE the
   upload (`REMOTE_STT_MAX_AUDIO_SECONDS`). The voice settings name the engine,
   so the privacy notice says who receives the audio.

10. **The voice library is the administrators', and each act owes something.**
    `/admin/voice/fishaudio/library` lists the account's voices — every state, so
    a failed one can be deleted — and the slots speaking with each. A CLONE needs
    the administrator's attestation that the voice is theirs or that its owner
    consented in writing; the attestation is filed in the admin audit log BEFORE
    the vendor is called (no record, no clone), the voice is private, the
    recordings leave under neutral names and within one bounded body. A DESIGN is
    paid by the instance: its daily ceiling is asked first, its flat price
    (`FISHAUDIO_VOICE_DESIGN_COST_USD`) charged after a success
    (`record_instance_fixed_spend`) and filed under the administrator; its
    candidates wait server-side (`fishaudio:design`), so a save uploads the audio
    the vendor designed. A voice a TTS slot speaks with is never deleted (409
    naming the slots). Creating is the operator's switch
    (`FISHAUDIO_VOICE_CREATION_ENABLED`, off on the demonstrator); renaming and
    deleting stay open. Every route authenticates on a session of its own and
    holds none while the vendor answers (ADR-304).

11. **Every voice client refuses by its facts** (amended 2026-10-14). The rule
    Fish Audio's wire followed is now the domain's, in `vendor_refusal.py`: a
    refusal is its HTTP status and the vendor's code when that code is a bounded
    identifier (`details = {status_code, vendor_code}`), read where each vendor
    documents it (`detail.code` then the legacy `detail.status` for ElevenLabs,
    `error.code` for OpenAI), and logged by those facts at the refusal. The
    ElevenLabs and OpenAI transcription clients carried up to 512 characters of
    the body, the ElevenLabs speech client and voice listing 200 in their
    messages — and a FastAPI-style 422 echoes the field it refused, the line
    being voiced included. An answer LIA cannot read travels by its keys
    (`payload_shape`): a transcription is the person's words. A refused key is
    read from the structure — a vendor code naming the key, or a 401 naming no
    other cause (the vendor answers `quota_exceeded` with 400 or 401 too) — on
    both ElevenLabs transcription paths, where the live dictation used to answer
    an unclassified HTTP error. The OpenAI speech client reads the SDK's exception
    TYPE, never its message (`Error code: <status> - <body>`): read for words,
    a message holding « generate » was a rate limit, a timeout an HTTP error, a
    refused key « no key configured ». `Retry-After` has one reader
    (`retry_after_of`). `test_vendor_body_excerpt_guard.py` refuses a slice of a
    response body in any module of `src` that imports an HTTP client, DEBUG
    lines excepted, and counts the debt left outside the voice domain.

12. **The spoken comment has one path and no metric of its own** (amended
    2026-10-14). `generate_voice_comment`, the non-streaming twin ADR-082 left
    behind, had no caller, and it was the only producer of
    `voice_comment_tokens_total`: dashboard 11 charted a series nothing could
    write. Both are deleted; the panel reads
    `llm_tokens_consumed_total{node_name="voice_comment"}`, which the
    streamed comment feeds like every model call.

13. **One catalogue and one language rule for every voice picker** (amended
    2026-10-14). The engine's catalogue — a shipped list, or the vendor account's
    live one — and the rule that orders or narrows it for a person's language
    moved from the radio to `voice/engine_voices.py`, read by the radio's roles
    and the person's voices alike: on a multilingual engine every voice, those
    native to the person's language first, then those naming none; on an engine
    with one language per voice, the person's language alone, or every voice
    when it has none. Every picker — the administrator's slots, which list the
    whole catalogue, included — offers the switch « only voices in <language>,
    and multilingual ones » (`VoiceLanguageFilter`) where it narrows the list —
    on by default, never hiding a voice the form holds.

14. **The public voices are pinned once, for every voice slot** (amended
    2026-10-14). A voice pinned for the chat was not offered to the radio: the
    pins lived in each slot's tuning. They are now ONE list
    (`fishaudio_pinned_voices`, migration `8ba7655b548b`, which moved both slots'
    pins — the chat's first, each once, within the ceiling — under the
    administrator who last saved the slot, and removed the key). A pin is an act
    of its own, immediate, never part of a slot's save:
    `PUT /admin/voice/fishaudio/library/pins/{voice_id}` reads the voice, files the
    attestation in the admin audit log BEFORE the pin is stored (no record, no
    pin), then `fishaudio_voice_pinned`; the published ceiling is held under an
    instance-wide advisory lock (`owner_lock.INSTANCE_OWNER`). `DELETE` refuses
    while a slot speaks with the voice, like the library's delete. Each route
    publishes the list and its ceiling, which the form never mirrors; the
    listing reads the shared list (its `pinned` parameter is gone). On the way,
    the voice admin routes stopped holding a request session across the vendor's
    listing (ADR-304): each authenticates on a session of its own.

15. **LIA's voices are the person's choice, per engine** (amended 2026-10-14). In
    the voice mode settings a person chooses LIA's male and female voice among
    the voices of the engine that speaks in the chat — the `voice_tts` slot's, or
    Edge's when it cannot be served (`factory.served_config`). The choice is kept
    PER PROVIDER since 2026-10-16 (`users.lia_voices`, migration `4c2e8a6f1d3b`,
    `{provider: {male, female}}`, the column's comment by `1ed6c591761a`): every
    model of a provider offers the same voices, and kept per `provider/model` a
    model change gave the person the instance's voices back (ADR-324 decision 43
    found it on the radio). An entry an older release kept per model is still
    read (`engine_voices.stored_choice`) and replaced by the provider's save, in
    its one statement. Written strictly (a voice the engine
    does not offer in the person's language is refused, `lia_voice_unknown`,
    a catalogue unavailable at write time refuses a selection with
    `503 lia_voice_catalogue_unavailable`; returning to defaults remains
    available), read forgivingly (a voice no
    longer offered speaks with the administrator's; an unlistable engine keeps
    the choice), and stored by one atomic JSONB statement. It is read at the one
    seam every chat surface speaks through
    (`VoiceCommentService._get_voice_for_language`) — voice comments, progressive
    stream, read-aloud — once per language and service, and only for a person
    who chose; never by the radio, a live session or a phone call. There it is
    checked against the catalogue known WITHOUT asking the vendor
    (`engine_voices.known_engine`: a shipped list, or a cache): a cold Fish Audio
    listing took 6.8 to 10.4 s on dev, so a catalogue not cached yet keeps the
    choice rather than delaying the first sentence. Deleting a voice from the
    library gives every person who chose it the instance's voice back
    (`lia_voices.forget_voice`) — the one way a voice disappears that LIA
    performs itself. The ElevenLabs list a person is offered or checked against
    is cached like Fish Audio's (`elevenlabs:voices`, ten minutes); the
    administrator's picker reads it live.
    The column is exported with the account while it lives and erased when it is
    deleted (owner decision 2026-10-14): a setting that serves nothing once the
    account is gone — the first `SCRUBBED_PREFERENCE` of the `users` column map
    (ADR-067), set to None by `_mark_user_deleted`. A None reaches it as SQL NULL
    (`JSONB(none_as_null=True)`), never as the JSON `null` the atomic merge
    would turn into an array.
    A catalogue wait cannot resurrect an erased preference: the atomic update
    also requires an active, undeleted owner and refuses with 403 when no row
    qualifies. Successive browser choices are serialized per account lifetime;
    an account change cancels the queued writes and discards late replies.
    Fish Audio library deletion also fences a catalogue already returned to a
    caller. A singleton `fishaudio_catalogue_revisions` row (migration
    `7f428c3e0a19`) stores an opaque UUID revision and pending deletion tokens
    keyed by vendor voice id, never credentials or recordings.
    The instance catalogue lock protects the initial absence too. Deletion
    advances that revision and forgets personal choices in the same transaction;
    the final choice write compares the revision captured before listing.
    Its cache key includes that revision, so a listing returning after deletion
    cannot refill the current catalogue. Fresh choices remain possible after
    deletion; resetting to defaults requires no catalogue revision.
    The library reads committed TTS slot references in one query, never a
    worker's possibly stale cache. Deletion reserves the voice under the same
    instance lock as slot writes, then returns its SQL connection before the
    vendor wait. Slot saves validate their catalogue and compare its revision
    at the final write; unpinning checks references and changes the revision
    under that lock too. A cancellation or uncertain dispatched failure keeps
    its reservation; an explicit deletion retry can confirm absence (404) and
    finish local cleanup. Only the current operation token can release it.
    A refusal before dispatch releases a fresh reservation. Personal choices
    are forgotten in one correlated SQL update, preserving concurrent writes
    to other engines. These transitions are tested on disposable PostgreSQL.

## Consequences

- A new speech engine is a family, a client, a capacity pool, a dialect when it
  reads cues, and catalogue rows by seed and migration — the five places the
  guards hold equal.
- A sentence heard is billed once, by the engine that spoke it; nothing is
  billed for a voice that was not served.
- The remote dictation, the voice preference and the meetings cannot disagree on
  which engine receives the audio: one function answers.
- A request the vendor would refuse after a full upload is refused before it
  (a meeting past 60 minutes, a clone past the body ceiling), and every refusal
  reaches the administrator as a translated sentence named by a stable code.
- The global request-body ceiling must carry a clone: `Settings` refuses to boot
  when it cannot.
- A public voice pinned for one voice slot is offered to every slot; unpinning
  never takes a voice from a slot that speaks with it.
- A person's voice follows the engine it was chosen on: the administrator may
  switch engines, and switching back finds the person's voices again.

## Measured

On `s2.1-pro-free`, through the real client, 2026-10-13 and 2026-10-14:

- HTTP: 1.59-1.65 s per sentence; WebSocket: 2.62-2.74 s. HTTP stays the default.
- The socket streams: on 135, 407, 815 and 1631 bytes the first audio frame came
  0.6-1.0 s after the text and no two frames were more than 1.7 s apart, while
  HTTP answered the whole text in 3.9 s to 40.2 s. Before the silence bound,
  nothing shorter than the request's own 60 s ended a silent session, and on Docker
  dev three socket syntheses of one chat turn returned nothing for 22 s until the
  turn's voice wait ran out (the stage they waited in was not logged): the bound
  comes from that.
- A dialogue take of three lines in two voices placed exactly, billed by the bytes
  of the text sent, markers included; the mix lasted the take plus its edges.
- French and Chinese timestamped streams: every turn placed by letters and digits.
- The voice clients' refusals, 2026-10-14: the excerpt guard reads eight slices
  of a vendor body in the voice clients as they stood before the change, none
  after. Through the real OpenAI SDK (2.54.0) over a mock transport, a 400 whose
  message holds « generate » was filed as a rate limit, a read timeout as an
  HTTP error and a 401 as a missing key; each is now read from its type.
- Cues in brackets performed on the S2 models.
- The shared pins, 2026-10-14, on a real PostgreSQL: two pins racing for the last
  slot both landed, and two pins of one voice raised a unique violation, with
  the lock removed; with it, one lands and one is refused, and one voice is one
  row. The migration was run both ways and back on the test's connection. Two
  saves of the person's voices for two engines, racing, both land.
- A person's voices, 2026-10-14, on a real PostgreSQL: forgetting their last
  voice and deleting their account each left the JSON `null` in the column, not
  SQL NULL — on which the next save built `[null, {...}]`, read as no choice,
  and the removal of an engine failed (« cannot delete from scalar »). The
  column now maps None to SQL NULL; both tests pass.
- A cached voice list holding a JSON object, not a list, read as « no voice » for
  the cache's lifetime: it now reads as no cache.
- The person's voices on Docker dev, 2026-10-14, the proof account on
  `s2.1-pro-free` (free): the settings listed 129 voices, those of the account's
  language first and the administrator's named; an unknown voice was refused
  (422) with nothing stored; a pinned public voice was kept for the engine; a
  read-aloud through the real route was spoken in it (the audio counter of that
  voice went from 0 to 239,931 bytes); the choice was then given back. Of five
  cold Fish Audio listings outside the API, four succeeded (6.8, 9.2 and 10.4 s
  for the three timed) and one failed past a request's 15 s bound; inside the
  API, the listings of the first two proof runs failed the same way, one of them
  under a radio session's load: the speaking path never lists.

## Not measured

- The paid models (`s2.1-pro`, `s2-pro`, `drama-3`, `s1`): owner decision. The
  client names the model on every request, so each is billed as itself.
- Transcription (`transcribe-1`, `transcribe-1-pro`): paid.
- Cloning and design on a real account: the test account has no credit, and a
  clone needs a voice its owner consented to; both are covered by tests on the
  vendor's documented shapes.
- The design-to-model signature (`voice_design_signatures`): the candidate's
  documented schema carries none, so none is sent — a designed voice is saved as
  an uploaded one.

## Rejected

- **The WebSocket by default**: measured slower on the free model.
- **`drama-3` directed in words**: unmeasurable, and the direction could be read
  aloud on air.
- **A « per request » unit in the tariff table for the design**: an enum, a
  workbook and a form changed for one flat price — a setting says it.
- **Public voices offered without an attestation**: the public library is mostly
  clones nobody licensed.
- **Guessing the signature's field name**: an invented field is a request the
  vendor may refuse, or worse, accept with another meaning.
- **Pins kept per slot**: a voice an administrator attested for the chat would
  have to be attested again for the radio, and the two lists drift.
- **Checking a person's voice against a live listing before LIA speaks**: first
  written so, until a cold Fish Audio listing was measured at 6.8 to 10.4 s — the
  turn would have waited that long before its first sentence. The check reads
  what is known without the vendor, and only for a person who chose.
- **Refusing to unpin a voice a person chose**: a person's choice reads
  forgivingly, so the administrator's voice speaks instead — refusing would let
  any account block the instance's list.
- **Keeping a person's voices on the anonymised row**: first classified so, as
  an ADR-067 preference; they serve nothing once the account is gone. Leaving
  them out of the export with the scrubbed secrets was rejected too: they are
  the person's setting like every other one the export carries.
- **The vendor's own transcription as the clone form's prefill**: it already
  transcribes when no text is given; the local engine is free, and its words can
  be checked before they are sent.

## Amendment 2026-10-15 — current administrative authority before mutation

The HTTP dependency's administrator snapshot does not admit a mutation after a
later vendor read, candidate lookup, budget check or catalogue-lock wait. Voice
library writes re-read the active, non-deleted administrator from PostgreSQL.
The shared `lock_current_admin` holds that user's row through the local intent
or write transaction. Catalogue operations take the catalogue lock before the
user lock; pin-list writers then take their instance lock.

Clone and pin attestations authorize and commit before dispatch or storage. A
lost privilege remains a 403, rather than being relabelled as an audit outage.
Design, save and rename authorize immediately before the external mutation;
delete authorizes after its catalogue wait and before reserving removal. Pin
and unpin also hold current authority through their database write.

Every SQL context closes before a vendor call. This defines admission, not a
promise to cancel a remote operation already admitted. After an effect, audit
completion and cleanup continue to report the facts; revocation must not turn
an action that happened into a claimed refusal.

Disposable PostgreSQL tests revoke the role, deactivate the account or mark it
deleted across those waits, and verify no subsequent mutation. Positive tests
observe pool checkout/checkin and one simulated vendor dispatch. Distinct
administrators race for the final pin slot and the same voice, so a per-user
row lock cannot conceal a missing instance lock. These tests make no paid
vendor call and do not qualify the vendor's live service.

## Amendment 2026-10-15 — one save per designed preview

Saving a preview claims its Redis record atomically before the current-role
check and vendor dispatch. The ownership token and audio share ONE key and its
original expiry. Losing or evicting that key cannot leave reusable audio behind
a vanished lock. Ordinary preview reads do not expose a claimed record.

Only a failure before dispatch or a vendor refusal known to have caused no
effect restores the preview, with a token comparison. After success the same
comparison removes it. Cancellation after dispatch, a lost vendor response or
failed cleanup leaves it claimed until its original expiry: a second request
receives a conflict and must check the library. Missing previews also direct
the administrator to check the library before generating another. No automatic
vendor retry or promise of exactly-once remote execution is made.

Real Redis regressions race distinct administrators, lose a cleanup or claim
acknowledgement, cancel before and after dispatch, preserve the original TTL,
evict the record and fence stale ownership tokens. Vendor effects are simulated;
the existing PostgreSQL tests independently exercise current-role admission.

## Amendment 2026-10-15 — credential-bound catalogue and previews

A catalogue revision alone does not identify the vendor account: a worker may
still cache account A's key after another worker commits account B's. Live
catalogue reads now capture the actual key once, before their waits, and carry
an internal fingerprint of that key. Personal choices for account-dependent
catalogues, and Fish Audio TTS configuration writes, compare it with fresh SQL
before writing. The shared provider-row lock lasts through that local write,
so a concurrent key update or deletion waits. Missing or unreadable credentials
cannot authorize a selection; returning to default voices remains available.

The library applies the same comparison at administrative admission, after its
budget, candidate or catalogue waits, and through a pin's local write. A preview
also retains the fingerprint of the account which generated its audio: changing
the instance key cannot upload that audio to a different account. Old previews
without this identity are unavailable. Fingerprints remain internal, with no
credential in API responses, audit details or public logs. They add no setting,
environment variable or schema migration.

This fences admission and local writes; it does not cancel a remote operation
already admitted. SQL connections close before provider I/O. Disposable database
tests rotate and remove keys, retain a stale worker cache, reload that cache
during a catalogue response, and observe PostgreSQL actually blocking a rotation
until the validated transaction commits. Redis tests refuse a preview under a
different account without uploading its audio. No paid provider call is made.
