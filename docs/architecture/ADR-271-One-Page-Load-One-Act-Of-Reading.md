# ADR-271 — One page load, one act of reading

**Status:** Accepted — 2026-09-07
**Amends:** ADR-184 (a constraint that is enforced must be published), ADR-185
(a count shown to the reader is a claim), ADR-248 (one predicate, never two
copies), ADR-254 (a burst is what breaks a dependency, not a volume), ADR-263
(the effect register records acts, not callers)

---

## Context

The Today dashboard renders through two endpoints issued in parallel by
`useBriefing`: `GET /briefing/cards` (fast, no LLM) and `GET
/briefing/synthesis` (LLM-bound). The split is deliberate and stays — the grid
must not wait for a model.

Each of them, however, obtained the nine-section bundle on its own. `/cards`
always built it; `/synthesis` read the Redis cache and, when it judged the
cache too thin, built it again. On a page load the two builds were concurrent,
so **the same person's sources were opened twice within the same second.**

This was not inferred from the code. It was measured on the running instance.

**One page load, in the API log:**

```
08:34:40.780  path=/briefing/cards      duration_ms=1108  cache_state=partial
08:34:40.803  path=/briefing/synthesis  duration_ms=1108  cache_state=partial
```

Two builds, started 23 ms apart, finishing together. In the same three-second
window every connector operation appears exactly twice:

```
2  weather_current_retrieved     2  calendar_list_retrieved    2  drive_search_completed
2  weather_forecast_retrieved    2  calendar_events_listed     2  tasks_list_tasks_completed
2  briefing_cards_built          2  treatments_recorded        2  llm_factory_request  ← NOT doubled
```

**Over seven days**, from the shipped structured logs:

| | |
|---|---|
| Bundle builds | **151** |
| of which triggered by `/synthesis` | **44** |
| Page loads that built the bundle twice | **42** |
| Page loads that built it once | 67 |
| **Share of page loads paying double** | **39 %** |
| Duplicated build time (floor) | **≥ 40 s** |
| Duplicate builds concurrent with a `/cards` build | **44 / 44** |

That last row decided the design. Every duplicate was concurrent, so
coalescing — and coalescing alone — removes all of them.

The cost is not "nine fetches". One build issues up to ~21 external HTTP
calls: the contacts scan pages the People API at 1 000 contacts per page (up to
five pages), the mail section is one search plus up to ten `get_message`, plus
weather (two calls), calendar, tasks and Drive. Nine PostgreSQL sessions on top
— one per fetcher, as the concurrency rule requires.

Six defects followed from one root cause. Three more were found beside them,
and two of those only because this change moved something: a cache key with
four builders, and a bare count that had been unreachable until a section
became cacheable.

---

## Root cause

`/synthesis` asked **"does this bundle hold anything interesting?"** when the
only useful question was **"has this bundle been built?"**.

The two read alike and are not the same. A legitimately quiet dashboard is
indistinguishable from a cold cache under the first question — and the code
answered it with `_count_sections_with_data`, a **second implementation** of a
threshold `generate_synthesis` already owned: the service counted six sections,
the LLM helper counted nine, against the same constant. On the same bundle the
service counted 0 where the helper counted 2.

Below it sat the deeper gap: **nothing prevented two concurrent builds.** No
coalescing primitive existed in the codebase.

---

## Decision

**A briefing bundle build is single-flight per identity, and `/synthesis`
stops policing the cache.**

### 1. A coalescing seam — `infrastructure/utils/single_flight.py`

Whoever asks first runs the work; whoever asks while it is running is handed
the same result. It is deliberately **not a cache**: a finished run is never
given to a later caller, because "is this still true?" belongs to the caller's
own cache.

It sits beside `retry_async`, which it mirrors: both take a **factory** rather
than an awaitable, since a coroutine can only be awaited once.

Four properties, each answering a way this goes wrong:

- **The registry is the strong reference.** `asyncio.create_task` alone can be
  garbage-collected when the request that started it returns first — the trap
  `infrastructure/async_utils` documents.
- **Waiters are shielded.** `await task` propagates the awaiter's cancellation
  to the task, so one client disconnecting would cancel the work every other
  caller is still waiting for.
- **An entry belongs to an event loop**, checked before completion: a task from
  another loop is unusable whether or not it has finished.
- **A failure is shared, then forgotten** — every waiter sees it, and the entry
  is released so the next caller retries rather than inheriting it.

### 2. The flight key is the whole identity

`(user, language, timezone, hidden sections, forced sections)`. A key that is
too coarse hands a caller a bundle built for someone else, or in another
language — worse than building it twice. **A forced refresh therefore never
joins an unforced build**: joining would silently ignore the force and return
the very cache the caller asked to bypass.

