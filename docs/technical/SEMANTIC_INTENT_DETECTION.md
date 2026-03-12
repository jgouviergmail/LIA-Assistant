# Semantic Intent Detection

> **Technical Documentation** - Phase 7 Token Optimization
>
> Version: 1.1
> Date: 2025-12-27
> Related: [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md) | [ROUTER.md](ROUTER.md) | [PLANNER.md](PLANNER.md)

---

## Overview

Le **SemanticIntentDetector** est un service de classification d'intention basé sur des embeddings locaux (E5-small). Il remplace la detection par mots-clés (`keyword_strategies.py`) pour determiner la strategie de filtrage des tools.

### Key Features

- **Zero Maintenance** : Plus de listes de mots-cles a maintenir par langue
- **Multilingual Native** : E5-small gere automatiquement FR/EN/DE/ES/...
- **Max-Pooling Strategy** : Meilleure precision semantique
- **Category-Based Filtering** : Filtrage intelligent par categorie de tool
- **Fallback Mechanism** : Retry avec strategie "full" si echec

---

## Architecture

```
                          USER QUERY
                              |
                              v
+-------------------------------------------------------------+
|                      ROUTER NODE                             |
|                                                              |
|  1. SemanticIntentDetector                                   |
|     Query: "envoie un email a Jean"                         |
|              |                                               |
|              v                                               |
|     +-----------------------+                                |
|     | E5-small Embeddings   |                                |
|     | (384 dims, local)     |                                |
|     +-----------------------+                                |
|              |                                               |
|              v                                               |
|     +-----------------------+                                |
|     | Max-Pooling vs        |                                |
|     | Intent Anchors (EN)   |                                |
|     +-----------------------+                                |
|              |                                               |
|              v                                               |
|     Intent: "action" (0.87)                                  |
|                                                              |
|  2. Turn Type Refinement                                     |
|     - REFERENCE_PURE  -> strategy = "detail"                |
|     - REFERENCE_ACTION -> strategy = detected_intent        |
|     - ACTION          -> strategy = detected_intent         |
|                                                              |
|  3. Store in State: detected_intent                          |
+-------------------------------------------------------------+
                              |
                              v
+-------------------------------------------------------------+
|                      PLANNER NODE                            |
|                                                              |
|  1. Read detected_intent from state                          |
|  2. Load filtered catalogue by category                      |
|                                                              |
|     Strategy -> Categories Included                          |
|     ----------------------------------------                 |
|     action   -> BASE + create/update/delete/send/details    |
|     detail   -> BASE + details + readonly                   |
|     search   -> BASE + readonly                             |
|     list     -> BASE + readonly                             |
|     full     -> ALL categories                              |
|                                                              |
|     BASE = {search, list, system}                           |
|                                                              |
|  3. If planner fails AND strategy != "full"                 |
|     -> FALLBACK: Retry with strategy = "full"               |
+-------------------------------------------------------------+
```

---

## Intent Types

Le systeme detecte 5 types d'intentions :

| Intent | Description | Tool Categories |
|--------|-------------|-----------------|
| `action` | Actions CRUD (creer, modifier, supprimer, envoyer) | BASE + create, update, delete, send, details, readonly |
| `detail` | Demande de details sur un element | BASE + details, readonly |
| `search` | Recherche d'elements | BASE + readonly |
| `list` | Lister des elements | BASE + readonly |
| `full` | Fallback (faible confiance) | ALL |

**BASE** = `{search, list, system}` - toujours inclus

---

## Tool Categories

Chaque tool est categorise pour le filtrage :

| Category | Convention de nommage | Exemples |
|----------|----------------------|----------|
| `search` | `search_*` | search_contacts, search_emails |
| `list` | `list_*` | list_calendars, list_tasks |
| `details` | `*_details*` | get_event_details, get_contact_details |
| `create` | `create_*`, `add_*` | create_event, add_task |
| `update` | `update_*`, `modify_*` | update_event, modify_contact |
| `delete` | `delete_*`, `remove_*` | delete_event, remove_task |
| `send` | `send_*`, `reply_*` | send_email, reply_email |
| `readonly` | `get_*` (sans details) | get_weather, read_file |
| `system` | Tools systeme | resolve_reference, get_context_list |

### Inference Automatique

```python
from src.domains.agents.registry.catalogue import infer_tool_category

infer_tool_category("search_contacts_tool")  # -> "search"
infer_tool_category("get_event_details_tool")  # -> "details"
infer_tool_category("create_event_tool")  # -> "create"
infer_tool_category("get_weather_tool")  # -> "readonly"
```

### Category Explicite dans Manifest

```python
ToolManifest(
    name="special_tool",
    agent="my_agent",
    description="...",
    tool_category="create",  # Override inference
)
```

---

## Intent Anchors

Les anchors sont des phrases en **anglais uniquement** qui servent de reference pour la classification. Le modele E5 multilingue gere automatiquement la correspondance cross-linguistique.

```python
INTENT_ANCHORS = {
    "action": [
        "create a new item",
        "modify this item",
        "delete this item",
        "send a message",
        "update the information",
        "add a new entry",
        "remove this element",
        "write an email",
        "schedule a meeting",
        "book an appointment",
    ],
    "detail": [
        "show me the details",
        "give me more information",
        "what are the specifics",
        "tell me about this",
        "get the full information",
        "display the content",
        "read the details",
    ],
    "search": [
        "search for something",
        "find items matching",
        "look for results",
        "search in the database",
        "find by criteria",
        "lookup information",
    ],
    "list": [
        "list all items",
        "show everything",
        "display all entries",
        "enumerate the elements",
        "get the complete list",
        "show me all",
    ],
}
```

