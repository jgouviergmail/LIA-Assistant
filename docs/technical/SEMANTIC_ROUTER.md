# Semantic Tool Router

> **Technical Documentation** - Phase 6 LLM-Native Architecture
>
> Version: 1.2
> Date: 2026-01-22
> Related: [ADR-048](../architecture/ADR-048-Semantic-Tool-Router.md) | [LOCAL_EMBEDDINGS.md](LOCAL_EMBEDDINGS.md) | [SEMANTIC_INTENT_DETECTION.md](SEMANTIC_INTENT_DETECTION.md) | [SMART_SERVICES.md](SMART_SERVICES.md) (Semantic Expansion)

---

## Overview

Le Semantic Tool Router remplace le routing basé sur mots-clés par une approche sémantique utilisant des embeddings locaux. Il sélectionne automatiquement les tools pertinents en fonction de la similarité sémantique avec la requête utilisateur.

### Key Features

- **Max-Pooling Strategy** : Évite la dilution sémantique
- **Double Threshold** : Confiance haute (0.70) + zone d'incertitude (0.60)
- **Local Embeddings** : intfloat/multilingual-e5-small (100+ langues)
- **Zero API Cost** : Inférence 100% locale
- **Startup Caching** : Embeddings des tools pré-calculés

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEMANTIC TOOL ROUTER                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │ User Query   │───▶│ LocalE5Embeddings │───▶│ Query Vector │  │
│  │ "mes emails" │    │ (384 dims)        │    │ [0.12, ...]  │  │
│  └──────────────┘    └──────────────────┘    └──────────────┘  │
│                                                     │           │
│                                                     ▼           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              MAX-POOLING COMPARISON                       │  │
│  │                                                            │  │
│  │  search_emails_tool:                                       │  │
│  │    keywords: ["emails récents", "messages", "inbox"]       │  │
│  │    scores:   [0.85, 0.72, 0.45]                           │  │
│  │    MAX = 0.85 ✓                                           │  │
│  │                                                            │  │
│  │  search_contacts_tool:                                     │  │
│  │    keywords: ["contacts", "personnes", "numéro"]          │  │
│  │    scores:   [0.32, 0.28, 0.15]                           │  │
│  │    MAX = 0.32 ✗                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                     │           │
│                                                     ▼           │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              DOUBLE THRESHOLD DECISION                    │  │
│  │                                                            │  │
│  │  score >= 0.70  →  HIGH confidence (direct inject)        │  │
│  │  score >= 0.60  →  MEDIUM confidence (uncertainty flag)   │  │
│  │  score < 0.60   →  Not selected                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Usage

### Basic Usage

```python
from src.domains.agents.services.tool_selector import (
    get_tool_selector,
    initialize_tool_selector,
)

# At startup: initialize with tool manifests
selector = await initialize_tool_selector(registry.list_tool_manifests())

# Select tools for query
result = await selector.select_tools(
    query="montre-moi mes derniers emails",
    max_results=5,
)

# Check results
for tool in result.selected_tools:
    print(f"{tool.tool_name}: {tool.score:.2f} ({tool.confidence})")
    # search_emails_tool: 0.85 (high)
    # list_emails_tool: 0.72 (high)
```

### Checking Confidence

```python
result = await selector.select_tools(query="truc bizarre")

if result.has_uncertainty:
    # At least one selected tool has medium confidence
    print("Warning: uncertain tool selection")

if result.top_score < 0.60:
    # No tools matched
    print("No relevant tools found")
```

### Filtering Available Tools

```python
# Only consider email-related tools
email_tools = [t for t in manifests if t.agent == "emails_agent"]

result = await selector.select_tools(
    query="search inbox",
    available_tools=email_tools,
)
```

---

## Configuration

