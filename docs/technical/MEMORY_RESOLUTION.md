# Memory Reference Resolution Service

> Documentation technique du service `MemoryReferenceResolutionService` pour la résolution d'entités relationnelles pré-planner.

**Date**: 2026-01-12
**Version**: 1.1.0 (Architecture v3 - integration QueryAnalyzerService)
**Source**: `apps/api/src/domains/agents/services/memory_reference_resolution_service.py`

---

## Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Flow de Résolution](#flow-de-résolution)
4. [Patterns Relationnels](#patterns-relationnels)
5. [Structures de Données](#structures-de-données)
6. [Configuration](#configuration)
7. [Intégration](#intégration)
8. [Fail-Safe Design](#fail-safe-design)
9. [Exemples d'Usage](#exemples-dusage)
10. [Métriques & Observabilité](#métriques--observabilité)

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

```
┌─────────────────────────────────────────────────────────────────┐
│                        ROUTER NODE                               │
│  1. Semantic search → memory_facts                              │
│  2. Calls MemoryReferenceResolutionService.resolve_pre_planner()│
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│              MEMORY REFERENCE RESOLUTION SERVICE                 │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ Pattern Detection │────▶│ LLM Micro-Call   │                   │
│  │ (56 regex)       │    │ (gpt-4.1-mini)   │                   │
│  └──────────────────┘    └────────┬─────────┘                   │
│                                   │                              │
│                                   ▼                              │
│                          ┌───────────────┐                       │
│                          │ResolvedRefs   │                       │
│                          │- enriched_query│                       │
│                          │- mappings      │                       │
│                          └───────────────┘                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        PLANNER NODE                              │
│  Uses enriched_query with resolved entity names                  │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       RESPONSE NODE                              │
│  Uses mappings for natural phrasing:                             │
│  "J'ai trouvé l'adresse de ton frère (jean dupond)"       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flow de Résolution

### Séquence Détaillée

```
1. USER QUERY
   "recherche l'adresse de mon frère"
   │
   ▼
2. ROUTER NODE
   ├─ Semantic search on memories → memory_facts
   │  "J'ai un frère né en 1981, jean dupond"
   │
   ├─ Calls resolve_pre_planner(query, memory_facts)
   │
   ▼
3. PATTERN DETECTION
   ├─ Regex: \b(?:mon|ma)\s+frère\b
   ├─ Match: "mon frère"
   │
   ▼
4. LLM MICRO-CALL (timeout: 2000ms)
   ├─ Prompt: "Faits: {memory_facts}\nQuestion: Qui est {mon frère}?"
   ├─ Response: "jean dupond"
   │
   ▼
5. RESOLVED REFERENCES
   {
     original_query: "recherche l'adresse de mon frère",
     enriched_query: "recherche l'adresse de jean dupond",
     mappings: {"mon frère": "jean dupond"}
   }
   │
   ▼
6. PLANNER (uses enriched_query)
   Plan: search_contacts_tool(query="jean dupond")
   │
   ▼
7. RESPONSE (uses mappings)
   "Voici l'adresse de ton frère (jean dupond): ..."
```

---

## Patterns Relationnels

Le service détecte **56 patterns relationnels** via regex, organisés par catégorie.

### Famille - Core (16 patterns)

| Pattern | Type | Exemple |
|---------|------|---------|
| `\b(?:mon\|ma)\s+frère\b` | brother | "mon frère" |
| `\b(?:mon\|ma)\s+sœur\b` | sister | "ma sœur" |
| `\b(?:mon\|ma)\s+(?:femme\|épouse)\b` | wife | "ma femme", "mon épouse" |
| `\b(?:mon\|ma)\s+(?:mari\|époux)\b` | husband | "mon mari" |
| `\b(?:mon\|ma)\s+fils\b` | son | "mon fils" |
| `\b(?:mon\|ma)\s+fille\b` | daughter | "ma fille" |
| `\b(?:mon\|ma)\s+(?:père\|papa)\b` | father | "mon père", "mon papa" |
| `\b(?:mon\|ma)\s+(?:mère\|maman)\b` | mother | "ma mère", "ma maman" |

### Famille - Extended (12 patterns)

| Pattern | Type | Exemple |
|---------|------|---------|
| `\b(?:mon\|ma)\s+(?:grand-père\|papy\|papi)\b` | grandfather | "mon grand-père" |
| `\b(?:mon\|ma)\s+(?:grand-mère\|mamie\|mamy)\b` | grandmother | "ma grand-mère" |
| `\b(?:mon\|ma)\s+(?:oncle\|tonton)\b` | uncle | "mon oncle" |
| `\b(?:mon\|ma)\s+(?:tante\|tata)\b` | aunt | "ma tante" |
| `\b(?:mon\|ma)\s+(?:cousin\|cousine)\b` | cousin | "mon cousin" |
| `\b(?:mon\|ma)\s+neveu\b` | nephew | "mon neveu" |
| `\b(?:mon\|ma)\s+nièce\b` | niece | "ma nièce" |

### Social (20 patterns)

| Pattern | Type | Exemple |
|---------|------|---------|
| `\b(?:mon\|ma)\s+(?:ami\|amie\|pote\|copain\|copine)\b` | friend | "mon ami", "ma copine" |
| `\b(?:mon\|ma)\s+(?:meilleur(?:e)?\s+ami(?:e)?)\b` | best_friend | "ma meilleure amie" |
| `\b(?:mon\|ma)\s+collègue\b` | colleague | "mon collègue" |
| `\b(?:mon\|ma)\s+(?:patron\|boss\|chef)\b` | boss | "mon patron" |
| `\b(?:mon\|ma)\s+(?:médecin\|docteur)\b` | doctor | "mon médecin" |
| `\b(?:mon\|ma)\s+dentiste\b` | dentist | "mon dentiste" |
| `\b(?:mon\|ma)\s+avocat\b` | lawyer | "mon avocat" |
| `\b(?:mon\|ma)\s+comptable\b` | accountant | "ma comptable" |

### Generic (8 patterns)

| Pattern | Type | Exemple |
|---------|------|---------|
| `\b(?:mon\|ma)\s+(?:ami\|amie)\s+(\w+)\b` | friend_named | "mon ami Jean" |

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

    # Dict mapping reference → resolved name
    # Example: {"mon frère": "jean dupond"}
    mappings: dict[str, str] = field(default_factory=dict)

    def has_resolutions(self) -> bool:
        """Check if any references were resolved."""
        return len(self.mappings) > 0

    def format_for_response(self, reference: str) -> str:
        """
        Format for natural response.

        Example:
            result.format_for_response("mon frère")
            → "ton frère (jean dupond)"
        """
        if reference in self.mappings:
            resolved = self.mappings[reference]
            # Transform possessive: "mon" → "ton"
            display_ref = reference.replace("mon ", "ton ")
            return f"{display_ref} ({resolved})"
        return reference
```

### State Key

```python
STATE_KEY_RESOLVED_REFERENCES = "resolved_references"
```

Dans `MessagesState`:
```python
class MessagesState(TypedDict, total=False):
    resolved_references: dict[str, Any] | None
```

---

## Configuration

### Settings (dans `agents.py`)

```python
class MemoryReferenceResolutionSettings(BaseSettings):
    # Feature toggle
    memory_reference_resolution_enabled: bool = True

    # LLM Configuration
    memory_reference_resolution_llm_provider: str = "openai"
    memory_reference_resolution_llm_model: str = "gpt-4.1-mini"
    memory_reference_resolution_llm_temperature: float = 0.0
    memory_reference_resolution_llm_max_tokens: int = 50

    # Timeout (fail-safe)
    memory_reference_resolution_timeout_ms: int = 2000  # 2 seconds max
```

### Variables d'Environnement

```bash
# .env
MEMORY_REFERENCE_RESOLUTION_ENABLED=true
MEMORY_REFERENCE_RESOLUTION_LLM_PROVIDER=openai
MEMORY_REFERENCE_RESOLUTION_LLM_MODEL=gpt-4.1-mini
MEMORY_REFERENCE_RESOLUTION_TIMEOUT_MS=2000
```

---

## Intégration

### Router Node

```python
# router_node_v3.py (lignes 563-605)

async def _resolve_memory_references(
    state: MessagesState,
    user_query: str,
    memory_facts: str | None,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Resolve memory-based references before planning."""

    settings = get_settings()
    if not settings.memory_reference_resolution_enabled:
        return {"resolved_references": None}

    service = get_memory_reference_resolution_service()

    resolved = await service.resolve_pre_planner(
        query=user_query,
        memory_facts=memory_facts,
        user_language=state.get("user_language", "fr"),
        config=config,  # CRITICAL: propagate for token tracking
    )

    if resolved.has_resolutions():
        return {
            "resolved_references": {
                "original_query": resolved.original_query,
                "enriched_query": resolved.enriched_query,
                "mappings": resolved.mappings,
            }
        }

    return {"resolved_references": None}
```

### Planner Node

```python
# planner_node_v3.py

def _get_query_for_planning(state: MessagesState) -> str:
    """Get enriched query if available."""
    resolved = state.get("resolved_references")
    if resolved and resolved.get("enriched_query"):
        return resolved["enriched_query"]
    return state["current_user_query"]
```

### Response Node

```python
# response_node.py

def _format_with_mappings(response: str, state: MessagesState) -> str:
    """Format response with natural reference phrasing."""
    resolved = state.get("resolved_references")
    if not resolved or not resolved.get("mappings"):
        return response

    # Example: "ton frère (jean dupond)"
    for ref, name in resolved["mappings"].items():
        display_ref = ref.replace("mon ", "ton ").replace("ma ", "ta ")
        natural_form = f"{display_ref} ({name})"
        # ... insert in response
```

---

## Fail-Safe Design

Le service est conçu pour **ne jamais bloquer** la conversation.

### Comportements Fail-Safe

| Condition | Comportement |
|-----------|--------------|
| `memory_facts` is None/empty | Return original query |
| No patterns match | Return original query |
| LLM call fails | Return original query |
| LLM timeout (>2s) | Return original query |
| Invalid LLM response | Return original query |

### Code

```python
async def resolve_pre_planner(self, query, memory_facts, ...):
    # Fail-safe 1: No memory facts
    if not memory_facts:
        return ResolvedReferences(original_query=query, enriched_query=query)

    # Fail-safe 2: No patterns match
    detected = self._detect_relational_references(query)
    if not detected:
        return ResolvedReferences(original_query=query, enriched_query=query)

    # Fail-safe 3: LLM call with timeout
    for reference in detected:
        try:
            resolved = await asyncio.wait_for(
                self._resolve_reference_via_llm(reference, memory_facts),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("memory_resolution_timeout")
            continue  # Don't fail completely
        except Exception:
            continue  # Don't fail completely

    return ResolvedReferences(...)
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
| `services/memory_reference_resolution_service.py` | Service principal |
| `prompts/v1/memory_reference_resolution_prompt.txt` | Template prompt LLM |
| `nodes/router_node_v3.py` | Intégration router |
| `models.py` | STATE_KEY definition |
| `core/config/agents.py` | Configuration settings |

---

## Related Documentation

- [ADR-013: LangMem Long-Term Memory](../architecture/ADR-013-LangMem-Long-Term-Memory.md)
- [LONG_TERM_MEMORY.md](./LONG_TERM_MEMORY.md) - Architecture mémoire long-terme complète

---

**Fin de MEMORY_RESOLUTION.md**
