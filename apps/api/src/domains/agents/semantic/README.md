# Semantic Type System

Semantic contracts for LIA, with a schema.org-inspired hierarchy and validated
RDF/SKOS relation metadata. Runtime linking uses exact types and JSON shapes.

## 📋 Overview

This module replaces hardcoded semantic-expansion patterns with a structured,
queryable system built on a hierarchical type registry. It powers three
runtime mechanisms:

1. **Domain expansion** — adding provider domains (contact, event, place) to
   the planner catalogue when a referenced entity can supply a semantic type
   required by the selected domains' tools;
2. **Semantic linking** — cross-domain parameter hints (Jinja2 references)
   injected into the planner and ReAct prompts;
3. **Runtime parameter guard** — blocking tool calls that pass a person name
   on an address/email-typed parameter (`param_guard.py`).

### Key Characteristics

- **Validated vocabulary** — use `task semantic:audit` for the current inventory
- **Fast lookups** O(1) by name and by source domain — the runtime surface
- **Singular domain vocabulary** throughout (contact, email, event, place,
  route...), matching `DOMAIN_REGISTRY`

ADR-233 (2026-08-19): the transitive-subsumption API, Wu & Palmer distance,
SKOS relation graph and category/tool getters had zero runtime consumers and
were removed (doctrine: unwired capability is deleted, not kept "for later").
The SKOS-style fields on `SemanticType` (related/broader/narrower) are validated
metadata, not permission to substitute values. Its unused `labels` field went
with ADR-323.

## 🏗️ Architecture

```
semantic/
├── __init__.py              # Public exports
├── semantic_type.py         # SemanticType dataclass + TypeCategory enum
├── type_registry.py         # TypeRegistry with hierarchy and lookups
├── core_types.py            # Core value vocabulary and catalogue loading
├── entity_types.py          # Entity properties used as expansion evidence
├── native_types.py          # Verified native values and resource identifiers
├── manifest_semantics.py    # Account availability, leaf types, reference shapes
├── planner_links.py         # Concrete sources for plan revisions
├── expansion_service.py     # Domain expansion (iso-functional + evidence-driven)
└── param_guard.py           # Runtime semantic parameter guard
```

## 🚀 Usage

### Loading the Registry

```python
from src.domains.agents.semantic import get_registry, load_core_types

registry = get_registry()
load_core_types(registry)  # done automatically at startup
```

### Type Lookups

```python
# By name
email_type = registry.get("email_address")
print(email_type.source_domains)  # ["contact", "email", "event"]

# By domain (singular vocabulary)
contact_types = registry.get_by_domain("contact")
# {"email_address", "physical_address", "phone_number", "person_name", ...}

```

### Domain Expansion

Two modes, selected by `SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED`:

```python
from src.domains.agents.semantic.expansion_service import get_expansion_service

service = get_expansion_service()

# ISO-FUNCTIONAL (default): historical person→contact expansion.
# has_person_reference is the union of the memory-resolver evidence
# (extracted references, resolved mappings) and the analyzer LLM refs.
result = await service.expand_domains_iso_functional(
    domains=["route"],
    has_person_reference=True,
    required_semantic_types={"physical_address"},
    query="route to my brother's place",
)
# ["route", "contact"]

# EVIDENCE-DRIVEN (flag ON): every referenced entity whose ontology
# `properties` provide a required type adds its source domains (capped).
# Context evidence only covers items from PREVIOUS assistant responses
# (ordinal/demonstrative/pronoun): "how do I get to THIS appointment?"
# after an event was shown. A cold "my appointment tomorrow" is handled by the
# analyzer's direct domain detection, not by expansion.
result = await service.expand_domains_evidence_driven(
    domains=["route"],
    evidence_entities={"CalendarEvent"},   # "how do I get to this appointment?"
    required_semantic_types={"physical_address"},
    max_added_domains=3,
)
# ["route", "event"]
```

The entity anchoring is what prevents blind expansion: "what's the weather tomorrow?"
requires `physical_address` too, but with no referenced entity nothing is
added. Evidence entities are derived in the query analyzer (STEP 3) from:

- person references (memory resolver mappings/extraction, analyzer LLM) → `Contact`
- context references to previous items (`ContextReferenceOutput.reference_domain`)
  → `EVIDENCE_ENTITY_TYPE_BY_DOMAIN` (completeness asserted at boot,
  `assert_evidence_entity_types_complete`, ADR-085 pattern)

### Runtime Parameter Guard

