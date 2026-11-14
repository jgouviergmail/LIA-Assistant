# ADR-380 — A person's time travels with its zone

**Status**: Accepted, 2026-11-12.
**Date**: 2026-11-12

**Amends**:
[ADR-369](ADR-369-Workbench-The-Persons-Own-Door-To-Their-Services.md) — the calendar clients
take typed bounds, never text: the wall time and zone id the Tools send (spec §14) are no longer
turned into anything on the way to the provider.

## Context

The owner's report (2026-11-12, production v4.6.0): an event moved or edited from the Tools to
09:30–10:30 showed 10:30–11:30, whatever was typed; an event created by hand was right until it
was moved.

**The cause, proven** (the code, a red test, and a read-only look at production, where the
event was stored at `10:30:00+01:00`). The Tools send a WALL time and a zone id. On an update
the Google client passed that time through `normalize_to_rfc3339`, which appends `Z` to a time
that names no offset; on a create it did not. Google reads an offset before it reads `timeZone`,
so « 09:30 » became 09:30 in UTC — 10:30 in Paris, 11:30 in summer. The same road was taken by a
whole series the assistant moved. In production since v4.3.0.

**Why nothing saw it.** The client's frozen reference had frozen the `Z`. It was taken in UTC,
the one zone where a wall time and its UTC spelling are the same digits: every proof we had
checked a FORM, in the only zone where the wrong form is right.

**Not the first time.** In July 2026 the CalDAV client stamped UTC on a time, then ignored the
zone it was handed: an event created at 10:00 in Paris was stored at 10:00 UTC. Same class each
time — a time and its zone travel apart, and each step guesses what a string means.

**The owner's question**: how is this made reliable once and for all — central code, guards,
something else?

The codebase, measured the same day (AST, `apps/api/src`): 69 `.replace(tzinfo=…)` in 44 files,
126 `fromisoformat` in 82, 220 `astimezone` in 112, 96 `ZoneInfo(` in 65, and 39 lines doing
surgery on a `Z` in 35 files; on the web, 259 `new Date(` in 154 files and 159
`Intl.DateTimeFormat` in 76. One guard (`test_no_hardcoded_timezone_guard.py`). Time is handled
by local arithmetic everywhere, and nothing says WHICH of three things a value is.

## Decision

1. **Three things are called « a time », and they are named.** An INSTANT is a point everyone
   shares (an aware `datetime`). A WALL TIME is what a clock shows somewhere, what a person says
   and reads; it names an instant only WITH its zone. A DAY is no time at all. A bare `datetime`
   cannot say which of the first two it is, a string even less.
2. **A wall time and its zone are one object** (`core/wall_time.py::WallTime`). `read` takes
   what a person wrote: without an offset it is the time on the zone's wall, with one it is an
   instant seen on that wall. A value it cannot read is refused, never guessed. It gives the
   instant it is (`instant()`) or what its wall shows (`iso()`), and never one for the other.
3. **One rule for the two nights the clocks change**, the one Python's `zoneinfo` and RFC 5545
   §3.3.5 share: an hour the clocks skip is read with the offset before the change, an hour they
   show twice is its first passage, and an instant seen on a wall keeps which passage it was.
4. **The calendars are handed bounds, never text** (`connectors/clients/event_bounds.py`):
   `TimedBounds` (two wall times), `DayBounds` (days, the end exclusive) or `TimedSides` (a
   change that keeps the event's shape). Text becomes bounds ONCE, where it is still known who
   wrote it (`bounds_of`, `change_of`), in the Tools' service and in the confirmed-draft
   executors. `CalendarClientProtocol` lost `start_datetime`, `end_datetime`, `timezone` and
   `all_day`: a client cannot be handed a string to interpret, nor half a change of shape.
5. **A client says the bounds in its provider's words and converts nothing.** Google and Graph
   are told the wall time WITHOUT an offset, beside the zone's name; CalDAV the local time under
   the zone's IANA name. The provider places the time with its own zone data, as the person
   meant it.
6. **Where the zone alone does not place a time, the provider is told the instant**
   (`WallTime.zone_suffices`). No provider's reference says how it reads « 02:30, Europe/Paris »
   on a night that hour is skipped or shown twice. Google is told the offset — it reads it first,
   the very rule behind the incident, used on purpose; Graph, whose `dateTimeTimeZone` has no
   offset, the time on UTC's wall; CalDAV the time in UTC.
7. **A whole series takes its occurrence's bounds moved by whole DAYS, on the wall**
   (`event_bounds.series_bounds`). No instant is read: an occurrence across a clock change lasts
   an hour more or less than the series it belongs to, and the series shows the times the person
   wrote.
8. **CalDAV names a zone by its own name on both of its writers.** caldav's writer (every
   create) wrote the IANA name; vobject (every update) named the zone after its winter
   abbreviation unless told (`_IcalZone`). And a value written over an old one takes the old
   one's shape and zone off the line with it (`_STALE_PARAMS`).
9. **A time is proven on its JOURNEY, in a zone away from UTC.**
   `tests/helpers/calendar_providers.py` simulates the three providers from their own reference
   and nothing else, and refuses what a reference does not define;
   `test_event_time_round_trip.py` writes through the real service, executor and client, lets
   the provider read, reads back through the real normaliser, and compares with an instant
   spelled by hand. The clients' frozen reference no longer stands in UTC.
