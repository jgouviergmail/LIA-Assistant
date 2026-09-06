# Generic Recurrence — Design

**Status:** proposed (owner-approved framing, 2026-09-06)
**Supersedes:** the cron-based schedule of `domains/scheduled_actions`
**Amends:** ADR-140 (chat-piloted automations), ADR-175 (N-07 trigger kinds), ADR-265 (weekly timeline)

## 1. Problem

A scheduled action can only run **once a day, on a set of weekdays**. The owner
needs single occurrences, several times a day (fixed times or a step from a
start time), intervals of weeks/months/quarters/semesters/years, and a day of
the month. Reminders must gain the same vocabulary plus a management surface.

Two things make this more than a feature addition.

**The engine cannot express half of it.** `CronTrigger` knows no interval
("every other week"), no single occurrence, no anchored phase.

**The engine is defective, measured.** Comparing it against a candidate engine
over 598 IANA zones × 24 hours × 16 reference dates found 142 runs per year
silently dropped across 73 zones, at the 00:xx and 23:xx hours, including
`Europe/Paris` — which is `DEFAULT_USER_DISPLAY_TIMEZONE`:

```
Europe/Paris, daily 00:30
  ran 2026-03-29 00:30  ->  compute_rearm_trigger armed 2026-03-31
  2026-03-30 00:30 exists (+02:00) and is lost, silently
```

APScheduler skips that day; `_skipped_gap_run` cannot see it because its
predicate is "the wall-clock time does not exist" and here it does. Worse, the
engine contradicts itself: `week_slots` **draws** the 30/03 cell that no run
will ever serve — a permanently white cell in the ADR-265 grid.

## 2. Decisions taken by the owner (2026-09-06)

| Decision | Consequence |
|---|---|
| A reminder becomes **durable** | It carries the same recurrence; `once` is a recurrence. The row is deleted at fire time only when nothing follows. |
| **No new header destination** | `dashboard-nav.ts` documents 7 labels as the measured maximum. Reminders get a settings section, reachable from the rail, the settings search and the notifications hub. |
| **Two distinct settings sections** | "Actions planifiées" stays; "Rappels" is added. The recurrence editor is one component mounted twice. |
| **Distinct caps + a visible counter** | Routines run an agent pipeline, reminders send a notification. The form states what a setting costs per day. |
| **No reminder run history** | `last_notified_at` + a counter on the row. No new table. |
| **End of series is in scope** | never / until a date / after N occurrences. |
| **Genericity is a requirement** | The component must serve future consumers, not only these two domains. |

## 3. The model — `[calendar days] × [times of day]`

This shape is not a preference: it is what measurement H-perf forces (§4.5) and
it happens to match how a recurrence is spoken.

```
RecurrenceSpec
  freq          once | daily | weekly | monthly | yearly
  interval      N >= 1                  quarterly = monthly x3, semester = x6
  anchor_date   THE date for `once`; otherwise "starts on", and the phase
  byweekday     [1..7]                  weekly
  bymonthday    [1..31, -1]             monthly / yearly ; -1 = last day
  nth_weekday   {nth, weekday}          monthly: "the 2nd Tuesday"
  bymonth       [1..12]                 yearly
  times         at: [{h,m}, ...]  |  every: {step_minutes, from, to}
  end           never | on_date | after_count
```

`times.every` is **stored as declared** and materialised on every computation
(pure, bounded). Storing a derived list beside the parameters that produced it
would be a second authority.

**`anchor_date` and "starts on" are the same field.** Measured (§4.1): without
an anchor, "every 3 days" resolves to "in 3 days" on every call. With
`interval = 1` the anchor still means something — the series starts there — so
one field, one meaning, shown only when it changes an outcome (`once`, or
`interval > 1`, or a future start).

## 4. Invariants — each one paid by a measurement

### 4.1 An interval has an anchor, or it is not a series
Without `anchor_date`, "every other Tuesday" answered 15/09 from one reference
and 22/09 from another; "every 3 days" answered "in 3 days" from every
reference; "quarterly" slid from December to January to February with the day
it was read. **`anchor_date` is mandatory, always.**

