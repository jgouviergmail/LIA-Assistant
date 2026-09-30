# ADR-322 — One clock per routine: a schedule, or the system's checks

**Status**: accepted — 2026-09-25 (owner request: « for scheduled actions, when a trigger is defined the schedule is useless — it must then be disabled and the application must ignore it, and the other way round; offer the person a choice that then decides which fields to fill in »; owner arbitration Q1 = B: a condition routine has NO schedule; the system checks it at a cadence of its own per condition type — about ten minutes for mail, tasks, calendar and documents, an hour for the weather — day and night, with an optional last day; no quiet hours in this version)
**Amends**: ADR-175 (N-07 phase 1: « the clock stays the cron for both kinds » is withdrawn, and its set fingerprint becomes a fact ledger), ADR-281 (a mail watch loses its 09:00/17:00 schedule and its `SeriesEnd` for the system's checks and a last day; the push wake's arming is unchanged), ADR-265 (a condition routine's week shows the checks that FIRED; an unmet check writes no row), ADR-268 (a condition parameter is refused on a type that does not read it — the selectors rule), ADR-263 and ADR-272 (a check files its consultation and its spend), ADR-304 (the executor commits before the source answers), ADR-184 (the check interval and the daily cap are published because they are enforced; `within_hours` was published and not enforced)

## Context

A routine was either « time » or « condition » (ADR-175), but BOTH carried a
schedule: a condition was evaluated at each instant of the routine's
recurrence and at no other moment. Measured before the change:

1. **The schedule WAS the condition's clock.** The studio asked for a schedule
   and a condition side by side and said nothing of how they combined. The
   watch the briefing's « Watch » chip creates (ADR-281) was checked at 09:00
   and 17:00 only, so on an account with no push channel an awaited reply
   could wait sixteen hours.
2. **The ledger kept ONE fingerprint of the whole matching set.** Any change to
   the set read as a new fact, a set that SHRANK included — rare at two checks
   a day, the rule at one every ten minutes: an agenda watch would re-fire
   whenever an event ended, a task watch whenever a task was ticked off, a mail
   watch whenever one of two matching mails was read. Some facts were keyed on
   what the briefing DISPLAYS (« 09:00 tomorrow » becomes « 09:00 » at
   midnight): the same event, announced twice.
3. **Every unmet check wrote a run row** (`skipped_condition`): two a day then,
   144 a day per routine at ten minutes, for nothing that happened.
4. **`calendar_event.within_hours` was published and ignored** (1–48, default
   4 — the agenda fetcher's own 24 hours applied): ADR-184's trap pointing the
   other way.
5. **The evaluators claimed a bound they did not have**: « their Redis caches
   bound the provider-API cost ». Only the Gmail search is cached; every other
   source is a live read.
6. **A check was off the record.** It opened the person's mailbox, tasks,
   calendar or Drive outside any turn with no consultation filed (ADR-263), and
   a weather check on the Google provider — calls billed on the deployment's
   key — ran under no tracking context (ADR-272).
7. **A pending question counted as an execution.** A time routine skipped
   because its conversation held an unanswered question went through
   `mark_execution_success` — its count and its « last executed » moved though
   nothing ran — while `ScheduledRunOutcome` stated that the skips « count no
   execution ».

## Decision

1. **One clock per routine, chosen first.** `trigger_kind` decides: a `time`
   routine has a `RecurrenceSpec` and no condition; a `condition` routine has a
   condition and no recurrence. One rule states it
   (`schemas.trigger_mode_refusal`), read by the create schema and by the
   service's update — which sees the stored half of the pair the schema
   cannot — and the table holds it for every other writer
   (`ck_scheduled_actions_one_clock`, migration `3e625df0094a`). Switching mode
   drops what the OTHER mode stored, never what the payload sent: a payload
   carrying both clocks is refused, not trimmed. The studio asks « When does
   it run? » first and shows that mode's fields alone; the other mode's draft
   is kept while the dialog is open and never sent.

2. **The system's clock is declared once**
   (`domains/scheduled_actions/trigger.py`). `CONDITION_CHECKS` names, per
   condition type, the setting that paces it and the cache its source reads
   through — the Gmail search alone —, its completeness asserted at import
   (ADR-085). A check is never faster than that cache: a faster one would only
   re-read Redis and file a consultation for a mailbox nobody opened, so the
   interval is the larger of the two. Each routine keeps its own phase,
   derived from its id, on a grid anchored on the epoch: twenty watches
   created in one minute never check in the same second, and a check that ran
   late re-arms on the same grid. `TriggerPlan` is the one answer to « when
   does this routine next need the executor » — at creation, edit, re-enable
   and move of zone, and after every tick; a condition re-arms from NOW, so a
   missed check is not replayed. Two settings pace it:
   `SCHEDULED_ACTIONS_CONDITION_CHECK_MINUTES` (mail, tasks, calendar,
   documents) and `SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES` (the forecast comes
   in hourly or three-hourly slots, and a Google check is billed).

3. **An end, not a schedule.** `condition_config.until` is the last local day
   watched, that day included; the watch stops at the local midnight after it,
   built from the calendar rather than by adding 24 hours (a day of clock
   change lasts 23 or 25). A last day already over is refused where the person
   sets it — creating the routine, editing its condition — while renaming a
   finished watch still works. A watch past its last day has no next check,
   and the executor's existing sweep closes it (`close_finished`), exactly like
   an exhausted series; moving its last day later reopens it (ADR-281's rule
   on who closed it).

4. **A fact ledger** (`condition_ledger.py`, stored in `condition_state`:
   `seen`, `last_checked_at`, `last_check_error`, `last_fired_at`). A fact is
   new when its KEY was never seen. A key is what the fact IS — a message id, a
   task id and its due date (pushed back and late again is a lateness nobody
   was told about), an event id and its start, a file id alone (never its
   modification time: a document being edited would be announced at every
   check), a forecast's kind and local day — never a display string, even in
   a fallback — hashed, so the ledger holds no title, subject or address; the
   briefing's items now carry those ids and instants.
   A new fact the tick did not serve stays new (the daily cap, a pending
   question, a failed run); a fact still present is never evicted by the
   ledger's bound; a legacy fingerprint reads as having seen nothing, so the
   first check after the upgrade serves what it finds — announcing an awaited
   fact twice is recoverable, never announcing it is not.

5. **A daily cap on runs, never on checks**
   (`SCHEDULED_ACTIONS_CONDITION_MAX_FIRES_PER_DAY`): counted from the run
   history since the routine's local midnight (`FIRED_OUTCOMES`: a success, a
   failure, a proposal), never in a second counter beside it. A new fact past
   the cap stays new and runs at the next day's first check if it still holds.

6. **An unmet check is recorded on the routine, not in the history.** It
   re-arms and writes `last_checked_at` and, when the source could not be
   read, why — `not_configured` (the person can fix it) or `unavailable` —,
   both published with the routine; no run row. `skipped_condition` therefore
   has no producer any more: it stays readable until the retention purges the
   rows written before. A condition routine's week cells are the checks that
   FIRED, each at its own instant (`slot_at` is the check's start). A condition
   routine whose conversation holds a pending question re-arms with its facts
   still new and writes no row; a time routine keeps its `skipped_hitl` row
   and, as the enum always said, counts no execution.

7. **A check is on the record, and never raises** (`evaluate_condition`). It
   runs under the routine's own `TrackingContext` (`out_of_turn_spend`, run id
   `routine_condition_…`), so a billed weather lookup is attributed to its
   owner; it files ONE consultation under the surface `routine_condition` —
   `failed` when the source refused, nothing when there was nothing to open (no
   connector, no location); an unreadable source is an ERROR on the verdict,
   never « the condition is not met ». A weather check reads the forecast alone
   (`fetch_forecast_alert`: two provider calls where the card makes up to five
   — no city name, no air quality, no pollen). The calendar check reads the
   published window and ignores an event that has already started.

8. **No transaction across a wait** (ADR-304): the executor commits its reads
   before the source answers, before the model runs and before any push.

9. **Every reader asks the plan.** The studio card, the notifications hub and
   the chat's listing tool say when a routine runs through ONE sentence
   (`schedule_sentence`: the recurrence of a time routine; « Checked about every
   N min », then the last day, for a condition routine, in the six languages);
   the listing publishes the clock of a routine not yet created
   (`condition_check_minutes`, `condition_max_fires_per_day`), so the studio
   states the values the executor enforces (ADR-184); a condition routine
   publishes its interval and its last check, and its card offers « Check now »
   in place of « Test »; the « For you » card never names a condition
   routine as the next automation (its trigger is the next CHECK); a condition
   parameter is refused on a type that does not read it
   (`CONDITION_PARAMS_READ_BY`, ADR-268's selectors rule).

10. **The upgrade keeps what a schedule still meant — its end.** A series
    ending on a date keeps that date as `until`; a series ending after N
    instants (or a single occurrence) ends on the local day of its last
    instant, computed by the engine that armed it; a series with no end has
    none. A watch whose last day is over is closed by the next sweep; a running
    one is brought forward to its first check within ten minutes, spread at
    random so a deploy does not open every mailbox in the same second. The rows
    no writer should have produced are repaired rather than left to fail the
    constraint: a time routine carrying a condition loses it, a condition
    routine with no condition becomes a paused time routine marked in error.
    The downgrade gives each condition routine a schedule back — every day at
    09:00 and 17:00, ending on its last day — and loses two things, written in
    the migration rather than discovered: the invented hours, and a fact ledger
    the previous code cannot read, whose first check serves once what it finds.

**Found at the first HTTP proof, fixed and pinned**: a Python `None` on a
JSONB column is persisted as the JSON `null`, which `IS NULL` does not match.
Every time routine the service had ever created carried
`condition_config = 'null'`, and the new CHECK refused the first condition
routine created through the service. The three JSONB columns now store SQL NULL
(`JSONB(none_as_null=True)`), the migration repairs the JSON nulls, and a
PostgreSQL test creates both kinds and switches between them — no unit test
executes the INSERT.

Proven: the plan, the ledger, the refusals, the service's edits and the
executor's every exit (unit); on real PostgreSQL, the migration both ways and
back (the ends kept, the repairs, JSON nulls included), the service writing
both kinds and switching between them, the cap's count and the closing of a
watch past its last day; on Docker dev, through the API and on a proof account
no provider can answer for, the published clock, a condition routine created
with no schedule and armed within one period, the four refusals, the switches
both ways and « Check now » recording `not_configured` with no run row; in the
API container, a check whose source answers files one `routine_condition:tasks`
consultation `ok`, one whose source fails files it `failed`, one with nothing to
open files nothing; in the browser, a condition routine created with no
schedule and the dialog's modes (vitest, a hermetic Playwright journey), and
the routines list — a condition routine whose last check failed included —
scanned clean by axe.

## Consequences

- A condition routine acts within about one check of the awaited fact — ten
  minutes by default, an hour for the weather, a couple of minutes for a Gmail
  mail on an account with a push channel (ADR-281's wake) —, day and night, and
  never twice for the same fact.
- **Nights**: there are no quiet hours (owner arbitration Q1) — a fact found at
  03:00 is announced at 03:00, a push included.
- **The consultation register grows with the checks**: each check that opens a
  source is a row — up to 144 a day for one routine at the default ten minutes,
  24 for the weather —, instrumented like the rest of the register
  (`lia_ledger_rows`, ADR-263) and purged with the account.
- **The weather is billed per check** on the Google provider: two calls per
  check, 48 a day per weather routine at the default hour, attributed to its
  owner.
- **Limits, stated**: a check reads its source as the briefing projects it,
  rather than through a search of its own. A mail watch sees the
  `BRIEFING_MAX_MAILS_ITEMS` most recent unread messages (subject and sender
  only), a document watch the `BRIEFING_MAX_DOCUMENTS_ITEMS` most recently
  modified files, a calendar watch the first `BRIEFING_MAX_AGENDA_ITEMS` events
  of its window, its title filter applied after the read — so more new facts
  than that between two checks are not all seen. A task watch reads the
  provider's whole page instead of the card's cut: the card sorts overdue tasks
  oldest first, and behind that many older ones the task that has just become
  overdue — the very fact the routine waits for — was cut (found by the cold
  review). The daily cap counts runs, so a proposal the person never clicks
  still spends one. `skipped_condition` can be retired once the retention has
  purged the rows that carry it.

## Alternatives rejected

- **Keeping a schedule as a window for the checks** (« check between 08:00 and
  20:00 »): the owner chose day and night (Q1), and a window would be the
  schedule again under another name.
- **Push subscriptions for every source** (a Gmail watch, calendar webhooks,
  Drive changes): ADR-175's reason stands — a subscription per account and per
  provider, renewed and reconciled; the Gmail push already brings a mail
  watch's check forward (ADR-281).
- **A run row per check**: 144 a day per routine for nothing that happened; the
  ledger's `last_checked_at` says it in one field.
- **A counter of its own for the daily cap**: the history already records every
  run; a second count would be a second answer to the same question.
- **Keying a fact on its display** (« 09:00 tomorrow »): the display changes at
  midnight, the fact does not.
- **Pacing every source on a cache TTL**: only the Gmail search is cached; a TTL
  nobody applies would turn the cadence table into a claim.

## Amendment 2026-09-29 — a weather trigger reads Google Weather, four hours ahead, a likely change

**Owner request**: « it regularly happens that a routine triggered by a weather
change fires while LIA then says in its answer that, after checking, there is
no change of weather »; decisions: « the weather-change alert must fire for a
change due within the next 4 hours at most, only », « the trigger source must
ALWAYS be Google Weather, the only one the platform can guarantee is
enabled », « a threshold strictly above 50 % ».

**Measured in the code before the change** — four defects, each enough to
produce the reported contradiction:

1. **The horizon was five days.** `_detect_forecast_alert` scanned the whole
   forecast the card fetches — 40 three-hour slots, 120 hours — while its
   docstring and the `ForecastAlert` schema said « the next 24 h ». A shower
   four days away fired the routine.
2. **No probability was read.** Google's `CHANCE_OF_SHOWERS`,
   `SCATTERED_SHOWERS` and `CHANCE_OF_SNOW_SHOWERS` normalise to `Rain` /
   `Snow`; the slot's `pop` was available and ignored.
3. **The run was told an hour with no day.** The note read « rain expected
   around 15:00 »: the run checked today at 15:00, found nothing, and said so.
4. **The source was the person's provider.** `resolve_weather_client` returns
   OpenWeatherMap when the person set a key of their own — a trigger fired by a
   source the platform does not guarantee, and read differently from Google
   Weather.

Two smaller ones rode along: a routine watching some kinds took the FIRST
notable slot of ANY kind and then dropped it (snow after a shower was never
announced), and « already falling » was read over every kind (a snow routine
stayed silent while it rained).

**Decision.**

- **One source**: `fetch_forecast_alert` opens
  `weather_provider.open_platform_weather_client` — Google Weather under the
  keyless predicate (ADR-307), never a per-account row; when the instance
  withholds it the check is `not_configured`, never a fallback on another
  provider. The card keeps the person's provider.
- **One rule, two readers**: `briefing.formatters.detect_forecast_alert` takes
  a `ForecastAlertRule` — horizon (inclusive), watched kinds, optional
  probability floor (STRICTLY above; a slot with no readable probability never
  passes). The card's rule is its documented 24 hours, every kind, no floor
  (`BRIEFING_CARD_ALERT_RULE`); the routine's is
  `SCHEDULED_ACTIONS_WEATHER_HORIZON_HOURS` (default 4, 1–23, so that with the
  hour under way it fits one 24-hour page) and
  `SCHEDULED_ACTIONS_WEATHER_MIN_PRECIPITATION_PERCENT` (default 50, 0–99)
  over the routine's kinds. The earliest accepted slot wins whatever the
  list's order; a slot under way is stated from now, never at a past hour;
  « already falling » only counts for a watched kind.
- **Hourly, unsampled**: `GoogleWeatherClient.get_hourly_forecast` returns
  every hour (`get_forecast` is now its 3-hour sample); a check reads the
  horizon plus the hour under way — ONE page, so two billed calls per check
  where the five-day read made six (1 + 5 pages of 24 hours).
- **The note says everything the run needs**: « rain expected around 14:00 on
  2026-09-29 (Europe/Paris), 80% chance of precipitation (source: Google
  Weather) ». The fact key is unchanged (kind and local day).
- **Coverage without a hole**: `SCHEDULED_ACTIONS_WEATHER_CHECK_MINUTES` above
  the horizon is refused at boot — a check reads up to T + horizon, the next
  one starts at T + interval.
- **Published because enforced** (ADR-184):
  `ScheduledActionListResponse.weather_condition_rule` (horizon, floor,
  source); the studio states it under the condition, naming the edited
  routine's own kinds (`weatherRuleSentence`).

**Consequences.** A weather routine fires at most once per watched kind and
local day, as before — a second shower the same afternoon is not announced
(the key is the day, a deliberate choice against forecasts that move by an
hour). The card no longer announces a change more than 24 hours away at an
hour of today. What a triggered run then reads with its own weather tools is
still the person's provider: the note names the source so the answer can say
which one saw the change.

**Proven by**: `tests/unit/domains/briefing/test_formatters.py` (horizon,
strict floor, kinds, the hour under way, the card), `test_fact_identity.py`
(Google-only, hourly, errors), `test_google_weather_client.py`
(`TestHourlyForecast`), `test_weather_provider.py`,
`tests/unit/core/config/test_scheduler_settings.py`,
`test_condition_evaluators.py` (the note, the published rule), and
`tests/integration/domains/scheduled_actions/test_condition_ticks_pg.py` —
the five condition types through five successive checks on PostgreSQL.
