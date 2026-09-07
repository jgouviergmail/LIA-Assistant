# ADR-273 — A register extraction is complete, or it is not an extraction

**Status:** Accepted — 2026-09-07
**Amends:** ADR-263 (the three registers and their five extractions), ADR-185
(a count shown to a reader is exact or it does not exist), ADR-184 (what a
system enforces, it publishes)

---

## Context

ADR-263 gave the account holder and the operator five downloadable records and
was careful about honesty: every one of them stated its ceiling in its own
header, and ADR-263 lot 9 went further by stating it **per source**, because a
file complete in four records of five is not a complete file.

That was the right rule for a capped file. It was not an answer to the
question a register exists to answer.

Measured on the working tree, 2026-09-07:

| Surface | Audience | Ceiling |
|---|---|---|
| `GET /effects/export` (markdown / csv / technical) | account holder | 5 000 rows |
| `GET /effects/export/article12` | account holder | 1 000 rows **per source** × 5 |
| `GET /admin/effects/export` | operator | 5 000 rows |
| `GET /admin/effects/export/article12` | operator | 1 000 rows per source |
| `GET /admin/effects/export/readable` | operator | 5 000 rows |

The ceilings were not arbitrary, and this ADR does not pretend otherwise. They
were measured: five sources at 5 000 rows rendered a 10,8 MB file with a
**33,9 MB peak** and 939 ms of pure serialisation, on the Raspberry Pi 5 this
project deploys to. At 1 000 the same file was 2,1 MB, peaked at 6,6 MB and
rendered in 201 ms.

**What was actually scarce was memory, and what was bounded was the truth.**
Every renderer built the whole document as one string in memory
(`"\n".join(lines)`), so the only lever available was to read fewer rows. The
constraint was real; the variable it was applied to was the wrong one.

Two consequences follow, and the second is the one that matters. A person
exercising a portability right received a sample of their own record, and an
operator answering « what did this system do » received a sample of the
instance's. Neither file lied — both said `truncated` — but a record that
answers with an unexplained subset is a record nobody can rely on, and no
header wording repairs that.

**How large the subset was, measured on the developer instance on 2026-09-07**,
for one account's unified extraction:

| Source | Rows held | Rows the ceiling let through |
|---|---|---|
| `decisions` | 111 | 111 |
| `actions` | 11 | 11 |
| `consultations` | 363 | 363 |
| `inference` | **48 710** | **1 000** |
| `integrity` | 0 | 0 |
| **Total** | **49 195** | at most 5 000 |

**97,9 % of the inference record was absent from every unified extraction**, on
an instance with one account and a few weeks of history. The record that says
which model answered, with which parameters — the one Article 12 lot 7 exists
for — was the one the ceiling emptied.

## Decision

**An extraction of a register is complete. What bounds it is the memory it
holds, never what it contains.**

### 1. A server-side cursor replaces the ceiling

`infrastructure/database/export_stream.py` replaces `export_window.py`. The
rows are read in partitions through `AsyncSession.stream_scalars` and handed
to the renderer one at a time, so a request holds one partition rather than a
register. `EFFECT_EXPORT_BATCH_ROWS` (default 1 000) replaces the two ceiling
settings; raising it trades memory for round trips and never changes what a
file contains.

The lesson `export_window` was written for survives its cause: **the ordering
is applied in one place**, chronologically. It existed because a ceiling had
been applied to an unordered read and PostgreSQL returned the oldest rows — an
export read on 2026-09-05 covered January to March and named models the
instance no longer configured. No caller composes that ordering itself.

### 2. Rows are detached ONE BY ONE, never with `expunge_all`

A streamed ORM read still registers every instance in the session, so a
session that survives the whole scan holds the whole register and the cursor
buys nothing. The first implementation emptied the identity map between
partitions — and `Session.expunge_all()` **replaces** that map and kills the
old one, which the open cursor is still loading into: the second partition
died on *"this identity map is no longer valid"*.

It was found by the integration tests against real PostgreSQL and **could not
have been found by the unit tests**, because a stubbed stream has no identity
map at all. Rows are now expunged individually, after the consumer has
rendered each.

### 3. The renderers stream; nothing else about them changes

`stream_markdown`, `stream_csv`, `stream_jsonl` and `stream_article12` yield
chunks. The Markdown day grouping survived verbatim: it only ever needed the
previous row's day, and the register is read forward.

### 4. The count is EXACT, and the window is CLOSED so that it stays exact

A streamed response sends its headers before its body, so a total cannot be
tallied while rendering — the first line is already on the wire. It is counted
first, by an aggregate over the same statement the body then streams
(ADR-185: count the set, page the rows).

For the two to describe the same set, an extraction with no upper bound is
given one: **the instant the file is generated**. The window is closed, the
file is reproducible, and the bound it applied is named in the header's
`filters` rather than pinned in silence.