### 3. `/synthesis` decides on COVERAGE, not richness

`_read_cached_bundle` returns the bundle *and* the visible sections the cache
had no entry for. A build happens when something is missing — never because
the day looks empty. `_count_sections_with_data` is deleted; the threshold
stays in `generate_synthesis`, the one place that owns it.

Building there is not a duplicate: it is coalesced, so on a page load it joins
the build `/cards` is already running and **both responses describe the same
bundle object**.

### 4. Every section is written to the cache

`SECTION_REMINDERS_TTL_SECONDS` moves from `0` to `60`. The reminders **card**
stays always-live (the plan forces it, so the TTL never serves a card); the
TTL exists so the section is *written*, and therefore readable by the
cache-only readers.

### 5. The cache key carries the language, and has ONE builder

Agenda times, mail dates, reminder wordings and document timestamps are
pre-formatted server-side. Keyed on the account alone, the cache served the
previous language until each TTL elapsed.

That key had **four** builders: three literal f-strings inside
`BriefingService` and a fourth in `push_channels/cache_invalidation`, a
different domain. Adding the language segment to the three visible ones left
the fourth deleting a key that no longer existed — and `redis.delete` on an
absent key succeeds and returns 0, so **a Gmail or Calendar push would have
stopped invalidating anything, in silence**, with staleness bounded only by the
TTL the push exists to short-circuit.

So the key now has one builder, `briefing/cache_keys.py`, and the invalidation
asks it for every language variant rather than guessing which one the person
reads in. Enumerating the six supported languages costs one DELETE; matching
them with a SCAN would walk the keyspace on a path that runs on every push. The
module refuses to load on an empty language list, because `SUPPORTED_LANGUAGES=`
in the environment reaches one (the validator filters blanks and nothing
rejects the result) and `redis.delete()` with no arguments is an error the
caller swallows by doctrine — a silent no-op again.

### 6. The greeting is not given a bare count of reminders

Making the section cacheable made it reach `_summarize_cards_for_llm`, whose
non-verbose branch handed the greeting a bare `reminders_count`. The rule
written directly above it, for the agenda, records what that produces:

> Deliberately NO aggregate count — a bare count made the greeting lump
> tomorrow's events into today ("deux rendez-vous cet après-midi"); a per-event
> list keeps each day explicit.

