# Recherche Hybride BM25 + Sémantique

> Système de recherche mémoire combinant BM25 (keyword matching) et embeddings sémantiques (pgvector)
>
> **Version**: 1.0
> **Date**: 2026-02-02

## Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Algorithme de Scoring](#algorithme-de-scoring)
- [Composants](#composants)
- [Configuration](#configuration)
- [Métriques](#métriques)
- [Dépannage](#dépannage)

---

## Vue d'Ensemble

La recherche hybride améliore le rappel (recall) des mémoires en combinant deux signaux complémentaires :

| Signal | Force | Faiblesse |
|--------|-------|-----------|
| **Sémantique** (pgvector) | Comprend le sens, synonymes | Rate les mots-clés exacts |
| **BM25** (keyword) | Correspondances exactes | Ne comprend pas le sens |

**Résultat** : Meilleure précision pour les requêtes mixtes ("mon frère Jean" → correspondance sémantique "famille" + keyword "Jean").

### Flux d'Exécution

```
search_hybrid(store, namespace, query)
    │
    ├─ 1. SEMANTIC SEARCH (pgvector, limit×3, min_score=0.3)
    │
    ├─ 2. GET CORPUS (jusqu'à 500 documents)
    │
    ├─ 3. BUILD/GET BM25 INDEX (cache LRU par user)
    │
    ├─ 4. SCORE QUERY (BM25, normalisation 0-1)
    │
    ├─ 5. COMBINE SCORES (alpha × semantic + (1-alpha) × bm25)
    │
    ├─ 6. APPLY BOOST (+10% si les deux signaux forts)
    │
    └─ 7. FILTER & SORT (≥ min_score, top K)
```

---

## Architecture

### Formule de Scoring (RRF-like)

```
final_score = α × semantic_score + (1 - α) × bm25_score_normalized

Où:
- α = 0.6 (default) → 60% sémantique, 40% BM25
- semantic_score = similarité cosine pgvector (0.0-1.0)
- bm25_score_normalized = raw_bm25 / max(bm25_scores)
```

### Boost Optionnel

Si les deux signaux sont forts (> threshold), amplification de 10% :

```python
if sem_score > boost_threshold and bm25_score > boost_threshold:
    final_score *= 1.1
```

### Fallback Strategy

```
Hybrid désactivé?     → semantic-only
Semantic results vide → []
Corpus vide           → semantic results
Query tokens vide     → semantic results
BM25 all-zero         → semantic results
Exception             → semantic results
```

---

## Composants

### 1. BM25IndexManager

**Fichier** : `apps/api/src/infrastructure/store/bm25_index.py`

```python
class BM25IndexManager:
    """Gestion des indices BM25 avec cache LRU par utilisateur."""

    def __init__(self, settings: Settings):
        self._local_cache: dict[str, tuple[BM25Okapi, list[str]]] = {}
        self._max_users = settings.memory_bm25_cache_max_users  # 100

    def get_or_build_index(
        self,
        user_id: str,
        documents: list[str],
        document_ids: list[str],
    ) -> tuple[BM25Okapi, list[str]]:
        # 1. Compute content hash (MD5 des documents triés)
        # 2. Cache hit? → Return
        # 3. Cache miss? → Build BM25Okapi + cache
        # 4. LRU eviction si plein
```

**Cache Key** : `bm25:{user_id}:{content_hash[:8]}`

**Invalidation** : Automatique via hash du contenu.

### 2. Tokenization French-Aware

```python
def tokenize_text(text: str) -> list[str]:
    """Tokenization avec support Unicode/accents."""
    _TOKEN_PATTERN = re.compile(r"[\w']+", re.UNICODE)
    tokens = _TOKEN_PATTERN.findall(text.lower())
    return [t for t in tokens if len(t) > 1]  # Filtre < 2 chars
```

**Exemple** :
```
"C'est très difficile à faire"
→ ["c'est", "très", "difficile", "faire"]
```

### 3. search_hybrid()

**Fichier** : `apps/api/src/infrastructure/store/semantic_store.py`

```python
async def search_hybrid(
    store: BaseStore,
    namespace: StoreNamespace,
    query: str,
    limit: int = 10,
    min_score: float | None = None,  # default: 0.5
    alpha: float | None = None,      # default: 0.6
) -> list[SearchItem]:
    """Recherche hybride BM25 + sémantique."""
```

### 4. Intégration Memory Injection

```python
# apps/api/src/domains/agents/middleware/memory_injection.py

async def build_psychological_profile(...):
    # Utilise search_hybrid() au lieu de search_semantic()
    results = await search_hybrid(store, namespace, query, limit, min_score)
```

---

## Configuration

### Variables d'Environnement

```bash
# Activer/désactiver la recherche hybride
MEMORY_HYBRID_ENABLED=true

# Poids sémantique (0.0-1.0)
MEMORY_HYBRID_ALPHA=0.6

# Score minimum pour inclusion
MEMORY_HYBRID_MIN_SCORE=0.5

# Seuil pour boost 10%
MEMORY_HYBRID_BOOST_THRESHOLD=0.5

# Taille max du cache BM25
MEMORY_BM25_CACHE_MAX_USERS=100
```

### Pydantic Settings

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `memory_hybrid_enabled` | bool | True | Active la recherche hybride |
| `memory_hybrid_alpha` | float | 0.6 | Poids sémantique (0=BM25 only, 1=semantic only) |
| `memory_hybrid_min_score` | float | 0.5 | Score minimum combiné |
| `memory_hybrid_boost_threshold` | float | 0.5 | Seuil pour boost 10% |
| `memory_bm25_cache_max_users` | int | 100 | Max utilisateurs en cache |

### Constantes

**Fichier** : `apps/api/src/core/constants.py`

```python
MEMORY_HYBRID_ALPHA_DEFAULT = 0.6
MEMORY_HYBRID_MIN_SCORE_DEFAULT = 0.5
MEMORY_HYBRID_BOOST_THRESHOLD_DEFAULT = 0.5
MEMORY_BM25_CACHE_MAX_USERS_DEFAULT = 100
```

---

## Métriques

### Prometheus

```python
# Recherche hybride
hybrid_search_total = Counter(
    "memory_hybrid_search_total",
    labels=["status"]  # success, error, fallback
)

hybrid_search_duration_seconds = Histogram(
    "memory_hybrid_search_duration_seconds",
    buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0]
)

# Cache BM25
bm25_cache_hits_total = Counter("memory_bm25_cache_hits_total")
bm25_cache_misses_total = Counter("memory_bm25_cache_misses_total")
bm25_cache_size = Gauge("memory_bm25_cache_size")
```

### Logs Structurés

```python
logger.debug(
    "hybrid_search_completed",
    namespace=namespace.to_tuple(),
    semantic_count=len(semantic_results),
    bm25_corpus_size=len(all_items),
    result_count=len(combined),
)

logger.debug(
    "bm25_index_built",
    user_id=user_id,
    document_count=len(documents),
    cache_size=len(self._local_cache),
)
```

---

## Performance

### Complexité Temporelle

| Opération | Complexité | Notes |
|-----------|-----------|-------|
| Semantic search | O(1) | Indexé pgvector |
| Get corpus | O(n) | Jusqu'à 500 docs |
| BM25 scoring | O(n×m) | n=corpus, m=tokens |
| Combine scores | O(n) | Single pass |
| **Total** | **O(n×m)** | Dominé par BM25 |

### Benchmarks Estimés

```
Corpus: 100 mémoires/user
Query: "réunions demain"

Semantic search:    5-10ms   (indexé)
Get corpus:         20-50ms  (DB)
BM25 cache hit:     0-2ms    (in-memory)
BM25 scoring:       10-20ms  (CPU)
Combine scores:     2-5ms    (single pass)

Total avec cache:   ~40-90ms
Sans cache:         ~60-120ms
```

---

## Dépannage

### Problèmes Courants

#### Résultats non pertinents

1. Vérifier `MEMORY_HYBRID_ALPHA` (augmenter pour plus de sémantique)
2. Vérifier `MEMORY_HYBRID_MIN_SCORE` (baisser pour plus de résultats)
3. Consulter les logs `hybrid_search_completed`

#### Performance dégradée

1. Vérifier `bm25_cache_hits_total` vs `bm25_cache_misses_total`
2. Augmenter `MEMORY_BM25_CACHE_MAX_USERS` si nécessaire
3. Vérifier la taille du corpus (> 500 docs peut être lent)

#### Fallback fréquent

1. Consulter les logs `no_semantic_results`, `bm25_all_zero`
2. Vérifier que les embeddings sont correctement générés
3. Vérifier la tokenization des queries

### Commandes Utiles

```bash
# Vérifier les métriques BM25
curl -s localhost:8000/metrics | grep bm25

# Vérifier les métriques hybrid
curl -s localhost:8000/metrics | grep hybrid_search
```

---

## Comparaison Avant/Après

### Semantic-Only (Avant)

```
Query: "Je déteste les réunions longues"

Results:
1. "Réunion importante demain" (0.75)
2. "Déteste les emails longs" (0.70)
3. "Long rapport à lire" (0.65)

→ Rate la correspondance exacte "déteste" + "réunion"
```

### Hybrid (Après)

```
Query: "Je déteste les réunions longues"

Semantic: [0.75, 0.70, 0.65]
BM25:     [0.95, 0.50, 0.30]  (keyword "déteste réunion")
Combined: [0.83, 0.62, 0.51]

→ Meilleur ranking avec boost keyword!
```

---

## Références

- **BM25Index**: `apps/api/src/infrastructure/store/bm25_index.py`
- **Semantic Store**: `apps/api/src/infrastructure/store/semantic_store.py`
- **Memory Injection**: `apps/api/src/domains/agents/middleware/memory_injection.py`
- **Configuration**: `apps/api/src/core/config/agents.py`
- **Constants**: `apps/api/src/core/constants.py`
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
- [rank-bm25 library](https://github.com/dorianbrown/rank_bm25)

---

**Fin de HYBRID_SEARCH.md** - Documentation technique recherche hybride.
