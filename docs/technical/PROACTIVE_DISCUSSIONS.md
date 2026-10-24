# Proactive discussions — how a run works, and what its context keeps

LIA may open a personal conversation of its own accord: taking an interest in a plan,
encouraging the person, asking an open question. This page explains a run end to end
and, above all, the **discussion context** — how it is built, enriched, reused and
forgotten. The decisions and their measurements live in three ADRs:
[ADR-358](../architecture/ADR-358-Independent-Proactive-Discussions-And-Native-Delivery.md)
(the initiative and its delivery),
[ADR-359](../architecture/ADR-359-Longitudinal-Discussion-Context-And-User-Control.md)
(the context and the person's control) and
[ADR-360](../architecture/ADR-360-Bounded-Discussion-Research-And-Accounted-Abstention.md)
(bounded research and spend). Every bound named here is a setting of
[`proactive_discussions.py`](../../apps/api/src/core/config/proactive_discussions.py),
declared in the « PROACTIVE DISCUSSIONS » section of every env template; its value is
the code's, so this page names settings and never restates their numbers.

## A run, from the tick to the conversation

1. **The tick** ([scheduler](../../apps/api/src/infrastructure/scheduler/proactive_discussions.py))
   runs every `DISCUSSION_INTERVAL_MINUTES` on the leader and serves at most
   `DISCUSSION_TICK_OWNERS`, `DISCUSSION_TICK_CONCURRENCY` at once, drawn among
   `DISCUSSION_TICK_CANDIDATES` examined at random (never fewer than the owners): a
   requested rebuild first, whatever the hour, then owners whose window is open. It
   also sweeps up to `DISCUSSION_DELIVERY_BATCH_SIZE` pending deliveries and maintains
   up to `DISCUSSION_MAINTENANCE_BATCH_SIZE` accounts (context retention, expired
   reservations).
2. **Admission** ([run setup](../../apps/api/src/infrastructure/proactive/discussion_run_setup.py)):
   the capability switch, the person's controls (rules within
   `DISCUSSION_DIRECTIVES_MAX_TOKENS` and live reply guards within
   `DISCUSSION_REPLY_GUARD_MAX_ROWS` and `DISCUSSION_REPLY_GUARD_MAX_TOKENS`, read
   whole or the run defers), the person's **attention** for an opening (no turn
   written lately, no opening still awaiting a reply — it holds the next one back for
   `DISCUSSION_ATTENTION_UNANSWERED_OPENING_MINUTES`, never past its reply window
   `DISCUSSION_OPENING_PENDING_HOURS` — no recent opening, no reminder about to ring,
   no turn streaming, no approval waiting — each delay a `DISCUSSION_ATTENTION_*`
   setting), then the **claim** (one run per account, under a lease), the person's **usage
   limit** — the verdict every model call asks, asked before any source is read: a
   refused run settles `usage_limit_reached` and the next tick asks again — and the
   **reservation** (below). A run refused before its claim writes no row: its outcome
   on `proactive_discussion_runs_total` and the `discussion_run_not_started` log line
   name why — the first attention hold met (`recent_turn`, `pending_opening`,
   `recent_alert`, `recent_opening`, `reminder_due`, `turn_streaming`,
   `approval_pending`), `capability_disabled` or `claim_refused` (the window, a pause,
   the daily maximum, a deferral, a live lease, a rebuild no longer requested).
3. **The context** is built (next section). A rebuild stops here. An opening run reads
   its facts again before and after each paid call and before its decision, one read
   per page and operation shared by the facts that ask for it; a rebuild does not,
   since every proof it stores is read again at its version before any later use. A
   re-read that could not be made stops the run under its own reason
   (`evidence_refused`, `read_budget_exhausted`, `evidence_page_missing`), never as a
   changed fact; nor does a re-read page that stopped before the fact (truncated, in
   a busy window or after a search): the fact is read again around its own instant,
   and only a page that covered it can say it changed. An opening stops at `DISCUSSION_RUN_DEADLINE_SECONDS`, a rebuild at
   `DISCUSSION_REBUILD_DEADLINE_SECONDS` — longer, since every pass shows the model what
   earlier passes understood — and a run its deadline stops says so
   (`deadline_reached`); a rebuild so cut resumes at the next tick.
