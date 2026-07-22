# Lot 1 — Proactive Refinements (P8, P4, P10, P7, P14)

**Program**: [Interdomain Intelligence Program](2026-07-21-interdomain-intelligence-program.md) · **Status**: IN PROGRESS (2026-07-22)
**Scope**: five low-risk cross-domain wins, all in existing chokepoints. No new tables, no migrations, no frontend changes.
**Process**: strict TDD (red → green → refactor per item), deep self-review, full gates, Docker runtime proof.

---

## P8 — Dynamic memory query in heartbeat second pass

**Gap**: `_fetch_memories` uses the static query `"important upcoming events preferences routines"` while journals get a dynamic second-pass query built from aggregated context (ADR-135 fixed this for journals only).

**Design**:
- Remove the memories fetcher from the first-pass `asyncio.gather` (and from `source_names`).
- After the gather, build the dynamic query ONCE (`_build_second_pass_query`, renamed from `_build_journal_query_from_context` — docstring updated: serves journals AND memories; grep call sites + tests).
- Run `_fetch_journals` then `_fetch_memories(user_id, settings, query=...)` sequentially (CLAUDE.md: sequential loop fine for a handful of queries). Memories keep their own scoped session (unchanged).
- Static query remains the fallback when the aggregated context is empty.
- Failure handling preserved: exception → `failed_sources.append("memories")`, context stays usable.

**Tests** (`test_context_aggregator.py`):
1. Memories fetched with the dynamic query when context has calendar/weather/interests (assert embedding call receives dynamic text).
2. Fallback static query when context is empty.
3. Memory fetch failure → `"memories"` in `failed_sources`, journals unaffected.
4. Memories no longer fetched during first pass (aggregate with second pass short-circuited → no memory call).

## P4 — Adjacency matrix completion + chaining guidance + doc-bug fix

**Gap**: `related_domains` is consumed ONLY by the initiative node (reverse lookup implemented consumer-side, `initiative_node.py:237-240`). No domain lists `task` → after a task query the initiative node can never enrich; the `task` entry's comment claims an event→task adjacency that does not exist (doc-contradiction). Email→file (attachments) edge missing. Place→telephony chaining works de facto (place payloads carry `phone`) but is undocumented for the planner/ReAct.

