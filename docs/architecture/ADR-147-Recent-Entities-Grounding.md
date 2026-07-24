# ADR-147: Response Grounding on Recent Entities

**Status**: ✅ IMPLEMENTED (2026-07-23)
**Date**: 2026-07-23
**Deciders**: jgouvier + Claude
**Technical Story**: Production defect — asked about the weather for an appointment, LIA answered that the podologue slot was at "16h" when the calendar tool had returned **11h15** two turns earlier. Root-caused to a structural gap, not a model whim.

## Context

Three mechanisms, each correct in isolation, combine into a blind spot:

1. `filter_registry_by_current_turn` returns `{}` when the current turn produced no `registry_updates` — a deliberate 2025-12-26 fix preventing cross-turn contamination (a stale Places photo leaking into a weather answer).
2. `{data_for_filtering}` is derived **exclusively** from that current-turn registry, so it is empty on any tool-less turn.
3. `filter_conversational_messages` deliberately drops `ToolMessage` from `<History>` — its own docstring states *"Agent results should be provided separately"*.

Consequence: on a turn that runs no tool, the response LLM receives **no authoritative structured data at all**. It can only echo whatever prose an earlier answer happened to contain — a lossy channel. Misquoting an attribute is then a matter of luck.

Note on vocabulary: this is **not** a "conversational turn" phenomenon. No producer ever emits `turn_type = "conversational"` (`QueryIntelligence.turn_type` yields only `ACTION` / `INITIAL` / `REFERENCE_PURE` / `REFERENCE_ACTION`); the trigger is the **absence of registry updates for the turn**.

## Decision

Re-ground the response prompt from state when, and only when, the turn produced no data of its own.

- **Gate** (`should_ground_from_recent_entities`) — applies only when `current_turn_registry` is empty **and** the turn is not a REFERENCE variant. The REFERENCE exclusion is a **security** property: an empty registry there is the data-leak fail-safe of `filter_registry_by_current_turn` (reference resolution found no match), and re-injecting would defeat that control. Pinned by a parametrized test.
- **Selection by recency, never by domain** — items produced within the last `RESPONSE_RECENT_ENTITIES_MAX_TURN_AGE` turns, derived from `agent_results` keys (`"{turn_id}:{agent}"`), most recent turn first, de-duplicated, capped at `TOOL_CONTEXT_MAX_ITEMS` with the drop **logged** (no silent truncation).
- **Source = merged `state["registry"]`** — already in memory (the `merge_registry` reducer keeps every prior item with its payload). **Zero I/O on the response hot path.**
- **Same serializer as the nominal channel** (`generate_data_for_filtering`), so an entity reads identically whether it comes from this turn or an earlier one.
- **Dedicated, non-authoritative prompt section** — `<RecentEntities>`, emitted through `_wrap_section` (no empty tag when there is nothing), placed **after** the dynamic-context marker so the cacheable prefix is untouched, and explicitly framed: *"NOT current-turn results … whenever current turn data covers the same entity, that data wins"*, preserving the `<DataAuthority>` hierarchy.
- **Paired prompt rule** — `<DataAuthority>` now forbids inventing or approximating any entity attribute (time, date, number, name, address): state it only if visible, otherwise say so and offer to re-check. Grounding supplies the value; this rule forbids guessing when it is absent. The rule **names `<RecentEntities>` among its citable sources**: enumerating only "current turn data or `<History>`" would have told the model to refuse the very block grounding had just injected (a tool-less turn has neither). It also covers data the turn was *asked about but never received* — the prod case where no weather step ran and temperatures were invented; the plan-level cause of that case is out of this ADR's scope.

## Consequences

- Text-only by construction: the HTML/photo/widget path keeps reading the empty current-turn registry, so the 2025-12-26 contamination fix stays intact.
- Bounded cost: at most `TOOL_CONTEXT_MAX_ITEMS` entities, no store round-trip, no extra LLM call.
- `RESPONSE_RECENT_ENTITIES_MAX_TURN_AGE=0` disables the feature outright.
- Residual: end-to-end efficacy depends on the entity payloads a connector actually returns; the chain is proven by tests and in-container runtime checks, but real-conversation validation remains an observation task.

## Rejected alternatives

- **Re-injecting into `current_turn_registry`** — would reintroduce the exact 2025-12-26 contamination bug (that path drives photo/HTML injection). Rejected outright.
- **Scoping by the current query's domains** (implemented first, then abandoned) — measurably wrong: `RoutingDecider` routes to the response node *precisely* when no domain is detected ("no domains → response" fallback), and a follow-up routinely references an entity from a domain the current query does not name (asking about the weather while referring to an appointment). Domain scoping made the grounding inert exactly where it was needed.
- **Reading the Tool Context Manager store** — viable (the TCM does retain the entities), but it adds a store round-trip on the hot path, a domain-enumeration problem, and a `get_result_key` mapping, for data the graph state already holds.
- **Reusing `{data_for_filtering}`** — cheaper to wire, but that placeholder is labelled *"available data for filtering"* and feeds the `<relevant_ids>` mechanism; presenting older entities there would blur the current-turn authority contract.