4. **The decision** (`discussion_decision` slot): engage, defer or skip, on the
   ready context and the openings already made (none is repeated).
5. **The wording** (`discussion_message` slot), then **publication**: the opening is
   archived in the conversation — an earlier opening still pending is closed first,
   superseded once any reply written to it is bound (one past its reply window keeps its
   deadline) — and delivery starts at
   once, re-checking that its proofs are still fresh
   (`DISCUSSION_DELIVERY_PROOF_MAX_AGE_MINUTES`, also the longest
   a delivery attempt may last before it is settled as uncertain) and its sources still
   allowed. The publication settles the run in its own transaction, so it writes the
   run's reason (`published`) and counts. A provider that asks to wait defers the run
   until its `Retry-After`, or `DISCUSSION_BACKOFF_MINUTES` when it names none.
6. **Settlement**: the reservation closes on what was really spent, and the run row
   records its state, **why it ended** (`reason`, one code of
   [`RunReason`](../../apps/api/src/domains/proactive_discussions/run_types.py), shown in the
   settings in six languages) and **what it read** (`stats`, counts only — kept when the
   build stops before its end, a fact changed or a call failed — `context_updates`
   counting the publications that moved the context's generation).

Every source a run opens is filed in the consultation register under the run's id;
a rebuild's reads are the person's request (authored `user`), an opening's are LIA's.
The opening itself is an **action** of LIA's own (`proactive_discussion`, shown under
« Actions menées d'elle-même »): claimed before its message is posted, settled from the
commit that posts it, whatever a push does afterwards (ADR-263). Every model call and
every paid read is billed to the account under the run's id — its `token_usage_logs`,
its `message_token_summary` row and the account's `user_statistics`, like a chat turn.

## What the settings show

Two folded panels share one read of the context: **Context** (the rebuild and where
the work stands) and **Context data** (the elements, their filters, switches and
purge). The **Context** panel reads one activity ([activity](../../apps/api/src/infrastructure/proactive/discussion_activity.py)):
when the context was last **updated** (the latest run whose `context_updates` is not
zero, rebuild or opening), when it was last **rebuilt**, and the **last run** — its
kind, why it ended, what it read and what it cost, from its own ledger row: the
figures on screen are always that run's. The page re-reads the activity every minute
while either panel is open, and the context list once a run updated it. Spending ceilings are
never quantified there: when one stops LIA, one sentence says which — the instance's
daily budget, the person's usage limit, a run ceiling below one call, the account's
day, the instance's day for discussions — in the order a run meets them, with the day
it renews when it is a day. Below it, when an opening still awaits a reply and holds the
next one back, one sentence says since when and until when — read through the attention
gate's own predicate (`unanswered_opening`), so the page never announces a wait no run
would observe, nor hides one.

## The context

### Reading

Before any page is read, the person's statements that restrict reading (« never read
my SMS », in a procedural memory or a reply) are **compiled** into the sources they
deny ([rule controls](../../apps/api/src/domains/proactive_discussions/rule_controls.py)),
at most once per `DISCUSSION_RULE_CACHE_HOURS` for the same rules, sources and prompt.
Every denial must quote the person's own words: one that does not refuses the whole
compilation, and the run reads nothing and says so (`rules_refused`). The refusal is
cached too — the same inputs are compiled again only after
`DISCUSSION_RULE_REFUSAL_FIRST_WAIT_INTERVALS` tick intervals, then twice as long at
each new refusal, up to `DISCUSSION_RULE_CACHE_HOURS` — so a tick never pays the
compiler again for an answer it has just refused (ADR-359 amendment 2026-10-23).

