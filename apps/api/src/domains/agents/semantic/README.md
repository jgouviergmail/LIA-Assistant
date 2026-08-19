# Semantic Type System

Complete semantic typing system for LIA, inspired by schema.org, RDF, SKOS and OWL.

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

- **101 semantic types** catalogued (hierarchy kept as validated data)
- **Fast lookups** O(1) by name and by source domain — the runtime surface
- **Singular domain vocabulary** throughout (contact, email, event, place,
  route...), matching `DOMAIN_REGISTRY`

ADR-233 (2026-08-19): the transitive-subsumption API, Wu & Palmer distance,
SKOS relation graph and category/tool getters had zero runtime consumers and
were removed (doctrine: unwired capability is deleted, not kept "for later").
The SKOS-style data fields on `SemanticType` (labels, related/broader/
narrower) remain as dated debt recorded in the ADR.

## 🏗️ Architecture

```
semantic/
├── __init__.py              # Public exports
├── semantic_type.py         # SemanticType dataclass + TypeCategory enum
├── type_registry.py         # TypeRegistry with hierarchy and lookups
├── core_types.py            # Catalogue of the 96+ types (ontology)
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
    query="itinéraire chez mon frère",
)
# ["route", "contact"]

# EVIDENCE-DRIVEN (flag ON): every referenced entity whose ontology
# `properties` provide a required type adds its source domains (capped).
# Context evidence only covers items from PREVIOUS assistant responses
# (ordinal/demonstrative/pronoun): "comment aller à CE rendez-vous ?"
# after an event was shown. A cold "mon RDV de demain" is handled by the
# analyzer's direct domain detection, not by expansion.
result = await service.expand_domains_evidence_driven(
    domains=["route"],
    evidence_entities={"CalendarEvent"},   # "comment aller à ce rendez-vous ?"
    required_semantic_types={"physical_address"},
    max_added_domains=3,
)
# ["route", "event"]
```

The entity anchoring is what prevents blind expansion: "quel temps demain ?"
requires `physical_address` too, but with no referenced entity nothing is
added. Evidence entities are derived in the query analyzer (STEP 3) from:

- person references (memory resolver mappings/extraction, analyzer LLM) → `Contact`
- context references to previous items (`ContextReferenceOutput.reference_domain`)
  → `EVIDENCE_ENTITY_TYPE_BY_DOMAIN` (completeness asserted at boot,
  `assert_evidence_entity_types_complete`, ADR-085 pattern)

### Runtime Parameter Guard

```python
from src.domains.agents.semantic.param_guard import (
    check_semantic_params,
    collect_resolved_person_names,
)

names = collect_resolved_person_names({"mon frère": "Marc Lemoine"})
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

### Manifest annotation coverage (ADR-121 back-fill, 2026-07)

Parameters: **120/224 typed (53 %)** — outputs: **137/338 typed (40 %)** —
**72/100 ontology types consumed** by at least one manifest. The remaining
untyped fields are deliberate (booleans, counters, free text, containers
whose leaves are typed). Rule for outputs: never annotate a path without
verifying it against the real tool payload (Jinja references execute on it).

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
- [Wu & Palmer (1994)](https://aclanthology.org/P94-1019/): semantic distance algorithm

## 📄 License

Proprietary - LIA