10. **The call is type-checked where the callers live.** `agents/tools/*` and
    `connectors/clients/*` are under an old MyPy exemption that hides a wrong argument (proven by
    injecting one). `calendar_draft_execution` gets `call-arg`, `arg-type` and `misc` back: an
    enabled code wins over a disabled one, and the ratchet counts no new pair.

## What the journey found beyond the incident

Each proven before it was fixed; none had been reported.

- **The assistant could not change a timed event on iCloud.** Its tool hands times with the
  zone's offset, the old client turned them into a fixed-offset `tzinfo`, and vobject refused to
  name it (`Unable to guess TZID for tzinfo UTC+01:00`). A rename failed too: a draft carries the
  event's own times. Proven on the tree before the change, by one script, then on the change.
- **An event the assistant created on iCloud named a zone that is none**:
  `DTSTART;TZID="UTC+01:00":…`, with no definition beside it.
- **An iCloud event updated from New York was named « EST »**, which is another zone's name,
  five hours behind all year: a reader that knows the name places a summer morning an hour late
  (an independent iCalendar reader does: 14:30 UTC for 13:30). Paris escaped by luck: « CET »
  happens to carry the same rules.
- **An instant written over a start that came with a zone kept that zone**:
  `DTSTART;TZID=America/New_York:…Z`, which RFC 5545 forbids.

## Measurements

- The journey: 222 tests — three providers; Paris, New York, Kolkata, Auckland and UTC, summer
  and winter; create, move, one side alone; the six nights of 2026 on which those zones change
  their clocks, and the second passage of a repeated hour; days in four zones; a series from
  both entry points; and each simulator shown to refuse what its reference does not define.
- Nine mutants, run on a copy of the tree, each turning the time tests red. « A `Z` stamped on
  the wall time » — the incident — reddens 72 of them.
- Before the fix the journey was red where predicted, and only there: every night on the three
  providers, and New York's summer on a CalDAV update.
- Production, read-only: the event of the report, and over Loki's seven days the ten updates of
  2026-11-12 alone.

## What this decision leaves, and says so

- **The way back is still read in several places.** 96 lines in some thirty files read a
  provider's `dateTime` outside the clients, and four functions each read
  `{dateTime, timeZone}` their own way (`workbench/calendar_times.provider_time`,
  `core/time_parsing.parse_provider_datetime`, `event_recurrence.first_day_of`,
  `apple_calendar_client._start_instant`). One reader is the next lot.
- **No ratchet yet.** `normalize_to_rfc3339` stays, for search bounds, where its `Z` is right;
  its docstring and the doctrine of `core/time_utils` now say what it must never be handed. A
  shrink-only AST ratchet over the patterns counted above is the lot after.
- **The web** has its own doors (`new Date`, `Intl`), untouched here.
- **No provider account was written to for this decision.** The three calendars are simulated
  from their published references, and a simulator is only as right as its reading of them.
  The one thing read on a real system is the production event of the report.
- A CalDAV create carries the zone's name and no definition of it — caldav's own writer, as
  before: a server reads it by reference (RFC 7809). An update carries both.
- A CalDAV time that names no zone at all is read as UTC by the screen's reader.
- Graph publishes the list of IANA names it accepts; a zone outside it is sent as it is, as
  before.
- `TimedSides` handed to an all-day event: Google names its day, Graph and CalDAV write a time.
  No caller does it — the assistant states the shape, the Tools always send a pair with one.
- The assistant's tool reads the hour a model wrote as the person's own, whatever offset the
  model put beside it: the second passage of a repeated hour cannot be asked through a model.
- The report's first observation — an appointment written by another application and shown an
  hour late before anything in LIA had touched it — is not explained by this defect: LIA's
  reading does not move an event Google holds right. To be settled on the fixed version.

## Consequences

- A calendar client that grows a new write takes bounds; a new caller turns its text into
  bounds at its own door. Neither can stamp, strip or guess an offset: there is no string left
  to do it on.
- A proof about time that checks a form, or that only passes in UTC, proves nothing: it goes
  through the simulators, in a zone away from UTC, written then read back.
- A new provider is one more simulator, written from its reference, and one more column of the
  same journey.
- What the assistant writes on iCloud now carries the person's zone, so a series created in
  winter keeps its hour in summer.

## References

- `apps/api/src/core/wall_time.py`, `apps/api/src/domains/connectors/clients/event_bounds.py`
- `apps/api/tests/helpers/calendar_providers.py`,
  `apps/api/tests/unit/domains/connectors/clients/test_event_time_round_trip.py`
- Google Calendar API, `events` resource (`start.dateTime`, `start.timeZone`); Microsoft Graph,
  `dateTimeTimeZone` resource type; RFC 5545 §3.3.5 (DATE-TIME) and §3.2.19 (TZID); PEP 495.
- [ADR-318](ADR-318-Assistant-Tools-Exact-Answers-And-Own-Records.md) — elapsed time is
  measured between instants; this decision is its counterpart for what a person SAYS.