A pass reads the **recent page** of each readable source — a source the person
allowed, the instance serves and the account can reach, with its dependencies; health
also needs the health topic. A page holds at most `DISCUSSION_RESEARCH_ITEM_LIMIT`
items, each an excerpt of at most `DISCUSSION_RESEARCH_ITEM_MAX_CHARS` (the portrait
is read whole), over `DISCUSSION_RESEARCH_DEFAULT_WINDOW_DAYS` around now; every read
is bounded in calls and time (`DISCUSSION_READ_CALL_LIMIT`, `DISCUSSION_READ_TIMEOUT_SECONDS`,
whose highest accepted value is the read contract's own), and a run's reads together
by `DISCUSSION_RUN_READ_CALLS_MAX`. A page that could not be read says why, and that
reason reaches the model as data: `consent` only when the person refused,
`feature` when the operator did, `provider` otherwise.

### Admission

What a page read is admitted through the person's controls before any model sees it:
the allowed sources and topics, the elements marked **not usable** (and the evidence
known to relate to them), what a **purge** forgot (a forgotten version is never read
back as new), and topics the person asked to avoid.

### Interpretation

The **context call** (`discussion_context` slot) receives the person's rules, the
admitted facts that changed since they were last interpreted, the stored items still
usable, and the coverage of the pages read. It returns, for every fact offered, a
topic classification (one of the five sensitive topics, or none), a few compact
**proposals** — observations, episodes, qualified patterns — and a **resolution**:
ready (these references suffice to speak), research (one bounded wave more, within
the published window bounds) or insufficient.

The prompt must fit the configured slot: its window, less its output budget and a
framing margin. No envelope is written in the code — a model is what an
administrator configured. A pass offers at most `DISCUSSION_CONTEXT_FACTS_PER_PASS`
facts, spread across sources so one busy mailbox cannot take every place.

Whatever model the slot runs, one malformed proposal never refuses the whole answer:
each is [read on its own](../../apps/api/src/domains/proactive_discussions/contextualization/proposal_reading.py).
A reference listed twice or left empty, or an anchor missing from its own references,
is repaired, and an observation resting on several facts becomes the episode the store
defines for them; a proposal beyond the published cap, or any other shape the contract
refuses, is set aside alone. The decision is read the same way: a free text past its
published length is cut at it, an engagement's reference listed twice is read once. A topic label only ever adds a topic: a fact labelled twice takes
both labels, and a fact the call left unlabelled leaves the pass — never read as an
ordinary one, neither interpreted nor checkpointed, offered again later
(`facts_unclassified`). A research request the policy or the pages refuse is never
read and never refuses the run (`research_refused`). The publication then
[prepares each proposal alone](../../apps/api/src/domains/proactive_discussions/context_store/preparation.py)
and refuses, under a named reason, one that touches a refused topic, rests on evidence
no longer admitted, is qualified beyond what its evidence supports, spans two subjects
or makes an item another proposal of the pass already makes. Every refusal is counted
on the run (`proposals_refused`) and logged by reason, never by content.

### What is kept

- **Items** (observation, episode, pattern): a short summary in the person's language,
  its qualification (planned, reported, observed, possible, unknown), its sensitive
  topics and its **proofs** — body-free references to the facts it rests on. An item
  is usable only while every proof is read again at the same version, by the read that
  can return it (`reread_operation`, also used before every paid decision: an
  expanded history for a calendar occurrence, a detail read where the source has one,
  the future for a planned fact of a source without one). The current weather is one
  object per provider and place, versioned by what it says at the precision a
  sentence would (whole degrees, humidity by five points, a precipitation chance by
  tenths — the model still reads every value), whatever instant the provider stamps
  it with; a forecast point is the instant it forecasts. A re-read that finds a fact
  changed logs which source moved (`discussion_evidence_changed`), never its content.
- **Checkpoints**: for each fact interpreted, its version and the signature of what
  its meaning depended on (readable sources, consented and refused topics, clock,
  language). An unchanged fact under an unchanged signature is not paid for again;
  editing the hours, the daily limit or a pause changes no signature.
- **The ready context**: the references the last ready resolution settled on, reused
  by the next opening while they hold.
- **Coverage**: the latest page read per source, shown in the settings.

### What is forgotten

- **Retention**: an item outlives its read by at most the smaller of its source's
  retention and `DISCUSSION_CONTEXT_RETENTION_DAYS` (`DISCUSSION_PEER_CONTEXT_RETENTION_DAYS`
  for what comes from a peer); the maintenance job expires it even while the
  producer is off. Retention is lifecycle, never forgetting: an expiry moves the
  generation and clears the ready context, never the epoch — every other checkpoint,
  the run in progress and the pending opening hold, so a source that lives minutes
  (location, current weather) costs one fact interpreted again, not the whole context.
- **The person's acts**: *not usable* excludes an item and its known evidence;
  *purge* deletes items and writes forgetting markers so the same versions are never
  re-learned (streamed `DISCUSSION_CONTEXT_PURGE_BATCH_SIZE` observations at a time);
  the reaction *this context is incorrect* forgets what the opening rested on and
  requests a rebuild.
- **A rebuild** moves the context epoch: every checkpoint becomes stale, so every fact
  is due once. Each pass checkpoints what it analysed and the next offers the rest; a
  rebuild does not stop at its first ready pass but interprets every admitted fact it
  can afford, within `DISCUSSION_REBUILD_CONTEXT_CALLS`, and an interrupted rebuild
  resumes where it stopped. An opening run keeps `DISCUSSION_CONTEXT_CALLS_PER_RUN`:
  it needs enough to speak, not everything.

## Money

Three ceilings, in USD: per run, per account per UTC day and for the instance per UTC
day; without all three, paid production stays closed. A run **reserves** its ceiling
or what is left of the day, whichever is smaller, and starts only with room for its
**first call** — a context call on the rules alone, priced on the configured slot's
output budget and tariff. Each call is admitted against the reservation: what the run
really committed plus the call's bound must fit, and a finished call commits its bill,
never its bound. Every refusal is a reason (`tariff_unavailable`,
`allowance_exhausted`, `phase_exhausted`, `day_over`, `budget_exhausted`, …), and the
settings say when a day can no longer fund the next first call. A run ceiling below
that first call can never start a run, whatever the day holds: it is named
`run_ceiling_too_low` — raising a slot's output budget raises the bound, so its run
ceiling must follow. Above these three, the account's usage limits and the instance's
daily budget (ADR-272) bound every call like any other model call; a run they refuse
stops as `usage_limit_reached`.

## Consent and privacy

Each source is its own switch, and a new source stays off. A new account consents to
the operator's default sensitive topics (`DISCUSSION_DEFAULT_SENSITIVE_TOPICS`, all
five unless configured otherwise) and withdraws any of them; an account that chose
keeps its choice. An opening touching a sensitive topic is private: its push is masked
and no external channel receives it. Reading an SMS does not make an opening private —
an SMS is personal data like a mail (ADR-357 amendment 2026-10-23).

