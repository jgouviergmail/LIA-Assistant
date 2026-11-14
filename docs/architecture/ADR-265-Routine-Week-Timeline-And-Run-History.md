# ADR-265 — The routines' week: a run history at the result, a grid that only paints

**Date**: 2026-09-05
**Status**: Accepted
**Context**: The routines page listed its cards in the API's order —
`next_trigger_at` ascending — which moves every day as runs happen, and gave
the reader no picture of the week. The owner asked for a vertical timeline
(hours down, days across), a chronological order with a number on every card
so the grid and the list can be correlated, a paused indicator, and then a
colour per cell: white while a slot has not run, green when it ran, red when
it failed, grey when the routine is paused, with a reset at the start of every
week and whenever the schedule changes.

A colour on a cell is a claim about ONE slot. Nothing held that record:
`scheduled_actions` keeps one `last_executed_at` and one `last_error` with no
timestamp, so at best the LAST slot could be qualified, never "Monday green,
Wednesday red" — and the activity feed already documents that gap ("there is
no runs table", `activity/repository.py`). Two sources were measured before
deciding:

- the turn register `agent_decisions` (ADR-263) records every scheduled turn
  with `source=scheduled` and an outcome, but files it under the
  CONVERSATION's id, not the routine's (`service.py`: `thread_id =
  conversation.id`). Joining back through the conversation breaks the day the
  user deletes it, the register cannot say "condition not met", "proposed" or
  "skipped, an approval was pending" (three exits that happen BEFORE the
  pipeline runs), and it knows no served slot — so "reset on change" would
  have needed a column and a tolerance window;
- the executor itself knows everything at the instant it writes the result:
  the due slot it was armed for, the outcome, the error, the attempts, and
  whether the user pressed "Test now".

Three defects surfaced on the way, each pre-existing and each closed here:
every poll (30 s, 10 s while a run executes) set `loading` and the section
unmounted its cards — spinner, blank, every open disclosure shut — twice a
minute; a routine paused during a timezone move kept the OLD zone and woke up
on the old clock; and APScheduler 3.11.2 SKIPS the whole day for a routine
scheduled inside a spring-forward gap that opens at midnight (Santiago,
Havana, Cairo, Beirut…), while it shifts the same gap by an hour everywhere
else — measured over every IANA zone and every 2026 transition: 2 112 slots
shifted, 72 skipped, all 72 in the 00:00-00:59 hour of six zones.

## Decision

### 1. The order is the client's, the API's order stays

The cards sort at the display, by hour, minute, title (numeric, accent-
insensitive, in the reader's language) and id — a total order, so the rank is
deterministic whatever order the rows arrived in. The API keeps
`next_trigger_at` ascending: the notifications hub, the briefing's For-you
card and the automation tool read that order, and for them "soonest first" is
right. A paused routine keeps its rank (toggling never renumbers); creating or
rescheduling one does — a rank is an order, not an identity, and the owner
accepted that.

### 2. A run history written AT THE RESULT

`scheduled_action_runs`: one row per tick, inserted from the executor's
explicit outcome in the SAME transaction as `mark_execution_success` /
`mark_execution_failure`, never before it — a crash mid-run leaves no row,
which is the truth. Five outcomes, one per executor exit (`success`,
`failure`, `skipped_condition`, `proposed`, `skipped_hitl`), so a skip is
recorded rather than read as silence. The insert runs inside a SAVEPOINT and
its failure is logged, never raised: a history write must not cost the routine
its own marking, or stale recovery would re-run it. The `outcome` column is a
VARCHAR with a REAL check constraint — `create_constraint=True` is explicit
because SQLAlchemy 2 defaults it to False, and measured on the dev database
the three register tables that say "CHECK-backed" carry none; this one is
proven by an integration test that inserts an undeclared value.

The row carries the SERVED SLOT. A due run serves its due instant; a manual
run serves the day's slot only once that slot has passed (a test at 07:00 of an
08:00 routine is a rehearsal, `slot_at` NULL, and colours nothing), and it is
computed by the very function the week uses (`local_day_slot`, one reference
shape: the instant before local midnight) so the two agree by construction,
repeated hour of the fall-back included.

Retention is a setting (`SCHEDULED_ACTIONS_RUNS_RETENTION_DAYS`, 90), purged
inside the executor's own tick — step 0, BEFORE the empty-batch early return,
because the empty tick is the common one — in its own session so a failed
DELETE cannot poison the batch, and never fatal. The table is declared
`USER_CASCADE` / exported in full: it is the user's own execution history.

