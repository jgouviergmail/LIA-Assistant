# ADR-101: Calendar Search Hardening (list-and-filter, date reset, volumetry cap)

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Related**: [ADR-084](ADR_INDEX.md) (Indexable vs Semantic), [ADR-070](ADR_INDEX.md) (Pipeline vs ReAct)

## Context

"recherche mes prochains rdv médicaux" and "recherche le rdv hotel particulier"
worked in ReAct mode but returned nothing (randomly) in Pipeline mode.

Investigation (API logs + reproductions + per-API code analysis) found several
distinct root causes, not one:

1. **Weak free-text search.** The pipeline planner wrote `get_events_tool(query=…)`.
   Google Calendar `q` is a weak full-text "contains" match over
   summary/description/location/attendees. It fails on:
   - semantic categories — "médical" never matches an event titled "Dentiste";
   - accents / paraphrase — "hotel" vs "hôtel particulier".
   ReAct survives by falling back to `query=null` → list events → filter with the
   LLM. The one-shot pipeline had no such recovery.
2. **Hallucinated date bounds.** For an open/relative query ("prochains") the
   planner sometimes set a narrow `time_max` (e.g. now + 2 days) that hid the
   very events asked for — the residual randomness.
3. **Per-API asymmetry.** A blanket "drop the query" would be catastrophic:
   Gmail `q` is a powerful query language (kept), Tasks has no text search and
   already list-and-filters (nothing to do), Contacts/Drive use purpose-built
   search (kept). Only the calendar's free-text is weak.
4. **Volumetry cap bypass.** The global ceiling `api_max_items_per_request` is
   applied by `apply_max_items_limit`, but Google Calendar (`list_events`),
   the three Apple clients and `microsoft_calendar_client.list_events` built
   their page size directly, escaping it — so the calendar could return an
   unbounded number of events regardless of the configured ceiling.

## Decision

Four orthogonal, deterministic changes, scoped to the calendar (the verified
weak-search store) plus a cross-cutting cap fix.

### 1. Free-text is never sent to the weak API — list-and-filter

`get_events_tool` resolves its `query` via `_resolve_calendar_query_param`:
- a PERSON name is resolved to an **attendee email** (a reliable, structured
  filter — the one `q` use we keep);
- **everything else** (title, concept, category, unresolved name) is **dropped**;
  the tool lists by the time window and the Response LLM filters the concept —
  the same model Tasks already uses and the behaviour that makes ReAct succeed.

This replaces the hardcoded `GENERIC_CALENDAR_QUERY_TERMS` allow-list (removed):
no exact-match guessing, handles "médical", "hotel particulier", "Dentiste"
uniformly. Gmail/Contacts/Drive are untouched (their search is reliable).

### 2. Open/relative query end-of-window date reset

The query analyzer emits a new boolean **`has_temporal_reference`**: True when
the query carries a concrete time bound (explicit date, relative day, named
period), False for open horizons ("upcoming", "my next 3") and no-time queries.
Empirically reliable (12/12 across fr controls).

The validator gains `_apply_open_query_date_reset`: when
`has_temporal_reference` is False, it empties any param the manifest declares as
`search_role="range_end"` (calendar `time_max`) so the tool's own default window
applies. Deterministic — one reliable boolean, **no string matching**. Explicit
temporal queries ("le 15 août", "les deux prochains jours") report True and keep
their bounds. Gated by `settings.planner_open_query_date_reset` (prod kill switch,
default on). `search_role` is a per-param manifest role (opt-in), replacing name
guessing.

### 3. Volumetry cap centralized + guarded

All item search/list clients route their page size through the single helper
`apply_max_items_limit` (global ceiling). The four bypasses (Google Calendar
`list_events`, Apple email/contacts/calendar, Microsoft calendar `list_events`)
were fixed. A new AST guard `tests/unit/test_max_items_cap_guard.py` fails CI if
any client builds a pagination request (`maxResults`/`pageSize`/`$top`, a
`limit=` size, or a `[:size]` slice) without the helper — preventing future
oversights. Metadata enumerations (`list_calendars`, `list_labels`,
`_resolve_list_id`) and the bulk contact sync (`list_connections`) are explicitly
allow-listed (structural, not item volumetry).

Ceiling raised: `api_max_items_per_request` 10 → **25**,
`calendar_tool_default_max_results` 10 → **25** (constants + `.env` +
`.env.prod`). Other domains keep their key at 10 (they pass their own key, so
`min(10, 25) = 10` — unchanged, verified). The calendar bypassed the global, so
raising its key is now actually effective and also enforced by the helper.

### 4. Busy-calendar transparency (data plumbed)

`get_events_tool` returns a `truncated` flag (`len(events) >= cap`) in its output
metadata; the searched window is already present there as `time_min`/`time_max`.
So the searched period and any truncation are available to the frontend and to a
future response fewshot that states "showing your N nearest events between X and
Y — narrow the period to see more". **Scope note**: `response_node` synthesizes
from the registry payloads, not the tool metadata, so surfacing this in the
answer *text* needs a small response-node change — deliberately deferred: with
the window now capped at 25 events, truncation is rare, and the data is ready
when that fewshot is added.

## Consequences

- Pipeline answers concept/category and accented calendar queries reliably,
  matching ReAct, across all 6 languages. No token matching on the path.
- New additive analyzer field `has_temporal_reference` threaded analyzer →
  `QueryAnalysisResult` → `QueryIntelligence` (+ to/from-dict round-trip) →
  `ValidationContext`. Default preserves bounds (no surprise reset).
- New per-param `ParameterSchema.search_role` (opt-in; only `time_max` annotated).
- Dead constants removed: bare `API_MAX_ITEMS_PER_REQUEST`,
  `*_TOOL_DEFAULT_MAX_RESULTS = 50` (comment-only references).
- **Residuals (documented, ReAct shares them)**: (a) a concept that coincides
  with a contact name ("Centre Médical") is resolved to that attendee (rare,
  pre-existing resolution behaviour); (b) completeness is bounded by the (now
  25-event) window — surfaced via the truncation flag.

## Alternatives considered

- **Keep `q` + retry-on-empty in the tool** — recovers accent misses but does a
  second API call on every legitimately-empty search and can under-return on a
  partial literal match. Rejected in favour of never trusting the weak `q`
  (list-and-filter), which is consistent with Tasks and single-call.
- **Blanket "drop query" for all stores** — catastrophic for Gmail (strong
  search). Rejected: the decision is per-API, driven by real search semantics.
- **Gate the date reset on the reused semantic-leak mode** — its default
  "observe" would make the fix inert by default. Rejected: the reset is
  deterministic and reliable, so it ships on with its own bool kill switch.
- **`query_is_purely_semantic` (prior ADR-101 draft)** — too narrow (missed
  "hotel particulier", pure=False). Superseded: free-text is handled in the tool
  and dates by `has_temporal_reference`.

## Validation (2026-07-04, dev container)

- Analyzer: `has_temporal_reference` 12/12 correct (open → False incl. "my next
  3"; explicit dates/periods → True).
- Validator: open query → `time_max` emptied, `time_min` kept; dated query →
  preserved; kill switch, required-param skip, unannotated tool, multi-step — all
  covered (9 tests).
- Free-text: category / literal phrase / unresolved name → dropped; email &
  resolved person → kept (7 tests).
- Cap guard green after fixing 5 bypasses + 4 allow-listed metadata methods.
- Round-trip preserves `has_temporal_reference`. Full unit suite green.
