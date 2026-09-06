# ADR-268 — One recurrence engine, two consumers, and a reminder that can repeat

**Date**: 2026-09-06 · **Status**: Accepted · **Amends**: ADR-051 (reminder notifications), ADR-198 (one run per local day), ADR-265 (routine week timeline)

## Context

### What the schedule could say, and what it could not

A routine stored three columns — `days_of_week`, `trigger_hour`, `trigger_minute` —
and the next instant came from an APScheduler `CronTrigger`. That shape could express
"weekdays at 08:00" and nothing else: no single occurrence, no "every other Tuesday",
no "the 2nd Monday of the month", and above all **no second time in the same day**.

A reminder stored one instant and was deleted after notification. It could not repeat
at all.

Two measurements decided the engine rather than a preference:

- **APScheduler 3.11 skips a whole day when the daylight-saving gap opens at
  midnight.** Over every IANA zone and every 2026 transition: 2 112 slots shifted by
  an hour, **72 skipped entirely**, all in the 00:00-00:59 hour of the six zones that
  change at midnight (Santiago, Havana, Cairo, Beirut…). That is 142 runs lost per
  year across 73 zones, `Europe/Paris` included.
- Asking a trigger "which day comes next" is what makes that reachable. `dateutil.rrule`
  enumerates calendar DAYS and the engine localises each moment with `fold=0`, so the
  question is never asked.

### The decision this reverses

The reminders domain deliberately had no management surface. Its router said so in
its own docstring: *"`PendingReminderItem` carries three fields on purpose: the ones
an edit or a snooze would need are absent, so this surface cannot drift into the
management UI the domain refuses."* A project memory dated 2026-04-20 said the same,
and added: for anything recurring, point at scheduled actions.

The owner reversed it on 2026-09-06: a schedule someone configured once must be
visible and changeable without asking for it in prose.

## Decision

### 1. One recurrence, stored the same way everywhere

`src/core/recurrence` holds the vocabulary (`RecurrenceSpec`), the engine, the
sentence (`describe`, six languages) and the three questions a scheduled thing asks
(`week_slots`, `served_slot`, `rearm_after`). Both domains store it in a JSONB
`recurrence` column.

The model is a product: **which calendar days × which moments inside them**. The two
axes are independent, which is what makes "every Tuesday at 08:00 and 18:00" a shape
rather than a special case.

**`anchor_date` is mandatory.** Without it, "every 3 days" resolved to "in 3 days"
from whatever instant asked, and "every other Tuesday" answered a different Tuesday
depending on the day it was read — the series was not a series.

**Caps are injected, never owned by the model.** `RecurrenceLimits` travels with the
caller: a routine runs an agent pipeline and is capped at 12 firings a day, a reminder
sends a notification and is capped at 48. One engine, two ceilings, no branch.

### 2. The post-it is a case of the general rule, not an exception

The scheduler asks `rearm_after` what to arm next and reads the answer:

```
None  -> DELETE
else  -> trigger_at = the instant, status = pending
```

A consumed single occurrence answers `None`, which **is** the historical
"delete after notification". A daily one answers tomorrow. A bounded series answers
`None` after its last instant. Nothing anywhere asks "does this repeat".

Two consequences follow:

- **A reminder's `trigger_at` stays NOT NULL**, unlike a routine's `next_trigger_at`.
  A reminder with no future does not exist — it is deleted (owner decision). A routine
  is kept and reads "finished", because its configuration is the thing of value.
- **`retry_count` is reset after every successful notification.** It never was: the
  row always died at that point. Left alone, a reminder firing every morning would
  accumulate three failures over months and delete itself.
- **Exhausted retries abandon the OCCURRENCE, not the series.** Three transient
  failures cost one morning, not a whole schedule.

### 3. One authority for when something fires

`POST /reminders` accepts **either** a `trigger_at` **or** a `recurrence`, never both.
Measured before the schema refused it: a payload saying "every day at 08:00" beside an
instant at 23:00 was accepted and the caller's instant won — the card announced 08:00,
the notification arrived at 23:00, and only the first re-arm corrected it.

