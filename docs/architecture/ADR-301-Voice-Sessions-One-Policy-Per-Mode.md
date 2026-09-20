# ADR-301 — Voice sessions: one policy per mode, whichever the line

**Date**: 2026-09-20
**Status**: Accepted
**Amends**: ADR-290 (the owner call gains a LIVE mode — the browser's live session on the phone line — and its direct mode keeps the relay), ADR-299 (a DIRECT browser session is no longer « nothing recorded »: it is relayed at its end, like the phone; the bounded context of voice sessions is shared with the phone), ADR-300 (the delegation block of the mandates and the bridge lines are the voice sessions' own, rendered per carrier), ADR-272 (every euro of a voice session — a delegated turn, the relay synthesis, the tool host, the learning — lands under a run id the carrier owns and the account's ceilings see), ADR-263 (a phone Live call and a browser session are each one decision row of their own route, every delegated turn its own), ADR-185 (the card's figures stay the server's and are RE-READ when a fate changes), ADR-184 (Live is offered only where the vendor can call back; the effective mode is published)

## Context

The phone as a channel (ADR-290) let LIA call the account holder and relay
the conversation into the chat **at its end**: the voice read the person's
data itself (lot 7, live tools) and a synthesis turned the transcript into
the message they would have typed. The browser's live mode (ADR-299) did the
opposite: **every request went through the chat while the person spoke**,
with HITL, the registers and the archive — and its later DIRECT mode
(ADR-300 wave 4) read the tools itself and recorded nothing at all.

Three surfaces, three closings, and code written three times: a learning
pass in `live/learning.py`, summary queries in `live/summary.py`, a relay in
`telephony/self_call_relay.py`, a delegation bridge in
`lib/live/delegation.ts`, a delegation block in each mandate. The owner asked
for one thing (2026-09-20): « un choix Live / Live direct dans Réglages ›
Téléphonie · Mon identité ; en Live le téléphone fait comme le Live du
navigateur, avec les actions directes dans la discussion courante ; symétrie
parfaite entre les canaux ; généraliser et mutualiser le code ». And a
corollary the analysis made explicit: a browser DIRECT session must then be
relayed at its end too, or « direct » would mean two different things on two
lines.

Everything below was decided against measurements, never against the
documentation alone (spec `docs/superpowers/specs/2026-09-20-voice-sessions-symmetry-design.md`,
§10 for the vendor, §3.5–3.6 for the runtime proofs).

## Decisions

### 1. A voice session has a MODE and a CARRIER, and the policy follows the mode alone

`domains/voice_sessions/session.py` names the value: `VoiceSession(carrier,
key, run_id, origin_id, mode, user_id, conversation_id, language, timezone)`.
The **key** is what every row of the session carries in `live_session_id` —
a browser session's id, a phone call's run id (`phone_call_<hex>`, minted
HERE so `telephony` reads it from this package and never the reverse). The
**mode** is `delegated` (the person's requests go to the chat as they are
said) or `direct` (the voice reads for the person and the words are relayed
at the end); the UI says « Live » / « Live direct ».

**One closing** (`infrastructure/scheduler/voice_session_closing.close_voice_session`),
called by the browser's `POST /live/sessions/{id}/end` AND the phone's
post-call webhook: delegated → the voice-only exchanges are archived (the
phone hands its transcript; the browser archived turn by turn), the card with
the EXACT figures, the decision row, the learning of the voice-only rows;
direct → the transcript becomes the person's own turn (the relay synthesis,
then `run_voice_relay` in a task the closing owns), the card says the fate
and is rewritten when the turn settles. The carriers keep what is theirs —
the Redis record, the `phone_calls` row, their own metrics, their own
outbox and push — and call the door.

### 2. What the two lines share moved OUT of both

