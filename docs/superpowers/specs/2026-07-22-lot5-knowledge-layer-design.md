# Lot 5 — Knowledge Layer: Documents Domain (P1) + Person-360 (P3)

**Program**: [Interdomain Intelligence Program](2026-07-21-interdomain-intelligence-program.md) · **Status**: SPEC (2026-07-22) → implementation
**ADR**: ADR-141 (single ADR covering both — same "active knowledge" decision).

## P1 — RAG Spaces as an active routable domain `document`

**Verified**: RAG injection is passive-only (last user message, `response_context`);
`retrieve_rag_context(user_id, query, db, limit, min_score, ...)` is directly
reusable; routability flag-filtering has an exact precedent (telephony) at the
`_build_available_domains` chokepoint.

- **Taxonomy**: routable domain `document` (result_key `documents`, provider
  internal, no OAuth). Filtered out at `_build_available_domains` when
  `rag_spaces_enabled` is off (telephony pattern — is_routable is static).
- **Tool** `search_user_documents_tool(query, max_results?)` in
  `agents/tools/documents_tools.py` (`@read_tool`, agent `document_agent`):
  own DB session, calls `retrieve_rag_context`, returns `data_success` with
  `{documents: [{content, space, filename, score}], count}` — content
  excerpt-capped (token budget). Friendly failure when the feature flag is
  off or no active space (`not_configured` semantics, LLM can relay).
- **Manifests**: `agents/documents/catalogue_manifests.py` (agent + 1 tool).
- **Loader headroom**: the frozen loader has 1 SLOC of headroom → replace the
  automation-specific registration call with a neutral aggregator
  `agents/registry/program_manifests.py::register_program_manifests(registry)`
  fanning out to automation + documents (+ future lots) — net 0 in the loader.

## P3 — Person-360 tool

**Scope v1** (tight): `get_person_overview_tool(person_name)` on the
**contact_agent** (person-centric home; cross-domain by construction), read
category. Parallel sub-fetches, each with its OWN session/client and its own
try/except (partial overview on any failure — briefing pattern):
1. **Contact card** — active contacts provider search (provider resolution
   pattern from heartbeat `_fetch_calendar`): name, emails, phones, orgs.
2. **Recent emails** — active email provider, query = person name/email,
   last N (subject, from, date).
3. **Upcoming shared events** — active calendar provider, `q=` name,
   next 30 days (title, start, location).
4. **Relevant memories** — `MemoryRepository.search_by_relevance` on the
   name embedding (+ trigger_topic case-insensitive match).
Output: `data_success` structured overview `{contact, recent_emails,
upcoming_events, memories, partial_failures: [...]}` — honest partiality.

**Deferred (recorded)**: shared Drive files + linked reminders sub-fetches;
`Memory.linked_contact_id` column (migration) — revisit after J+14 of the
extraction quality; person-360 as a dedicated registry card (UI).

## Tests (TDD)
P1: taxonomy entry + flag filtering at the chokepoint; tool happy path
(chunks→documents mapping), flag-off friendly failure, empty result; manifest
registration via the aggregator; tool-registry smoke auto-covers invocation.
P3: full overview mapping; each sub-fetch failing alone → partial_failures
carries it and the rest survives; unknown person → not_found failure;
provider-absent (no connector) → sub-block skipped not crashed.

## Gates
Backend fast suite + lint/mypy + ratchets (loader stays ≤ cap via aggregator;
taxonomy growth re-measured) + runtime smoke in-container.
