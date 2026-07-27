# ADR-090: Semantic Layer Governance — Ontology ∪ Manifests + Test-Enforced Integrity

**Status**: ✅ IMPLEMENTED (2026-07-02)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-062](ADR-062-Agent-Initiative-Phase.md) (Initiative phase), [ADR-070](ADR-070-ReAct-Execution-Mode.md) (ReAct mode)

## Context

The semantic layer links data types to the tools that produce and consume them.
It feeds three prompt surfaces: the planner's cross-domain dependencies section,
the initiative node's connection candidates (new, see Decision 3), and the ReAct
system prompt (new, see Decision 4).

Until 2026-07 it had **two unsynchronized sources of truth**:

1. `semantic/core_types.py` — the static ontology (99 types, schema.org-style
   hierarchy) with hand-maintained `used_in_tools` / `source_domains` links.
2. `catalogue_manifests.py` modules — `semantic_type` annotations on
   `ParameterSchema` (what a tool CONSUMES) and `OutputFieldSchema` (what a
   tool PRODUCES), maintained together with the tools.

An audit found the ontology badly rotted:

- **12 phantom tool names (~50% of all `used_in_tools` references)** — leftovers
  from the v3.2 tool renaming (`get_contact_tool` → `get_contacts_tool`,
  `search_place_tool` → `get_places_tool`, `search_email_tool` →
  `get_emails_tool`, …). Consequences: hallucination-prone tool names injected
  into the planner prompt, and initiative connection candidates silently dead
  (e.g. contact → get_places_tool never proposed).
- **Registry frozen at 12 domains** — health, hue, image_generation, brave,
  web_search, web_fetch, browser (all added after 2026-01) had no types at all.
- **Case drift**: 10 manifest outputs declared `semantic_type="text"` while the
  registered type is `"Text"`.
- **No test detected any of this.**

Meanwhile the manifests were **already correct and richer** than the ontology
(`URL → fetch_web_page_tool`, `physical_address → get_places_tool /
get_current_weather_tool / get_hourly_forecast_tool / get_route_matrix_tool`):
producers were already resolved dynamically from manifests
(`_get_output_paths_by_semantic_type`), but consumers still relied on the
rotten static copy.

A second question was whether to merge the semantic layer with the domain
taxonomy's `related_domains` (coarse product-level adjacency used by the
initiative pre-filter and routing).

## Decision

### 1. Consumers = ontology ∪ manifests (union, per request)

`collect_manifest_param_consumers(manifests)` (in `expansion_service.py`)
indexes tools by the `semantic_type` of their parameters. Both consumer
surfaces union it with the ontology's editorial links:

- `generate_semantic_dependencies_for_prompt()` (planner + ReAct): consumers =
  `used_in_tools ∪ manifest param annotations`, resolved against
  `get_request_tool_manifests()` (request-scoped → covers MCP/user tools;
  degrades to ontology-only outside a request lifecycle).
- `_build_semantic_context()` (initiative): same union, intersected with the
  adjacent read-only manifests actually available this turn.

Division of labour: **manifests are the live, rename-proof source of truth**
for formal parameter-level links; the **ontology remains the editorial layer**
for usage relations no single typed parameter can express. The enrichment rule
going forward: **annotate manifests, not core_types** — one `semantic_type` on
an unambiguous parameter creates the bridge everywhere at once. Generic
`query` parameters are deliberately NOT annotated (a contact query can be a
name, an email or a phone number — a single semantic type would be wrong).

### 2. Five test-enforced integrity locks

`tests/unit/domains/agents/semantic/test_semantic_registry_integrity.py`:

1. Every `used_in_tools` entry must exist in the real catalogue manifests
   (failure message includes a difflib "did you mean" hint) — phantoms are now
   impossible by construction.
2. Every `source_domains` entry must exist in `DOMAIN_REGISTRY` (∪ the
   documented `"agents"` pseudo-domain) — locks the SINGULAR domain vocabulary
   ("contact", not "contacts").
3. Every `semantic_type` declared in a manifest must name a registered type —
   locks typos on the manifest side.
4. Internal ontology references (`parent`, `related_types`, `broader_types`,
   `narrower_types`) must resolve — self-consistency.
5. Every taxonomy `related_domains` link must be justified by ≥1 type bridge
   (produced by one side, consumed by the other, either direction, ontology ∪
   manifests) — except pairs consciously recorded in
   `KNOWN_UNBRIDGED_RELATED_DOMAINS` (currently `(file, contact)` and
   `(reminder, contact)`: legitimate product adjacencies without a data pivot).

### 3. Initiative `<SemanticBridges>` (fixes the frontier-model dependency)

The initiative node (ADR-062) previously received NO semantic links — the LLM
had to infer every cross-domain connection alone, which only frontier
reasoning models did reliably. `_build_semantic_context()` now injects into
`initiative_prompt.txt`:

- the generic cross-domain type map (same section as the planner, no Jinja2
  patterns — initiative actions carry literal values), and
- **pre-computed connection candidates**: types PRODUCED by the executed
  domains × adjacent read-only tools CONSUMING them
  (`- physical_address (from contact results) → consumable by: get_places_tool,
  get_route_tool`). Prompt-size guards: 3 tools per type, 20 lines max, with
  explicit `(+N more)` markers — never silent truncation.

The DecisionLogic instructs the model to judge the concrete user value of each
candidate — not to rediscover the bridges. Both are gated by
`SEMANTIC_LINKING_ENABLED` and degrade to neutral fallback strings on any error.

### 4. ReAct prompt: PRECISION rule + `<CrossDomainDataTypes>`

Field bug (2026-07-02): "comment aller chez mon frère ?" — memory resolution
gave the brother's name and city, semantic expansion correctly added the
contact domain, but the ReAct LLM routed to "Montpellier, France" (city centre)
without ever calling `get_contacts_tool` for the exact address. Root cause:
memory context provides a "good enough" approximation and the ReAct prompt had
neither the semantic links (the planner had them) nor a precision directive.

`react_agent_prompt.txt` now carries a generic PRECISION rule ("memory tells
you WHO, tools give exact values — retrieve the exact value with the lookup
tool BEFORE calling the consumer tool") and a `<CrossDomainDataTypes>` section
fed by the same `generate_semantic_dependencies_for_prompt()`.

### 5. NO merge of taxonomy and type registry

`related_domains` (coarse, product intent, "often used together") and the type
registry (fine-grained, mechanical, "which field feeds which parameter") answer
different questions. A mechanical derivation of one from the other would both
add false adjacencies (generic types like `datetime` link everything to
everything) and lose usage links that have no formal pivot. Governance is
cross-checked by lock #5 instead: any new taxonomy link without a type bridge
requires a conscious allowlist entry — annotating the manifests is the
preferred path.

## Consequences

- Positive: dead bridges resurrected (contact→places/weather/route measured
  live); planner prompt free of hallucination-prone names; naming drift now
  breaks CI instead of silently degrading two prompt surfaces; new domains get
  semantic links by annotating their manifests only.
- Negative / accepted: `get_semantic_provider_tool_names()` (catalogue-filter
  protection) keeps its ontology-only gate — its behaviour is sensitive and all
  pivot types have editorial links; the ontology's `used_in_tools` remains a
  second (now test-guarded) place to look at when reading the code.
- Follow-up (not started): offline evaluation harness comparing initiative
  decision quality across models (gpt-5.2 reference vs deepseek/qwen) with the
  enriched prompt — stage 3 of the S2i plan.