### 4.2 Days are enumerated, never delegated to a cron
This is what removes the 30/03 defect (§1). The engine walks calendar days and
localises them; it never asks a cron which day comes next.

### 4.3 Naive wall clock, then `fold=0`
Preserves "08:00 where I live" across clock changes, and reproduces the shift
the current engine already documents. Additionally it serves the midnight-gap
day (Santiago) that the cron skipped.

### 4.4 Sort and de-duplicate **by instant**
On a sub-daily rule the spring transition produces an inversion
(02:30 → 01:30Z, then 03:00 → 01:00Z) and a duplicate (02:00 and 03:00 on one
instant). Ordering by wall clock would fire twice and go backwards.

### 4.5 The times of a day are finite and bounded
`MINUTELY` costs 1.9 s per occurrence with a 2024 anchor and 7.9 s with a 2016
one. It is not offered. A day's times are a bounded list, and every computation
costs ~0.05 ms.

### 4.6 The bound is strict (`> after`), in one place
Production currently mixes both: the listing is inclusive of its reference, the
re-arm forces strict with `+1 µs`. One convention, one implementation.

### 4.7 Re-arm after `max(due_at, now)`
Measured: after a 3-day outage, re-arming from `due_at` fired **145 runs
back-to-back**; from `max(due_at, now)`, exactly **1**. A missed slot is missed
— the system never replays three days of agent pipelines at restart. This
preserves the semantics of `compute_next_trigger_after_execution`.

### 4.8 An impossible calendar date is refused at construction
"30 February" passed validation, cost 166 ms and produced nothing, which would
store `next_trigger_at = NULL`: a dead routine that does not say so. The
validator refuses 30/31 February and the 31st of April, June, September and
November. Rare-but-legal rules stay instant (29 Feb every 4 years, 5th Monday
every 12 months, the 31st every 6 months: 0.1 ms each).

### 4.9 The anchor is a phase, never a starting point to iterate from
Walking the rule from the anchor cost 60 ms for one weekly grid with an
8-month-old anchor. Fast-forwarding the day rule brings a **4-year-old** anchor
to 35.8 ms. The exception is an `after_count` series, whose count is defined
from the beginning — and which is bounded by that very count.

### 4.10 A per-day count is announced as an upper bound
`per_day()` declares 24 for an hourly rule; the spring day really fires 23. The
UI says "up to N times a day", never an exact number a clock change denies.

### 4.11 A manual run serves the LATEST passed slot of its local day
`served_slot` is undefined once a day has several slots: a manual run at 14:00,
with 08:00 and 12:30 already passed, could claim either. The rule is **the
latest passed slot of the local day**, and none at all when no slot has passed
(a rehearsal, `slot_at` NULL).

Two properties make this the right extension rather than a new rule. With one
slot a day it reduces **exactly** to the current behaviour, so it is
retro-compatible by construction. And it needs no database read: when a run
already serves that slot, `fold_runs_by_slot` keeps the LATEST run per slot,
which is already ADR-265's rule.

`local_day_slot` therefore returns a **list**, and `served_slot` picks from it.

## 5. Genericity — the boundary

The component knows nothing about routines or reminders. Two rules carry that.

**Caps are injected, never hard-coded.** This is what lets a routine allow 12
runs a day and a reminder 48, with one engine — and lets a future consumer
bring its own.

```
src/core/recurrence/            no import from domains/
  spec.py      RecurrenceSpec (Pydantic v2) + RecurrenceLimits (injected)
  engine.py    occurrences · next_occurrence · slots_between
  display.py   describe(spec, locale) -> the sentence, in the 6 languages

apps/web/src/lib/recurrence.ts                 types + pure helpers (mirror)
apps/web/src/components/recurrence/
  RecurrenceEditor.tsx     props: value, onChange, limits, timezone
  RecurrenceSummary.tsx    the sentence + the next real dates
```

