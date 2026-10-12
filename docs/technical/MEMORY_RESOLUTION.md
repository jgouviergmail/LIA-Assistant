# Memory Reference Resolution Service

> Documentation technique de la résolution d'entités relationnelles pré-planner (3-phase architecture).

**Date**: 2026-04-08
**Version**: 2.0.0 (3-phase architecture — LLM extraction + targeted search + resolution)
**Source**: `apps/api/src/domains/agents/services/analysis/memory_resolver.py`

---

## Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Flow de Résolution](#flow-de-résolution)
4. [Reference Detection](#reference-detection)
5. [Structures de Données](#structures-de-données)
6. [Configuration](#configuration)
7. [Intégration](#intégration)
8. [Fail-Safe Design](#fail-safe-design)
9. [Exemples d'Usage](#exemples-dusage)
10. [Métriques & Observabilité](#métriques--observabilité)
11. [Fichiers Associés](#fichiers-associés)
12. [Related Documentation](#related-documentation)

---

## Vue d'ensemble

Le **Memory Reference Resolution Service** résout les références implicites basées sur la mémoire (relationnelles, temporelles, contextuelles) en noms d'entités concrets **AVANT** que le planner génère le plan d'exécution.

### Cas d'Usage Principaux

| Requête Utilisateur | Mémoire | Résolution |
|---------------------|---------|------------|
| "recherche l'adresse de **mon frère**" | "J'ai un frère... jean dupond" | "recherche l'adresse de **jean dupond**" |
| "envoie un email à **ma femme**" | "Mon épouse s'appelle Corinne" | "envoie un email à **Corinne**" |
| "appelle **mon médecin**" | "Mon médecin est le Dr Martin" | "appelle **Dr Martin**" |

### Différence avec Reference Resolver

| Service | Scope | Exemples |
|---------|-------|----------|
| **MemoryReferenceResolutionService** | Références relationnelles basées sur la mémoire | "mon frère", "ma femme", "mon patron" |
| **ReferenceResolver** | Références contextuelles dans la conversation | "le premier", "celui-ci", "le dernier" |

---

## Architecture

### 3-Phase Architecture (v2.0 — 2026-04-08)

The resolution pipeline runs inside `MemoryResolver.retrieve_and_resolve()` during
`QueryAnalyzerService.analyze_full()` (Step 1). It replaces the previous regex-based
pattern detection with an LLM-based extraction for language-agnostic reference detection.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                    QUERY ANALYZER SERVICE (Step 1)                         │
│                                                                           │
│  ┌─────────────────────┐     ┌──────────────────────────────┐            │
│  │ BROAD RETRIEVAL      │     │ PHASE 1: REFERENCE EXTRACTION │            │
│  │ Full query embedding │     │ LLM (bounded timeout)        │            │
│  │ → memory_facts       │     │ → ["ma femme", "mon fils"]    │            │
│  └──────────┬──────────┘     └──────────────┬───────────────┘            │
│             │         (parallel)             │                             │
│             ▼                                ▼                             │
│  ┌─────────────────────┐     ┌──────────────────────────────┐            │
│  │ For planner context  │     │ PHASE 2: TARGETED SEARCH      │            │
│  │ (general awareness)  │     │ Per-reference embedding        │            │
│  └─────────────────────┘     │ (parallel, higher threshold)  │            │
│                               │ → targeted_facts per ref      │            │
│                               └──────────────┬───────────────┘            │
│                                              │                             │
│                                              ▼                             │
│                               ┌──────────────────────────────┐            │
│                               │ PHASE 3: LLM RESOLUTION       │            │
│                               │ MemoryReferenceResolutionSvc  │            │
│                               │ → ResolvedReferences          │            │
│                               │   - enriched_query            │            │
│                               │   - mappings                  │            │
│                               └──────────────┬───────────────┘            │
│                                              │                             │
└──────────────────────────────────────────────┼─────────────────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────┐
                              │         PLANNER NODE          │
                              │ Uses enriched_query + mappings│
                              └──────────────────────────────┘
```

### Why 3 Phases?

Embedding the full query (e.g., "envoie un email à ma femme et mon frère") produces
poor cosine similarity with specific memory entries like "Mon épouse s'appelle Corinne"
because the semantic signal is diluted by the action context. By extracting references
first and embedding each one separately ("ma femme", "mon frère"), the targeted search
yields higher similarity scores, allowing a higher threshold and less noise.

### Concurrency Model

- Phase 1 (extraction) and broad retrieval run **in parallel** via `asyncio.gather`
- Phase 2 per-reference searches run **in parallel** via `asyncio.gather`
- Phase 3 (resolution) is sequential (single LLM call with all targeted facts)

---

## Flow de Résolution

### Séquence Détaillée (3-Phase)

```
1. USER QUERY
   "recherche l'adresse de mon frère"
   │
   ├──────────────────────────────┐
   ▼                              ▼
2a. BROAD RETRIEVAL          2b. PHASE 1: LLM EXTRACTION (bounded timeout)
    Full query embedding          Prompt: memory_reference_extraction_prompt
    → memory_facts: [             → references: ["mon frère"]
      "J'ai un frère jean dupond"
    ]
   │                              │
   │                              ▼
   │                         3. PHASE 2: TARGETED SEARCH (parallel)
   │                            Embed "mon frère" separately
   │                            → targeted_facts: [
   │                                "J'ai un frère jean dupond"
   │                              ]  (higher similarity score)
   │                              │
   │                              ▼
   │                         4. PHASE 3: LLM RESOLUTION
   │                            MemoryReferenceResolutionService
   │                            facts: targeted_facts
   │                            → ResolvedReferences:
   │                              enriched_query: "recherche l'adresse de jean dupond"
   │                              mappings: {"mon frère": "jean dupond"}
   │                              │
   ▼                              ▼
5. PLANNER receives:
   - memory_facts (from 2a, for general context)
   - enriched_query (from Phase 3, for entity names)
   Plan: search_contacts_tool(query="jean dupond")
   │
   ▼
6. RESPONSE uses mappings:
   "Voici l'adresse de ton frère (jean dupond): ..."
```

### Fallback Paths

- If Phase 1 (extraction) times out or fails → no references → fallback to broad facts for resolution
- If Phase 2 (targeted search) returns empty → fallback to broad facts for resolution
- If Phase 3 (resolution) fails → return None, planner uses original query

---

## Reference Detection

### LLM-Based Extraction (v2.0)

Reference detection is now handled by a lightweight LLM call (Phase 1) instead of
regex patterns. This makes the system **language-agnostic** — it works for all 6
supported languages without maintaining per-language regex patterns.

**Prompt**: `memory_reference_extraction_prompt.txt`
**LLM slot**: `memory_reference_extraction`, configured through central LLM administration. The outer call is also bounded by `MEMORY_REFERENCE_EXTRACTION_TIMEOUT_SECONDS`; it is not a fixed two-second call.

The LLM extracts any expression that designates a person, place, or entity through
a relationship or possession rather than by name:

| Query | Extracted References |
|-------|---------------------|
| "envoie un email à mon voisin et mon père" | `["mon voisin", "mon père"]` |
| "appelle mon frère" | `["mon frère"]` |
| "quelle est l'adresse de Jean Dupont ?" | `[]` (named entity, no resolution needed) |
| "météo demain à Paris" | `[]` |
| "dis à la petite que je l'aime" | `["la petite"]` |

### Migration Note (v1 → v2)

The previous regex-based approach (56 French patterns in `MemoryReferenceResolutionService`)
still exists for Phase 3 (resolution) but pattern **detection** is now fully LLM-driven.
This eliminates the need to maintain language-specific regex patterns and handles edge
cases (nicknames, regional expressions, non-standard possessives) that regex could not.

---

## Structures de Données

### ResolvedReferences

```python
@dataclass
class ResolvedReferences:
    """Result of memory-based reference resolution."""

    # Requête originale (inchangée)
    original_query: str

    # Requête avec références remplacées par les noms résolus
    enriched_query: str

    # Dict mapping reference → resolved value (a name, or an address for a
    # location query). Example: {"mon frère": "jean dupond"}
    mappings: dict[str, str] = field(default_factory=dict)

    # What each value IS, as the resolver declares it (prompt rule 6):
    # "person_name", or "postal_address" for a location query.
    value_kinds: dict[str, str] = field(default_factory=dict)

    def has_resolutions(self) -> bool:
        """Check if any references were resolved."""
        return len(self.mappings) > 0
```

### Where the references live

The turn's references have ONE home: `QueryIntelligence.resolved_references`, a
tuple of `ResolvedReferenceEntry(reference, value, kind, source)`
(`analysis/resolved_references.py`). The router rewrites it on every turn and the
checkpoint carries it through a HITL resume; it is read back through
`turn_references(state)` alone (guard
`tests/unit/domains/agents/test_resolved_references_single_reader_guard.py`).
There is no state key of its own any more: written only when non-empty, such a
copy was inherited by every later turn (ADR-120 amendment 2026-10-11).

---

## Configuration

The two slots are `memory_reference_extraction` and
`memory_reference_resolution`. Provider, model, reasoning, token budget and
configured timeout come from the [central LLM configuration](LLM_CONFIG_ADMIN.md)
and its database overrides/defaults. Do not infer an instance's model from a
historical environment example.

`MemoryResolver._extract_references()` has an additional outer timeout from
`core.constants.MEMORY_REFERENCE_EXTRACTION_TIMEOUT_SECONDS`.
`MemoryReferenceResolutionService._resolve_with_llm()` reads its timeout through
`get_llm_config_for_agent(settings, "memory_reference_resolution")`.

```python
from src.core.config import settings
from src.core.llm_config_helper import get_llm_config_for_agent

resolution_config = get_llm_config_for_agent(settings, "memory_reference_resolution")
timeout_seconds = resolution_config.timeout_seconds
```

There is no `MEMORY_REFERENCE_RESOLUTION_ENABLED` feature switch. Reference
resolution remains part of query analysis; access to memory facts still respects
the active account, memory capability and personal consent. A failed or timed-out
resolution preserves the original query. The typed result and current-turn reader
described above prevent a reference from being inherited by a later turn.

## Intégration

The resolution runs inside the query analysis, not in a node of its own (each
point below is read from the code):

- **Query analysis** — `MemoryResolver.retrieve_and_resolve`
  (`services/analysis/memory_resolver.py`) retrieves the memory facts, then calls
  `resolve_pre_planner(query, memory_facts, config)`. The analysis LLM may add
  references of its own (`QueryAnalyzerService`), never replacing one the memory
  service resolved.
- **State** — the references live in `QueryIntelligence.resolved_references`,
  typed (`person_name`, `postal_address`, `place`, `datetime`, `other`) and read
  through `turn_references`; the planner renders them one per line with their
  kind (`render_reference_lines`) and works from `english_enriched_query`.
- **Clarification** — a clarification answer is resolved the same way before it
  is planned again (`planner_node_v3`, log event
  `clarification_resolution_memory_success`).
- **Response** — nothing rewrites the answer: `get_response_prompt` renders
  each reference with its kind (`- "my brother" = jean dupond [person_name]`)
  and the model phrases the reference itself, in the person's language.
- **ReAct and parameters** — the ReAct loop reads the pipeline's own
  `<ResolvedReferences>` section (`nodes/react_context.py`); the parameter guard
  (`semantic/param_guard.py`) reads `person_name_values` only — a value a
  producer declared a person's name, unless another producer declared the same
  value a place or an address that turn. The resolver declares its `kinds`
  (prompt rule 6); after a change of the `memory_reference_resolution` slot,
  rerun `python -m scripts.semantic_simulation.memory_kinds --real-models`.

---

## Fail-Safe Design

Le service est conçu pour **ne jamais bloquer** la conversation.

### Comportements Fail-Safe

| Phase | Condition | Comportement |
|-------|-----------|--------------|
| Phase 1 (extraction) | LLM timeout (outer bound) | Return `[]` → fallback to broad facts |
| Phase 1 (extraction) | LLM error | Return `[]` → fallback to broad facts |
| Phase 2 (targeted search) | All searches fail | Return None → fallback to broad facts |
| Phase 2 (targeted search) | No facts found | Return None → fallback to broad facts |
| Phase 3 (resolution) | LLM call fails | Return None → planner uses original query |
| All phases | No references + no broad facts | Return (None, None) → no resolution |

### Code (MemoryResolver.retrieve_and_resolve)

```python
async def retrieve_and_resolve(self, query, user_id, config):
    # Parallel: broad retrieval + Phase 1 extraction
    memory_facts, references = await asyncio.gather(
        self._retrieve_memory_facts(query, user_id, config),
        self._extract_references(query, config),
    )

    if references:
        # Phase 2: targeted search per reference (parallel)
        targeted_facts = await self._search_memories_targeted(references, user_id, config)

        if targeted_facts:
            # Phase 3: resolve using targeted facts
            resolved = await self._resolve_memory_references(query, targeted_facts, config)
        elif memory_facts:
            # Fallback: broad facts if targeted search found nothing
            resolved = await self._resolve_memory_references(query, memory_facts, config)
    elif memory_facts:
        # No references extracted → try resolution with broad facts anyway
        resolved = await self._resolve_memory_references(query, memory_facts, config)

    return memory_facts, resolved
```

---

## Exemples d'Usage

### Exemple 1: Référence Familiale

```python
# Input
query = "recherche l'adresse de mon frère"
memory_facts = "J'ai un frère né en 1981 qui s'appelle jean dupond"

# Resolution
service = get_memory_reference_resolution_service()
result = await service.resolve_pre_planner(query, memory_facts)

# Output
result.original_query  # "recherche l'adresse de mon frère"
result.enriched_query  # "recherche l'adresse de jean dupond"
result.mappings        # {"mon frère": "jean dupond"}
```

### Exemple 2: Référence Professionnelle

```python
# Input
query = "envoie un email à mon patron pour demander congé"
memory_facts = "Mon patron s'appelle Pierre Durand, il est directeur technique"

# Resolution
result = await service.resolve_pre_planner(query, memory_facts)

# Output
result.enriched_query  # "envoie un email à Pierre Durand pour demander congé"
result.mappings        # {"mon patron": "Pierre Durand"}
```

### Exemple 3: Références Multiples

```python
# Input
query = "organise un dîner avec ma femme et mon frère"
memory_facts = """
- Mon épouse s'appelle Corinne
- J'ai un frère jean
"""

# Resolution
result = await service.resolve_pre_planner(query, memory_facts)

# Output
result.enriched_query  # "organise un dîner avec Corinne et jean"
result.mappings        # {"ma femme": "Corinne", "mon frère": "jean"}
```

### Exemple 4: Aucune Résolution

```python
# Input
query = "quel temps fait-il demain ?"
memory_facts = "Je vis à Paris"

# Resolution - No relational references detected
result = await service.resolve_pre_planner(query, memory_facts)

# Output
result.has_resolutions()  # False
result.enriched_query     # "quel temps fait-il demain ?" (unchanged)
```

---

## Métriques & Observabilité

### Logs Structurés

| Event | Level | Description |
|-------|-------|-------------|
| `memory_resolution_skipped_no_facts` | DEBUG | Skipped - no memory facts |
| `memory_resolution_no_references_detected` | DEBUG | Skipped - no patterns match |
| `memory_resolution_started` | INFO | Resolution started |
| `memory_resolution_success` | INFO | Reference resolved |
| `memory_resolution_timeout` | WARNING | LLM call timed out |
| `memory_resolution_error` | ERROR | LLM call failed |
| `memory_resolution_complete` | INFO | All references processed |

### Example Log Output

```json
{
  "event": "memory_resolution_success",
  "level": "info",
  "reference": "mon frère",
  "resolved_name": "jean dupond",
  "timestamp": "2025-12-24T10:30:00Z"
}
```

### Token Tracking

Les tokens LLM sont comptés via `TokenTrackingCallback` propagé depuis le config:

```python
config = enrich_config_with_node_metadata(base_config, "memory_reference_resolution")
result = await llm.ainvoke(prompt, config=config)
# Tokens attributed to "memory_reference_resolution" node
```

---

## Fichiers Associés

| Fichier | Description |
|---------|-------------|
| `services/analysis/memory_resolver.py` | Orchestrator (3-phase pipeline) |
| `services/memory_reference_resolution_service.py` | Phase 3: LLM resolution service |
| `prompts/v1/memory_reference_extraction_prompt.txt` | Phase 1: extraction prompt |
| `prompts/v1/memory_reference_resolution_prompt.txt` | Phase 3: resolution prompt |
| `services/query_analyzer_service.py` | Integration (Step 1 of analyze_full) |
| `analysis/resolved_references.py`, `analysis/query_intelligence_helpers.py` | Typed entries, serialization and the single `turn_references` reader |
| `core/config/agents.py` | Configuration settings |
| `domains/llm_config/constants.py` | LLM type: memory_reference_extraction |

---

## Related Documentation

- [ADR-013: LangMem Long-Term Memory](../architecture/ADR-013-LangMem-Long-Term-Memory.md)
- [LONG_TERM_MEMORY.md](./LONG_TERM_MEMORY.md) - Architecture mémoire long-terme complète

---

**Fin de MEMORY_RESOLUTION.md**
