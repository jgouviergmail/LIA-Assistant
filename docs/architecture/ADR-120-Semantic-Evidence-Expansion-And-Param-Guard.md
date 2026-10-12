# ADR-120: Semantic Evidence-Driven Domain Expansion and Runtime Parameter Guard

**Status**: ✅ IMPLEMENTED (2026-07-10) — evidence gate + guard active; evidence-driven expansion on by default since 2026-07 (`SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED`, code default `true`). Amended 2026-10-11: the guard reads declared person names only (see the amendment below).
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

2. **Evidence-driven expansion (C2, under flag, on by default).**
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

## Amendment 2026-10-11 — a resolved reference says what its value is

**Context.** On Docker dev (run `791de59e`, pipeline) the guard blocked
`get_places_tool(location=<the city asked about>)` twice as « a person's name »:
the turn's references were `"les 5 prochains jours" = 2026-10-11 to 2026-10-15`
and `"<the city>" = <The City>`, both from the query analyzer, and
Decision 3 read every value as a person's name. The memory resolver returns an
ADDRESS for a location query by design (its rule 4), blocked the same way
(reproduced). And the state copy of the references, written only when
non-empty, outlived its turn: on production, the latest checkpoint of 4 of 10
threads held references its own turn had not produced (read-only, 2026-10-11).

**Decision.**
1. Every resolved reference carries what its VALUE is
   (`analysis/resolved_references.py`: `person_name`, `postal_address`,
   `place`, `datetime`, `other`). The memory resolver declares it per mapping
   (`kinds`, rule 6; unreadable = `person_name`, the resolver's scope); the
   analyzer's `type` is a closed vocabulary describing the value (`person`,
   `place`, `temporal`, `contextual`; unreadable = `contextual`, never a failed
   analysis).
2. The references have ONE home, the turn's `query_intelligence` (rewritten
   every turn, carried through a HITL resume). The `resolved_references` state
   key is retired; `turn_references` is the one reader of the checkpointed form
   (`test_resolved_references_single_reader_guard.py`).
3. Decision 3 reads `person_name_values`: a value a producer declared a
   person's name, unless any producer declared the same value a place or an
   address that turn (a genuine homonym fails open). Legacy checkpoint values
   never count.
4. The planner, response and ReAct prompts render each reference with its kind;
   the planner block states the rule the guard enforces (ADR-284); ReAct reads
   the pipeline's own section.

**Model independence.** The declarations are model outputs; every slot is
configurable, so the guard is never better than the configured producers. What
any model's misbehaviour does is stated in the plan's degradation table: no
readable declaration reproduces today's reading, and only a real name declared
something else is guarded less than before. `scripts/semantic_simulation/memory_kinds.py`
and the `nearby_places_city_reference` scenario are per-deployment checks, to
rerun when the `query_analyzer` or `memory_reference_resolution` slot changes.

**Consequences.** Fewer `semantic_param_guard_blocks_total` (no alert reads
it). Doors that run no guard (voice/phone lookups, sub-agents, confirmed draft
replay) are unchanged and listed for a separate decision.

**What the value IS, judged (JEV usage `parameter_kind`, off by default).** The
rule above refuses only a name a producer RESOLVED this turn: a name the person
typed into a destination, a phone number or a date in an address slot, a name
mixed with a place all pass it. Once that rule lets a call through, the optional
judgment (`semantic/jev_value_kind.py`) asks JEV what each guarded value is — the
question measured as decision d5 of
[JEV_SEMANTIC_QUALIFICATION.md](../technical/JEV_SEMANTIC_QUALIFICATION.md), with
the request, the parameter as published and the value — and the CODE decides
compatibility (`ACCEPTED_VALUE_KINDS`): a location refuses only a value positively
identified as another kind, since a calendar's location is free text; an email
parameter accepts an email address alone. It can only add a refusal: switched off,
with no spend tracker, without a request, uncertain or failed, it refuses nothing. One
door, `semantic/argument_guard.guard_tool_arguments`, composes both for the
pipeline executor and the ReAct loop, so a refusal is counted and logged the same
way in both. The request travels as the turn's `original_query`, never the run's
message, which a HITL resume replaces with the reply.

**The ontology says what the code does.** The planner's semantic-dependencies
section renders « <type>: provided by [domains], used by [tools] » from the
editorial `source_domains` and `used_in_tools`. Measured the same day: 40 value
types named a producer domain whose tools never output them (`search_mode`
« provided by place » — a files parameter), 12 types were annotated, inherited,
composed or hinted by nothing, and 9 enumerations gave examples that were not —
or not all — the values the code emits or reads (`unit_system` « METRIC » where
the weather tools read `metric`). The phantom producers and the dead types are removed, the examples
are the values the code emits or reads, and
`tests/unit/domains/agents/semantic/test_semantic_registry_alignment.py` holds
it: a declared producer outputs the type, a declared consumer carries it, every
value type is read somewhere, and examples of a published enumeration are its
members. A domain is read from a manifest's agent by ONE rule,
`domain_taxonomy.domain_of_agent` (a qualified family such as
`devops_diagnostics_agent` belongs to `devops`). The weather tools now publish
their units (`WEATHER_UNITS`) and refuse any they cannot read instead of
sending it on (ADR-310).