```python
from src.domains.agents.semantic.param_guard import check_semantic_params, turn_person_names

names = turn_person_names(state)  # names a producer declared — never places, dates, addresses
violation = check_semantic_params("get_route_tool", {"destination": "Marc Lemoine"}, names)
# violation.llm_message() → recoverable error guiding the LLM to fetch the
# contact's address first. Wired in the parallel executor (pipeline) and
# react_execute_tools_node (ReAct); fail-open by design.
```

## 📊 Semantic Types

### Categories (8)

1. **IDENTITY**: Person, Contact, email, phone, name
2. **LOCATION**: Place, Address, Coordinates
3. **TEMPORAL**: DateTime, Duration, Timezone
4. **RESOURCE_ID**: event_id, contact_id, file_id, etc.
5. **CONTENT**: Text, HTML, Markdown, etc.
6. **MEASUREMENT**: Distance, Temperature, Rating, etc.
7. **STATUS**: task_status, traffic_condition, etc.
8. **CATEGORY**: travel_mode, language_code, etc.

### Entity types with `properties` (evidence-driven expansion)

| Entity | Provides (properties) | source_domains |
|---|---|---|
| `Contact` | person_name, email_address, phone_number, physical_address | contact |
| `CalendarEvent` | physical_address (location), event_start_datetime, email_address (attendees) | event |
| `Place` | physical_address, phone_number, coordinate | place |
| `EmailMessage` | email_address (sender), thread_id, message_id | email |

### Current manifest coverage

Run `task semantic:audit` from the repository root. It scans optional and split
native manifest modules without connecting to services, and writes the complete
field inventory to `.tmp/semantic-contracts.json`: annotated and untyped fields,
JSON shapes, producers, consumers and integrity errors. The annotation floors
are enforced by `test_identity_bridge_coverage.py`.

See the [2026-10-06 review](../../../../../../docs/technical/SEMANTIC_CONTRACT_REVIEW.md)
for the measured changes and limits. Booleans, counters, generic queries,
ambiguous identifiers and arbitrary result objects may intentionally remain
unannotated. An output path must be verified against the real payload.

Generic `Text` and `QuantitativeValue` describe a value, without establishing a
cross-domain pivot. Similar or related types never authorize substituting an
email address for a message id, a local timestamp for an ISO instant, or an
array/object for a scalar parameter.

### User MCP contracts

MCP tools are discovered per account. Declared `inputSchema`, `outputSchema`,
known semantic extensions (`x-semantic-type` / `semantic_type`) and unambiguous
formats provide the available contract. Field names alone never establish a
semantic type. Missing output schemas remain unknown. The SDK's
`structuredContent` is kept for exact inter-step references; the ReAct view
pages whole items under its existing budget. Schema discovery does not prove
that every remote server always returns valid values.

### Hierarchy Example

```
Thing (root)
├── Person
│   └── Contact → provides: email_address, phone_number, person_name, physical_address
├── Place → provides: physical_address, phone_number, coordinate
│   ├── PostalAddress
│   │   ├── physical_address → contact, place, event, route
│   │   └── formatted_address → place, route
│   └── GeoCoordinates
│       └── coordinate → place, route
├── Event
│   └── CalendarEvent → provides: physical_address, event_start_datetime, email_address
└── Intangible
    └── Identifier
        ├── event_id → event
        └── contact_id → contact
```

## 🧪 Tests

```bash
pytest tests/unit/domains/agents/semantic/ tests/unit/semantic/ -v
```

## 🔄 History

- **2026-01**: registry + iso-functional expansion (exact reproduction of the
  historical hardcoded person→contact behavior) + semantic linking.
- **2026-07 (ADR-120)**: person-reference evidence made deterministic
  (memory-resolver mappings and Phase 1 extracted references union the
  analyzer LLM refs); evidence-driven expansion added under flag (replaces
  the never-wired threshold-based `expand_domains_semantic`); runtime
  parameter guard added (pipeline + ReAct).
- **2026-07 (ADR-121)**: manifest annotation back-fill (~120 annotations,
  15 files — the ontology had 73/99 types consumed by no manifest);
  `EmailMessage` entity added as expansion evidence; `emails[].from`
  promoted to top-level payload for Jinja addressability.

## 📚 References

- [schema.org](https://schema.org): class hierarchy
- [RDF](https://www.w3.org/RDF/) / [SKOS](https://www.w3.org/2004/02/skos/) / [OWL](https://www.w3.org/OWL/)

## 📄 License

Proprietary - LIA
