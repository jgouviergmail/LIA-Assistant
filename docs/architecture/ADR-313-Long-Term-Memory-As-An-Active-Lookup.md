# ADR-313 — Long-term memory becomes an active lookup, through one door

**Status**: accepted — 2026-09-24 (owner question: would a memory search/read domain help the ReAct mode, and what else would?)
**Amends**: ADR-070 (the ReAct loop gains a capability), ADR-293 (a new family the binding covers), ADR-304 (no transaction across the embedding call), ADR-303 (a failure is never « nothing remembered »)

## Context

Long-term memory reached a turn one way only: the profile injected into the prompt,
ranked on the person's MESSAGE. It holds what their words evoke and nothing about a
subject the turn discovers on the way — the sender of an e-mail the loop just read, a
place named in a document, « the rules I gave you ». Neither the planner nor the ReAct
loop could look such a subject up.

Writing the lookup exposed a defect in the paths that already existed. Three callers
turned a query into memories three different ways, and one did not search at all: the
phone's `recall_memories` lookup and the owner call's context handed their query to the
chat's profile builder WITHOUT a vector, which then served the ten most RECENT memories
whatever was asked.

## Decision

1. **One lookup door** — `domains/memories/search.py`: `embed_lookup` embeds a query as
   a KEY (`is_conversational=False`: the chat triviality patterns collide with real
   names and short questions), `search_memories` serves the owner's live memories above
   the relevance floor, optionally narrowed to categories. The vector is computed before
   a session opens, and the session serves one query (ADR-304). The embedding's cost
   lands in whatever tracking context is active (turn, routine, phone call).
2. **Every existing caller goes through it**: the memory facts of the planner, the
   initiative and the reference resolution (`get_memory_facts_for_query`), the 360°
   person recall, and the phone's lookups (`build_profile_for_lookup` in the memory
   middleware) — the phone now searches instead of listing the most recent memories;
   only when no vector can be computed (provider down) does the recency fallback
   answer, as it always did.
3. **A routable `memory` domain with one read tool**, `search_memories_tool`
   (`memory_agent`): internal, read-only, no OAuth, no HITL. Its bounds are published
   from the sources the tool enforces (ADR-184): the category vocabulary IS the stored
   `MemoryCategoryType`, the result ceiling IS `MEMORY_MAX_RESULTS`, the query has a
   minimum length. The person's `memory_enabled` preference refuses the lookup like it
   refuses the injection; a sensitive or painful memory comes back flagged with its
   usage nuance as an obligation; a failure is classified, never an empty success.
4. **The phone is untouched by construction**: the domain is not in `PHONE_DOMAINS`,
   which already carries the native `recall_memories`.
5. **The skill generator knows it** (`validate_skill.py` `VALID_AGENTS`, the tool
   catalogue): a generated skill may look up what the person told LIA.

## Consequences

- The ReAct loop and the planner can resolve a subject the message did not name.
- The phone call answers « what do I know about X » with X, not with last week.
- The consultation register files the lookup under the `memory` domain (translated in
  the six languages of the treatment labels).
- Proven on real PostgreSQL (`tests/integration/domains/memories/`): relevance order,
  the floor, the category narrowing, the owner isolation.