`PATCH` refuses a `trigger_at` alone on a repeating reminder for the same reason: the
next re-arm reads the rule and discards the manual instant, so the change would appear
to accept itself and then undo itself.

### 4. A wall clock follows the person

A timezone change recalculates **every** routine and **every** reminder, single
occurrences included (owner decision). This CHANGES reminder behaviour — the instant
used to be frozen at creation — and buys one rule instead of two.

The composition lives in `infrastructure/scheduler/timezone_propagation.py`, not in
`users/service.py`: calling the two domain services from there closed a
`reminders<->users` cycle, and the cycle ratchet is shrink-only whatever twins it
already tolerates.

A reminder that is DUE but not yet collected — the scheduler runs on a tick — answers
`None` and is left entirely alone, zone included: it is about to fire on arithmetic
done in its old zone.

### 5. The message knows whether it repeats

The reminder prompt ordered *"Mention when the request was made"* unconditionally. For
a daily reminder set three months ago, the model was instructed to open with "you asked
me three months ago…" on **every** occurrence.

Two versioned fragments replace that line. The recurring one forbids citing the setup
date and names the schedule instead. The scheduling rule has no branch on "is this
recurring"; this wording does, and legitimately.

### 6. Six languages, on a path that had two

Three fr/en branches lived in the notification path — elapsed time, the creation stamp,
and the neutral persona — plus the header above recalled memories and, worst,
**the fallback notification body sent when generation fails**. Four readers out of six
received English, and on the fallback path an entire English notification precisely
when something had already gone wrong. All five now read the central tables.

## What was rejected

- **A nested `RecurrenceSpec` as a tool parameter.** Measured 2026-09-06: across 109
  manifests, 295 of 296 parameters are scalars or arrays, and the catalogue's own
  compaction flattens a referenced sub-model — `times` and `end` are published as
  `{"type": "string"}`. A tool declaring the spec would announce a contract the
  validator refuses, which is worse than announcing none.
- **Teaching the chat tools without a corpus first.** Guessing at what a model produces
  is how a planner learns a dead end. (Superseded below: the corpus now exists.)
- **Keeping an exhausted reminder as "finished".** Symmetric with routines, but it
  would make `trigger_at` nullable, add a state every reader must handle, and let dead
  rows accumulate with no purge.
- **A snooze.** Not asked for; a schedule change already does it, and a snooze would
  need to say which occurrence it moves.
- **Widening the cycle baseline** to admit `reminders<->users` because its twin is
  tolerated.

## Consequences

- 384 frozen cron cases prove the engine loses nothing the old one produced; the
  migration was verified over seven zones in strict JSON equality, including the two
  Paris seasons, Kathmandu's `+05:45` and Chatham's `+13:45`.
- The generic editor mounts unchanged in both screens; two guards assert it
  (`core/recurrence` imports no domain and no configuration; the React editor imports
  nothing from a consumer), and each was verified by reintroducing the defect.
- `core/recurrence` must stay importable with no environment. Reaching for
  `core.time_utils` there is not merely impure: `core.constants` reads
  `RecurrenceLimits` from that package, so the chain closes on a partially-initialised
  `core.config` and **nothing boots**.
- The demonstrator exposes the reminder CRUD, as it exposes the routines': a visitor
  reaches every feature their own account owns.
- The listing is still never a history, and there is still no snooze and no
  acknowledgement. The guard that asserted "no edit either" was narrowed, not deleted.

---

## Amendment, 2026-09-06 — saying it out loud

The two chat tools now take a schedule. The decision above stands ("no nested spec"),
so the SPOKEN surface is **flat**: one named parameter per question a person answers,
declared once in `registry/recurrence_parameters.py` and translated in exactly one
place, `core/recurrence/dictation.py`. The stored vocabulary is unchanged — this is a
projection, in the same sense the `relative_trigger` mini-language already was.

**Each tool publishes ITS OWN bounds.** A routine may fire 12 times a day and step no
faster than 15 minutes; a reminder gets 48 and 5. Both numbers come from the same
`RecurrenceLimits` the validator applies, so what the planner reads is what will be
enforced — and out-of-bounds values are CLAMPED before validation rather than reported
(verified through the planner's own clamp: a routine asking for a 5-minute step gets
15, a reminder keeps 5).

