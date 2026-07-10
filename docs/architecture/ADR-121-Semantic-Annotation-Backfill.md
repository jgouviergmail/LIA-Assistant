# ADR-121: Semantic Annotation Back-fill & EmailMessage Evidence

**Status**: ✅ IMPLEMENTED (2026-07-10)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-120 (evidence-driven expansion & param guard)](ADR-120-Semantic-Evidence-Expansion-And-Param-Guard.md), [ADR-090 (semantic layer governance)](ADR-090-Semantic-Layer-Governance.md), `src/domains/agents/semantic/` ([README](../../apps/api/src/domains/agents/semantic/README.md))

## Context

An exhaustive inventory of the live catalogue (75 tools loaded via
`initialize_catalogue()`, the same path as runtime and CI) measured the
semantic annotation coverage that the ADR-120 machinery depends on:

- **31/224 parameters (14 %)** and **75/336 outputs (22 %)** carried a
  `semantic_type`;
- **73 of the 99 ontology types were consumed by no manifest at all** —
  including obvious ones (`contact_id`, `place_id`, `distance`, `duration`,
  `travel_mode`, `birthday`, `website_url`, `google_maps_url`). The ontology
  was built exhaustively in 2026-01; the back-annotation of manifests never
  happened.

Consequences: the Jinja2 suggestion engine, the planner/ReAct
semantic-dependencies prompt sections, the runtime parameter guard and
evidence-driven expansion (ADR-120) were all running on a fraction of the
signal they were designed for. The test fixture supposed to cover the
suggestion engine yielded an **empty registry** (its docstring claimed
auto-loading that does not exist), so every historical linking test silently
exercised the not-found path.

## Decision

1. **Back-fill campaign across 15 manifest files (~120 annotations)**, three
   tiers: flagship chains (attendees → send_email.to, email sender →
   event attendees, route.origin/destination → weather/places, waypoints +
   contact address/email under the ADR-120 guard, reminder trigger_datetime),
   ID/filter params (`message_id`, `event_id`, `contact_id`, `task_id`,
   `place_id`, `file_id`, `email_label`, `datetime` windows…), and
   measurements (distance, duration, temperature, humidity, rating,
   locality…). Coverage after: **120/224 params (53 %), 137/338 outputs
   (40 %), 72/100 ontology types consumed**. The remaining untyped fields are
   deliberate (booleans, counters, free text, containers whose leaves are
   typed — inventoried as T3).
2. **Rule: no output annotation without payload verification.** Output paths
   are executed by Jinja references against real results; a wrong path is a
   silent feature failure. Two paths required action:
   - `events[].attendees[].email`: verified as the native Google shape
     flowing through the calendar tools (update_event reads `a.get("email")`).
   - `emails[].from`: did NOT exist (Gmail buries From in
     `payload.headers[]`, a list not addressable in Jinja). Fixed by
     promoting `from` to top-level in `build_emails_output` — the exact
     existing pattern used for `subject` in the same function, same
     rationale. This is the campaign's only non-manifest code change.
3. **`EmailMessage` entity** in the ontology (`properties = {sender:
   email_address, thread: thread_id, identifier: message_id}`,
   `source_domains=["email"]`) and `EVIDENCE_ENTITY_TYPE_BY_DOMAIN["email"]`
   — a referenced email becomes expansion evidence ("invite the sender of
   this email to the meeting" adds the email domain when `email_address` is
   required). Covered by the ADR-120 boot-time completeness assert.
4. **Fixed the `agent_registry` test fixture** to actually call
   `initialize_catalogue()`; added flagship chain tests that pin the exact
   Jinja2 suggestions on the REAL manifests (attendees→to, sender→attendees,
   route.destination→weather.location, place.address→contact.address).

## Consequences

- The ADR-120 runtime guard now also protects `create/update_contact.email`,
  `update_contact.address` and `get_route.waypoints` — for free.
- The planner and ReAct semantic-dependencies sections, Jinja2 hints and
  provider-tool protection see the full cross-domain surface (participants,
  sender, destination, IDs).
- Prompt-size impact is marginal: the deps section only surfaces types that
  are both provided and consumed within the selected domains.
- 28 ontology types remain unconsumed: 16 abstract hierarchy roots plus
  legitimately internal types; no action (recorded in the inventory).

## Verification

- Inventory before/after via catalogue-loading audit script (same loading
  path as runtime).
- Flagship chain tests on real manifests; registry smoke + semantic suites;
  full unit suite; mypy/ruff/black.
