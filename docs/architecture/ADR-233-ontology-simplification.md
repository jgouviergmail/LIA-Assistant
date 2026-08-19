# ADR-233 — Semantic ontology: remove the unconsumed reasoning machinery

**Date**: 2026-08-19
**Status**: Accepted
**Context**: The semantic module shipped a schema.org/RDF/SKOS/OWL-inspired
apparatus — transitive subsumption over a NetworkX DAG, Wu & Palmer
distance, SKOS relation graph, multilingual labels, category/tool getters.
The 2026-08-19 audit measured its consumption: **zero call sites outside
the module and its own tests**. The runtime consumes exactly three lookups
(`get`, `get_all`, `get_by_domain`) plus the `properties` /
`source_domains` / `used_in_tools` data fields (expansion service,
initiative bridges, param guard) and `validate_hierarchy` (diagnostics).

## Decision

Apply the repo doctrine — unwired capability is deleted, not kept "for
later":

- **Removed** from `TypeRegistry`: `compute_distance_wu_palmer`,
  `get_hierarchy_path`, `get_subtypes`, `is_subtype_of`,
  `get_related_types`, `get_by_category`, `get_by_tool`, and the SKOS
  relation `MultiDiGraph`.
- **Removed** from `SemanticType`: `get_label`, `is_subtype_of` (instance).
- **Retained**: the three runtime lookups, the internal category/tool
  indexes (they feed `get_stats`), the parent/child hierarchy graph
  (validated at boot via `validate_hierarchy`), and every data field.
- The tests that existed solely to exercise the removed surface were
  removed with it; the retained surface got a dedicated pinned test class
  (`TestLivingSurface`).

## Consequences

- The graph-adjacency intelligence the initiative needs lives where it is
  actually consumed: `related_domains` (now guarded bidirectionally by the
  identity-bridge test) and the manifest `semantic_type` annotations (now
  under an absolute-count ratchet).
- **Dated debt**: the SKOS-style data fields (`labels`, `related_types`,
  `broader_types`, `narrower_types`, `format_pattern`,
  `validation_rules`) remain populated in `core_types.py` without a
  consumer. Purging them is a ~1,200-line data edit kept out of this
  change's blast radius; do it in a dedicated pass or wire a consumer
  (e.g. `format_pattern` in the param guard) — whichever comes first.