---

## Reference Type Refinement

Pour les requetes de type REFERENCE (suivi d'une action precedente), le systeme distingue :

| Type | Exemple | Comportement |
|------|---------|--------------|
| `REFERENCE_PURE` | "detail du premier" | Strategy = "detail", Domains = source uniquement |
| `REFERENCE_ACTION` | "envoie-lui un email" | Strategy = detected_intent, Domains = semantic + source |

```python
# Dans router_node_v3.py
if turn_type == TURN_TYPE_REFERENCE:
    if detected_intent == "action":
        refined_turn_type = TURN_TYPE_REFERENCE_ACTION
        # Garder domains semantiques + source
    else:
        refined_turn_type = TURN_TYPE_REFERENCE_PURE
        detected_intent = "detail"  # Forcer detail
        # Utiliser uniquement le domain source (75% token reduction)
```

---

## Fallback Mechanism

Si le planner echoue avec un catalogue filtre, le systeme retry automatiquement avec la strategie "full" :

```python
# Dans planner_node_v3.py
if tool_strategy != "full":
    # Re-prepare avec full strategy
    catalogue_retry, _ = _load_catalogue(
        registry, state, settings, run_id,
        force_full_strategy=True  # Override
    )

    # Retry plan generation
    execution_plan_retry = await planner_service.generate_plan(
        catalogue=catalogue_retry,
        ...
    )
```

---

## Usage

### Basic Detection

```python
from src.domains.agents.services.semantic_intent_detector import (
    get_intent_detector,
    initialize_intent_detector,
)

# Initialize (lazy - done automatically in router)
await initialize_intent_detector()

# Detect intent
detector = await get_intent_detector()
result = await detector.detect("envoie un email a Jean")

print(result.intent)       # "action"
print(result.confidence)   # 0.87
print(result.is_high_confidence)  # True
```

### Check All Scores

```python
result = await detector.detect("recherche mes contacts")

for intent, score in sorted(result.all_scores.items(), key=lambda x: -x[1]):
    print(f"{intent}: {score:.3f}")
# search: 0.823
# list: 0.654
# action: 0.432
# detail: 0.398
```

---

## Configuration

### Threshold

```python
# Default threshold (50% confidence - below this, use "full" strategy)
DEFAULT_THRESHOLD = 0.50

# If max score < threshold, fallback to "full"
if best_score < self._threshold:
    return IntentResult(intent="full", confidence=0.0)
```

### Custom Threshold

```python
await initialize_intent_detector(threshold=0.75)  # More strict
```

---

## Performance

| Metric | Value |
|--------|-------|
| Model | intfloat/multilingual-e5-small |
| Dimensions | 384 |
| Anchor Count | ~35 phrases |
| Init Time | ~2s (embedding all anchors) |
| Detection Time | ~50ms per query |
| Memory | Shared with SemanticToolSelector |

---

## Token Reduction

| Scenario | Strategy | Tools Loaded | Reduction |
|----------|----------|--------------|-----------|
| "recherche mes contacts" | search | ~8 | ~75% |
| "detail du premier" | detail | ~6 | ~80% |
| "envoie un email" | action | ~15 | ~55% |
| "cree un evenement demain" | action | ~15 | ~55% |
| Low confidence | full | ~34 | 0% |

---

## Debugging

### Logs

```json
{
  "event": "semantic_intent_detected",
  "query_preview": "envoie un email a Jean",
  "intent": "action",
  "confidence": 0.87,
  "is_high_confidence": true,
  "top_3": [
    ["action", 0.87, "send a message"],
    ["detail", 0.45, "show me the details"],
    ["search", 0.32, "search for something"]
  ]
}
```

### Test Detection

```python
# Python shell
from src.domains.agents.services.semantic_intent_detector import (
    get_intent_detector,
    initialize_intent_detector,
)

await initialize_intent_detector()
detector = await get_intent_detector()

# Test various queries
queries = [
    "recherche mes contacts",
    "envoie un email a Jean",
    "detail du premier",
    "liste mes evenements",
    "cree un rdv demain",
]

for q in queries:
    r = await detector.detect(q)
    print(f"{q[:30]:30} -> {r.intent:8} ({r.confidence:.2f})")
```

---

## API Reference

### Classes

#### `SemanticIntentDetector`

```python
class SemanticIntentDetector:
    async def initialize(
        self,
        threshold: float | None = None,
    ) -> None

    async def detect(
        self,
        query: str,
    ) -> IntentResult

    def is_initialized(self) -> bool
```

#### `IntentResult`

```python
@dataclass
class IntentResult:
    intent: IntentType  # "action" | "detail" | "search" | "list" | "full"
    confidence: float   # 0.0 - 1.0
    all_scores: dict[str, float]  # All intent scores

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= 0.75

    @property
    def is_uncertain(self) -> bool:
        return 0.5 <= self.confidence < 0.75
```

### Functions

```python
# Get singleton instance
async def get_intent_detector() -> SemanticIntentDetector

# Initialize at startup
async def initialize_intent_detector(
    threshold: float | None = None,
) -> SemanticIntentDetector

# Reset for testing
def reset_intent_detector() -> None
```

---

## Related Documentation

- [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md) - Tool selection semantique
- [ROUTER.md](ROUTER.md) - Router node integration
- [PLANNER.md](PLANNER.md) - Planner node et tool strategy
- [LOCAL_EMBEDDINGS.md](LOCAL_EMBEDDINGS.md) - E5 model configuration