**One authority for when.** `create_reminder_tool` now takes three mutually exclusive
ways to say it — a single instant, a schedule, or a FOR_EACH expression — and refuses
two together, exactly as the API layer does. A repeating reminder is also confirmed as
a SCHEDULE ("Rappel récurrent créé : tous les jours à 08:00"), not by naming its next
instant, which reads as a one-off.

### Measuring the transcription, without making it a gate

The corpus (`transcription_corpus.json`) holds 18 families × 6 languages = 108
utterances, each with the parameters a correct transcription produces and the LOCAL
wall clocks it must fire at. It feeds two consumers:

- a **unit test**, in CI, with no network: parameters → spec → instants, compared to
  wall clocks a human can verify by eye;
- an **on-demand script** (`task recurrence:corpus:measure`) that replays the
  utterances through a real model.

The script is not a test, and that is deliberate: this repository's CI holds no
provider key, no test in it calls a provider, and the F006 allowlist is shrink-only —
a corpus of skipped tests would be new debt. The measurement is run on purpose and its
number published with its date and its model, the shape `mobile:probe` and
`llm:catalogue:fetch` already use.

**The oracle is the instants, not the parameters.** A model that says
`repeat=weekly, weekdays=[1..5]` where the corpus says `repeat=daily` is not wrong, and
comparing fields would report a failure for a right answer — the invented diagnosis
ADR-182 removed.

### The measurement, 2026-09-06

`openai / gpt-5.6-luna`, reasoning level `none` — the planner slot's own
production configuration — over the 18 families × 6 languages:

| | exact |
|---|---|
| **total** | **105 / 108 (97 %)** |
| fr · en · es | 18/18 each |
| de · it · zh | 17/18 each |
| families perfect in all six languages | 16 / 18 |

The three misses are soft, and none is a wrong schedule:

- *"ogni 15 giorni alle 9"* and *"每15天上午9点"* transcribe the shape correctly
  (`daily`, `repeat_every=15`, `09:00`) but omit `starting_on`, so the series
  anchors on the day it was described and the first firing lands fifteen days
  out instead of tomorrow.
- *"am 31. jedes Monats"* becomes `month_days=[-1]` — the LAST day rather than
  the 31st. The two coincide in seven months and diverge in the other five.

**Two corrections were made to the harness and the corpus before this number,
and both were mine rather than the model's:**

1. The prompt named the DATE but not the TIME, so the model could not know that
   today's 08:00 had passed; "the next 3 times" then produced two. In
   production the model is given the current instant. Fixed, and
   `max_occurrences` now says it counts from `starting_on`.
2. The corpus expected an interval schedule to anchor on the day it was
   described — so *"tous les trois jours à 7h30"*, said at noon, would first
   fire three days later. Every one of the six languages produced the useful
   reading instead: the next available slot. **The model was right and the
   corpus was wrong**; the expectations were corrected on that semantics, not
   on the model's output.

A first run scored 0/108 and measured nothing: every call died on
`400 — 'top_p' is not supported`. The cause is recorded below.

### A reasoning model with no declared intent refuses every call

The adapter strips the sampling parameters a reasoning model cannot take
(`top_p`, `frequency_penalty`, `presence_penalty`) — but only when a reasoning
intent is present. With none configured, `top_p` reaches the provider and every
call fails.

Measured 2026-09-06 on `gpt-5.6-luna`: intent absent → `top_p=1.0` on the wire →
400; intent `none` or `low` → `top_p` dropped → success. **Latent, not live**:
all eleven production slots on a gpt-5.6 model carry an explicit intent, and
the three slots with a null one (`evaluator`, `image_generation` on
`gpt-image-2`, `web_search_agent`) point at no reasoning text model. It fires
the day an admin points one of them at a `gpt-5*` or `o*`. Same class as
ADR-267, and left for its own change rather than folded into this one.

### A declaration that had stopped being true

`create_reminder_tool` declared `mutation_policy="draft"` and wrote immediately. `draft`
is pass-through in the effect gate — precisely because a draft only BUILDS the
confirmation someone will answer — so a reminder created by conversation was **neither
asked for nor recorded** in the effect register, on a tool whose declaration said the
opposite.

