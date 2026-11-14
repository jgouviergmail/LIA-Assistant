# ADR-387 — A watched page is read without a model

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13

**Relates to**:
[ADR-322](ADR-322-One-Clock-Per-Routine.md) — a condition routine is checked by the system, and
fires on a NEW fact;
[ADR-326](ADR-326-Linear-Flatteners-And-Pinned-Fetches.md) — a validated URL is fetched on the
address the check saw, one validated hop at a time;
[ADR-324](ADR-324-A-Personal-Radio-A-Grid-Decides-Models-Only-Write.md) — the newsroom's public
fetcher, reused here;
[ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md) — a bound the system enforces
is published to whoever writes the value;
[ADR-386](ADR-386-A-Signed-Call-Starts-A-Routine.md) — what comes from another system is data,
wrapped as such.

## Context

A person wants to hear when a price drops, when a product is back in stock, when a notice is
posted. Lot 23 of the programme drawn from hermes-agent (a price monitor: the model chooses once
what to read, a script reads it again with no model), approved by the owner with wave 5. LIA's
routines already wait for conditions the system checks (ADR-322) — the person's mail, tasks,
calendar, documents and the weather — but none reads a public web page.

## Decision

1. **A sixth condition: a page changes.** `page_change` takes the page's `url` (required) and an
   optional `contains`: only the page's lines holding that text are watched, case-insensitive (one
   character is a filter: `€`). A parameter another type reads stays refused (ADR-322's rule). The
   address is refused at the API boundary when its own spelling rules a public page out — scheme,
   host, a blocked name, a blocked literal address (`url_validation.literal_refusal`, the checks
   `validate_url` makes before any DNS, now its one implementation) — and when it carries
   credentials; no network call runs there. Its bound is the field's own (`maxLength`), so the
   assistant reads it in the schema.

2. **The system reads the page, with no model.** At the condition's own cadence
   (`SCHEDULED_ACTIONS_PAGE_CHECK_MINUTES`, phase-shifted per routine like every condition), one
   GET through the public fetcher every page in LIA gets (`radio.newsroom.fetch.fetch_public`):
   every hop validated and requested on the address the check saw (ADR-326), the decoded body
   bounded (`PAGE_WATCH_MAX_BYTES`), the whole read bounded in time, the reader named
   (`PAGE_WATCH_USER_AGENT`). The fetcher learns to carry a caller's name and the body's media type,
   nothing else. A person's watch of one page is not a crawler: `robots.txt` is not consulted, and
   the site sees one named request per check.

3. **A page is the lines a person reads.** The visible text, one line per block — the head,
   scripts, styles, templates and hidden blocks dropped, blanks folded, a repeated line kept once,
   the filter applied, `PAGE_WATCH_MAX_LINES` lines of at most `PAGE_WATCH_LINE_MAX_CHARS`, the
   total stated. Plain text reads line by line, JSON one value per line; a body that is no text is
   no page. The page is decoded the way a browser decodes it (the newsroom's `decode_page`), parsed
   in a thread, walked iteratively. Each line is a FACT keyed by what it says, hashed: the ledger
   stores no page text.

4. **A page's ledger is a snapshot.** A mail seen once stays seen; a page is ONE thing read whole
   at every check, and a line that comes back is news again (« in stock », sold out, « in stock »
   once more). So for `SNAPSHOT_CONDITION_TYPES` the ledger keeps exactly the lines on the page at
   the last served reading, forgets what left it, keeps an unserved new line new, and a reading
   that failed forgets nothing. Until a reading has been served (`last_fired_at`), the run is told
   that nothing from the page was reported yet — a first run whose turn failed is retried as a
   first report, never as news; and a usage ceiling standing a check aside before it read
   anything moves nothing but the reason.

5. **The run is shown the new lines, as another site's words.** The note follows the routine's
   instruction: a header (« N line(s) appeared … since it was last reported », or « nothing from it
   reported yet: what it shows now »), the lines wrapped by `wrap_external_content`
   (`watched_page`), bounded at `PAGE_WATCH_NOTE_MAX_CHARS` with the rest counted; a page holding
   more lines than a check keeps says so there, since a change past them is not seen. The words are a
   versioned lines file
   (`page_watch_lines`). What a page says can be what the routine reads, never what it obeys. A
   price threshold is the instruction's, judged by the run (« tell me if it drops below 300 € »),
   with « only when there is something new » keeping a run that found nothing quiet: no
   locale-dependent price parser in code.

6. **A failure is said, never read as « nothing changed ».** An address that leads to no public
   page at a check (a name resolving to a private address, a redirect to one) is `not_configured`
   — something the person can fix, nothing opened, no consultation filed. A page that did not
   answer, answered an error, was too large, too slow or not text is `unavailable`, filed as a
   failed consultation of the `routine_condition` surface's `page` section (`web_fetch`).

## Consequences

- The form offers « A web page changes » with the page's address and the line filter; the address
  is checked before saving, the read itself states its limits in the hint. The assistant creates
  one through the same schema, which publishes both fields and their bounds.
- A first reading runs the routine once, with what the page shows: the person sees what is watched.
- A page drawn by scripts, or reserved to signed-in accounts, shows the read its static HTML: the
  watch reads what that HTML says — a challenge page included — and the run, which reads it as
  data, can say so.
- The daily cap of runs of a condition routine bounds a page that changes at every check.

## What this decision leaves, and says so

- No browser rendering: a page whose content only scripts draw is not read.
- No selector: a person narrows a page by the text of its lines, not by its structure. A CSS
  selector would be precise, and nobody — person or model reading the page as text — could write
  one that survives the page's next deploy.
- No before/after in the note: the ledger keeps hashes, not the page's text; the run reads what
  appeared, and the conversation holds what earlier runs said.
- No conditional request (ETag): most pages that change send none, and an unchanged page costs one
  bounded read an hour by default.

## References

- `apps/api/src/domains/scheduled_actions/page_watch.py` — the address a watch may keep
- `apps/api/src/infrastructure/scheduler/page_reading.py` — the read, the lines, the note
- `apps/api/src/infrastructure/scheduler/condition_evaluators.py` — `_eval_page_change`
- `apps/api/src/domains/scheduled_actions/condition_ledger.py` — the snapshot ledger, `last_read_at`
- `apps/api/src/infrastructure/utils/url_validation.py` — `literal_refusal`
- `apps/web/src/components/settings/ScheduledActionsSettings.tsx` — the form's page fields
- [SCHEDULED_ACTIONS.md](../technical/SCHEDULED_ACTIONS.md) — the routines and their conditions
