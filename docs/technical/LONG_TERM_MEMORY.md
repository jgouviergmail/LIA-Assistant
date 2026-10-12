# Long-Term Memory - Architecture PostgreSQL + pgvector

> Système de mémoire long terme pour la construction de profils psychologiques utilisateurs
>
> **Version**: 2.0
> **Date**: 2026-03-30
> **Updated**: 2026-10-12 — PostgreSQL ownership, centralized embeddings and consent-revision fencing

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
| **PostgreSQL + pgvector** | Dedicated Memory table with HNSW cosine distance index |
| **Profil psychologique** | Schéma enrichi avec poids émotionnel et nuances d'usage |
| **Create/Update/Delete** | LLM can create, update, or delete memories (micro-consolidation) |
| **Centralized embeddings** | Single embedding per turn, shared across injection + extraction |
| **Personnalité-aware** | Extraction adaptée à la personnalité de l'assistant |

### Caractéristiques

- **Extraction automatique** : Psychoanalyse en background avec create/update/delete (micro-consolidation)
- **Injection contextuelle** : Mémoires pertinentes injectées via pgvector semantic search (pre-computed embedding)
- **Triviality filter** : Messages triviaux ("ok", "merci") skip extraction (0 LLM calls)
- **Pinned protection** : Memories épinglées par l'utilisateur protégées de toute modification automatique
- **Indicateur émotionnel** : Feedback visuel de l'état émotionnel (comfort/danger/neutral)
- **Édition manuelle** : Modification des champs émotionnels/importance via l'UI
- **Contrôles de données personnelles** : export, édition, suppression et consentement ; la conformité dépend aussi de l’exploitation de l’instance
- **i18n complet** : Interface en 6 langues (fr, en, es, de, it, zh)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    MEMORY STORAGE (PostgreSQL + pgvector)                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Memory model (SQLAlchemy) + HNSW index (pgvector cosine distance)      │
│  Embeddings Gemini configurés + index HNSW du modèle SQL                  │
│                                                                          │
│  OWNERSHIP SQL:                                                          │
│  ├── memories.user_id               → propriétaire du souvenir            │
│  ├── RAG Spaces                     → domaine documentaire distinct       │
│  └── Contexte du tour               → observations distinctes             │
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
│                      │ → MemoryService : SQL + révision    │           │
│                      │                                     │           │
│                      │ ⚠ Skipped pour sources automatisées │           │
│                      │   (scheduled actions, etc.)         │           │
│                      └─────────────────────────────────────┘           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

> **Sources automatisées exclues.** Le skip illustré ci-dessus est appliqué en amont, dans `response_node`, via le drapeau `is_automated_source` (propagé par `configurable`, positionné à `True` par l'exécuteur d'actions planifiées et `False` par défaut pour toute entrée directe). Le même drapeau garde aussi l'extraction des centres d'intérêt, du journal et de la psyché.

---

## Schéma de Mémoire

### ExtractedMemory (Pydantic)

C'est le schéma que l'extraction valide réellement, dans
`apps/api/src/domains/memories/schemas.py` :

```python
class ExtractedMemory(BaseModel):
    """Une opération de mémoire proposée par le LLM d'extraction."""

    action: Literal["create", "update", "delete"]
    memory_id: str | None          # requis pour update/delete

    # Contenu
    content: str | None            # Le fait en une phrase concise

    # Classification — vocabulaire de MemoryCategory (voir ci-dessous)
    category: MemoryCategoryType | None

    # Dimension émotionnelle
    emotional_weight: int | None   # -10 (trauma) à +10 (joie), 0 = neutre

    # Contexte d'activation
    trigger_topic: str | None      # Mot-clé activateur (ex: "voiture", "père")

    # Nuance d'usage (pour personnalité)
    usage_nuance: str | None       # Comment utiliser l'info selon la personnalité

    # Importance
    importance: float | None       # 0.0-1.0 pour prioritisation
```

### Le vocabulaire des catégories

L'autorité est l'énumération `MemoryCategory`
(`apps/api/src/domains/memories/models.py`), celle que stocke la colonne :
`preference`, `personal`, `relationship`, `event`, `pattern`, `sensitivity` et
`procedural` (les « règles et directives », ADR-236).