It is now `reversible` (owner decision): the write happens without asking, exactly as
before, and it is recorded. Creating a reminder is anodyne and already undoable; the
DELETION is the step that asks, and it already did. The policy required an effect label,
which the boot assert would otherwise have refused to start without.

Two smaller repairs on the same path: the tool's parameter descriptions were in French
while ADR-256 mandates technical English for what the model reads (the manifest's were
already English, so the two execution modes described the same parameter differently),
and `tests/agents/` runs in CI but in neither the pre-commit hook nor `ci:fast`, so it
is run explicitly before this lot is called done.

## Amendment, 2026-09-06 — a stored selector is a read selector

A cold adversarial review of the whole component, after every gate was green, found
one defect class the tests had no reason to look for: **the model accepted day
selectors the engine never reads**.

The engine builds one `rrule` per frequency and hands it only that frequency's own
selector. Everything else was accepted, stored, returned by the API, rendered by the
editor — and dropped. Measured on the code as shipped:

| What was stored | What was shown | What actually fired |
|---|---|---|
| `daily` + `byweekday=(1..5)` | "Tous les jours" | every day, weekend included |
| `monthly` + `bymonth=(1, 7)` | "Le 15 de chaque mois" | twelve times a year |
| `weekly` + `bymonthday=(15)` | the weekly sentence | the day of month ignored |

This is ADR-184's trap pointing the other way. There, a bound was **enforced without
being published**, so the planner could not obey it. Here a value is **published
without being enforced**, so a producer believes it was obeyed. Both end the same way:
the system does something other than what the value says, and nothing anywhere reveals
the gap.

It was reachable from the chat. "Every weekday at 8" is very plausibly transcribed
`repeat=daily, weekdays=[1,2,3,4,5]` — and the reminder rang on Saturday.

**The rule now has one home and two more layers behind it.**

- `SELECTORS_READ_BY` in `core/recurrence/spec.py` says what each frequency reads, and
  the model refuses anything else. That is the invariant, and it holds for every writer
  including the REST API. It cost nothing to adopt: both migrations write clean shapes,
  and no row in any database violated it (verified before the change, not after).
- `core/recurrence/dictation.py` **repairs what is mechanically repairable** and refuses
  only what would need an intention — the doctrine `parameter_bounds` already applies to
  out-of-bounds numbers. At `repeat_every=1`, a daily rule restricted to named days IS
  the weekly rule on those days, and a monthly rule restricted to named months IS the
  yearly one; both are exact identities, so both are rewritten. An interval breaks the
  identity — one period in three is not one week in three — so that case is refused
  instead of guessed. **The repair is visible**: the confirmation is built by `describe`,
  so "every weekday at 8" now answers *"En semaine, à 08:00"*.
- `lib/recurrence.ts` clears, on a frequency change, every selector the new frequency
  cannot read. Without it the editor would have sent a residue the API now refuses, and
  the reader would have met a validation error for a choice made in one click. The two
  tables cannot be imported across languages, so a test parses both and compares them.

### Three defects found in the same pass

**A yearly sentence named only its first month and its first day.** `_calendar_clause`
read `bymonth[0]` and `bymonthday[0]`, so "the 15th of January and July" rendered
*"Tous les ans, le 15 janvier"* — July fired and nothing on screen said so. Worse than
the first defect, because there the engine was wrong and here the engine was right and
the sentence lied. Both axes are joined now, as the monthly clause already joined its
days.

**Two languages marked a day of month, and the mark sat in the sentence.** German writes
an ordinal point and Chinese appends a day classifier; carried by the template, they
were applied once after a whole list — *"Am 1 und 15. jedes Monats"*, one ordinal for
two ordinals. The mark belongs to the NUMBER, so it is a `day_number` template per
language, applied before joining. This one predates the lot: any monthly routine on two
days of the month was already worded wrong in German and Chinese. Every single-day
sentence is byte-identical to before, pinned in the six languages.