**Labels live under a `recurrence.*` namespace**, never under
`scheduled_actions.*`: otherwise reminders would reuse keys named after
automations, and the third consumer would inherit the first one's vocabulary.

Placement follows the ADR-245 precedent (`core/reasoning_intent.py`, "one
stored shape for every provider"): pure computation with no I/O belongs in
`core/`. Three files, so none approaches the 600 logical SLOC cap.

Plausible future consumers, deliberately **not** implemented: recurring
calendar events, periodic reports, diagnostic probes, habits.

## 6. Backend impact

`recurrence` is a JSONB column (always reassigned as a new dict — JSONB rule),
and `next_trigger_at` becomes **nullable**: NULL means nothing follows. The
legacy columns are **dropped** — no dual authority.

| | Actions planifiées | Rappels |
|---|---|---|
| Recurrence | `RecurrenceSpec` | the same |
| Series end | row kept, status `completed` | row **deleted** — a reminder stays a post-it |
| History | `scheduled_action_runs` (unchanged) | none: `last_notified_at` + counter |
| Cap per day | low (agent pipeline) | high (a notification) |

Files: `scheduled_actions/{models,schemas,service,repository,week,runs}.py`,
`schedule_helpers.py` (absorbed by the engine), `reminders/*`,
`scheduler/{scheduled_action_executor,reminder_notification}.py`,
`agents/tools/{automation_tools,reminder_tools}.py`, the two catalogue
manifests, `drafts/{display,preview_renderer}.py`, one Alembic migration.

**ADR-265 keeps its rule** — a cell takes the last run whose `slot_at` equals
the week's instant — but a cell is now keyed by **(day, instant)**, not by day.

## 7. Frontend impact

Two decisions carry the simplicity the owner asked for.

**Two questions, never a form**: "which days?" then "at what time?" — the
structure of the thought, and of the model.

**The sentence and the dates under the form**: "Toutes les 2 semaines, le
mardi, à 18:00 — jusqu'à 1 fois par jour", then the three next real dates. The
same device makes a chat transcription verifiable inside the HITL draft.

`ScheduledActionsSettings.tsx` is **not** in `.cc-baseline.json`: putting the
editor inside it would fail the shrink-only complexity ratchet. The editor is a
standalone component with its logic in pure helpers.

**Mobile parity is a requirement**: every control available on desktop is
available on a phone. `MemorySettings.tsx:395` records the precedent — an
export was `hidden lg:flex`, amputated on mobile and tablet.

### 7.1 Located regressions — found by inventory, each verified

| # | Regression | Evidence |
|---|---|---|
| R1 | `chipKey(actionId, day)` collides as soon as a routine fires twice a day | key must carry the instant |
| R2 | `cells.find(c => c.day === day)` keeps only the first occurrence | one cell per (day, instant) |
| R3 | `useScheduledActions.ts:52` declares `next_trigger_at: string` **not nullable**, while `ScheduledActionsList.tsx:29` and `types/briefing.ts:194` declare it nullable | three declarations, two agree, one does not |
| R4 | `ScheduledActionsSettings.tsx:221` falls back to `[action.next_trigger_at]`, and `renderOccurrences` only filters `NaN` | `new Date(null)` is **1970-01-01** and `isNaN` is false — a finished series would announce "next run: 01/01/1970" |
| R5 | `repository.py` orders by `next_trigger_at.asc()`; NULLs then sort last implicitly | make `NULLS LAST` explicit rather than inherited |
| R6 | `local_day_slot` returns a single instant (§4.11) | signature becomes a list; two callers follow |

Each is fixed with a test that fails first.

### 7.2 The recurrence sentence is composed, never enumerated
`format_schedule_display` today spells three named shapes plus a day list. The
new space is combinatorial (freq × interval × selectors × times × end) and one
i18n key per shape would explode across six languages. The sentence is
**assembled from parts** — a frequency clause, a selector clause, a time
clause, an end clause — each a key, in the `recurrence.*` namespace.

Wiring for the new section: `settings-sections.ts`,
`settings-section-registry.tsx`, `settings-search.ts`,
`settings-section-icons.ts`, `capability-sections.ts`, `NotificationsHub.tsx`,
plus the 6 locales.

## 8. Migration and non-regression

The migration is a strict equivalence, no interpretation:

```
days_of_week + trigger_hour + trigger_minute
   -> {freq: weekly, interval: 1, byweekday: days_of_week,
       times: {at: [{h, m}]}, anchor_date: created_at::date}
```

Non-regression is established on **76 902 comparisons**, in two independent
places:

| Surface | Comparisons | Identical | Differing | Direction of every difference |
|---|---|---|---|---|
| Next occurrences (`compute_next_triggers_utc`) | 384 | 381 | 3 | the current engine skips 30/03 |
| **Weekly grid (`week_slots`, ADR-265)** | 76 518 | 76 492 | 26 | the current engine skips a cell |

In the grid comparison the "only OLD — the new engine would drop it" column is
**empty in all 26 cases**. The new engine loses nothing; it serves 26 slots the
current one skips.

This matters beyond the grid: a cell is coloured by the equality
`slot_at == the week's instant`, so an engine that moved a single instant would
un-match every past run and blank the whole week. It moves none.

The differential simulation is kept as a test, over every IANA zone: **any
divergence must be a known defect of the current engine, never a new one.**

## 9. Test plan

Enriched during implementation, executed at review.

**Engine (unit, no database)**
1. Corpus coverage: the 17 requested formulations resolve to the expected instants.
2. Series stability: identical results from 60 different reference instants (§4.1).
3. `slots_between` ≡ `occurrences` on the same window (the ADR-265 equality).
4. DST: spring gap, fall repeat, midnight-gap zones, 30- and 45-minute shifts.
5. Strictly increasing, no duplicates, on sub-daily rules across both transitions.
6. Calendar edges: 29/30/31 of the month, 5th weekday, last weekday, 29 February.
7. End of series: `after_count` counts instants; `on_date` includes the last local day; an exhausted series yields nothing.
8. Validation refuses: interval 0, weekly without a day, monthly with both selectors, step below the floor, no time, `once` with an end rule, impossible calendar dates (§4.8).
9. Cost: a 4-year-old anchor stays under the grid budget (§4.9).

**Executor (unit + integration)**
10. One simulated year, tick by tick, on 12 configurations: every instant served exactly once, no skip, no double, no reordering.
11. Catch-up: a 3-day outage fires exactly one run (§4.7).
12. Re-arm, condition skip, propose-first, HITL skip and failure each leave the row coherent and one run row.

**Persistence**
13. JSONB round-trip: spec → column → spec, over every field.
14. `db:migrate:replay-check`, plus a differential over the dev database rows.
15. `next_trigger_at` NULL: excluded from the poll, drawn as "finished".

**Domains**
16. Reminders: `once` deletes the row at fire time, a recurring one re-arms, an exhausted series is deleted.
17. Caps: a routine refuses beyond its cap, a reminder accepts up to its own.

**Existing consumers — no regression**
18. Weekly grid: old vs new `week_slots` over every IANA zone; every difference must be a known defect of the current engine (76 518 comparisons).
19. `served_slot`: with one slot a day, identical to today's behaviour; with several, the latest passed slot; none passed, a rehearsal.
20. `next_trigger_at` NULL read by every consumer: briefing For-you, notifications hub, automation tool listing, settings card, ordering (`NULLS LAST`).
21. The five executor exits (success, failure, condition skip, propose-first, HITL skip) each leave one coherent row and one run row.
22. R3/R4: a finished series never renders 01/01/1970, and the TypeScript contract admits null.

**Frontend**
23. `chipKey` and the week cells with several occurrences a day.
24. The editor produces every corpus shape and refuses what the API refuses.
25. Mobile parity: every control reachable at 390 px; axe on both sections.
26. Live summary: sentence + next dates, and "up to N times a day".
27. The composed sentence: every freq × interval × selector × end combination renders in the 6 languages, no missing key.

**Transcription (LLM)**
28. A frozen corpus of formulations in the 6 languages, deterministic against the schema.
29. Real calls on the configured model: measure exact-transcription rate; failures correct the catalogue descriptions, never the assertion.
30. Ambiguous formulations request a clarification instead of guessing.

**Gates**: `task lint`, `task test:backend:unit:fast`, `task test:frontend`,
`task test:frontend:coverage`, `task ci:fast`, plus runtime proof in the Docker
dev containers.

## 10. Lots

| Lot | Content | Done when |
|---|---|---|
| 1 | `core/recurrence/` + its tests (tests 1-9) | Engine green, zero domain import |
| 2 | Migration + `scheduled_actions` on the engine | Tests 10-15, differential green |
| 3 | Executor, weekly grid, ADR-265 by instant | Tests 18-21, grid drawn |
| 4 | Reminders: durable, CRUD, section | Tests 16-17, 22 |
| 5 | `RecurrenceEditor` + the two sections + 6 locales | Tests 23-27 |
| 6 | Catalogue, drafts, transcription corpus | Tests 28-30 |
| 7 | ADR, docs, INDEX, `AGENTS.md`, release surfaces | `task lint:docs` green |

## 10bis. Known risks, and why they are already bounded

**Routines aligning on round slots.** ADR-254's rule — "periodic jobs that
share a divisor align forever" — applies here in a new way: several routines at
08:00, or a step of 30 minutes, put many pipelines on the same tick. Two
existing bounds already absorb it: `SCHEDULED_ACTIONS_MAX_CONCURRENCY` (4) and
`SCHEDULED_ACTIONS_BATCH_SIZE` (50). No new shaper is introduced; the risk is
recorded so a future spike is diagnosed rather than rediscovered.

**Cost per account.** The per-routine cap does not bound the account: 20
routines × 12 runs is a large theoretical daily total.
`UsageLimitService.is_user_blocked_for_llm` already gates every run, so the
ceiling exists and is enforced elsewhere — the form's per-day counter is what
makes it *visible* before the fact.

**Partial index with NULLs.** `ix_scheduled_actions_due` keeps rows whose
`next_trigger_at` is NULL, which the poll excludes anyway
(`NULL <= now` is unknown). The migration narrows the index predicate rather
than relying on that.

## 11. Out of scope

- RRULE / iCal export — the model is translatable to it; nothing is built.
- Recurring calendar events — a plausible consumer, not a deliverable.
- Reminder run history — the owner declined it.
- Event-driven triggers — ADR-175 phase 2, untouched.

## 12. Measurement appendix

| # | Measurement | Result |
|---|---|---|
| M1 | Corpus coverage, `dateutil.rrule` | 17/17, 0.03-0.5 ms |
| M2 | `byhour`/`byminute` cartesian product | 3 times → 6 runs a day |
| M3 | Sub-daily DST | 1 inversion, 1 duplicate per spring |
| M4 | `MINUTELY` cost | 1.9 s (2024 anchor), 7.9 s (2016) |
| M5 | Differential, 598 zones × 24 h × 16 dates | 142 runs/year dropped by the current engine, 73 zones |
| M6 | Re-arm vs grid coherence | `week_slots` draws a cell no run serves |
| M7 | Anchorless interval | series drifts with the reading date |
| M8 | Grid cost, 4-year-old anchor | 60 ms → 35.8 ms with fast-forward |
| M9 | Migration equivalence | 381/384 identical, 3 = the known defect |
| M10 | Executor, one year, 12 configurations | 12/12, 17 518 runs served exactly once |
| M11 | Catch-up after a 3-day outage | 145 runs vs 1 |
| M12 | Impossible date | accepted, 166 ms, silently empty |
| M13 | Declared vs real per-day count | 24 vs 23 on the spring day |
| M14 | **Weekly grid, old vs new, every IANA zone** | **76 518 comparisons, 26 differing, 0 lost by the new engine** |
| M15 | `served_slot` with several slots a day | undefined by the current helper |
| M16 | `new Date(null)` in `renderOccurrences` | 1970-01-01, not filtered |
