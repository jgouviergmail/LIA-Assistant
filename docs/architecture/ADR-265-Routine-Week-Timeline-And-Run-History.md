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