**The translation did not keep its own promise.** `recurrence_from_parameters` documents
`Raises: RecurrenceError`, but the structural refusals are raised inside Pydantic
validators and come back wrapped in `ValidationError`. Seven families of refusal — "the
31st of February", a single occurrence given an interval, a weekday of 9 — walked
straight through both tools' `except RecurrenceError`: the tool raised instead of
answering, and the message that would have been relayed carried Pydantic's field names
and a documentation URL, which is precisely what an error payload returned to a model
must never contain. The wrapping is undone at the source, so one exception leaves the
function, as the contract always said.

### What is deliberately left

A yearly rule naming several months AND several days is a cartesian product, and no
wording in any of the six languages makes *"le 1 et 15 mars et novembre"* unambiguous.
It is now COMPLETE — nothing is hidden — which is the property that matters; making it
elegant would mean a new sentence shape in six languages for a shape nobody has yet
asked for.

## Amendment, 2026-09-06 — the two test-plan items that had no coverage

Answering "is anything left?" against the design's own test plan (§9, thirty
items) rather than against memory found two that were never covered.

**Test 25 — axe on both sections at 390 px.** The phone viewport was scanned,
but on the *Appearance* section: neither recurrence section was. They mount the
SAME editor, and it is the densest control the settings pane carries — a
frequency select, an interval, a day picker, a list of times and an end rule, in
a drill-down pane 390 px wide — so a violation there lands on both features at
once. The journey exists now, and it was **executed**: pointing Playwright at
the dev container's server (`E2E_BASE_URL`, no managed build) sidesteps the
host's build defect entirely, and the whole suite — 15 journeys — passes in 1.2
minutes. Nothing was shipped unverified on the strength of "CI will tell us".

**Test 30 — an unclear rhythm is asked about, not guessed.** "Remind me often"
names no frequency. Choosing one silently commits the reader to a rhythm they
never asked for, on a capability that then acts by itself every day until they
notice; the failure is not a wrong answer, it is an unnoticed one. The
instruction now travels with the `repeat` parameter — the one place the producer
reads (ADR-184) — and a test asserts it reaches BOTH tools in BOTH execution
modes, since the manifest feeds the planner and the signature feeds ReAct, and a
rule present in one only is a rule that applies in one mode only. Whether a
given model obeys it is a MEASUREMENT and belongs to
`task recurrence:corpus:measure`; asserting it here would pin a provider's
behaviour to a unit test, which ADR-155 is precisely about not doing.

## Amendment, 2026-09-06 — second cold review, five more findings

A second adversarial pass, on the surfaces the first one had not opened:
the executor, the routers, the migration's downgrade, the prompts, and the
timezone composition. A scan for the classes CLAUDE.md forbids — in-place JSONB
mutation, bare enums in `case()`, naive datetimes, empty `except`, raw
`HTTPException`, `print`, hardcoded timezones — came back clean across the whole
perimeter; what follows was found by reading.

**The re-arm was computed at five call sites.** Every exit of the executor —
condition not met, proposal, pending HITL, success, final failure — called
`rearm_after` with the same three arguments, in five literal copies. Nothing was
wrong; the shape was. It is ADR-248's second invariant: a rule in five copies
gets changed in four, and the exit nobody updated re-arms differently from its
siblings with nothing to reveal it. One `_next_trigger` helper now, and an AST
test that fails if a second call site appears. The file lost 18 SLOC on the way.

**A cleared end date stopped the form without saying why.** `recurrenceIsComplete`
refuses an empty `on_date` — the column cannot hold one — so the save went
`aria-disabled`, and `validationError` had no message for it. A text input is
legitimately empty while someone retypes a date, so this was reachable by
ordinary use: the reader clears a date and the form goes quiet. The count field
could not reach it (its handler floors at 1). One message, six languages.

**The prompt fallback contradicted the versioned fragment it backs up.**
`reminder_origin_recurring.txt` forbids naming when a reminder was set up — right
for a post-it, wrong on the ninetieth morning. The inline fallback stated it
unconditionally, so losing one file would not have degraded the wording, it would
have reintroduced the defect the lot removed, on every recurring reminder.