### 3. The week is computed server-side; the browser paints

`GET /scheduled-actions/week` returns, per routine, the seven instants it
fires at this week and how the run serving each one ended. The instants come
from `week_slots`, the same cron engine that arms the runs, from the local
Monday of the ROUTINE's zone (a routine in Auckland is on Monday while the
server is still on Sunday). A cell takes the LAST run whose `slot_at` EQUALS
the week's instant for that day. Equality, never a window: a schedule change
moves the instants, so old runs stop matching by construction — that is the
"reset on change" the owner asked for, without a column; the next Monday the
window slides — that is the weekly reset. The route is declared before any
`/{action_id}` route and a test pins the order.

The grid positions a chip by the routine's own `trigger_hour` and
`days_of_week` — the wall clock of its zone, named beside the grid — and
never converts an instant. When the week read is unavailable the grid still
draws, every chip idle, and SAYS the states are unavailable. Amber is a fifth
colour, for a proposal awaiting the reader's click: neither "not run" nor
"run". A skip keeps the idle colour but carries its reason in the chip's name.

### 4. The grid is a table, the chip is a button, the title stays on the card

A real `<table>` — seven `scope="col"` day headers, twenty-four `scope="row"`
hour headers, a caption naming the zone — because that is what a screen
reader walks by row and column. Rows have a fixed height so the axis stays
linear; the resolution is the hour, the minute is in the chip's name. Each
chip is a `<button>` named "rank, title, time, state" that scrolls to the card
and FOCUSES it, so the keyboard lands on the routine. The title is never
visible text on the grid: the card owns it, and a second copy would make every
"find by name" query ambiguous. One `RoutineNumberChip` serves the card and
the grid — same glyph, five theme-token tones the contrast guard already
covers, a ring for a condition routine, a pulse (still under reduced motion)
while it runs. Today's column is highlighted from the server's reading, from
`Intl` on the single zone otherwise, and not at all across several zones.

### 5. Three repairs on the way

- **A refresh is not a first load.** The hook derives a monotone
  `initialLoading` (`data === undefined && loading`, the list query no longer
  seeds `initialData`); the section gates its spinner on it and marks the
  region `aria-busy` while a poll refreshes it. The cards, the disclosures and
  the grid fold survive every poll.
- **A paused routine follows a timezone move.** `recalculate_all_for_user`
  covers every routine; `toggle` and `update` read the stored zone, which is
  now the user's.
- **A midnight gap shifts, never skips.** One seam, `_next_fire`, is the only
  reader of `CronTrigger.get_next_fire_time` in the helpers; it looks for a
  configured local day the cron jumped over whose wall clock does not exist
  and returns the first existing instant of that day (`fold=0` on a
  non-existent time resolves to the post-gap instant). Differential over every
  IANA zone and every 2026 transition: 15 684 identical to the raw cron, 144
  corrected, 0 anomalies.

## Rejected

- **Reading the register instead of a runs table** — see Context: the join
  through the conversation, the three missing outcomes, no served slot.
- **A tolerance window to match a run to a slot** — fragile under batch
  delays and restarts, and it would have needed a `schedule_changed_at`
  column; slot equality needs neither.
- **Minute-precise vertical placement** — collisions and illegibility at
  28 px per hour; the hour row plus the minute in the name reads better.
- **Sorting the API** — three other readers depend on its order.
- **Re-reading the cron in the browser** for the week's instants — a second
  authority that disagrees exactly at the daylight-saving edges (ADR-252's
  rule for `next_occurrences`, kept).
- **A purge job of its own** — a new interval to jitter and a new lock for a
  DELETE that returns zero rows most minutes.

## Amendment 2026-10-13 — a run whose routine another tick took still writes its row

