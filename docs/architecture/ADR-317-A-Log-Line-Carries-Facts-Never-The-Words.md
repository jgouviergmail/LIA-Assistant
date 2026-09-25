# ADR-317 — A log line carries facts, never the person's words

**Status**: accepted — 2026-09-24 (owner request: « il faut traiter les deux sujets car nous devons être conforme RGPD » — the repository's SQL error logging, and every log line above DEBUG that carried personal content)
**Amends**: [ADR-027](ADR-027-Structured-Logging.md) (structured logging), [ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md) (the level-sensitive content net), SEC-012 (credentials in URLs), [ADR-303](ADR-303-Tool-Failure-Restitution.md) (classify by structure, never by words), [ADR-266](ADR-266-Diagnosis-Evidence-At-Diagnosis-Time-And-Exact-Str-Embedding-Inputs.md) (the evidence pack is sanitised)

## Context

CLAUDE.md has always said « no PII at INFO level: names, emails, GPS coordinates,
memory/journal content, message bodies ». The PII filter enforced it by field NAME
(`CONTENT_FIELD_NAMES`), and a name is a convention. Everything below was measured
before anything changed.

**Every log call of `src` above DEBUG, read value by value (2026-09-24)**: 438 values
carried the person's words or text cut from them — search queries (`query=` alone on
43 lines), interest topics on 35 (health included), a conversation excerpt of 500
characters, a draft's modification instructions, the typed answer to a clarification,
the model's reasoning about the person's context, a script's stdout and stderr, the
names of contacts, labels, files, folders and knowledge spaces, the URLs the person
browsed, GPS coordinates (`geocoded_lat`/`geocoded_lon` at INFO), CardDAV responses
logged up to 2,000 characters (address-book XML), a merged memory's content.

**Database errors (dev database, a temporary table, the value « Jean Dupont »)**:
`BaseRepository` logged `error=str(e)` at ERROR in six methods, and `str(e)` of a
PostgreSQL failure quotes the row:

- SQLAlchemy appends `[parameters: ('Jean Dupont', 'jean.dupont@example.org')]`;
- `hide_parameters=True` removes that line and NOTHING else;
- PostgreSQL's `DETAIL` names the duplicated key (`Key (name)=(Jean Dupont) already
  exists.`) or prints the whole failing row (`Failing row contains (Marie Curie, null).`);
- asyncpg quotes a parameter it cannot encode (`invalid input for query argument $1:
  'Jean Dupont'`), a refused cast quotes its input, psycopg (the LangGraph checkpointer
  and store) adds `CONTEXT:  JSON data, line 1: {"a": "Jean Dupont"`;
- every traceback of such an error carries all of it: `format_exc_info` renders the
  traceback before the PII filter runs.

The metric label `db_query_errors_total{error_type}` was decided by words of the
message (`"deadlock" in str(e).lower()`), which also filed every data or syntax error
as a CONNECTION error. And Pydantic's `str(ValidationError)` carries `input_value=`.

**Two holes in the filter itself**: `filename` sat in `STRUCTLOG_META_FIELDS` (the
bypass list for the log envelope) although no processor of the chain adds call-site
parameters — so an attachment's name, and an address inside it, escaped every rule; and
provider keys carried in a query string (`?key=AIza…` for Google Maps Platform,
`?appid=…` for OpenWeatherMap) were not masked while an httpx status error renders the
full request URL.

## Decision

1. **At the source, a database failure is reported by its facts.** Every engine is
   built with `hide_parameters=True` (guard `test_sql_parameters_hidden_guard.py`, which
   reads the literal at each construction). `infrastructure/database/errors.py` reads
   the driver's ATTRIBUTES — asyncpg's `constraint_name`/`table_name`/`column_name`,
   psycopg's `diag` — into `database_error_fields` (driver class, SQLSTATE, constraint,
   table, column) and decides the metric label by SQLSTATE in
   `classify_database_error` (a message never decides). `BaseRepository` reports through
   ONE helper (`_report_query_error`, six copies before) and `database_session_error`
   logs the same facts.
2. **The net withholds what a line QUOTES, above DEBUG.** `observability/quoted_content.py`
   recognises the fixed layouts of the texts that quote rejected data — PostgreSQL's
   `DETAIL` and `CONTEXT` fields (to the next field — a failing row can span lines — or
   to the junction Python writes between chained exceptions, whose frames must survive),
   SQLAlchemy's `[parameters: …]`, asyncpg's query-argument message, the PostgreSQL
   message families that end by quoting their input, Pydantic's `input_value=` (to the
   LAST marker of the line: a value can forge one) — and replaces the quotation alone:
   the constraint, the table, the statement and the error class stay. The PII filter
   applies it to every string value, the rendered traceback included, and to foreign
   stdlib messages. Free-text query parameters (`q`, `query`, `$search`, `srsearch`,
   `input`, `address`, …) are withheld above DEBUG; provider keys (`key`, `appid`) are
   masked at every level, like any credential. The content names grew, but a name
   joins only when NO line used it for anything else; content SUFFIXES (`*_preview`,
   `*_query`, `*_content`, `*_text`, …) redact text and lists only, so a flag, a length
   or a configuration dict sharing the suffix survives. `STRUCTLOG_META_FIELDS` holds
   the four envelope fields the chain writes and no caller does (`event`, `logger`,
   `level`, `timestamp`).
3. **At the call sites, the 438 values became facts**: a length, a count, an
   identifier, a URL's host (security and navigation events — `url_host`, which never
   raises: several of those lines handle a URL that failed to parse), or the line moved
   to DEBUG. An output the code could not parse is reported by `log_unreadable_text`
   (`observability/log_facts.py`): its length at the caller's level, its words on
   a DEBUG line of their own. The plan validator's debug context no longer holds the
   value it refused, and five exception messages stopped quoting the value the model
   had sent (it knows it): a filter value, an e-mail address, a date, an attachment's
   name, a location.
4. **The guard reads the value, not its name** (`test_log_content_guard.py`, AST over
   `src`): a value above DEBUG is refused when it is a PREVIEW (a slice of anything but
   an identifier) or DERIVED from content (its leaf names are content words; the LAST
   word decides — `query_length` is a length, `detection_query` a query); the field
   name counts only when the value is not already metadata, and a bare `name=` must say
   whose name it is. What an exception's text quotes is the net's (point 2), not the
   guard's. Twenty-six values are ALLOWED with a written reason — a numeric bound, the
   system FAQ space's code-constant name, an administrator's instance setting, an
   address the operator configured, a vendor's refusal text, a media type — and an
   allowance that no longer matches a line fails the build.

DEBUG keeps the words: « contents at DEBUG or redacted » is the policy (CLAUDE.md), and
a developer reproducing a failure needs them.

## Consequences

- Loki keeps what operates the system: counts, identifiers, codes, hosts, SQLSTATEs,
  constraint names. The diagnosis evidence pack (ADR-266) runs the same quotation rules
  over the lines it reads back.
- `db_query_errors_total{error_type}`: a data or syntax error is now `unknown`, a pool
  exhaustion `connection_error`.
- **What this does not cover, stated rather than implied**: our own exception messages
  in general (30 `raise` sites interpolate a value; the five personal ones were fixed,
  the others quote code identifiers or configuration); vendor error texts outside the
  recognised layouts; an operator raising `LOG_LEVEL` to DEBUG in production gets the
  words (the policy's own exception); and the lines already stored in Loki keep what
  they carried until the retention expires — this change purges nothing.
