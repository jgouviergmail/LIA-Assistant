# Long-Term Memory - Architecture LangMem Native + Profil Psychologique

> Système de mémoire long terme pour la construction de profils psychologiques utilisateurs
>
> **Version**: 1.2
> **Date**: 2026-02-02
> **Updated**: Ajout Hybrid Search BM25 + Sémantique

## Table des Matières

- [Vue d'Ensemble](#vue-densemble)
- [Architecture](#architecture)
- [Schéma de Mémoire](#schéma-de-mémoire)
- [Composants Backend](#composants-backend)
- [Composants Frontend](#composants-frontend)
- [Configuration](#configuration)
- [API Endpoints](#api-endpoints)
- [Flux de Données](#flux-de-données)
- [Optimisations](#optimisations)
- [Recherche Hybride](#recherche-hybride)
- [Sécurité et RGPD](#sécurité-et-rgpd)
- [Métriques](#métriques)
- [Dépannage](#dépannage)

---

## Vue d'Ensemble

Le système de Long-Term Memory de LIA permet à l'assistant de **se souvenir des informations utilisateur** à travers les sessions, construisant un **profil psychologique** pour personnaliser les interactions.

### Philosophie

> **Objectif** : Pas une base de données de faits, mais une **accumulation de munitions psychologiques** pour une expérience utilisateur unique.

| Principe | Implémentation |
|----------|----------------|
| **Patterns LangGraph natifs** | LangMem tools + AsyncPostgresStore avec semantic search |
| **Profil psychologique** | Schéma enrichi avec poids émotionnel et nuances d'usage |
| **Personnalité-aware** | Extraction adaptée à la personnalité de l'assistant |
| **Généricité** | Infrastructure réutilisable pour RAG documentaire futur |

### Caractéristiques

- **Extraction automatique** : Psychoanalyse en background du dernier message utilisateur
- **Injection contextuelle** : Mémoires pertinentes injectées via semantic search
- **Indicateur émotionnel** : Feedback visuel de l'état émotionnel (comfort/danger/neutral)
- **Édition manuelle** : Modification des champs émotionnels/importance via l'UI
- **RGPD compliant** : Export et suppression des données utilisateur
- **i18n complet** : Interface en 6 langues (fr, en, es, de, it, zh)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SEMANTIC STORE UNIFIÉ                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  AsyncPostgresStore + Semantic Index (pgvector)                         │
│  index = { dims: 1536, embed: text-embedding-3-small, fields: [...] }   │
│                                                                          │
│  NAMESPACES:                                                            │
│  ├── (user_id, "memories")           → Profil psychologique utilisateur │
│  ├── (user_id, "documents", source)  → Futur RAG documentaire           │
│  └── (user_id, "context", domain)    → Tool context existant            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    FLUX MÉMOIRE + PERSONNALITÉ                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  User Message                                                            │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────┐                                                            │
│  │ Router  │                                                            │
│  └────┬────┘                                                            │
│       │                                                                  │
│       ▼                                                                  │
│  ┌────────────────────────────────────────────────────┐                 │
│  │ Memory Injection (Middleware)                       │                 │
│  │ → Récupère mémoires pertinentes via semantic search│                 │
│  │ → Construit PROFIL PSYCHOLOGIQUE ACTIF             │                 │
│  │ → Injecte dans system prompt avec personnalité     │                 │
│  │ → Calcule emotional_state (comfort/danger/neutral) │                 │
│  └────────────────────────────────────────────────────┘                 │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────┐                                                    │
│  │ Planner/Agents  │ ← Contexte enrichi + profil psycho                 │
│  └────────┬────────┘                                                    │
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────┐                                                    │
│  │    Response     │ → Retourne emotional_state au frontend             │
│  └────────┬────────┘                                                    │
│           │                                                              │
│           ├──────────────────────────┐                                  │
│           ▼                          ▼                                  │
│  ┌──────────────┐    ┌─────────────────────────────────────┐           │
│  │     END      │    │ Background Psychoanalysis Extractor │ (async)   │
│  └──────────────┘    │ → Analyse DERNIER message user      │           │
│                      │ → Contexte minimal (4 messages)     │           │
│                      │ → Dedup par semantic search         │           │
│                      │ → Store.aput() nouveaux souvenirs   │           │
│                      │                                     │           │
│                      │ ⚠ Skipped pour sources automatisées │           │
│                      │   (scheduled actions, etc.)         │           │
│                      └─────────────────────────────────────┘           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Schéma de Mémoire

### MemorySchema (Pydantic)

```python
class MemorySchema(BaseModel):
    """Structure d'une mémoire avec profil psychologique."""

    # Contenu
    content: str  # Le fait en une phrase concise

    # Classification
    category: Literal[
        "preference",    # Préférences explicites
        "personal",      # Infos identité (travail, famille, lieu)
        "relationship",  # Relations mentionnées
        "event",         # Événements significatifs
        "pattern",       # Patterns comportementaux
        "sensitivity"    # Sujets sensibles/tabous
    ]

    # Dimension émotionnelle
    emotional_weight: int  # -10 (trauma) à +10 (joie), 0 = neutre

    # Contexte d'activation
    trigger_topic: str  # Mot-clé activateur (ex: "voiture", "père")

    # Nuance d'usage (pour personnalité)
    usage_nuance: str  # Comment utiliser l'info selon la personnalité

    # Importance
    importance: float  # 0.0-1.0 pour prioritisation
```

### Exemples de Mémoires

| Contenu | Category | Weight | Trigger | Nuance |
|---------|----------|--------|---------|--------|
| "Déteste les réunions longues" | preference | -5 | réunion | Sujet irritant, éviter de proposer des meetings longs |
| "Son père Jacky est décédé en 2020" | sensitivity | -9 | père, famille | Sujet très sensible, aborder avec grande délicatesse |
| "Passionné de voile" | preference | +7 | voile, bateau | Source de joie, peut être utilisé pour créer du lien |
| "Travaille chez Google depuis 5 ans" | personal | 0 | travail, Google | Information factuelle |

---

## Composants Backend

### 1. Store Sémantique

**Fichier** : `apps/api/src/domains/agents/context/store.py`

```python
# Configuration du store avec index sémantique
index_config = {
    "dims": settings.memory_embedding_dimensions,  # 1536 par défaut
    "embed": embeddings,  # text-embedding-3-small
    "fields": ["content", "text", "trigger_topic", "memory"],
}
```

### 2. Memory Injection Middleware

**Fichier** : `apps/api/src/domains/agents/middleware/memory_injection.py`

Fonctions principales :
- `build_psychological_profile()` : Construit le profil à injecter
- `compute_emotional_state()` : Calcule l'état émotionnel agrégé
- `get_memory_context_for_response()` : Interface pour response_node

### 3. Background Extractor

**Fichier** : `apps/api/src/domains/agents/services/memory_extractor.py`

```python
async def extract_memories_background(
    store: BaseStore,
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
) -> int:
    """
    Extraction psychoanalytique asynchrone post-conversation.

    OPTIMISÉ: Analyse uniquement le DERNIER message utilisateur
    avec contexte minimal (4 messages) pour éviter:
    - Retraitement des messages déjà analysés
    - Extraction de doublons
    - Coûts API inutiles
    """
```

### 4. Prompts Externalisés

**Fichiers** :
- `apps/api/src/domains/agents/prompts/v1/memory_extraction_prompt.txt`
- `apps/api/src/domains/agents/prompts/v1/memory_extraction_personality_addon.txt`

Le prompt principal inclut :
- Analyse du dernier message USER uniquement
- Instructions pour les 7 types d'informations à détecter
- Format JSON avec tous les champs du schéma
- Règles strictes (max 0-2 mémoires par message)

### 5. API Router

**Fichier** : `apps/api/src/domains/memories/router.py`

Endpoints :
- `GET /api/v1/memories` : Liste des mémoires
- `GET /api/v1/memories/categories` : Liste des catégories
- `PATCH /api/v1/memories/{id}` : Modifier une mémoire
- `DELETE /api/v1/memories/{id}` : Supprimer une mémoire
- `DELETE /api/v1/memories` : Supprimer toutes (RGPD)
- `GET /api/v1/memories/export` : Export JSON (RGPD)

### 6. Namespace Helper

**Fichier** : `apps/api/src/infrastructure/store/semantic_store.py`

```python
class MemoryNamespace:
    """Helper pour namespace LangGraph Store."""
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.collection = "memories"

    def to_tuple(self) -> tuple[str, str]:
        return (self.user_id, self.collection)
```

---

## Composants Frontend

### 1. MemorySettings Component

**Fichier** : `apps/web/src/components/settings/MemorySettings.tsx`

Fonctionnalités :
- Affichage groupé par catégorie
- **Tri par date décroissante** dans chaque catégorie
- **Horodatage internationalisé** avec `Intl.DateTimeFormat`
- Indicateurs émotionnels visuels (🔴🟠⚪🟢💚)
- Actions : modifier, supprimer, exporter
- Confirmation pour suppression totale

#### Dialog d'Édition

Champs éditables :
- **Contenu** : Textarea
- **Catégorie** : Select (6 options)
- **Nuance d'usage** : Input texte
- **Sujet déclencheur** : Input texte
- **Poids émotionnel** : Slider -10 à +10 avec indicateur emoji
- **Importance** : Slider 0% à 100%

### 2. Slider Component

**Fichier** : `apps/web/src/components/ui/slider.tsx`

Composant Radix UI pour les champs numériques.

### 3. EmotionalStateIndicator Component

**Fichier** : `apps/web/src/components/chat/EmotionalStateIndicator.tsx`

```tsx
type EmotionalState = 'comfort' | 'danger' | 'neutral';

// Indicateur visuel dans le chat
const EMOTIONAL_CONFIG = {
  comfort: { color: 'green', icon: '🟢', label: 'Terrain positif' },
  danger:  { color: 'red',   icon: '🔴', label: 'Zone sensible' },
  neutral: { color: 'gray',  icon: '⚪', label: 'Mode factuel' },
};
```

### 4. useMemories Hook

**Fichier** : `apps/web/src/hooks/useMemories.ts`

```typescript
interface Memory {
  id: string;
  content: string;
  category: MemoryCategory;
  emotional_weight: number;
  trigger_topic: string;
  usage_nuance: string;
  importance: number;
  created_at?: string;
  updated_at?: string;
}

function useMemories() {
  return {
    memories,           // Liste des mémoires
    total,              // Nombre total
    byCategory,         // Comptage par catégorie
    categories,         // Info catégories
    loading, deleting,  // États de chargement
    updating,           // État mise à jour
    deleteMemory,       // Supprimer une mémoire
    updateMemory,       // Modifier une mémoire
    deleteAllMemories,  // Supprimer toutes
  };
}
```

### 5. Internationalisation (i18n)

**Fichiers** : `apps/web/locales/{fr,en,es,de,it,zh}/translation.json`

Clés i18n pour les mémoires :

| Clé | FR | EN |
|-----|----|----|
| `memories.all_categories` | Toutes | All |
| `memories.field_trigger_topic` | Sujet déclencheur | Trigger topic |
| `memories.field_emotional_weight` | Poids émotionnel | Emotional weight |
| `memories.field_importance` | Importance | Importance |
| `memories.emotional_negative` | Négatif | Negative |
| `memories.emotional_positive` | Positif | Positive |
| `memories.importance_low` | Faible | Low |
| `memories.importance_high` | Haute | High |

---

## Configuration

### Variables d'Environnement (.env)

```bash
# Activer le système de mémoire
MEMORY_ENABLED=true
MEMORY_EXTRACTION_ENABLED=true
MEMORY_INJECTION_ENABLED=true

# Paramètres de recherche sémantique
MEMORY_MAX_RESULTS=10
MEMORY_MIN_SEARCH_SCORE=0.6

# LLM pour extraction
MEMORY_EXTRACTION_LLM_MODEL=gpt-4.1-mini
MEMORY_EXTRACTION_LLM_TEMPERATURE=0.3
MEMORY_EXTRACTION_MAX_TOKENS=1000
MEMORY_EXTRACTION_TOP_P=0.9
MEMORY_EXTRACTION_FREQUENCY_PENALTY=0.0
MEMORY_EXTRACTION_PRESENCE_PENALTY=0.0

# Embedding
MEMORY_EMBEDDING_MODEL=text-embedding-3-small
MEMORY_EMBEDDING_DIMENSIONS=1536
```

### Paramètres Settings (Pydantic)

| Paramètre | Type | Défaut | Description |
|-----------|------|--------|-------------|
| `memory_enabled` | bool | True | Active le système global |
| `memory_extraction_enabled` | bool | True | Active l'extraction background |
| `memory_injection_enabled` | bool | True | Active l'injection dans le prompt |
| `memory_max_results` | int | 10 | Max mémoires par recherche |
| `memory_min_search_score` | float | 0.6 | Score minimum pour inclusion |
| `memory_extraction_top_p` | float | 0.9 | Top-p pour LLM extraction |
| `memory_extraction_frequency_penalty` | float | 0.0 | Frequency penalty LLM |
| `memory_extraction_presence_penalty` | float | 0.0 | Presence penalty LLM |

---

## API Endpoints

### GET /api/v1/memories

Liste les mémoires de l'utilisateur authentifié.

**Query Parameters** :
- `category` (optional) : Filtrer par catégorie

**Response** :
```json
{
  "items": [
    {
      "id": "mem_abc123",
      "content": "Déteste les réunions longues",
      "category": "preference",
      "emotional_weight": -5,
      "trigger_topic": "réunion",
      "usage_nuance": "Éviter de proposer des meetings longs",
      "importance": 0.7,
      "created_at": "2025-01-15T10:30:00Z",
      "updated_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 15,
  "by_category": {
    "preference": 5,
    "personal": 3,
    "relationship": 4,
    "sensitivity": 3
  }
}
```

### PATCH /api/v1/memories/{memory_id}

Modifie une mémoire spécifique.

**Body** :
```json
{
  "content": "Nouveau contenu",
  "category": "preference",
  "emotional_weight": -3,
  "trigger_topic": "nouveau trigger",
  "usage_nuance": "Nouvelle nuance",
  "importance": 0.8
}
```

### DELETE /api/v1/memories/{memory_id}

Supprime une mémoire spécifique.

### DELETE /api/v1/memories

Supprime toutes les mémoires (RGPD - droit à l'oubli).

### GET /api/v1/memories/export

Exporte toutes les mémoires en JSON (RGPD - portabilité).

---

## Flux de Données

### 1. Extraction (Background)

```
Response généré
     │
     ▼
safe_fire_and_forget(extract_memories_background(...))
     │
     ▼ (async, non-bloquant)
┌────────────────────────────────────────┐
│ 1. Trouver DERNIER HumanMessage        │
│ 2. Récupérer contexte (4 messages max) │
│ 3. Semantic search pour dédup          │
│    → query = message_content[:500]     │
│    → limit = 10, score >= 0.5          │
│ 4. Charger prompt externalisé          │
│ 5. Appel LLM avec prompt formaté       │
│ 6. Parser JSON (avec récupération)     │
│ 7. Valider avec MemorySchema           │
│ 8. store.aput() + vérification         │
└────────────────────────────────────────┘
```

### 2. Injection (Synchrone)

```
User message reçu
     │
     ▼
build_psychological_profile(store, user_id, query)
     │
     ▼
┌────────────────────────────────────────┐
│ 1. store.asearch() avec query          │
│ 2. Filtrer par min_score               │
│ 3. Grouper par catégorie               │
│ 4. Formater avec emojis émotionnels    │
│ 5. Appliquer PSYCHOLOGICAL_PROFILE_TEMPLATE │
│ 6. compute_emotional_state()           │
└────────────────────────────────────────┘
     │
     ▼
Retourne (profile_text, emotional_state)
```

---

## Optimisations

### 1. Extraction Ciblée

**Avant** : Analyse des 20 derniers messages à chaque réponse
**Après** : Analyse uniquement du **dernier message utilisateur** avec contexte minimal (4 messages)

Bénéfices :
- Réduction des coûts API (~80%)
- Évite le retraitement des messages déjà analysés
- Évite les extractions de doublons
- Ignore les messages assistant (pas d'info utilisateur)

### 2. Déduplication Sémantique

**Avant** : Chargement de 50 mémoires existantes pour dédup par LLM
**Après** : Semantic search ciblée sur le contenu du message

```python
# Avant (inefficace)
existing = await store.asearch(namespace, query="", limit=50)

# Après (optimisé)
existing_results = await store.asearch(
    namespace.to_tuple(),
    query=message_content[:500],  # Truncate for efficiency
    limit=10,  # Only top 10 similar memories
)
# Filtrage par score >= 0.5
```

Bénéfices :
- Réduction tokens envoyés au LLM (~90%)
- Dédup basée sur similarité sémantique (plus précise)
- Scalabilité indépendante du nombre de mémoires

### 3. Prompts Externalisés

**Fichiers** :
- `prompts/v1/memory_extraction_prompt.txt`
- `prompts/v1/memory_extraction_personality_addon.txt`

Bénéfices :
- Modification sans redéploiement
- Versioning des prompts
- Cohérence avec les autres prompts système

---

## Recherche Hybride

> **Nouveau (2026-02-02)** : Combinaison BM25 + sémantique pour meilleur rappel.

### Principe

La recherche hybride combine deux signaux complémentaires :

| Signal | Force | Faiblesse |
|--------|-------|-----------|
| **Sémantique** (pgvector) | Comprend le sens, synonymes | Rate les mots-clés exacts |
| **BM25** (keyword) | Correspondances exactes | Ne comprend pas le sens |

### Formule

```
final_score = α × semantic_score + (1 - α) × bm25_normalized
```

- `α = 0.6` par défaut (60% sémantique, 40% BM25)
- Boost +10% si les deux signaux sont forts

### Usage

```python
# Utilisé automatiquement dans build_psychological_profile()
results = await search_hybrid(store, namespace, query, limit=10, min_score=0.5)
```

### Configuration

```bash
MEMORY_HYBRID_ENABLED=true
MEMORY_HYBRID_ALPHA=0.6
MEMORY_HYBRID_MIN_SCORE=0.5
MEMORY_BM25_CACHE_MAX_USERS=100
```

> Documentation complète : `docs/technical/HYBRID_SEARCH.md`

---

## Sécurité et RGPD

### Isolation des Données

- **Namespace** : Chaque utilisateur a son propre namespace `(user_id, "memories")`
- **Authentification** : Tous les endpoints vérifient `current_user`
- **Chiffrement** : PostgreSQL + SSL pour stockage

### Conformité RGPD

| Droit | Implémentation |
|-------|----------------|
| **Accès** | GET /api/v1/memories |
| **Portabilité** | GET /api/v1/memories/export |
| **Effacement** | DELETE /api/v1/memories |
| **Rectification** | PATCH /api/v1/memories/{id} |

### Directive Comportementale Dynamique (v1.9.3)

Le profil injecté inclut une **directive comportementale dynamique** basée sur l'état émotionnel détecté :

**État DANGER** (au moins une mémoire avec `emotional_weight ≤ -5`) :
- `⛔ DIRECTIVE DE SÉCURITÉ ÉMOTIONNELLE` avec 4 interdictions absolues :
  - Jamais de blague/ironie/sarcasme sur les sujets TRAUMA/NÉGATIF
  - Jamais de référence désinvolte ou banalisante
  - Jamais de minimisation
  - Jamais de projection/comparaison
- Les `usage_nuance` des mémoires sensibles sont formatées en `⚠ OBLIGATION :` (impératif, pas informatif)

**État NEUTRAL/COMFORT** (pas de mémoire sensible activée) :
```
1. Tâche technique → Ignore les émotions, garde le style
2. Tâche conversationnelle → Utilise les leviers pour personnaliser
3. Ne force jamais l'utilisation d'une mémoire non pertinente
```

---

## Métriques

### Prometheus (à implémenter)

| Métrique | Type | Description |
|----------|------|-------------|
| `memory_extraction_duration_seconds` | Histogram | Durée extraction |
| `memory_extraction_count` | Counter | Mémoires extraites |
| `memory_injection_count` | Counter | Mémoires injectées |
| `memory_search_latency_seconds` | Histogram | Latence recherche sémantique |
| `emotional_state_distribution` | Counter | Distribution comfort/danger/neutral |

### Logs Structurés

```python
logger.info(
    "psychological_profile_built",
    user_id=user_id,
    memory_count=len(results),
    categories=list(by_category.keys()),
    emotional_state=emotional_state.value,
)

logger.info(
    "memory_extraction_completed",
    user_id=user_id,
    session_id=session_id,
    extracted_count=len(new_memories),
    stored_count=stored_count,
)

logger.debug(
    "memory_dedup_semantic_search",
    user_id=user_id,
    query_length=len(message_content),
    similar_memories_found=len(existing_texts),
)
```

---

## Dépannage

### Problèmes Courants

#### Aucune mémoire extraite

1. Vérifier `MEMORY_EXTRACTION_ENABLED=true`
2. Vérifier que la conversation a ≥ 1 message utilisateur
3. Consulter les logs pour `memory_extraction_*`
4. Vérifier les logs `extraction_json_parse_failed` pour problèmes de parsing

#### Mémoires non injectées

1. Vérifier `MEMORY_INJECTION_ENABLED=true`
2. Vérifier `MEMORY_MIN_SEARCH_SCORE` (trop haut = moins de résultats)
3. Vérifier que le namespace existe
4. Utiliser le **Debug Panel > Memory Injection** pour visualiser les mémoires injectées avec leurs scores de similarité, catégories, et poids émotionnels. Affiche aussi les settings actifs (`min_score`, `max_results`, `hybrid_enabled`) pour faciliter le tuning.
5. Utiliser le **Debug Panel > Memory Detection** pour visualiser les mémoires extraites et stockées en mémoire long-terme depuis le message courant. Affiche les mémoires nouvellement créées (catégorie, poids émotionnel, importance, statut de stockage), les mémoires similaires trouvées lors de la déduplication, et les métadonnées LLM (modèle, tokens).

#### Erreurs de semantic search

1. Vérifier `OPENAI_API_KEY` est configuré
2. Vérifier que pgvector est installé dans PostgreSQL
3. Consulter les logs pour `semantic_search_config_failed`

#### Doublons de mémoires

1. Vérifier que l'extraction n'est pas déclenchée plusieurs fois
2. Consulter `memory_dedup_semantic_search` dans les logs
3. Augmenter le seuil de similarité (score >= 0.5 par défaut)

### Commandes Utiles

```bash
# Vérifier les mémoires d'un utilisateur (PostgreSQL)
SELECT * FROM store WHERE namespace[1] = 'user-id' AND namespace[2] = 'memories';

# Compter les mémoires par catégorie
SELECT
  value->>'category' as category,
  count(*)
FROM store
WHERE namespace[2] = 'memories'
GROUP BY category;

# Voir les mémoires récentes
SELECT key, value->>'content', created_at
FROM store
WHERE namespace[2] = 'memories'
ORDER BY created_at DESC
LIMIT 10;
```

---

## Références

- [LangMem Official](https://langchain-ai.github.io/langmem/)
- [LangGraph Semantic Search](https://blog.langchain.com/semantic-search-for-langgraph-memory/)
- [Memory Tools API](https://langchain-ai.github.io/langmem/reference/tools/)
- [ADR-013: LangMem Long-Term Memory](../architecture/ADR-013-LangMem-Long-Term-Memory.md)
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