### Variables .env - Semantic Thresholds

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_TOOL_SELECTOR_HARD_THRESHOLD` | 0.70 | High confidence (injection directe) |
| `SEMANTIC_TOOL_SELECTOR_SOFT_THRESHOLD` | 0.60 | Uncertainty zone (confidence reduite) |
| `SEMANTIC_TOOL_SELECTOR_MAX_TOOLS` | 8 | Max tools retournes |
| `SEMANTIC_DOMAIN_HARD_THRESHOLD` | 0.75 | High confidence domain match |
| `SEMANTIC_DOMAIN_SOFT_THRESHOLD` | 0.65 | Uncertainty zone domain |
| `SEMANTIC_DOMAIN_MAX_DOMAINS` | 5 | Max domains retournes |
| `SEMANTIC_INTENT_HIGH_THRESHOLD` | 0.75 | High confidence intent detection |
| `SEMANTIC_INTENT_FALLBACK_THRESHOLD` | 0.50 | Sous ce seuil → intent "full" |
| `SEMANTIC_FALLBACK_THRESHOLD` | 0.4 | Fallback perplexity/wikipedia |

### Variables .env - Semantic Pivot LLM

Le **Semantic Pivot** traduit les queries vers l'anglais avant embedding matching.
Ceci ameliore significativement le matching car les embeddings E5 sont optimises pour l'anglais.

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_PIVOT_LLM_PROVIDER` | openai | Provider LLM |
| `SEMANTIC_PIVOT_LLM_MODEL` | gpt-4.1-mini | Modele LLM (fast, cheap) |
| `SEMANTIC_PIVOT_LLM_TEMPERATURE` | 0.2 | Temperature |
| `SEMANTIC_PIVOT_LLM_MAX_TOKENS` | 200 | Max tokens (translations courtes) |
| `SEMANTIC_PIVOT_LLM_REASONING_EFFORT` | minimal | Effort raisonnement (o-series) |

### Thresholds (Code)

```python
# apps/api/src/domains/agents/services/tool_selector.py

DEFAULT_HARD_THRESHOLD = 0.70  # High confidence
DEFAULT_SOFT_THRESHOLD = 0.60  # Uncertainty zone
DEFAULT_MAX_TOOLS = 8          # Maximum tools returned
```

### Custom Thresholds at Init

```python
await selector.initialize(
    tool_manifests=manifests,
    hard_threshold=0.75,  # More strict
    soft_threshold=0.65,
    max_tools=5,
)
```

### Embedding Model

```python
# Local E5 model configuration
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSIONS = 384
```

---

## Semantic Keywords

Les tools définissent leurs `semantic_keywords` dans leurs manifestes pour améliorer le matching sémantique.

**IMPORTANT** : Les keywords doivent être en **anglais uniquement**. Le modèle E5 multilingue (intfloat/multilingual-e5-small) gère automatiquement la correspondance sémantique cross-linguistique via le "semantic pivot". Une requête française comme "mes emails récents" correspondra correctement au keyword anglais "recent emails" grâce à l'espace sémantique partagé.

### Example: Email Tool

```python
# apps/api/src/domains/agents/emails/catalogue_manifests.py

search_emails_catalogue_manifest = ToolManifest(
    name="search_emails_tool",
    agent="emails_agent",
    description="Search emails by query, sender, date range",

    semantic_keywords=[
        # Core search actions
        "get my emails",
        "get my last emails",
        "get my recent emails",
        "fetch my emails",
        "list my emails",
        "show my emails",
        "find emails",
        "search emails",
        "look for emails",
        # Filters
        "unread emails",
        "new messages",
        "latest emails",
        "emails from",
        "emails with attachment",
        "important emails",
        "starred emails",
    ],

    # ... rest of manifest
)
```

### Best Practices for Keywords

1. **English Only** : Tous les keywords en anglais (le modèle E5 gère le multilingual via semantic pivot)
2. **Include action + noun** : "search emails", "find contacts", "get calendar events"
3. **Add variations** : "email", "mail", "message" - couvrir les synonymes courants
4. **Natural language phrases** : Inclure des phrases comme l'utilisateur pourrait les dire
5. **No duplicates** : Chaque keyword unique (max-pooling élimine la redondance)
6. **10-20 keywords** : Sweet spot pour coverage vs précision
7. **Discriminate read vs write** : Ensure read-only tools have keywords distinct from mutation tools. Example: `get_events_tool` needs "which appointment do I have on Saturday" (read intent) to avoid being outranked by `update_event_tool`'s "change appointment time" keyword (write intent). Without discriminant keywords, the hybrid scorer may rank the wrong tool higher (see v1.11.1 fix).

---

## Max-Pooling Strategy

### Problem with Average-Pooling

```
Query: "montre mes derniers emails"

Average-Pooling (old):
  keywords = ["emails", "messages", "inbox"]
  combined = embed("emails | messages | inbox")  # Single embedding
  score = cosine(query_emb, combined)
        = 0.58  # Diluted by irrelevant "inbox"

Result: Score too low → tool not selected
```

### Max-Pooling Solution

```
Query: "montre mes derniers emails"

Max-Pooling (new):
  kw_embeddings = [embed("emails"), embed("messages"), embed("inbox")]
  scores = [
      cosine(query_emb, embed("emails"))   = 0.85,
      cosine(query_emb, embed("messages")) = 0.72,
      cosine(query_emb, embed("inbox"))    = 0.45,
  ]
  score = MAX(scores) = 0.85

Result: High score → tool selected with high confidence
```