**And that fallback made the reader's words part of its own template.** It was an
f-string interpolating `reminder_content`, and the result was then passed to
`.format()` — so a reminder saying *"payer la facture {montant}"* raised
`KeyError: 'montant'`, which the per-reminder handler turns into three retries and
an abandoned occurrence. Measured, then fixed by shaping the fallback like the
versioned file it backs up: a module constant with PLACEHOLDERS, filled by the
same call. The versioned prompt never had the defect, because there the content
is a keyword argument.

**Timezone propagation caught its failures but not its transactions.** The
contract says neither surface's failure aborts the profile update; a caught
exception does not deliver that, because a failed statement poisons a PostgreSQL
transaction. A reminder whose flush failed would have taken the routines just
moved — and the profile update that triggered all of this — down with it on the
caller's commit. Each surface runs in its own savepoint now, the way
`scheduled_actions/runs.py` writes its history, with `test_begin_nested_contract.py`
already holding the primitive's semantics against a real database.

### Checked and clean

Ownership on every reminder route (a row owned by someone else answers 404, never
403); the exact total behind the paged list is an aggregate, not a page length
(ADR-185); the downgrade refuses every recurrence the cron columns cannot express,
and its one remaining case is already blocked upstream; the briefing card warns
that cancelling a repeating reminder removes the SERIES; the weekly grid reads the
engine rather than a second implementation.

## Amendment, 2026-09-06 — the form people actually fill in

Four measured layout defects and two structural ones, all found by looking at the
rendered screen rather than at the source.

**The unit was 330 px from its field.** `Every [1] ......... week(s)`: every
`Input` wraps itself in `FieldFrame`, which is `w-full`, and inside a flex row
that wrapper claims every spare pixel. The `w-20` on the input looked correct and
was irrelevant — it bounded the field, not the box the row measures. The class
that looks wrong is not always the one that is.

**The weekend trailed the working week.** Seven day buttons in one wrapping row.
A zero-height flex break after Friday groups Saturday and Sunday — a break rather
than a second container, so at 320 px the working days still reflow freely while
the weekend keeps starting on its own line.

**The stepped window read as one strip**, and broke at whatever point the widths
happened to fall. It asks two questions — how often, then between when and when —
so it takes two lines, and the step control grew to hold its longest label in
every locale (`360 minutes`, `360 Minuten`). The bounds then lost their captions
entirely: `08:00 to 18:00` is one phrase, with the joining word decorative and
each clock keeping its `aria-label`, because removing a VISIBLE caption must
never remove an accessible name.

**And the form was one monochrome column of eight fields.** Not a matter of
taste: the charter already mandates that a title carries an icon in the theme
colour, and this form had no titles at all. It has two named groups now — "what
to do", "when" — and the heading pattern, written 68 times by hand across this
application with no shared component, finally has one (`ui/form-section.tsx`).
`fieldset`/`legend` rather than a styled `div`, so the fields become groups
assistive technology announces.

**The rarely-changed settings fold away** (owner trial): interval, end rule and
anchor sit behind one disclosure, taking the form from eight visible questions to
five. Two rules make folding safe, and the second was found by a test rather than
by review:

- the fold **opens itself** on any non-default value — a routine already saying
  "every third week" that rendered as a plain weekly rule would read as an
  interval silently lost;
- the field that CARRIES the answer never folds. For a single occurrence the
  anchor is not a setting, it is the date the reminder fires; it was folded in
  the first draft, and an existing test refused it.

**One boundary held, and moved a component.** Importing `SettingsDisclosure` into
the generic editor was refused by `genericity-boundary.guard.test.ts` — the
editor must not depend on a consumer. The real defect was the component's
address: no settings dependency, and three non-settings domains already importing
it. It is `ui/disclosure.tsx` now, across its 22 call sites. The guard did not
just block a mistake; it named a misplacement that predated this work.

### The template covers the routine form too

The reminder form asks two questions; the routine form asks three. The third —
its trigger, the condition gating it, and whether it proposes before acting —
stayed a bare column of controls below the two named groups. It is
`How it runs` now, with the same heading pattern, so no field on either form
sits outside a named group.

One line moved with it: the sentence explaining what the trigger does with the
chosen time used to sit BETWEEN the two groups, the last element outside the
template. It explains the trigger, so it belongs beside it.