A count of reminders carries no day at all, and it had been unreachable — which
is precisely why it must not be reached now. The **synthesis** gets the
day-aware `{content, trigger}` pair its own prompt already documents; the
greeting gets nothing, following the ranking `chat/suggestions` states
explicitly ("a meeting and a mail batch are more time-bound than a reminder,
which will fire on its own anyway"). A fifteen-word greeting has one hint to
spend.

---

## Consequences

### What each change fixes

| Defect | Closed by |
|---|---|
| Cold/partial cache: every connector opened twice | the seam |
| A failing connector retried twice per load, forever | the seam |
| The synthesis describing a bundle the reader never sees | the seam |
| Two batches of consultation rows for one act | the seam |
| A warm cache rebuilt on every `/synthesis` for a quiet day | coverage |
| Two implementations of one threshold | coverage |
| Reminders unreachable by the ordinary page load | the reminders TTL |
| Cards stuck in the previous language until the TTL | the language key |
| A push silently invalidating nothing | one shared key builder |
| A bare reminder count reaching the greeting | the greeting is given none |
| A dead constant documenting a TTL nothing applied | deleted |

### The register repairs itself

The shared task runs in the context of the caller that started it, so its
consultations land in **that** caller's live list. A joining caller collects
nothing and files no decision — which is the honest record, one act and one set
of rows, obtained without a line of register code.

### Grafana 25 will show lower numbers

`briefing_build_duration_seconds_count` and
`briefing_section_status_total{origin="live"}` drop by roughly the duplicate
share. That is the end of a double count, not a regression. Two panels make it
readable: *Duplicate builds avoided (24h)* and *Bundle builds: owned vs joined*,
fed by `briefing_bundle_builds_total{outcome}`.

### The synthesis arrives after the cards, on purpose

Where `/synthesis` previously returned a text summarising a **stale** cache
while `/cards` was fetching fresh data, it now waits for the shared build. The
grid renders at the same instant as before; the hero already announces the wait
through a translated `aria-live` label and the synthesis slot already has a
skeleton, so the wait degrades gracefully. A greeting one second later beats a
greeting that contradicts the card beside it (ADR-185).

---

## What this does NOT solve

- **Coalescing is in-process, and production is NOT single-process.** This
  paragraph first claimed the opposite, from two checks that were true and one
  that was never made: the Dockerfile `CMD` carries no `--workers`, and
  `container_name` does forbid replicas — but **uvicorn also honours
  `WEB_CONCURRENCY`, and production sets it to 4** (`.env.prod.example`; the
  demonstrator uses 3, `.env.example` uses 1 and says "prod: 4"). The four
  `multiprocessing.spawn` children are those workers.

  Measured on production 2026-09-07, after deployment: three page loads whose
  `/cards` and `/synthesis` builds **overlapped in time**, and **none** was
  joined — one registry per worker, and the two requests of a page load land on
  the same worker roughly one time in four. The same split explains metrics that
  changed between consecutive scrapes: each scrape answers from a different
  worker.

  The seam itself is correct, and proven on the deployed code (two concurrent
  builds for one account → one gather, verified inside the production
  container). What it could not do is reach across workers — and the cache did
  NOT absorb the difference, contrary to a first reading of a window that
  happened to be warm: `agent_treatments` for the following twelve minutes
  shows `briefing:mails` opened **five** times, `for_you` four, `agenda`,
  `tasks` and `documents` three each, for two page loads. A consultation row is
  written only on a LIVE fetch, so those are real connector calls.

  **Closed by the cross-worker claim** (`infrastructure/utils/shared_flight.py`):
  one worker claims the build in Redis and the others wait for what it
  publishes — the section cache it fills anyway, so no payload of the seam's own
  travels through Redis. The two seams compose: the in-process one dedupes
  within a worker for free, the claim covers the rest. Verified against a real
  Redis: two workers on a cold cache open each source once, both receive a
  complete bundle, and no claim outlives its build.

  Three rules the claim does not bend: it is **released by its owner**
  (compare-and-delete on a token, never an unconditional `DELETE` after a
  `SET NX`); **waiting is bounded and a waiter that times out builds**, so a
  holder that dies strands nobody; and **every failure falls back to building**,
  because the worst outcome of this seam must be the behaviour it replaces. A
  FORCED refresh never waits — what a holder publishes is exactly the cache the
  caller asked to bypass.
- **A failing connector still costs one extra build** when `/synthesis` runs
  with no concurrent `/cards`. It was not designed away because the measurement
  says the case does not occur: 44 of 44 duplicates were concurrent, and zero
  ERROR sections were recorded over seven days.
- **A build outliving a disconnected caller reads a detached `User`.** Safe
  here and not by luck: `expire_on_commit=False`, no deferred column on `User`,
  and the whole build path touches loaded columns only — never a relationship.
  Adding a relationship read there would break it silently, which is why the
  constraint is written at the call site.
- **A language change costs one extra build.** The scope covers all nine
  sections rather than only the six that take a `language` argument: deriving
  it per section needs a table, and such a table drifts the first time someone
  adds the argument without updating it.

---

## Alternatives rejected

- **Sequencing the two calls in the frontend.** Makes `/synthesis` depend on
  call order; a direct API caller would get an empty synthesis.
- **Caching ERROR sections briefly.** Would make a transient failure sticky for
  the card as well — the opposite of what `_section` deliberately does.
- **A "built at" marker key.** Answers the freshness question for ERROR
  sections too, but a marker that is still valid while some TTLs have expired
  lets `/synthesis` summarise a staler bundle than the one on screen — the same
  defect, pointing the other way.
- **Section-level coalescing.** Finer, but it drops the property that makes the
  fix worth having: that both responses describe the *same* bundle.

---

## Verification

- `tests/unit/infrastructure/utils/test_single_flight.py` — the seam alone:
  coalescing, distinct keys, cancelled waiter, cancelled owner, shared failure,
  a finished flight never reused, no leak, foreign event loop.
- `tests/unit/domains/briefing/test_page_load_single_flight.py` — the
  behaviour: one build per page load whichever endpoint arrives first, each
  source opened once, a failing connector opened once, the synthesis handed the
  **same object** the cards returned, a warm cache never rebuilt, a missing
  section still rebuilding, hidden sections not counted as gaps, a forced
  refresh never joining, the language honoured, Redis down, and the
  owned/joined counter.
- `tests/unit/domains/briefing/test_cache_key_contract.py` — the key the
  briefing WRITES is the key the push invalidation DELETES, asserted between the
  two domains for every provider × every supported language, plus the ADR-260
  family scopes and the reset scan still reaching the key.
- `tests/unit/domains/briefing/test_llm.py` — the synthesis receives each
  reminder with its own day, capped at three; the greeting receives no count.
- `tests/unit/domains/briefing/page_load_harness.py` — the shared rig. Connector
  **latency is mandatory** in it: written without, `/cards` fills the cache
  before `/synthesis` reads it and the race the harness exists to observe never
  happens. Two green-over-broken measurements were produced that way while this
  work was being done, and both are recorded in the harness docstring.
