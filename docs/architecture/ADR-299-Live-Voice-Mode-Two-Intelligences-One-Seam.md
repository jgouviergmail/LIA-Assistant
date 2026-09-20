# ADR-299 — The live voice mode: two intelligences, one seam

**Date**: 2026-09-18
**Status**: Accepted
**Amends**: ADR-070 (execution modes: the delegated turn is an ordinary chat turn), ADR-245 (reasoning profiles: a live provider family with its own ladder), ADR-258 (one microphone owner), ADR-263 (the registers: a session is a decision row, a delegated turn its own run), ADR-272 (every euro LIA spends reaches both ceilings: the session's is the sum of its delegated turns), ADR-280 (one switch per capability), ADR-282 / ADR-292 (what LIA learns: a voice-only exchange feeds memory and interests at the session's end), ADR-290 (the phone as a channel: the read-only rule does NOT apply here), ADR-260 (Redis key families), ADR-184 (a bound is published), ADR-185 (a count is exact)

## Context

The owner asked for a second voice: not the push-to-talk of the voice mode
(speech to text, a written turn, text to speech) but a **speech-to-speech
model** that listens and answers in the same breath — Gemini's Live API today,
another provider's tomorrow — on a connector the person configures with their
**own key**, so nothing of the provider's is billed to the instance.

Three decisions were arbitrated before any code:

- **LIA's own spend during a session is counted and shown** at the end of the
  live mode; the provider's tokens are never counted, never shown, and never
  reach the application (the person's key pays them).
- **The live mode is not bridled**: it substitutes the written mode and allows
  everything the chat allows — the phone's read-only rule (ADR-290) is a rule
  about a stranger's line, not about the person at their own screen.
- **The thread reports everything in real time**, and the voice model keeps
  its live intelligence: interruptions, filler speech while it waits, its own
  turn-taking.

The last two pull apart. A voice model that "allows everything" would have to
own tools, HITL, the registers, the spend ledger and the archive — a second
agent engine, outside the graph. The owner's question was exact: « je ne
bypasse pas l'intelligence du LLM live j'espère … MAIS j'aimerais bien que tous
ces échanges soient traités comme une discussion non live ».

Lot 0 measured the provider before the design was frozen
(`apps/api/scripts/live/probe.py`, `task live:probe`; the measurements are in
the spec's § 9). Four of them changed the design: a token's constraint does
**not** lock the system instruction; a used single-use token **cannot**
reconnect; the provider **silently accepts an unknown voice name**; and a raw
browser WebSocket is accepted **only** by the `…Constrained` method with the
token in the `access_token` query.

## Decision

**Two intelligences, one seam.** The voice model owns the conversation —
listening, speaking, interrupting, filling a wait — and delegates every request
for data or action to the chat engine through ONE function, `send_to_lia`,
declared `NON_BLOCKING`. The browser turns that call into an ordinary
`POST /chat/stream` with the person's own cookie: the delegated turn runs in
the graph (pipeline or ReAct, HITL, registers, quotas, archive), draws itself in
the thread as a user bubble and its answer, and the bridge hands the voice a
bounded, flattened answer — or LIA's pending question, which IS the answer.
The voice never holds a tool, a credential or a row of its own.

- **Topology (A1)**: client → provider. The API mints a **single-use
  ephemeral credential** locked to the model and renders the `setup` the
  browser replays verbatim (the constraint does not lock the instruction, so
  the server renders and the client replays — spec A4's fallback). The audio
  never transits the API; the CSP allowlists the provider's WebSocket host
  exactly (`LIVE_PROVIDER_CONNECT_SRC`), and the transport opens the
  `BidiGenerateContentConstrained` method, the only one that accepts a token
  from a page.
- **One session per account, bounded (A5, A6)**: a Redis claim with an owner
  token (`live:session`, USER_RUNTIME) refuses a second session; a global sorted
  set (`live:active`) caps the instance; a mint rate limit bounds the starts.
  The record outlives the session by `LIVE_SESSION_RECORD_GRACE_SECONDS` so a
  session that ran to its cap still closes its books. **Every reconnection
  mints a fresh credential** for the same record (`POST
  /live/sessions/{id}/credential`) and rides the provider's resumption handle;
  a close with no handle ends the session as `provider_closed`, too many
  attempts as `resumption_failed`. **A new start by the same account
  SUPERSEDES the session it holds** (outcome `superseded`: its books are
  closed, its slot freed) rather than answering 409 until the record's TTL —
  a tab that died without closing its books must not lock the person out for
  half an hour; a record superseded during its own mint is refused and never
  counted, and a superseded tab closes itself on its first 404.
- **What the thread shows (A7)**: a delegated turn is a chat turn stamped with
  `live_session_id` and the person's `spoken_text` beside the request the voice
  wrote; a voice-only exchange is archived at `turnComplete` as two visible
  rows (`live_turn`, both roles, bounded), so the next written turn sees what
  was said (the out-of-graph injection the proactive rows already use); the
  session closes on ONE card (`live_session_summary`) carrying the outcome, the
  figures and LIA's spend **aggregated from the delegated turns' own summaries**
  — the meter's vocabulary, never the provider's. **The card's figures are the
  server's, never the client's claim** (ADR-185): the delegations are the
  delegated runs found by the stamp, the voice exchanges a `COUNT(DISTINCT)`
  over the archived rows' `started_at`; the client only says how the session
  ended. The learning pass that follows the card spends under the session's
  run id and is filed in the ledger, not on the card — it runs after the card
  is written, like every turn's own post-response extraction.
- **Registers (A8)**: a session is ONE decision row (route `live_session`,
  `answered` iff the person ended it); each delegated turn is its own run and
  writes its own effects and consultations through the gate. What the voice
  said alone is not a consultation: nothing of the person's was opened.
- **Capability (A9)**: `PlatformCapability.LIVE`, route-enforced, family
  `media`, its own map node; `/config.features.live_enabled` gates the button,
  the settings section and the connector group.
- **The connector (A10)**: category `live`, provider-agnostic on the wire
  (`provider` names the transport); the key is verified by the very listing
  that fills the model select (`POST /live/models/discover`), the voices come
  from the provider's **published** list with its date and source (the provider
  offers no listing and refuses no name, so LIA is the only place a wrong name
  is caught), and the thinking level is offered **only** for a model whose
  ADR-245 profile declares a ladder — and refused off it on the write path.
  The provider judges the model again on every save (a setup + close probe, no
  audio, no token).
- **What the person settles (A10 bis)**: `users.live_preferences` (JSONB,
  full-replace PUT): interruptions, talk mode (automatic / hold to talk), end
  of speech (calm / normal / lively), result delivery (say it right away / at
  the next pause — the provider's `INTERRUPT` / `WHEN_IDLE` scheduling).
- **The surface (A11)**: a band above the thread on the `ActiveCallBanner`
  model — a named region, a status line, folded captions, mute or hold-to-talk,
  Stop (cancels LIA's turn AND ends the session: the one door that kills a
  turn) and End — while the composer says why it is closed. The entry button
  decides its own presence (capability + connector) and is `aria-disabled`,
  never `disabled`, so the click that opens the session never loses its focus.
  The eyes read the session's voice state through `effectiveVoiceState`
  without a new input; the wake-word loop stands aside while a session holds
  the microphone (ADR-258's one-owner rule, extended).
- **What LIA learns (R4)**: at the session's end the voice-only exchanges feed
  the memory extractor and the interest detector under the session's run id,
  fire-and-forget — a delegated turn learns in its own turn.
- **Spend (A5)**: the session creates no accounting of its own. Its card sums
  the `message_token_summary` rows of its delegated runs (found by the stamp),
  and every one of those runs was already bounded by both ceilings (ADR-272).

## Consequences

- A second provider is one transport in `lib/live/transports/`, one
  `LiveProvider` implementation, one CSP host and one reasoning family — the
  session, the bridge, the banner and the registers do not change.
- The delegated turn is the ONLY execution path: nothing of the graph is
  re-implemented outside it, so every rule the chat enforces (HITL, quotas,
  registers, archive, learning) holds by construction in the live mode.
- The provider's tokens are invisible to the application by construction: no
  route receives them, no column stores them, no card shows them.
- Measured on lot 0 and pinned by the probe: the constraint that does not
  lock, the token that does not reconnect, the voice name that is never
  refused, the transport method that accepts a token. Each is a rule in the
  code with its measurement in the comment; the probe replays them.
- **A fixture more forgiving than the real thing proves nothing** (found the
  first time the owner clicked Live on dev): the provider's frames are
  BINARY, a browser hands them as `Blob`, and the transport read text — the
  Python probe reads bytes transparently and the hermetic fake sent text, so
  both were green while every real session stayed on « Connecting… ». The
  transport now asks for `ArrayBuffer`s and decodes them itself, and the fake
  provider sends `Buffer`s: the hermetic journey exercises the real shape.
- Two things this ADR does NOT change: the phone (ADR-290) keeps its read-only
  set — a stranger's line is not the person's screen — and the voice mode's
  push-to-talk keeps its STT/TTS pair; the live mode is a third door beside
  them, not a replacement.

## References

- Spec: `docs/superpowers/specs/2026-09-18-live-llm-connector-design.md`
  (A1–A14, § 9 measured)
- Plan: `docs/superpowers/plans/2026-09-18-live-mode.md`
- Technical: `docs/technical/LIVE_MODE.md`
- Probe: `apps/api/scripts/live/probe.py` (`task live:probe`)