Since [ADR-276's amendment 2026-10-13 (b)](ADR-276-Workboard.md), a routine's reservation is
held by its token, and the settle that follows the model writes nothing of the ROUTINE once
the recovery handed it to another tick: its state is that tick's. The run itself happened, so
its row is still written, with its own outcome. Every exit of the executor keeps ending with a
row (`runs.py`), and a condition routine's daily cap, counted from these rows (ADR-322), sees
the run.

The slot may then carry two rows. The week keeps the LAST started one — the tick that holds
the routine — since the fold reads the rows oldest first. Guard:
`test_a_settle_whose_reservation_was_taken_meanwhile_leaves_the_routine_alone`.

## Amendment 2026-11-12 — a routine that does not run says so

Three silences, read in the executor on 2026-11-12:

- a routine failed, and its owner was told nothing: the result push is sent only when there is an
  answer, so a failure reached the person as nothing at all;
- after its failures in a row the repository paused the routine (`mark_execution_failure`) with a
  log line and no word to anybody;
- the usage pre-check returned before any settle — no row, no re-arm, the routine left `executing`
  until the stale recovery freed it, then refused again — and a ceiling met INSIDE the turn
  (`RunOutcome.QUOTA_BLOCKED`) was filed as a `failure`, so a series of ceiling refusals paused a
  routine that had nothing wrong with it.

One reader of a failing routine already existed, and stays: the nightly usage proposal
`fix_routine` (ADR-375) offers to open the routines of an account whose routine keeps failing.
It speaks the following night, on the proposals page; what follows speaks when the tick ends.

**Decision.**

1. **A failure is announced once per series, and once more when it pauses the routine**
   (`scheduled_action_notices.failure_notice`): the first failure, then silence — the person
   knows — then the pause. A run the person started is waited for, and always says how it ended.
   The verdict is read from the row `mark_execution_failure` returns: the threshold keeps one
   owner.
2. **A ceiling refusal is not a failure** (ADR-272), on both doors — the pre-check and the turn's
   own refusal: the routine is re-armed on its clock, nothing counts toward the pause, and the
   reason is written where each kind of routine keeps its history. A TIME routine's slot gets a
   row, `skipped_quota` (the seventh outcome, migration `1e2baddce0fe`). A CONDITION routine
   writes no row — a refused check would write one per check, the rule of ADR-322 — and says it
   on its ledger: `last_check_error = quota_blocked`, which its card already reads. The check
   itself is not made: it costs what its source bills (a weather watch), and the ceiling bounds
   that too. The ceiling is asked of an AUTHORIZED tick only: one that lost its reservation, or
   a chat launch whose approved instruction changed meanwhile (ADR-335), neither runs nor
   settles, so it leaves no reason on the week either — the order is pinned on PostgreSQL by
   `test_application_routine_execution.py`.
3. **The ceiling's notice is the ACCOUNT's.** The ceiling blocks every routine of an account at
   once; one notice per routine would be a burst. It is claimed atomically (`SET NX EX`) once per
   window (`SCHEDULED_ACTIONS_QUOTA_NOTICE_COOLDOWN_HOURS`), after the commit — nothing is held
   while the cache answers (ADR-304) — and it fails CLOSED: without the cache nobody is told,
   where failing open would tell at every tick of every routine.
4. **A notice is a status report, not an act of LIA's own initiative**: it leaves through
   `NotificationDispatcher` like the proposal of a propose-first routine (archive, push, SSE,
   external channels), reads the dispatch's verdict for its log line, and files no register row
   (owner decision 2026-10-30). Every notice is sent AFTER the tick's outcome is committed.

**Rejected.** A ceiling notice per routine (a burst). A window counted from the run rows (a
condition routine writes none, so the window would differ by kind of routine). Evaluating a
condition past the ceiling to tell the person only when a fact was waiting (the check is billed).
Releasing the claim when a dispatch reaches no durable channel (the archive IS the durable
channel; its failure is a database failure the next window covers).

**Along the way.** The executor stood just under its size cap: what a routine TELLS its owner
(result, proposal, notices) moved to `scheduled_action_notices.py`, the tick's housekeeping to
`scheduled_action_housekeeping.py`, and a tick's six facts travel in one `_Tick`.

Guards: `tests/unit/infrastructure/scheduler/test_scheduled_action_notices.py`,
`TestAFailedRoutineSaysSo` and `TestTheUsageCeilingStandsARoutineAside`
(`test_scheduled_action_executor.py`), and on PostgreSQL
`tests/integration/domains/scheduled_actions/test_quota_stand_aside_pg.py` and
`test_run_outcome_migrations_pg.py`.

## Amendment 2026-11-12 (b) — an occurrence is caught up inside its window

Two ways a time routine answered at the wrong moment, or not at all, read in the executor
on 2026-11-12:

- the scheduler claims every row whose `next_trigger_at` is past, with no lower bound: an
  occurrence was run however late it was reached — a morning routine answered at 14:00
  after an outage;
- an account found busy re-armed the routine on its NEXT occurrence (`rearm_after`), like
  every other exit: a daily routine was lost for a day because its owner was typing at
  08:00, or because two routines of one account were due the same minute (the second P1 of
  the cold review of 2026-11-12).

**Decision.**

1. **An occurrence runs late only inside its catch-up window**: half the gap to the
   occurrence that follows it, capped by `SCHEDULED_ACTIONS_CATCH_UP_MAX_MINUTES`
   (`TriggerPlan.catch_up_deadline`). The routine's own rhythm says when its occurrence is
   stale. An occurrence nothing follows — the last of a series, a single one — is never
   given up: running it late is all that is left of what the person asked for.
2. **Given up, it says so, and the freshest occurrence is armed.** Its slot carries
   `skipped_late` (the eighth outcome, migration `7a3c9e51d4b8`), nothing counts toward the
   pause, and nobody is notified — an outage that skipped five routines would answer with
   five notices. The routine re-arms on the MOST RECENT occurrence when it may still start
   (an outage ending twenty minutes after today's slot serves today, at the scheduler's next
   pass), else on the next one (`TriggerPlan.after_missed`). An occurrence whose successor
   has already come is past its window by construction — the window is at most half the
   gap — so the most recent one is the only candidate, found by walking back from now
   (`core.recurrence.latest_occurrence`), never forward through every instant of the outage.
3. **A busy account is waited for, inside the same window.** The occurrence stays armed on
   the SAME instant and no row is written: the scheduler's next pass finds it due again.
   When the next pass would start past the window, the attempt is the last: the slot
   carries `skipped_busy` and the routine re-arms on the next occurrence. The last
   occurrence of a series is waited for the maximum as well — an account busy for hours is
   not a turn under way.
4. **What is left as it was.** A question waiting in the chat (`skipped_hitl`) is not waited
   for: it lasts as long as the person takes. A ceiling refusal (`skipped_quota`) is not
   retried: a ceiling does not lift in minutes. A condition routine has no occurrence: a
   missed check is missed.
5. **A run the person started is never given up as missed.** « Run now » and a run asked
   in the chat DECLARE it at the call site (`execute_single_action(started_by_person=True)`):
   who started a run cannot be read off the pending slot — a slot can be overdue because
   the scheduler was down, which is exactly when a person clicks. The click is the
   person's act, so the slot's age is never a reason to do nothing; the slot it serves,
   when one was due, keeps its wait for a busy account.

**Bound.** A waited occurrence is claimed again at every pass, oldest first: the due
routines of one stuck account take at most `SCHEDULED_ACTIONS_MAX_PER_USER` of the
`SCHEDULED_ACTIONS_BATCH_SIZE` slots of a pass, for at most their window.

**Rejected.** One `skipped_late` row per occurrence an outage skipped (a routine every
five minutes would write hundreds at restart; only the occurrence that was pending is
written). A per-routine window (no screen asks for it yet; the operator's maximum is the
one knob). A column holding the last reason an occurrence waited (the reason is known at
the attempt that closes the wait, which is the one that writes).

Guards: `tests/unit/domains/scheduled_actions/test_catch_up.py`,
`tests/unit/core/recurrence/test_latest_occurrence.py`,
`TestAnOccurrenceIsCaughtUpInsideItsWindow` (`test_scheduled_action_executor.py`), and on
PostgreSQL `tests/integration/domains/scheduled_actions/test_catch_up_pg.py` and
`test_run_outcome_migrations_pg.py`.

## Amendment 2026-11-12 (c) — a routine may notify only when a run found something new

A routine notified its owner at every run, whether or not the run had anything to say: a
monitoring routine answered « nothing to report » on a phone every morning. The condition
routines (ADR-322) already fire on a new FACT the system can see; what was missing is the
routine whose own instruction decides whether there is something to say.

**Decision.**

1. **The option holds back the notification, never the run or its record.**
   `scheduled_actions.notify_only_when_new` (migration `b6e2f48a1c93`): the routine runs, its
   answer is archived in the conversation and counted on the week as any run, and the push
   and the on-screen message are not sent when the run declared it found nothing new.
2. **The answering model declares it, by a machine tag.** Whether an answer says anything
   new is known to the model that wrote it and to nothing else. It appends
   `<lia_nothing_new/>` after its answer — the shape the tone register travels in (ADR-253):
   declared with the other machine tags, kept out of the token stream and of the stored
   answer, handed to the `done` chunk, read by the engine (`RunResult.nothing_new`) and then
   by the executor. No second call judges the answer, and no marker is ever shown.
3. **The instruction is given only inside such a run** (`nothing_new.quiet_run_scope`,
   published by the engine from `StreamRequest.quiet_when_nothing_new`): an ordinary chat
   turn is never taught the tag and its prompt does not grow; a tag written outside such a
   run is removed and declares nothing.
4. **Doubt notifies.** No tag, a tag cut short, a turn without its `done` chunk, a failed
   run: the owner is told, as before. Silence is the one outcome that needs a complete
   declaration, and a failure notice never reads the option.
   **And a run with something to admit is never « nothing new »**, whatever its model
   declares: a step that failed, a search cut short, a step left unrun. The prompt says
   it; the code makes sure of it (ADR-303) — the seam that assembles what an answer must
   admit about its own run (`build_run_honesty_block`) voids the declaration
   (`nothing_new.note_run_admission`) before the model is even asked.
   **A platform degradation is no failure of the run.** What the diagnostics advisor
   reports is told to the model beside the failures, and voids nothing: the number of
   THIS turn's failures is one function (`failure_context.count_turn_failures`), read by
   the directive as its total and by this guard. Found on dev on 2026-11-12 by the
   measurement bench's dry run, before any model was asked: one open incident on the
   instance's disk made the failures block non-empty, and that alone voided every quiet
   routine's silence.
5. **Never with « ask me before running ».** A proposal IS a notification, so the option
   would be stored and never read (ADR-184 pointing the other way): one rule
   (`schemas.delivery_refusal`) refuses the pair at creation and, on the RESULTING row, at
   update; the form switches the option off and leaves it unavailable. An update that
   sends the option as `null` is refused (422): the column holds a boolean.

**Along the way.** The response node and the stream that assembles `done` are frozen at
their size: both now call one function each in `services/answer_annotations.py`, which
composes the tone register and this declaration — a third declaration grows neither.

**Measured (2026-11-13).** How reliably the answering model writes the tag when it
should, and only then, is a property of the configured models. The bench,
`task routines:quiet:measure` (`apps/api/scripts/routines/measure_quiet_delivery.py`),
asks five routine runs whose data is stated — a search that found nothing, one that found
something, a watched condition unmet, met, and what the previous run already reported —
in both execution modes (the pipeline's data, and the answer of the ReAct loop a routine
runs by default), through the response node's own functions inside `quiet_run_scope`:
the prompt is production's, instruction included, and the declaration is read by the
production seam. The platform is stated too (nothing degraded): a live degradation reaches
the answers — dev's open disk alert did — and would be one more variable. The column to
read first is the missed notification, a silence where the owner had to be told.

Three families × two modes × five scenarios × five runs, 0.60 € in all:

| Instruction | Missed notifications | Needless notifications |
|---|---|---|
| First wording (« nothing new or noteworthy ») | 0 | 34 of 60 |
| Judged against the routine's own instruction, with examples outside the bench | 0 | 20 of 60 |
| The same, plus a reminder in the last message | **5** | 0 |

The second wording ships: two families stay silent exactly when they should (20 of 20
each), the third never writes the tag — the safe failure, its owner notified as before.
The reminder in the last message made that third family write the tag on an overdue task
too: rejected, since one missed notification costs more than every needless one.

**Rejected.** A marker in the visible text (the person would read it, and every surface
would have to hide it). A second model call classifying the answer (a cost per run, and a
second opinion on what the first model already knows). Comparing an answer with the
previous one in code (two wordings of the same facts differ). Hiding the run from the chat
(a switch removes a capability, never the record — ADR-280).

Guards: `tests/unit/domains/agents/services/test_nothing_new.py` and
`test_answer_annotations.py`, `TestARoutineToldToNotifyOnlyOfSomethingNew` in
`test_out_of_turn_run.py` and in `test_scheduled_action_executor.py`,
`TestARoutineIsToldOnlyOfSomethingNewOrProposesFirst` (`test_service.py`), and the form in
`ScheduledActionsSettings.test.tsx`.