Trois surfaces la restatent parce qu'aucune ne peut la dériver — les deux
`Literal` (MyPy exige des valeurs littérales) et le catalogue publié par
`GET /memories/categories`. Les trois sont donc vérifiées au démarrage par
`assert_category_vocabulary_completeness` (doctrine ADR-085) : une catégorie
présente dans l'énumération et absente d'une restatement disparaît du produit
en silence. C'est exactement ce qui est arrivé à `procedural` jusqu'au
2026-08-28 — le parseur rejetait la catégorie que le prompt d'extraction
demandait, et l'échec était journalisé en `debug`.

### Une directive se corrige, elle ne se supprime pas (2026-09-10)

Toutes les catégories portent un FAIT que LIA a inféré et peut ré-inférer.
`procedural` non : elle porte les consignes que la personne a **dictées** sur
la façon dont LIA doit travailler pour elle (ADR-236) — « réponds-moi toujours
en français », « ne m'appelle jamais après 20 h ». Un balayage qui en fait
disparaître une change le comportement de l'assistante en silence, et personne
ne peut désigner le moment où c'est arrivé.

New `procedural` memories are automatically **pinned at creation**.
`MemoryService.create_memory` applies
this default to extracted memories, manual creation and supersession into this
category. Pinning also blocks automated changes; the person can still edit or
unpin a rule. Existing and explicitly unpinned directives keep their category
protection: they never leave the active set without a successor.

