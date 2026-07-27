# ADR-120: Semantic Evidence-Driven Domain Expansion and Runtime Parameter Guard

**Status**: ✅ IMPLEMENTED (2026-07-10) — evidence gate + guard active; evidence-driven expansion ships dark (`SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED=false`)
**Author**: Claude Code (Fable 5)
**Related**: `src/domains/agents/semantic/` ([README](../../apps/api/src/domains/agents/semantic/README.md)), `src/domains/agents/services/query_analyzer_service.py` (STEP 3), `src/domains/agents/semantic/param_guard.py`, [ADR-085 (registry completeness asserts)](ADR_INDEX.md)

## Context

In pipeline mode, "comment aller chez mon frère en voiture demain pour 18h ?"
intermittently produced a route to an arbitrary location. Root cause traced
end-to-end on a failing turn:

1. The memory resolver **did** resolve `{"mon frère" → "Marc Lemoine"}`,
   but the semantic-expansion trigger `has_person_reference` was computed
   **only from the analyzer LLM's typed references** — an intermittent signal
   the LLM sometimes omits. The expansion-service docstring even documented
   the intended contract ("detected by memory resolution"); the caller
   violated it.
2. Without expansion, `contact` was missing from the planner catalogue AND
   from the semantic-dependencies section of both the planner and the ReAct
   system prompts (all keyed on the same domain list). ReAct only recovered
   because it binds all tools and iterates.
3. The plan called `get_route(destination="Marc Lemoine")`; the Places
   lookup found nothing and the raw person name was **passed through** to the
   Routes API, which geocoded it arbitrarily — and the wrong route was cached
   (300 s).

The audit also found the "smart" generalization layer half-built and dead:
`expand_domains_semantic` was never called anywhere, and its setting
`SEMANTIC_EXPANSION_THRESHOLD` (a toggle disguised as a threshold) was defined
and read by nobody.

## Decision

Three complementary mechanisms, one per failure link:

1. **Deterministic person-reference evidence (C1, always on).**
   `has_person_reference` is now the union of three sources, most reliable
   first: (E1) memory-resolver mappings — person references by construction;
   (E2) Phase 1 extracted relational references, preserved even when
   resolution finds no memory fact (`MemoryResolution.references`, new typed
   result of `retrieve_and_resolve`); (E3) the analyzer LLM's person-typed
   refs (historical signal). Evidence sources are logged and surfaced in the
   debug panel (`person_evidence_sources`). Known limit: E1/E2 cover
   *relational* references only ("mon frère") — direct names ("chez Alexandre
   Lemoine") still depend on E3 and are backstopped by (3).

2. **Evidence-driven expansion (C2, under flag, ships dark).**
   `expand_domains_evidence_driven` generalizes person→contact: for every
   referenced **entity** (person → `Contact`; context reference to a previous
   item → `EVIDENCE_ENTITY_TYPE_BY_DOMAIN`: event → `CalendarEvent`, place →
   `Place`), when a semantic type **required** by the selected domains' tools
   appears in the entity's ontology `properties`, the entity's
   `source_domains` are added — capped (`SEMANTIC_EXPANSION_MAX_ADDED_DOMAINS`)
   and counted (`semantic_expansion_total{evidence_entity,added_domain}`).
   The entity anchoring prevents blind expansion ("quel temps demain ?"
   requires `physical_address` but references no entity → no expansion).
   Ontology enriched accordingly (`CalendarEvent.properties`,
   `Place.properties`); the evidence mapping is completeness-asserted at boot
   (`assert_evidence_entity_types_complete`, ADR-085 pattern). For person-only
   evidence the outcome is identical to the iso path, keeping the flag flip
   low-risk. The never-wired `expand_domains_semantic` and
   `SEMANTIC_EXPANSION_THRESHOLD` are **deleted** (dead code rule).

3. **Runtime semantic parameter guard (C3, always on, fail-open).**
   Last-resort net, manifest-driven, zero per-tool hardcode:
   - **C3a generic**: `param_guard.check_semantic_params` blocks a tool call
     whose argument is *exactly* a person name resolved this turn on a
     parameter typed `physical_address`/`email_address` — BEFORE the paid API
     call, with a recoverable error guiding the LLM to fetch the real value.
     Wired at both execution chokepoints: the parallel executor
     (`_execute_tool`; names travel via `configurable.resolved_person_names`,
     sourced from state in the task-orchestrator/initiative nodes — state is
     the only conduit that survives a HITL resume) and
     `react_execute_tools_node` (before the HITL interrupt, so users are never
     asked to approve a call that would be blocked). Metric:
     `semantic_param_guard_blocks_total{tool_name,semantic_type,execution_mode}`.
   - **C3b get_route**: a non-address destination that the Places search
     cannot find returns a recoverable `destination_unresolved` failure
     instead of passing the raw string to the Routes API (end of the
     arbitrary-geocode + wrong-route-cache path; nothing is cached since the
     error returns before `compute_route`). This covers direct names that the
     evidence layer cannot see. A Places API *failure* still passes through
     (best-effort: an outage is not evidence the destination is bad).

## Consequences

- The reported bug class is closed deterministically for relational
  references in both modes (same domain list feeds the planner catalogue, the
  planner prompt's semantic-dependencies section and the ReAct system
  prompt), and backstopped at runtime for direct names.
- E2 may over-trigger on relational *places* ("mon travail") — benign: the
  expansion still requires a matching required semantic type, worst case one
  extra domain in the catalogue; observable via `person_evidence_sources`.
- C3b trades the passthrough fallback for a recoverable error: a legitimate
  place that Places cannot find but the Routes geocoder could is now an
  explicit retry instead of a silent guess (accepted: a wrong cached route is
  worse than a clarification).
- Flag flip for C2 is a separate decision after a dev A/B on catalogue growth
  (each added domain grows the planner prompt).

## Verification

- Unit: evidence gate (E1/E2/E3/none, entity mapping), guard (exact-match,
  lists, fail-open paths, config plumbing), `_resolve_destination` marker +
  tool conversion, evidence-driven expansion (anchoring, cap, per-entity
  cases), boot assert (real ontology passes; ghost entry refuses boot).
- Runtime: dev Docker boot + pipeline turn on the failing query (expansion
  fires with `person_evidence_sources`), see release notes.