### 5. Completeness is CLAIMED, never inferred from silence

`truncated` stays in the header and is always `false`; `X-Register-Truncated`
stays on the response; the Article-12 header keeps `complete: true` and a
per-source count. `row_cap` and `cap_per_source` are gone, because a ceiling
that does not exist must not be advertised.

Dropping the `truncated` key would have been the tidier edit and the worse
contract: a reader would then tell a complete file from a partial one by the
**absence** of a warning, which is exactly what an extraction must never ask
of them — and it is the same reasoning that made the ceiling stated per source
in the first place.

### 6. The download is compressed, because that is what makes it usable

`core/streaming_download.py` wraps the chunks in an incremental gzip
compressor when the client offers `Accept-Encoding: gzip`. LIA is self-hosted,
typically behind a domestic uplink, and these files are pure text. The
compressor holds one 32 KiB window, never the document, so it composes with
the cursor instead of undoing it.

The file **name** does not change. `Content-Encoding` is transport: the
browser decompresses and saves `lia-actions-20260907.jsonl`, exactly the file
the header describes. A `.gz` artefact would be a different contract, and the
reader attaching an extraction to a complaint should not have to explain an
extra extension. `Vary: Accept-Encoding` travels with it, and a client that
refuses gzip with `q=0` gets plain text.

### 7. The streaming generator owns its session

FastAPI 0.136.3 exits `yield` dependencies from `request_stack`, which closes
**after** the response body is sent — so the request session would in fact
survive. The generator opens its own anyway (`get_db_context`), for two
reasons that do not depend on that version: rows are detached as they are
rendered, which is not what a shared session's other users expect; and
FastAPI 0.106 once shipped the opposite ordering.

### 8. A page keeps its page size

`/admin/effects/readable` is a screen, not a file: it keeps a bounded read
(`EffectLedgerRepository.list_latest`), and it keeps the newest-window rule
with it — capping an ascending read there would show an account's first fifty
actions forever.

## Consequences

- The five extractions return every matching row. On a large register the
  download is longer and the file bigger; the memory the API holds does not
  move.
- `EFFECT_TECHNICAL_EXPORT_MAX_ROWS` and `ARTICLE12_EXPORT_MAX_ROWS_PER_SOURCE`
  are removed from `.env.example` and `.env.prod.example`. An operator who set
  either of them loses nothing: the value no longer means anything.
- `row_cap` and `cap_per_source` disappear from the file headers. A parser
  reading `truncated` keeps working; one reading `row_cap` must stop.
- The tests that asserted a ceiling were **rewritten, not deleted**: each was
  replaced by the falsifiable half of the same claim (no route reads a row
  ceiling; the header claims completeness; the published total is the counted
  one, pinned by handing the count and the body apart).

## What this does NOT solve

- **A very large extraction is still a long download.** Nothing here makes it
  resumable: an interrupted download restarts. The period filter remains the
  way to ask a smaller question, and it is now a choice rather than a ceiling.
- **The account archive is unchanged.** It already carried both registers with
  no row cap, and it still fails loudly above a byte ceiling rather than
  shipping a partial archive.
- **Compression is negotiated, not guaranteed.** A client that does not offer
  gzip downloads plain text, and an edge that recompresses is outside this
  decision.
- **An in-flight download holds two connections**, for as long as it runs: the
  request's own (which counted) and the generator's (which streams). It is
  stated rather than optimised away — the pool is 20 per worker plus 10 of
  overflow, and the route's rate limiter bounds how many downloads an account
  can start. Should that ever bite, the fix is to release the request session
  before streaming, not to put the cursor back on it.
- **`token_usage_logs` still outlives the account** (ADR-263 lot 9). Removing
  a ceiling does not change what is retained.

## Verification

- `tests/integration/domains/agents/effects/test_export_stream_db.py` — every
  matching row comes back, chronologically, for all five records, over a set
  larger than one partition, with the count and the stream agreeing. Run
  against real PostgreSQL; the oracle was falsified on purpose (a read that
  yields nothing turns 7 of 8 red) before being trusted.
- `tests/unit/domains/agents/effects/test_article12_export.py` — no export
  route reads a row ceiling, both removed settings are gone, and every route
  publishes a completeness claim.
- `tests/unit/domains/agents/effects/test_export_router.py` — an open period
  is closed at the moment of generation, the published total is the counted
  one, and compression does not change the document.
- **Runtime, inside the container, against the real register** (2026-09-07):
  the consultation export carried 363 rows for a header stating 363 and a
  database holding 363, with no `row_cap` and a closed `until`; gzip took
  113 349 B down to 11 211 B (**×10,1**); the unified extraction declared
  49 195 lines and carried 49 195, `complete: true`, in a 1,52 MB compressed
  file.