**Design**:
- `domain_taxonomy.py`: `event.related_domains: ["contact"] → ["contact", "task"]` (one edge covers both directions via the consumer's reverse lookup — makes the existing comment TRUE); `email.related_domains: ["contact"] → ["contact", "file"]`. No cycles introduced (`validate_domain_registry` stays clean: task=[], file=["contact"]).
- Fix the `task` comment to describe the now-real adjacency; fix stale comments on `contact`.
- Prompt guidance: add a compact `CROSS-DOMAIN CHAINS` block (conditional phrasing — "if a phone-call tool is available…") to `smart_planner_prompt.txt` and `react_agent_prompt.txt`: place→phone call (booking), event location→route+weather (leave on time), email→file (attachments), task→event (block a slot).

**Tests**:
1. Taxonomy: new edges present; `validate_domain_registry()` returns no errors; reverse adjacency task↔event derivable the way the initiative node computes it.
2. Existing initiative-node structural-prefilter tests still green (adjacency for task now non-empty — check for tests asserting the old emptiness).
3. Prompt files still load via `load_prompt` (smoke).

## P10 — Extended anti-redundancy window

**Gap**: the decision LLM sees recent heartbeats + interest notifications, but NOT scheduled-action results, fired reminders, or telephony reports delivered in the same window → multi-surface same-morning pile-up is invisible to it.

**Design**:
- New fetcher `_fetch_recent_other_notifications(db, user_id, user)` (own session, one of the gathered fetchers): three sequential indexed queries within the `heartbeat_recent_window_days` window, max 3 rows each — ScheduledAction (`last_executed_at`, `title`), Reminder (status `sent`, `trigger_at`, `content` excerpt), PhoneCall (completed, `completed_at`, `objective` excerpt).
- `HeartbeatContext.recent_other_notifications: list[dict[str, str]] | None` + `recent_other_notifications_summary` property (lines `[when] kind: label`).
- `build_decision_user_prompt`: third anti-redundancy section "OTHER RECENT PROACTIVE MESSAGES (reminders, automations, call reports — avoid piling up on the same topics)".
- Decision prompt: extend rule 10 with level (c): topic overlap with other proactive surfaces → pivot or skip.
- Reuse existing window settings (`heartbeat_recent_window_days`); per-type cap is a module constant (3).

**Tests**:
1. Fetcher returns merged, per-type-capped, window-filtered rows (fakes for the three tables).
2. Empty everywhere → None (no prompt section).
3. Summary property renders; `build_decision_user_prompt` includes the section when data present.
4. Fetcher failure → context usable, no crash (gather semantics).

## P7 — Birthdays: shared fetcher + heartbeat source + action-chain guidance

**Gap**: birthdays exist briefing-side only (`briefing/fetchers.py:350`, Google People full scan, cached to local midnight). Heartbeat has no birthdays source. IMPORT CONSTRAINT: `briefing/fetchers.py` already imports `heartbeat.geocoding` → heartbeat→briefing would create a domain import cycle (forbidden). 

**Design**:
- New neutral module `src/domains/connectors/birthdays.py`: `BirthdayItem` + `upcoming_birthdays_from_connections` (moved from briefing schemas/formatters; briefing re-imports from here), `BirthdayFetchError(reason, detail)`, and `fetch_upcoming_birthdays(user, user_tz, *, horizon_days, max_items) -> list[BirthdayItem] | None` (None = Google Contacts connector not configured; full-scan pagination logic moved as-is).
- `briefing/fetchers.fetch_birthdays` becomes a thin wrapper: None → `ConnectorNotConfiguredError("google_contacts")`, `BirthdayFetchError` → `ConnectorAccessError` (briefing section-status contract intact).
- `_seconds_to_next_local_midnight` moves to `core/time_utils.py` (briefing/service imports updated).
- Heartbeat: new gathered source `_fetch_birthdays` — Redis cache `heartbeat:birthdays:{user_id}` (TTL to next local midnight, same rationale as briefing), horizon `heartbeat_context_birthdays_days` (new setting, default 1 = today+tomorrow, added to `.env.example` + `.env.prod.example`), silent None on not-configured/error.
- `HeartbeatContext.upcoming_birthdays` + prompt section `UPCOMING BIRTHDAYS` + `has_meaningful_context` + source label `UPCOMING_BIRTHDAYS` in `HeartbeatSourceLabel`.
- Decision prompt rule 18: birthday today = HIGH VALUE — congratulate AND propose the chained action (draft a message / place a call, matching available connectors); tomorrow = MEDIUM (heads-up).

**Tests**:
1. `connectors/birthdays`: port/extend existing birthday computation tests (keep briefing formatter tests passing via re-export or import update); not-configured → None; HTTP error → BirthdayFetchError.
2. Briefing wrapper: exception translation preserved (existing briefing fetcher tests stay green).
3. Heartbeat fetcher: cache hit skips fetch; miss → fetch + cache write with midnight TTL; horizon filter; not-configured → None.
4. Schema: prompt section renders; source label accepted by `HeartbeatDecision`.

## P14 — Deterministic post-call appointment suggestion

**Gap** (requalified): `StructuredCallData` (agreed, proposed_datetime, location) is already extracted and persisted, but `proposed_datetime`/`location` die as free text — no actionable follow-through.

**Design** (v1, deterministic, no new draft infra):
- New pure helper in `return_synthesis.py`: `build_appointment_suggestion(structured, status, language, user_timezone) -> str | None` — returns a localized suggestion line ONLY when status is COMPLETED, `agreed` is True, and `proposed_datetime` parses (defensive ISO-8601; naive → assume user tz). Renders local datetime as unambiguous `YYYY-MM-DD HH:MM` + optional location. Invites the user to confirm creating the calendar event in chat (next turn flows through the normal pipeline with full context).
- `process_completed_call`: append the suggestion to `proposal.proposal_text` BEFORE `mark_completed` (so the armed outbox record and every delivery path carry it).
- Phrases in `core/i18n_telephony.py` — all 6 languages (backend-canonical `zh-CN`).

**Tests**:
1. Helper: None when not agreed / no datetime / unparseable / status failed; suggestion contains local datetime and location when present; naive datetime interpreted in user tz.
2. Phrase parity across the 6 supported languages.
3. `process_completed_call` delivers content ending with the suggestion when conditions met (existing test harness for the return flow, mocked LLM).

## Out of scope (Lot 1)
Route/departure source (P6 — Lot 6), briefing UI changes (P15 — Lot 4), open loops (P5 — Lot 2), any migration.

## Gates
`task lint` · `task test:backend:unit:fast` · heartbeat/telephony/briefing suites targeted · no i18n frontend impact · runtime proof: dev container boots + heartbeat aggregate smoke.