---

## API Reference

### Classes

#### `SemanticToolSelector`

Main selector class (singleton pattern).

```python
class SemanticToolSelector:
    async def initialize(
        self,
        tool_manifests: list[ToolManifest],
        hard_threshold: float | None = None,
        soft_threshold: float | None = None,
        max_tools: int | None = None,
    ) -> None

    async def select_tools(
        self,
        query: str,
        available_tools: list[ToolManifest] | None = None,
        max_results: int | None = None,
        include_context_utilities: bool = True,
    ) -> ToolSelectionResult

    def get_cached_tools(self) -> list[str]
    def is_initialized(self) -> bool
```

#### `ToolMatch`

Single tool match result.

```python
@dataclass
class ToolMatch:
    tool_name: str
    tool_manifest: ToolManifest
    score: float
    confidence: str  # "high", "medium", "low"
```

#### `ToolSelectionResult`

Complete selection result.

```python
@dataclass
class ToolSelectionResult:
    selected_tools: list[ToolMatch]
    top_score: float
    has_uncertainty: bool
    all_scores: dict[str, float]

    @property
    def tool_names(self) -> list[str]
```

### Functions

```python
# Get singleton instance
async def get_tool_selector() -> SemanticToolSelector

# Initialize at startup
async def initialize_tool_selector(
    tool_manifests: list[ToolManifest]
) -> SemanticToolSelector

# Reset for testing
def reset_tool_selector() -> None
```

---

## Performance

| Metric | Value |
|--------|-------|
| Model Load | ~9s (one-time, Pi 5) |
| Query Embedding | ~50ms |
| Similarity Calculation | ~5ms for 30 tools |
| Total Selection Time | ~55ms |
| Memory (model) | ~470MB |

---

## Debugging

### Enable Debug Logging

```python
# Logs automatically include:
# - semantic_tool_selection_debug_top5: Top 5 tools with best keyword
# - semantic_tool_selection_complete: Final selection summary

# Example log:
{
    "event": "semantic_tool_selection_debug_top5",
    "query": "mes derniers emails",
    "top_5_tools": [
        ("search_emails_tool", 0.852, "derniers emails"),
        ("list_emails_tool", 0.721, "emails récents"),
        ("search_contacts_tool", 0.312, "contacts"),
        ...
    ],
    "hard_threshold": 0.70,
    "soft_threshold": 0.60,
    "strategy": "max-pooling"
}
```

### Testing Tool Selection

```python
# Test in Python shell
from src.domains.agents.services.tool_selector import get_tool_selector

selector = await get_tool_selector()

# Debug all scores
result = await selector.select_tools("mes emails")
for name, score in sorted(result.all_scores.items(), key=lambda x: -x[1])[:10]:
    print(f"{name}: {score:.3f}")
```

---

## Semantic Intent Detection (Phase 7)

En complement du Tool Router, le systeme inclut un **SemanticIntentDetector** qui classifie l'intention utilisateur pour optimiser le filtrage des tools.

### Integration

```
User Query
    |
    v
+-------------------+     +----------------------+
| SemanticToolRouter |     | SemanticIntentDetector|
| (Domain Detection) |     | (Intent Classification)|
+-------------------+     +----------------------+
    |                           |
    | domains: [emails]         | intent: "action"
    |                           |
    v                           v
+-------------------------------------------+
|            PLANNER NODE                    |
|  - Filter by domains (emails_agent only)  |
|  - Filter by intent (action -> CRUD tools)|
+-------------------------------------------+
```

### Intent Types

| Intent | Included Tool Categories |
|--------|--------------------------|
| `action` | BASE + create, update, delete, send, details, readonly |
| `detail` | BASE + details, readonly |
| `search` | BASE + readonly |
| `list` | BASE + readonly |
| `full` | All categories (fallback) |

**BASE** = `{search, list, system}` - toujours inclus

### Documentation Complete

Voir [SEMANTIC_INTENT_DETECTION.md](SEMANTIC_INTENT_DETECTION.md) pour:
- Architecture complete
- Configuration des anchors
- API Reference
- Debugging

---

## Related Documentation

- [ADR-048: Semantic Tool Router](../architecture/ADR-048-Semantic-Tool-Router.md)
- [ADR-049: Local E5 Embeddings](../architecture/ADR-049-Local-E5-Embeddings.md)
- [LOCAL_EMBEDDINGS.md](LOCAL_EMBEDDINGS.md)
- [SEMANTIC_INTENT_DETECTION.md](SEMANTIC_INTENT_DETECTION.md)
- [CATALOGUE_SYSTEM.md](CATALOGUE_SYSTEM.md)