- **Values and queries** in `domains/voice_sessions/`: the session, the
  transcript (`from_vendor_payload` with the delegated exchanges MARKED,
  `from_rows`, `voice_only_exchanges` grouped as the browser buffers), the
  projection (`flatten_for_voice`, `bound_to_tokens` — pinned to
  `lib/live/delegation.ts` by ONE corpus run by pytest and vitest), the
  summary queries (`session_run_ids`, `session_run_ids_by_key` for a page,
  `count_voice_turns`, `aggregate_usage`, the card's Markdown), the mandate
  blocks (`voice_delegation_block.txt`, `bridge_lines()`, `tone_lines()`).
  The package imports no carrier; the HTML flattener it needs is HANDED IN
  (a port — `agents` reads this package and must not be read back).
- **Runners** in `infrastructure/scheduler/`, beside the workboard and
  phone-relay runners and for the reason they are there: `voice_session_closing`
  (archives, records, learns — `agents`, which `telephony` must not import),
  `voice_relay` (the synthesis and the relayed turn, moved byte for byte from
  `self_call_relay` — a golden file proved the move and now pins the
  contract, the context's `SESSION:` line included), `voice_delegation` (the
  phone's bridge, below). `live/summary.py`, `live/learning.py` and
  `telephony/self_call_relay.py` are gone.

### 3. The phone's Live mode is the browser's delegation, server-side

The voice on the phone holds no context and no lookup (owner decision D5,
strict symmetry: a Live voice is offered no read tool). One asynchronous
vendor webhook tool, `send_to_lia` — the browser's own name, description
and schema — and `infrastructure/scheduler/voice_delegation.delegate`
mirrors `lib/live/delegation.ts` rule for rule, each a test: an empty
request costs nothing; **the newest request wins** (a Redis marker,
`voice_delegation:newest`, USER_RUNTIME, polled by the running bridge, which
cancels its own turn — two vendor webhooks may land on two workers, so the
marker cannot be in memory; proven on real Redis with two tasks); **a
question LIA asked IS the result** and the next request RESUMES the run that
asked (`original_run_id`, reused for the accounting, the chat router's own
resumption); **the turn is the person's** (`spoken_by_person`, their
execution mode, their flags, the extractions, no plan pre-approved, no
out-of-turn origin — an ordinary chat turn); **a wait past the vendor's bound
leaves the turn running** in the thread and the voice says so; **nothing
reaches the voice as an exception** (`busy`, `quota_blocked`, `failed`,
`budget_exhausted` are lines of `live_lines.txt`, technical English, the
model speaks the person's language). The engine (`out_of_turn_run`) gained
`original_run_id`, `live_session_id`, `spoken_text` and reads the answer's
register off the `done` chunk — the delivery note (ADR-253) travels beside
the result exactly as on the browser.

**Measured on the vendor's real engine** (lot 0 on a temporary agent, lot 4
on the production mandate and tool through a tunnel): `execution_mode:
async` + `pre_tool_speech: force` lets the voice announce the call and keep
talking; past `response_timeout_secs` the vendor hands the model an
`is_error` result and the LATE answer is lost — so the bridge answers
`timed_out` the inner margin BEFORE it (`TELEPHONY_DELEGATION_TIMEOUT_SECONDS`,
90 s, bounded 20..290); the transcript writes an async call as an EMPTY agent
entry with `tool_calls`, its acknowledgement as another, then a second pair
and the restitution — so a delegated exchange is marked WHOLE, from the
person's request to the restitution, exactly as the browser skips a buffer
it flagged `delegated`.

### 4. The choice is the person's; the effective mode is derived and published

`users.phone_call_mode` (Live by default — a call that leaves a trace in the
conversation is the point of the channel) and `phone_calls.call_mode` (the
mode a call RAN, written at the dial, read at the closing: a choice flipped
mid-call must not close a Live call as a direct one). Live needs the vendor
to call this API back, so it is AVAILABLE only when the callback base's host
is public (`telephony/callback.py`; `TELEPHONY_CALLBACK_BASE_URL` for a
development tunnel, else `API_URL`): `GET /telephony/identity` publishes
`live_available`, the reason and `call_mode_effective`, the settings list is
disabled with the reason, and a delegation tool the vendor refused degrades
the call to DIRECT and says so — never a Live mandate with no way to
delegate (ADR-184). The mode is settled
BEFORE the call is handed anything (review 2026-09-20): the dial provisions
the delegation tool first and, when it cannot, builds what a DIRECT call
needs — the lookups and the context block — rather than degrading a Live
call that had skipped both into a voice that could answer nothing. A refusal
at the attach itself, inside the dial, still degrades without them: the
same envelope as a direct call whose attach was refused.

**A call nobody answered has no mode.** No answer, a voicemail, a failed
line: no model is spent, no session books are opened, and the person is told
« nobody answered » or « the line failed » whatever they chose — the same
fallback push a direct call sends, decided BEFORE the mode. Review
2026-09-20: a Live call closed its row with nothing to deliver, so a line
that never picked up left the person, or the routine that planned the call,
uninformed.

### 5. A DIRECT browser session is relayed at its end

`POST …/turns` keeps a direct session's exchanges in its record (a Redis
list beside it, bounded, answering no row id — and living as long as the
record: an extension moves the list's life with the record's, a new claim
starts with none) and the end hands them to a task the closing owns, which
synthesises and relays them as the person's own turn — **no model runs
inside the request**: the claim is released at once and a slow provider
hangs nothing. The closing card says `scheduled` (or `empty`), is REWRITTEN
once the words settled (`answered`, `waiting`, `busy`, `pending_question`,
`quota_blocked`, `failed`… — every `RelayOutcome` has its sentence, guarded)
with its cost re-read (the turn spent under the session's run after the
card was written), does not stay at « scheduled » for anything that raises
in the settle (a hard crash mid-flight is the one exception — the settle is
a background task drained at graceful shutdown, the transcript persisted
nowhere, the phone's own envelope), and a notice on the SSE stream reloads
the thread. An authenticated
session is the account holder's by construction: the synthesis's own owner
flag is overwritten (review 2026-09-20: a model output could have answered
`not_owner` for the person's own session), AND the prompt is told which line
carried the session — a `SESSION:` line of the context, from
`voice_relay_lines.txt` — so its rule on who was speaking reads « the line is
authenticated » on a browser session and looks for the identity check on a
phone call alone; written for the phone alone, it asked the model for an
identity check a browser transcript never holds. The banner and
the mandate say so (« LIA reads your data for you and acts on nothing while
you talk; at the end, what you asked is relayed to your conversation as a
message from you »; a request is NOTED, not refused). The 409
`direct_not_archived` is gone.

## Consequences

- One vocabulary and one door per policy; a fourth carrier is a
  `VoiceSession.<carrier>()` constructor and its own record.
- **The lookup admission is ONE sequence** (review 2026-09-20,
  `agents/telephony/voice_lookup.serve_voice_lookup`): the two tool doors of
  a direct voice — the phone's `live_tools_router.live_tool_callback` and the
  browser's `live/tool_door.run_session_tool` — used to write the same three
  steps in the same order by coincidence. They now hand the shared admission
  what stays theirs — the offered set resolved under THEIR gate (the
  telephony flag, the live capability) and the person's switches, the
  budget of THEIR host, and the way a refusal is said (a vendor call-back
  answers « not found », a person's own session a sentence) — and the
  admission decides in the contract's order: offered, then the budget (a
  refused tool spends nothing), then the run under the `VoiceToolHost`. The
  authentication stays per door, deliberately: one is a derived token, the
  other the person's cookie. A MUTABLE tool with a spoken HITL (not built)
  adds its step between the budget and the run — the draft, the question the
  voice asks, the answer that resumes — in the admission and the shared
  runner, never in either door.
- Every euro of a session answers to both ceilings (ADR-272): the delegated
  turns under their run ids, the synthesis and the tool host under the
  session's, the learning under the session's — and the calls listing and
  the card SUM them (the phone: `session_run_ids_by_key`, two batched reads
  for the page).
- Two new metrics on dashboard 24 (`telephony_delegations_total{outcome}`,
  `telephony_delegation_duration_seconds`) and one on dashboard 30
  (`live_direct_relay_total{outcome}`).
- Found on the way and fixed: the backend `html_to_text` glued a definition
  list's label to its value (« IntituléSenterre ») where the browser's
  `htmlToPlainText` already read « Intitulé : … » — the corpus now pins the
  two; `ConversationRepository.get_by_id` is the CONVERSATION's, so a card
  read through it was never rewritten (`get_message`, a PostgreSQL test).
- **A voice runner holds no database session across the turn** (review
  2026-09-20, the workboard runner's own rule): `run_voice_relay` runs its
  two probes on a session it opens and closes, the direct settle opens its
  session AFTER the turn for the rewrite alone, and the phone's `run_relay`
  resolves the account on one short session and pushes on another. Measured
  on dev before: the settle's session sat 8.9 s in `idle in transaction` —
  the whole relayed turn — for two SELECTs it had finished; after: no
  session of the runners' in that state (a commit hands the pooled
  connection back — measured: `checked out` 1 → 0).
- The card's figures live under `live_summary`, their own key (review
  2026-09-20): `with_origin_stamp` writes under the origin KIND, and a relayed
  browser turn's kind is `live_session` — a card archived under that origin
  would have had its figures replaced by the stamp, silently. A guard holds
  the key off every origin kind and archives a card under a live origin.
- Known, written down: a pending question from a previous session takes the
  first request of the next call for its answer — the chat's own rule
  (ADR-276 lot 7), the same on the browser; the closing card of a delegated
  session is written before the learning pass spends, so its cost excludes
  that pass while the listing includes it.

## Proofs

`task telephony:simulate:live` and `task telephony:probe:live` (no phone —
owner constraint), the e2e `chat-live-session.spec.ts` on the standalone
bundle, the PostgreSQL and Redis integration tests, the unit suites of every
module named here. See the spec for the measured timelines.