| Chemin | Une directive |
|---|---|
| Balayage de rétention | jamais purgée, quels que soient son score et son âge |
| Consolidation (détruit le perdant d'une paire) | jamais appariée |
| `delete` de l'extracteur | ignoré, et dit |
| `invalidate_memory` (retrait sans successeur) | refusé |
| `supersede_with_update` (retrait AVEC successeur) | allowed only when unpinned |
| `update_memory` (édition automatisée sur place) | refused while pinned; allowed after the person unpins it |
| La personne qui la supprime elle-même | autorisé — c'est son acte |

Le prédicat unique est `memories/protection.py::is_protected_from_deletion`,
lu par la rétention, le service et le dépôt ; le prompt d'extraction interdit
le `delete` sur cette catégorie et l'écran le dit à la personne.

### Exemples de Mémoires

| Contenu | Category | Weight | Trigger | Nuance |
|---------|----------|--------|---------|--------|
| "Déteste les réunions longues" | preference | -5 | réunion | Sujet irritant, éviter de proposer des meetings longs |
| "Son père Robert est décédé en 2020" | sensitivity | -9 | père, famille | Sujet très sensible, aborder avec grande délicatesse |
| "Passionné de voile" | preference | +7 | voile, bateau | Source de joie, peut être utilisé pour créer du lien |
| "Travaille chez Google depuis 5 ans" | personal | 0 | travail, Google | Information factuelle |

---

## Composants Backend

### 1. Stockage sémantique

Les souvenirs sont des lignes du modèle
`apps/api/src/domains/memories/models.py::Memory`, détenues par `user_id`.
`MemoryService` valide les écritures et `MemoryRepository` porte les requêtes SQL
et la recherche multi-vecteurs pgvector. Aucun namespace LangGraph Store n'est
utilisé pour ces souvenirs. La porte de recherche active est décrite ci-dessous;
les paramètres d'embedding sont configurés par l'infrastructure LLM.

### 2. Memory Injection Middleware

**Fichier** : `apps/api/src/domains/agents/middleware/memory_injection.py`

Fonctions principales :
- `build_psychological_profile()` : Construit le profil à injecter
- `compute_emotional_state()` : Calcule l'état émotionnel agrégé
- `get_memory_context_for_response()` : Interface pour response_node

### 2 bis. Recherche active (ADR-313)

**Fichiers** : `apps/api/src/domains/memories/search.py` (la porte unique),
`apps/api/src/domains/agents/tools/memory_search_tools.py` (l'outil).

Le profil injecté est classé sur le MESSAGE de la personne. Pour un sujet que le
tour découvre en chemin (l'expéditeur d'un e-mail lu, un lieu, une consigne), le
planificateur et la boucle ReAct disposent du domaine routable `memory` et de
`search_memories_tool` (`memory_agent`, lecture seule, sans OAuth ni HITL) :

- `embed_lookup` vectorise une question comme une CLÉ (`is_conversational=False`) ;
  `search_memories` sert les souvenirs vivants au-dessus de `MEMORY_MIN_SEARCH_SCORE`,
  catégories en option ; le vecteur est calculé avant l'ouverture de session ;
- tous les appelants passent par cette porte : faits mémoire du planificateur, de
  l'initiative et de la résolution de références, rappel 360° d'une personne,
  recherches du téléphone (`build_profile_for_lookup` — qui cherchait jusque-là les
  dix souvenirs les plus récents quelle que soit la question) ;
- les bornes publiées sont celles que l'outil applique (catégories =
  `MemoryCategoryType`, plafond = `MEMORY_MAX_RESULTS`) ; la préférence
  `memory_enabled` refuse la recherche comme l'injection ; un souvenir sensible revient
  avec sa nuance d'usage comme obligation ; un échec n'est jamais lu comme « rien en
  mémoire ».

### 3. Background Extractor

**Fichier** : `apps/api/src/domains/agents/services/memory_extractor.py`

```python
async def extract_memories_background(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    personality_instruction: str | None = None,
    conversation_id: str | None = None,
    parent_run_id: str | None = None,
    query_embedding: list[float] | None = None,
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

### Consentement et règlement des écritures

`users.extraction_revision` borne les tâches d'apprentissage déjà parties.
`users/extraction_consent.py` lit le compte actif, le consentement mémoire et la
révision attendue au début de l'extraction, avant une nouvelle phase payante et
avant le règlement SQL. Les modifications explicites de consentement ou de
données personnelles avancent cette révision sous verrou du compte.

Les embeddings sont préparés avant le verrou d'écriture. La transaction finale
relit le consentement et la révision avec `lock=True`, puis applique les actions
validées par `MemoryService`, dont les protections d'épinglage. Un changement
survenu entre-temps abandonne l'ancien travail ; il ne suffit pas que le modèle
ait déjà proposé une action. Une attente fournisseur ne conserve pas ce verrou.
Les sources automatisées restent exclues du déclenchement post-réponse.

### 4. Prompts Externalisés

**Fichiers** :
- `apps/api/src/domains/agents/prompts/v1/memory_extraction_prompt.txt`
- `apps/api/src/domains/agents/prompts/v1/memory_extraction_personality_addon.txt`

Le prompt principal inclut 7 règles obligatoires :
1. **First person** — écrire comme l'utilisateur parle ("I like X")
2. **Exact words only** — ne jamais inférer, extraire uniquement les faits explicites
3. **Atomic** — un fait par mémoire
4. **Name relationships** — résoudre les relations connues en noms complets
5. **Absolute temporal references** (v1.16.2) — toutes les dates relatives ("demain", "samedi prochain", "la semaine prochaine") sont systématiquement converties en dates absolues via la date/heure courante. Liste noire explicite des termes relatifs interdits
6. **Qualify** — poids émotionnel (-10 à +10) et importance (0.0-1.0)
7. **Categorize** — preference | personal | relationship | event | pattern | sensitivity

Format JSON avec actions `create`, `update` (UUID existant), `delete` (UUID existant).

#### Doctrine d'admission (ADR-166)

Le prompt liste ce qui ne doit **jamais** devenir un souvenir. Trois classes ont
ete ajoutees le 2026-07-27, chacune sur un cas observe en production :

| Classe exclue | Cas reel |
|---|---|
| **Le sujet de l'echange** | une question sur les trous noirs ne dit rien de l'utilisateur |
| **Les faits propres a un tiers** | « X est un homme » stocke en `relationship`, sans lien avec l'utilisateur |
| **Un enonce vrai de presque tout le monde** | « j'aime bien quand il fait beau » ne personnalise rien |

La clause fourre-tout du 4e critere (« *…or useful informations* ») est fermee :
elle readmettait tout ce que les trois autres excluaient. Un **creneau
recurrent** (le cours de tennis du lundi) est desormais explicitement un
`pattern` a retenir, par opposition au rendez-vous ponctuel qui reste de la
logistique transitoire.

Ces regles sont verrouillees par
`tests/unit/domains/agents/prompts/test_extraction_prompt_doctrine.py` et
mesurables via `apps/api/scripts/measure_extraction_selectivity.py --battery memory`.

#### Plafond de suppressions (ADR-166)

Les actions `delete` ne portent **aucun champ de confiance** et ne sont validees
que sur la validite de l'UUID et la propriete. Au-dela de
`EXTRACTION_MAX_DELETES_PER_RUN` (2 par defaut), **toutes** les suppressions du
lot sont ecartees et comptees sous
`extraction_action_rejected_total{kind="memory", reason="delete_cap"}` ; les
creations et mises a jour du meme lot sont conservees. Le garde est partage avec
l'extracteur de centres d'interet
(`src/domains/agents/utils/extraction_guards.py`) : c'est la que 19 suppressions
en un seul tour ont ete observees.

### 5. API Router

**Fichier** : `apps/api/src/domains/memories/router.py`

Endpoints :
- `GET /api/v1/memories` : Liste des mémoires
- `GET /api/v1/memories/categories` : Liste des catégories
- `PATCH /api/v1/memories/{id}` : Modifier une mémoire
- `DELETE /api/v1/memories/{id}` : Supprimer une mémoire
- `DELETE /api/v1/memories` : Supprimer toutes (RGPD)
- `GET /api/v1/memories/export` : Export JSON (RGPD)

### 6. Commandes applicatives

Les lectures et opérations de gestion conversationnelles passent par les
[commandes applicatives](APPLICATION_COMMANDS.md) et les services du domaine.
Elles conservent le propriétaire, les confirmations, la version courante et les
protections des souvenirs épinglés. Les opérations explicites de gestion
invalident les tâches automatiques concernées via la révision d'extraction.

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
- **Catégorie** : Select du vocabulaire de catégories déclaré
- **Nuance d'usage** : Input texte
- **Sujet déclencheur** : Input texte
- **Poids émotionnel** : Slider -10 à +10 avec indicateur emoji
- **Importance** : Slider 0% à 100%

### 2. Slider Component

**Fichier** : `apps/web/src/components/ui/slider.tsx`

Composant Radix UI pour les champs numériques.

### 3. useMemories Hook

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

### 4. Internationalisation (i18n)

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

### Réglages et consentement

`core/config/agents.py` déclare les paramètres de recherche et d'extraction,
dont `memory_extraction_enabled`, `memory_max_results`,
`memory_min_search_score`, `memory_dedup_search_limit` et
`memory_dedup_min_score`. Les valeurs par défaut appartiennent à la
configuration et à ses constantes ; elles ne sont pas répétées ici.

Le consentement personnel (`users.memory_enabled`) est indépendant du réglage
global d'extraction. Les chemins d'injection et d'extraction contrôlent ce
consentement avec l'état du compte. `MEMORY_ENABLED` et
`MEMORY_INJECTION_ENABLED` ne sont pas des interrupteurs de configuration
déclarés.

### Modèle d'extraction et embeddings

Le slot `memory_extraction` passe par `get_llm()` et
`get_llm_config_for_agent()` : fournisseur, modèle, raisonnement, budget et délai
proviennent de la [configuration LLM centrale](LLM_CONFIG_ADMIN.md). Les anciens
exemples `.env` ne décrivent pas l'autorité du modèle exécuté sur une instance.

`infrastructure/llm/memory_embeddings.py::get_memory_embeddings()` construit les
embeddings Gemini à partir de `memory_embedding_model` et
`memory_embedding_dimensions`. Le rôle `RETRIEVAL_QUERY` est utilisé pour la
recherche, `RETRIEVAL_DOCUMENT` pour les passages stockés. La dimension doit
rester compatible avec les colonnes vectorielles et les données de l'instance ;
changer un nom de modèle n'est pas une migration de ses vecteurs.

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

```text
Réponse à une entrée humaine
    → safe_fire_and_forget(extract_memories_background(...))
    → compte actif + consentement + extraction_revision
    → dernier message humain et contexte admissible
    → recherche SQL pour déduplication et appel du slot memory_extraction
    → parsing, actions validées et protections des souvenirs épinglés
    → embeddings préparés hors verrou d'écriture
    → consentement/révision relus sous verrou du compte
    → MemoryService : écritures SQL + provenance
```

### 2. Injection (Synchrone)

`build_psychological_profile(user_id, query, query_embedding=...)` lit les
souvenirs vivants autorisés, les classe et compose le profil psychologique avec
leurs nuances d'usage. `compute_emotional_state()` calcule l'état agrégé ; le
texte et cet état suivent ensuite le chemin de réponse. Pour une recherche
active distincte d'une ligne de conversation, `search_memories()` calcule le
vecteur avant d'ouvrir sa session SQL et distingue recherche vide et indisponible.

---

## Optimisations

### 1. Extraction Ciblée

**Avant** : Analyse des 20 derniers messages à chaque réponse
**Après** : Analyse uniquement du **dernier message utilisateur** avec contexte minimal (4 messages)

Bénéfices :
- Moins de contexte et d’appels pour les messages écartés ; le gain dépend du tour
- Évite le retraitement des messages déjà analysés
- Évite les extractions de doublons
- Ignore les messages assistant (pas d'info utilisateur)

### 2. Déduplication Sémantique

L'extracteur réutilise le vecteur du message lorsqu'il est disponible et lit les
souvenirs pertinents via `MemoryRepository.search_by_relevance()`. Les limites
et scores viennent de la configuration. Le modèle reçoit les passages
sélectionnés avec leurs identités ; il ne charge pas tout le compte. La validation
métier conserve l'autorité sur les créations, mises à jour et suppressions.
Ce filtrage réduit le contexte à traiter sans garantir un gain fixe sur chaque tour.

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

Les mémoires utilisent la recherche sémantique multi-vecteurs du dépôt
PostgreSQL ; l'ancien `search_hybrid(store, namespace, ...)` n'est pas une API
actuelle de ce domaine. Le BM25 actif des espaces documentaires appartient aux
RAG Spaces et à leurs propres contrats. Voir [HYBRID_SEARCH.md](HYBRID_SEARCH.md)
pour ce mécanisme distinct et [la recherche active](#2-bis-recherche-active-adr-313)
pour la porte mémoire.

---

## Sécurité et RGPD

### Isolation des Données

- **Propriétaire SQL** : lectures et écritures sont filtrées par `Memory.user_id`, avec contrôle du compte actif et des permissions
- **Authentification** : Tous les endpoints vérifient `current_user`
- **Transport et stockage** : TLS dépend de la configuration de déploiement. Le contenu des souvenirs est du contenu applicatif dans PostgreSQL ; ce n’est pas un coffre à chiffrement de bout en bout. Les clés de connecteurs suivent leur chiffrement propre.

### Fonctions relatives aux données personnelles

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

### Prometheus

Les définitions actives appartiennent à
`apps/api/src/infrastructure/observability/`. Les garde-fous partagés peuvent
compter des refus, par exemple `extraction_action_rejected_total` ; l'extracteur
ne publie pas pour autant chaque nombre ou durée sous un nom propre à la mémoire.

Les anciennes propositions `memory_extraction_duration_seconds`,
`memory_extraction_count`, `memory_injection_count`,
`memory_search_latency_seconds` et `emotional_state_distribution` ne sont pas
des séries exportées. Les métriques de l'ancien chemin hybride ont également
disparu avec ce chemin. Vérifier la déclaration et son lecteur avant de bâtir
un panneau Grafana ; un nom simplement présent dans une documentation peut
donner un panneau vide sans erreur.

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

1. Vérifier le consentement `memory_enabled` du compte actif
2. Vérifier `MEMORY_MIN_SEARCH_SCORE` (trop haut = moins de résultats)
3. Vérifier les lignes `memories` du propriétaire et son consentement courant
4. Utiliser le **Debug Panel > Memory Injection** pour visualiser les mémoires injectées avec leurs scores de similarité, catégories, et poids émotionnels. Affiche aussi les settings actifs (`min_score`, `max_results`) pour faciliter le tuning.
5. Utiliser le **Debug Panel > Memory Detection** pour visualiser les mémoires extraites et stockées en mémoire long-terme depuis le message courant. Affiche les mémoires nouvellement créées (catégorie, poids émotionnel, importance, statut de stockage), les mémoires similaires trouvées lors de la déduplication, et les métadonnées LLM (modèle, tokens).

#### Erreurs de semantic search

1. Vérifier la clé Gemini et les paramètres du service d'embeddings de l'instance
2. Vérifier que pgvector est installé dans PostgreSQL
3. Consulter les logs pour `semantic_search_config_failed`

#### Doublons de mémoires

1. Vérifier que l'extraction n'est pas déclenchée plusieurs fois
2. Consulter `memory_dedup_semantic_search` dans les logs
3. Examiner `memory_dedup_min_score` et `memory_dedup_search_limit` avant de modifier la sélection

### Commandes Utiles

```sql
-- Exemples de diagnostic sur un compte contrôlé ; ne pas publier le contenu.
SELECT id, category, importance, created_at FROM memories WHERE user_id = :user_id;
SELECT category, count(*) FROM memories WHERE user_id = :user_id GROUP BY category;
```

Ces paramètres sont à lier dans le client SQL utilisé. Les références LangMem et
LangGraph ci-dessous décrivent l'origine du design ; la table `memories` et les
services du domaine portent l'implémentation courante.

---

## Références

- [LangMem Official](https://langchain-ai.github.io/langmem/)
- [LangGraph Semantic Search](https://blog.langchain.com/semantic-search-for-langgraph-memory/)
- [Memory Tools API](https://langchain-ai.github.io/langmem/reference/tools/)
- [ADR-013: LangMem Long-Term Memory](../architecture/ADR-013-LangMem-Long-Term-Memory.md)
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