The account export carries every discussion record: the preferences, the openings and
their delivery, the runs, the context items with their proofs, the evidence checkpoints,
the exclusions, the forgetting marks and the context state. Only the support links stay
out — each item's exported proofs already name them — and the rows lose the server's own
fencing, claim and cache tokens ([the data map](../../apps/api/src/domains/users/user_data_map.py),
[the archive builder](../../apps/api/src/domains/account_export/builder.py)).

## Measuring it

`task discussions:context:measure -- --email <account>` runs the read phase of a run
through its own readers, admission and prompt measure, and prints counts only;
`--mode verify` reads every admitted fact again as a run's revalidation does and counts
what came back unchanged, changed or missing; `--mode context` adds the run's own
context loop on the configured slot under an in-memory reservation (`--max-usd`),
billed to the account like a run, its proposals prepared as the publication prepares
them, with nothing written to the discussion tables; `--paid-weather` reads the paid
weather source as a run does
([harness](../../apps/api/scripts/proactive_discussions/measure_context.py)).

What the **execution tables** occupy — runs, openings, outbox, spend reservations and
budget buckets, which leave only with the account — is published per table on
dashboard 13 (`proactive_discussion_table_rows`, `proactive_discussion_table_bytes`,
read like the transparency registers: the planner's estimate, an exact count where it
has none, the real size with its indexes). No retention ships and no growth alert: both
are decided on that measurement (ADR-358 amendment 2026-10-23).
