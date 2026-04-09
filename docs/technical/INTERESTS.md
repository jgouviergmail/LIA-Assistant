# Systeme d'Apprentissage des Centres d'Interet

> Systeme d'extraction et d'apprentissage automatique des centres d'interet utilisateur via analyse LLM des conversations.

**Version** : 1.6
**Date** : 2026-03-02
**Statut** : ✅ Operationnel (Phases 0-8 completes)

---

## Table des Matieres

1. [Vue d'Ensemble](#1-vue-densemble)
2. [Architecture](#2-architecture)
   - [2.5 Regles de Gestion des Notifications Proactives](#25-regles-de-gestion-des-notifications-proactives)
3. [Modeles de Donnees](#3-modeles-de-donnees)
4. [Services Backend](#4-services-backend)
5. [Prompts LLM](#5-prompts-llm)
6. [API Endpoints](#6-api-endpoints)
7. [Frontend](#7-frontend)
8. [Configuration](#8-configuration)
9. [Observabilite](#9-observabilite)
10. [Tests](#10-tests)

---

## 1. Vue d'Ensemble

### 1.1 Objectif

Le systeme d'apprentissage des centres d'interet permet a LIA de :

1. **Apprendre** les centres d'interet de l'utilisateur via analyse LLM des conversations
2. **Evoluer** les poids des interets (consolidation, decroissance, feedback)
3. **Notifier** proactivement avec du contenu pertinent (Wikipedia, Perplexity, LLM) - *Phase future*
4. **Permettre** a l'utilisateur de configurer et gerer ses interets

### 1.2 Principes Cles

| Principe | Description |
|----------|-------------|
| **Fire-and-forget** | Extraction en arriere-plan sans bloquer la conversation |
| **LLM-based** | Analyse semantique via LLM (gpt-4o-mini par defaut) |
| **Deduplication** | Detection des interets similaires pour consolidation |
| **Bayesian weighting** | Evolution des poids via algorithme Bayesien |
| **User control** | Interface de gestion des interets (feedback, blocage) |

### 1.3 Categories d'Interets

| Categorie | Exemples |
|-----------|----------|
| `technology` | IA, programmation, gadgets, logiciels, internet |
| `science` | physique, biologie, astronomie, recherche |
| `culture` | art, musique, cinema, litterature, histoire |
| `sports` | football, tennis, course, fitness |
| `finance` | investissement, cryptos, economie |
| `travel` | destinations, cultures, aventures |
| `nature` | environnement, animaux, jardinage |
| `health` | bien-etre, nutrition, meditation |
| `entertainment` | jeux, series, podcasts |
| `other` | tout ce qui ne rentre pas ailleurs |

---

## 2. Architecture

### 2.1 Vue d'Ensemble

```
[response_node] ─────────────────────────────────────────────────────┐
       │                                                              │
       ▼                                                              ▼
safe_fire_and_forget(                                    safe_fire_and_forget(
  extract_memories_background()  <-- existant              extract_interests_background()  <-- NOUVEAU
)                                                        )
                                                                      │
                                                                      ▼
                                                         InterestExtractionService
                                                         - LLM analysis (0-2 interests)
                                                         - Dedup via OpenAI embeddings (0.89 threshold)
                                                         - Consolidate or create with embedding
                                                         - Token tracking via TrackingContext
```

### 2.2 Flow d'Extraction

```
1. User envoie message (interaction directe uniquement)
       │
       ▼
2. response_node traite et repond
       │
       ├── Guard: skip si source automatisee (scheduled actions)
       ▼
3. safe_fire_and_forget(extract_interests_background(...))
       │
       ▼
4. _analyze_interests_core()
       │
       ├── Check feature enabled
       ├── Find last HumanMessage
       ├── Check Redis cache
       ├── Load existing interests (top 20)
       ├── Format conversation
       ├── Build prompt from template
       ├── Call LLM (gpt-4o-mini)
       ├── Parse JSON result
       └── Cache result in Redis
       │
       ▼
5. For each extracted interest:
       │
       ├── Generate embedding for topic (OpenAI text-embedding-3-small, 1536 dims)
       │
       ├── Check similarity with existing (embedding-based)
       │   ├── cosine_similarity >= 0.89? → consolidate_on_mention()
       │   ├── String fallback if no embedding → consolidate_on_mention()
       │   └── New? → repo.create() with embedding
       │
       └── Persist tokens via TrackingContext
```

### 2.3 Structure des Fichiers

```
apps/api/src/domains/interests/
├── __init__.py
├── models.py                    # UserInterest, InterestNotification
├── schemas.py                   # Pydantic schemas API + ExtractedInterest
├── repository.py                # Queries optimisees, Bayesian weight
├── router.py                    # API endpoints
└── services/
    ├── __init__.py
    ├── extraction_service.py    # Fire-and-forget extraction + debug
    └── content_sources/         # Sources de contenu pour notifications proactives
        ├── __init__.py
        ├── base.py                  # ContentSource protocol, ContentResult
        ├── brave_source.py          # Brave Search API (source prioritaire)
        ├── perplexity_source.py     # Perplexity API (fallback)
        ├── llm_reflection_source.py # LLM reflection (fallback final)
        └── wikipedia_source.py      # Wikipedia (deprecie, remplace par Brave)

apps/api/src/domains/agents/prompts/v1/
├── interest_extraction_prompt.txt
├── interest_content_prompt.txt      # Phase future
└── interest_llm_reflection_prompt.txt  # Phase future

apps/web/src/components/settings/
├── InterestsSettings.tsx        # Section settings principale
└── InterestsDialog.tsx          # Dialog CRUD interets

apps/api/src/infrastructure/proactive/
├── __init__.py
├── base.py                      # ProactiveTask protocol, ProactiveTaskResult
├── runner.py                    # ProactiveTaskRunner orchestrator
├── eligibility.py               # EligibilityChecker (timezone, quota, cooldown)
├── notification.py              # NotificationDispatcher (FCM + SSE + archive)
└── tracking.py                  # Token tracking utilities
```

### 2.4 Infrastructure Proactive

L'infrastructure proactive gere l'envoi de notifications basees sur les interets.

#### Architecture

```
APScheduler (interval: 15min, max_instances=1)
       │
       ▼
interest_notification_job()
       │
       ▼
ProactiveTaskRunner.execute()
       │
       ├── _get_eligible_users(db)         # Query sans FOR UPDATE
       │
       └── for user in users:
               │
               ├── EligibilityChecker.check()   # timezone, quota, cooldown
               │
               ├── InterestProactiveTask
               │       ├── check_eligibility()  # interests_enabled
               │       ├── select_target()      # top weighted interest
               │       └── generate_content()   # Wikipedia/Perplexity/LLM
               │
               ├── NotificationDispatcher       # FCM + SSE + archive
               │
               ├── track_proactive_tokens()     # Transaction autonome
               │
               └── on_notification_sent()       # Transaction autonome
```

---

## 2.5 Regles de Gestion des Notifications Proactives

> **Section exhaustive** : Toutes les regles metier concernant l'emission des messages sur les centres d'interet.

### 2.5.1 Conditions d'eligibilite (EligibilityChecker)

Un utilisateur est eligible pour recevoir une notification **si et seulement si** TOUTES les conditions suivantes sont vraies :

| Condition | Verification | Parametre utilisateur | Defaut |
|-----------|--------------|----------------------|--------|
| **Feature activee** | `user.interests_enabled == True` | `interests_enabled` | `true` |
| **Dans la fenetre horaire** | `start_hour <= heure_locale < end_hour` | `interests_notify_start_hour`, `interests_notify_end_hour` | 9h - 22h |
| **Quota journalier non atteint** | `notifications_today < max_per_day` | `interests_notify_max_per_day` | 3 |
| **Cooldown global respecte** | `derniere_notif > 2h` | `INTEREST_GLOBAL_COOLDOWN_HOURS` (env) | 2h |
| **Utilisateur inactif** | `derniere_activite_chat > 5min` | `INTEREST_ACTIVITY_COOLDOWN_MINUTES` (env) | 5min |
| **Probabilite favorable** | `random() < probabilite_calculee` | Voir ci-dessous | Variable |

#### Regle Probabiliste de Declenchement (v1.6 — Time-Aware)

Meme si un utilisateur est eligible, le systeme **ne declenche pas systematiquement** une notification. Un algorithme **time-aware** determine si on envoie maintenant ou on attend le prochain check.

**3 mecanismes complementaires** :

1. **Zone de garantie** (derniers 20% de la fenetre) : Si `min_per_day` n'est pas atteint, force l'envoi
2. **Probabilite adaptative** : Basee sur le temps restant dans la fenetre (pas un taux fixe)
3. **Boost deficit** : Si en retard sur la cible temporelle, boost jusqu'a 2x

**Algorithme** :

```python
# Cible moyenne par jour
target_per_day = (min_per_day + max_per_day) / 2  # Ex: (2+5)/2 = 3.5

# Position temporelle dans la fenetre (0.0 = debut, 1.0 = fin)
time_fraction = elapsed_hours / window_hours
remaining_fraction = 1.0 - time_fraction

# 1. ZONE DE GARANTIE : Derniers 20% de fenetre, en-dessous du minimum → envoi force
if remaining_fraction <= 0.20 and today_count < min_per_day:
    return True  # Garantit que min_per_day est toujours atteint

# 2. PROBABILITE ADAPTATIVE : Basee sur le temps restant
checks_per_hour = 60 / interval_minutes  # 60/5 = 12 checks/heure
remaining_checks = remaining_fraction * window_hours * checks_per_hour
remaining_target = target_per_day - today_count
probability = remaining_target / remaining_checks

# 3. BOOST DEFICIT : Si en retard sur la progression attendue
expected_by_now = target_per_day * time_fraction
if today_count < expected_by_now:
    deficit_ratio = (expected_by_now - today_count) / expected_by_now
    probability *= 1.0 + deficit_ratio  # Boost jusqu'a 2x

# Tirage aleatoire
should_send = random() < probability
```

**Exemple concret** (config par defaut, user `08dfb351` : min=2, max=5, fenetre 12h-14h) :
- Fenetre : 2 heures, scheduler toutes les 5 min = 12 checks/heure
- Target : 3.5 notifications/jour, total 24 checks
- A 12h30 (25% ecoule, 0 envoye) : probabilite ~19.4% par check + boost deficit
- A 13h36 (80% ecoule, 1 envoye, min=2 non atteint) : **zone de garantie → envoi force**

**Proprietes garanties** :
- `min_per_day` est **toujours** atteint (sauf panne systeme)
- `max_per_day` n'est **jamais** depasse
- Les notifications sont reparties naturellement sur la fenetre
- La probabilite augmente progressivement si en retard

**Logging** : Chaque decision probabiliste est loguee au niveau `INFO` avec tous les details (`probability`, `roll`, `decision`, `time_fraction`, `expected_by_now`).

**Fichier** : `infrastructure/proactive/eligibility.py` — methode `should_send_notification()`

### 2.5.2 Selection du centre d'interet cible

Parmi les interets de l'utilisateur, un seul est selectionne selon l'algorithme :

1. **Filtrer** : Statut `active` uniquement (pas `blocked`, pas `dormant`)
2. **Exclure cooldown par topic** : Interets notifies dans les dernieres 24h exclus
3. **Calculer poids effectif** : `effective_weight = bayesian_weight * decay_factor`
4. **Top N%** : Garder les 20% avec le poids le plus eleve (min 1)
5. **Selection aleatoire** : Parmi le top N%, selection random

**Parametres de selection** :

| Parametre | Valeur | Description |
|-----------|--------|-------------|
| `INTEREST_TOP_PERCENT` | 0.20 | Pourcentage du top des interets a considerer |
| `INTEREST_PER_TOPIC_COOLDOWN_HOURS` | 24 | Cooldown par topic (eviter repetition) |
| `INTEREST_DECAY_RATE_PER_DAY` | 0.01 | Decroissance du poids (1%/jour sans mention) |
| `INTEREST_DEDUP_SIMILARITY_THRESHOLD` | 0.89 | Seuil similarite pour consolidation interets |

### 2.5.3 Generation du contenu

Le contenu est genere via une **chaine de fallback** :

```
1. Brave Search API (source prioritaire)
   └── Recherche web via Brave Search, extraction contenu pertinent
       └── Si echec ou non pertinent ↓

2. Perplexity API (si cle configuree)
   └── Recherche actualites/news recentes
       └── Si echec ou non disponible ↓

3. LLM Reflection (fallback final)
   └── Generation creative par le LLM
```

> **Note historique** : Wikipedia etait la source prioritaire initiale mais a ete remplacee par Brave Search (2026-02) pour obtenir du contenu plus frais et diversifie.

**Deduplication** :
- Hash SHA256 du contenu compare aux 30 derniers jours
- Similarite semantique via OpenAI embeddings (1536 dims) - seuil 0.90

**Generation des embeddings (automatique)** :
- Chaque contenu genere par une source recoit automatiquement un embedding OpenAI
- L'embedding est genere dans `InterestContentGenerator._try_source()` apres generation du contenu
- Permet la comparaison semantique avec les notifications recentes stockees en base

### 2.5.3b Diversity Retry (v1.5)

Quand **toutes** les sources (Brave, Perplexity, LLM) generent du contenu marque comme doublon par le check de similarite cosinus, le systeme retente **une seule fois** avec un topic modifie par un "angle de diversite".

**Principe** :

```
Original: "intelligence artificielle"
Retry:    "intelligence artificielle : perspectives futures"
```

L'angle est choisi aleatoirement parmi 8 angles pre-definis par langue (`INTEREST_CONTENT_DIVERSITY_ANGLES` dans `constants.py`) :

| Langue | Exemples d'angles |
|--------|-------------------|
| fr | "tendances actuelles", "analyse approfondie", "controverses et debats" |
| en | "current trends", "in-depth analysis", "controversies and debates" |
| es/de/it/zh | Traductions equivalentes |

**Semantique de retour de `_try_all_sources()`** :

| Retour | Signification | Action |
|--------|--------------|--------|
| `GenerationResult(success=True)` | Contenu non-doublon trouve | Succes, pas de retry |
| `None` | Au moins une source a produit du contenu, mais tout etait doublon | **Retry avec angle** |
| `GenerationResult(success=False)` | Aucune source n'a produit de contenu | Echec pur, pas de retry |

**Fichiers** : `content_generator.py` (methodes `_try_all_sources`, `_pick_diversity_angle`, `_apply_angle_to_topic`)

### 2.5.3c Runner Stats Tracking (v1.5)

Le `ProactiveTaskRunner` trace desormais les raisons exactes de chaque skip et chaque echec via `RunnerStats`.

**Invariant** : `processed == success + skipped + failed`

**Reasons de skip** (comportement attendu) :

| Raison | Quand |
|--------|-------|
| `feature_disabled` | Feature interets desactivee |
| `outside_time_window` | Hors plage horaire |
| `quota_exceeded` | Quota journalier atteint |
| `global_cooldown` | Cooldown global < 2h |
| `activity_cooldown` | Utilisateur actif recemment |
| `probabilistic_skip` | Tirage aleatoire defavorable |
| `task_eligibility_failed` | Eligibilite specifique task echouee |
| `no_target` | Aucun interet cible disponible |

**Reasons d'echec** (quelque chose a mal tourne) :

| Raison | Quand |
|--------|-------|
| `content_generation_failed` | Aucune source n'a pu generer de contenu |
| `dispatch_failed` | Notification non envoyee (FCM/SSE/archive) |
| `unexpected_exception` | Exception inattendue dans le pipeline |

**Logs** : Les stats completes sont loguees dans `proactive_batch_completed` avec les dictionnaires `skip_reasons` et `failure_reasons`.

**Fichier** : `runner.py` (methodes `record_skip`, `record_failure` sur `RunnerStats`)

### 2.5.4 Presentation du contenu

Le contenu brut est formate par le LLM via `interest_content_prompt` :

- Adapte a la **personnalite** de l'assistant configuree par l'utilisateur
- Traduit dans la **langue** de l'utilisateur
- Style naturel et engageant

### 2.5.5 Canaux de diffusion

Chaque notification est envoyee via **3 canaux simultanement** :

| Canal | Description | Usage |
|-------|-------------|-------|
| **FCM Push** | Notification mobile/web | Alerte meme si app fermee |
| **SSE Redis Pub/Sub** | Temps reel via EventSource | Affichage instantane si page chat ouverte |
| **Archive conversation** | Stockage en base `conversation_messages` | Persistance et historique |

### 2.5.6 Exploitation des Embeddings

Les embeddings OpenAI text-embedding-3-small (1536 dimensions) sont utilises a **trois niveaux** :

#### 1. Deduplication des interets (`_find_similar_interest`)

Lors de l'extraction d'un nouvel interet, le systeme verifie s'il existe deja un interet similaire :

```python
# extraction_service.py
topic_embedding = embeddings.embed_query(topic)
for interest in existing_interests:
    if interest.embedding:
        similarity = cosine_similarity(topic_embedding, interest.embedding)
        if similarity >= INTEREST_DEDUP_SIMILARITY_THRESHOLD:  # 0.89
            return True, interest  # Consolidation
```

**Fallback** : Si un interet existant n'a pas d'embedding, le systeme utilise une comparaison de chaines (`topic.lower() in ...`).

#### 2. Deduplication du contenu (`_is_duplicate`)

Lors de la generation de contenu, le systeme verifie si un contenu similaire a deja ete envoye :

```python
# content_generator.py
content.embedding = embeddings.embed_query(content.content)
for existing_embedding in recent_notification_embeddings:
    similarity = cosine_similarity(content.embedding, existing_embedding)
    if similarity >= INTEREST_CONTENT_SIMILARITY_THRESHOLD:  # 0.90
        return True  # Duplicate, skip
```

#### 3. Stockage pour historique

Les embeddings sont persistes en base pour permettre les comparaisons futures :

| Table | Colonne | Usage |
|-------|---------|-------|
| `user_interests` | `embedding` | Deduplication lors extraction |
| `interest_notifications` | `content_embedding` | Deduplication lors generation contenu |

**Seuils de similarite** :
- **Interets** : 0.89 (INTEREST_DEDUP_SIMILARITY_THRESHOLD) - plus tolerant pour consolider
- **Contenu** : 0.90 (INTEREST_CONTENT_SIMILARITY_THRESHOLD) - plus strict pour eviter repetition

### 2.5.7 Affichage temps reel (SSE → Chat)

Flow complet du backend vers l'affichage dans le chat :

```
Backend                                    Frontend
────────                                   ────────
NotificationDispatcher
    │
    ├── _publish_sse()
    │   └── Redis.publish("user_notifications:{user_id}", payload)
    │
    ▼
SSE Endpoint: /api/v1/notifications/stream
    │
    └── event: notification
        data: { type: "proactive_interest", content, target_id, metadata }
    │
    ▼
useNotifications hook (useNotifications.ts)
    │
    ├── EventSource.addEventListener('notification')
    │
    └── onProactiveNotification(content, targetId, metadata)
    │
    ▼
chat/page.tsx: handleProactiveNotification()
    │
    ├── toast.info() → Popup notification
    │
    └── appendMessage() → Ajoute au chat instantanement
    │
    ▼
ChatMessage.tsx → isInterestNotificationMetadata()
    │
    └── InterestNotificationCard (avec boutons feedback)
```

### 2.5.8 Boutons de feedback (dans le chat uniquement)

Les boutons de feedback **apparaissent uniquement dans le message du chat** (InterestNotificationCard), **jamais dans l'admin des interets**.

| Action | Icone | Effet Backend | Quand utiliser |
|--------|-------|---------------|----------------|
| **J'aime ce sujet** | 👍 ThumbsUp | `positive_signals += 2` | Le message etait interessant |
| **Moins interesse** | 👎 ThumbsDown | `negative_signals += 2` | Pas pertinent cette fois |
| **Ne plus jamais suggerer** | 🚫 Ban | `status = 'blocked'` | Ne plus jamais notifier sur ce sujet |

> **Important** : Ces actions s'appliquent au centre d'interet **dans le contexte d'une notification recue**. Elles n'ont pas de sens hors contexte (d'ou leur absence dans l'admin).

**Dans l'admin (InterestsSettings)** : Seules les actions **Bloquer** et **Supprimer** sont disponibles car elles ont du sens hors contexte de notification.

### 2.5.9 Protection contre les doublons

Plusieurs mecanismes empechent l'envoi de notifications en double :

| Mecanisme | Niveau | Description |
|-----------|--------|-------------|
| `max_instances=1` | APScheduler | Un seul job en cours a la fois |
| **SchedulerLock (TTL retain)** | Redis SETNX | Lock retenu jusqu'a expiration TTL (5min), pas release immediat |
| Cooldown global 2h | EligibilityChecker | Min 2h entre 2 notifications (tous topics) |
| Cooldown topic 24h | InterestRepository | Min 24h avant de reparler du meme sujet |
| Quota journalier | EligibilityChecker | Max N notifications par jour par utilisateur |
| Content hash | InterestNotificationRepository | Pas de contenu identique (SHA256) |

> **Important (v1.6)** : Le `SchedulerLock` ne release plus le lock dans `__aexit__`. Le lock expire
> naturellement via son TTL (5 min par defaut). Cela empeche les N workers uvicorn d'executer
> sequentiellement le meme job dans le meme intervalle du scheduler. Ancien bug : le lock etait
> supprime apres ~0.02s, permettant a tous les workers de s'executer l'un apres l'autre.
>
> **Fichier** : `infrastructure/locks/scheduler_lock.py`

### 2.5.10 Tokens et couts

Les tokens LLM consommes sont trackes et associes a chaque notification. Les tokens sont accumules des deux phases — generation de contenu (LLM reflection) et formatage de presentation :

```python
ProactiveTaskResult(
    content="...",
    tokens_in=975,      # Generation + presentation input tokens
    tokens_out=498,     # Generation + presentation output tokens
    model_name="claude-sonnet-4-6",
)
```

Les tokens sont persistes dans `token_usage_logs` avec `run_id` pour correlation avec `interest_notifications`.

**Affichage per-bulle** : `ProactiveTaskRunner` pre-genere un `run_id` via `generate_proactive_run_id()` et injecte `run_id`, `tokens_in`, `tokens_out`, `tokens_cache`, `cost_eur`, `model_name` dans `result.metadata` avant dispatch. Cela permet :
- L'archivage du `run_id` dans `message_metadata` pour le LEFT JOIN de `get_messages_with_token_summaries()` (chargement historique)
- L'inclusion des tokens dans le payload SSE pour affichage temps reel
- Un mecanisme centralise et DRY pour tous les types proactifs (interest, heartbeat, futurs)

### 2.5.11 Injection dans le contexte LangGraph

Les notifications proactives sont dispatchees par le scheduler **en dehors du graphe LangGraph**. Elles sont archivees dans `conversation_messages` mais **jamais ecrites dans les checkpoints LangGraph**. Quand l'utilisateur repond a une notification, le LLM n'a normalement aucun contexte.

**Solution** : Apres chargement du checkpoint, `OrchestrationService._inject_proactive_messages()` requete `conversation_messages` pour les messages proactifs crees apres le timestamp du checkpoint et les injecte comme `AIMessage` dans `state["messages"]` avant le `HumanMessage`.

**Flow** :
```
load_or_create_state()
  │
  ├── Load checkpoint (state + checkpoint_created_at)
  │
  ├── _inject_proactive_messages()
  │   ├── Query conversation_messages WHERE created_at > checkpoint_created_at
  │   ├── Filter: role="assistant", metadata.type LIKE "proactive_%"
  │   └── Convert to AIMessage (new UUID) → append to state["messages"]
  │
  └── Append HumanMessage (user's reply)
```

**Configuration** :
- `PROACTIVE_INJECT_MAX_MESSAGES` : Max messages injectes par tour (defaut: 5)
- `PROACTIVE_INJECT_LOOKBACK_HOURS` : Fenetre lookback si pas de checkpoint (defaut: 24h)

**Fichiers** : `orchestration/service.py`, `conversations/repository.py`

> Details : `docs/technical/STATE_AND_CHECKPOINT.md` (Pattern 4)

---

#### Pattern: Transactions Autonomes

Chaque composant gere sa propre transaction de maniere independante :

```python
# runner.py - Pattern
async def _process_user(self, user, db):
    # ... eligibility, content generation ...

    # 6. Track tokens (autonomous transaction)
    await track_proactive_tokens(...)  # Cree sa propre session

    # 7. Hook task-specific (autonomous transaction)
    await self.task.on_notification_sent(...)  # Cree sa propre session
```

**Avantages** :
- **Simplicite** : Chaque composant est independant et testable
- **Resilience** : Si un composant echoue, les autres ne sont pas impactes
- **Evolutivite** : Nouvelles taches proactives = implementer `ProactiveTask`

> **Note** : Le pattern `FOR UPDATE SKIP LOCKED` a ete retire car inutile avec ces protections.

#### Implementer une nouvelle tache proactive

```python
# domains/my_feature/proactive_task.py
class MyProactiveTask:
    task_type: str = "my_feature"

    async def check_eligibility(self, user_id, settings, now) -> bool:
        return settings.get("my_feature_enabled", False)

    async def select_target(self, user_id) -> MyTarget | None:
        # Selectionner la cible (email, event, etc.)
        ...

    async def generate_content(self, user_id, target, language) -> ProactiveTaskResult:
        # Generer le contenu via LLM
        ...

    async def on_notification_sent(self, user_id, target, result) -> None:
        # Hook post-notification (optionnel)
        ...
```

---

## 3. Modeles de Donnees

### 3.1 Table `user_interests`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID FK | Reference users.id (CASCADE) |
| `topic` | VARCHAR(200) | Sujet (ex: "iOS, Apple") |
| `category` | VARCHAR(50) | Enum: technology, science, culture, etc. |
| `positive_signals` | INT | Compteur signaux positifs (mentions, thumbs up) |
| `negative_signals` | INT | Compteur signaux negatifs (thumbs down, decay) |
| `status` | VARCHAR(20) | Enum: active, blocked, dormant |
| `last_mentioned_at` | TIMESTAMP | Derniere mention par l'utilisateur |
| `last_notified_at` | TIMESTAMP | Derniere notification envoyee |
| `dormant_since` | TIMESTAMP | Debut de dormance (pour auto-suppression) |
| `embedding` | ARRAY(Float()) | OpenAI embedding (1536 dims) pour deduplication future |
| `created_at` | TIMESTAMP | Date creation |
| `updated_at` | TIMESTAMP | Date modification |

**Index** :
- `ix_user_interests_user_id` : Index sur user_id
- `uq_user_interests_user_topic` : Contrainte unique (user_id, topic)

### 3.2 Table `interest_notifications` (Phase Future)

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | UUID | Primary key |
| `user_id` | UUID FK | Reference users.id (CASCADE) |
| `interest_id` | UUID FK | Reference user_interests.id (SET NULL) |
| `run_id` | VARCHAR(100) | Unique, pour lier aux token_usage_logs |
| `content_hash` | VARCHAR(64) | SHA256 du contenu pour dedup exact |
| `content_embedding` | ARRAY(Float()) | Embedding du contenu (1536 dims) pour dedup semantique |
| `source` | VARCHAR(50) | wikipedia, perplexity, llm_reflection |
| `user_feedback` | VARCHAR(20) | thumbs_up, thumbs_down, null |
| `created_at` | TIMESTAMP | Date envoi |

### 3.3 Extension User Model

Nouveaux champs dans la table `users` :

```python
# Feature toggle
interests_enabled: bool = True  # Opt-in par defaut

# Notification time window (Phase future)
interests_notify_start_hour: int = 9   # Debut plage horaire (0-23)
interests_notify_end_hour: int = 22    # Fin plage horaire (0-23)

# Notification frequency (Phase future)
interests_notify_min_per_day: int = 1  # Min notifications/jour (1-5)
interests_notify_max_per_day: int = 3  # Max notifications/jour (1-5)
```

### 3.4 Schemas Pydantic

```python
# schemas.py

class InterestCategory(str, Enum):
    TECHNOLOGY = "technology"
    SCIENCE = "science"
    CULTURE = "culture"
    SPORTS = "sports"
    FINANCE = "finance"
    TRAVEL = "travel"
    NATURE = "nature"
    HEALTH = "health"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"

class ExtractedInterest(BaseModel):
    """Interest extracted by LLM from conversation."""
    topic: str = Field(..., max_length=200)
    category: InterestCategory
    confidence: float = Field(..., ge=0.0, le=1.0)

class InterestResponse(BaseModel):
    """Interest returned by API."""
    id: UUID
    topic: str
    category: str
    weight: float  # Computed effective_weight
    status: str
    positive_signals: int
    negative_signals: int
    last_mentioned_at: datetime | None
    created_at: datetime

class InterestFeedback(BaseModel):
    feedback: Literal["thumbs_up", "thumbs_down", "block"]
```

---

## 4. Services Backend

### 4.1 InterestExtractionService

**Fichier** : `apps/api/src/domains/interests/services/extraction_service.py`

#### Fonctions Principales

| Fonction | Description |
|----------|-------------|
| `extract_interests_background()` | Fire-and-forget extraction apres response_node |
| `analyze_interests_for_debug()` | Analyse pour debug panel (avec cache Redis) |
| `get_user_interests_for_debug()` | Profil interets utilisateur (DB-only, rapide) |
| `_analyze_interests_core()` | Core LLM analysis (partagee entre debug et background) |

#### Flow d'Extraction

```python
async def extract_interests_background(
    user_id: str,
    messages: list[BaseMessage],
    session_id: str,
    conversation_id: str | None = None,
    user_language: str = "fr",
) -> int:
    """
    Background interest extraction from conversation.

    Returns number of new interests extracted and stored.
    """
    # 1. Run core analysis (uses cache if available)
    analysis = await _analyze_interests_core(user_id, messages, session_id, user_language)

    # 2. Persist tokens
    if analysis._raw_result:
        await _persist_interest_tokens(...)

    # 3. Process each extracted interest
    for extracted in analysis.extracted_interests:
        is_similar, existing = await _find_similar_interest(...)
        if is_similar:
            await repo.consolidate_on_mention(existing)
        else:
            await repo.create(user_id, extracted.topic, extracted.category)

    return stored_count
```

### 4.2 InterestRepository

**Fichier** : `apps/api/src/domains/interests/repository.py`

#### Methodes Principales

| Methode | Description |
|---------|-------------|
| `create()` | Creer un nouvel interet |
| `get_by_id()` | Recuperer par ID |
| `get_active_for_user()` | Interets actifs d'un utilisateur |
| `get_all_for_user()` | Tous les interets (actifs + blocked) |
| `consolidate_on_mention()` | +1 positive_signal, reset last_mentioned_at |
| `apply_feedback()` | Appliquer feedback utilisateur |
| `delete()` | Supprimer un interet |
| `calculate_effective_weight()` | Poids Bayesien avec decay temporel |

#### Algorithme de Poids Bayesien

```python
PRIOR_ALPHA = 2  # Prior positif
PRIOR_BETA = 1   # Prior negatif

def calculate_effective_weight(interest: UserInterest, decay_rate_per_day: float) -> float:
    """Confiance Bayesienne avec decroissance temporelle."""
    # Base Bayesian weight
    alpha = PRIOR_ALPHA + interest.positive_signals
    beta = PRIOR_BETA + interest.negative_signals
    base_weight = alpha / (alpha + beta)

    # Temporal decay
    if interest.last_mentioned_at:
        days_since = (now() - interest.last_mentioned_at).days
        decay = max(0.1, 1.0 - (days_since * decay_rate_per_day))
    else:
        decay = 1.0

    return base_weight * decay
```

---

## 5. Prompts LLM

### 5.1 Interest Extraction Prompt

**Fichier** : `apps/api/src/domains/agents/prompts/v1/interest_extraction_prompt.txt`

#### Structure du Prompt

```
Tu es un analyste comportemental qui identifie les VRAIS centres d'interet d'un utilisateur.

##TACHE
Extraire 0 a 2 centres d'interet PERTINENTS de cette conversation.
Tu formules les topics dans la langue {user_language}.

## REGLES STRICTES

### 1. EXCLURE les actions quotidiennes:
- Email, calendrier, meteo, navigation, rappels, taches
- Questions pratiques (horaires, adresses, conversions)
- Demandes administratives ou transactionnelles

### 2. NIVEAU D'ABSTRACTION CORRECT:
Extraire des CATEGORIES, pas des produits specifiques.
- MAUVAIS: "iPhone 18 Pro Max" -> BON: "iPhone, iOS, smartphones Apple"
- MAUVAIS: "Tesla Model Y" -> BON: "vehicules electriques, Tesla"

### 3. SIGNES D'INTERET AUTHENTIQUE:
- Enthousiasme ou curiosite exprimee
- Demande d'information sur un sujet specifique
- Mentions repetees du meme theme
- Opinions personnelles partagees
- Connaissance prealable demontree

### 4. SI INTERET SIMILAIRE EXISTE:
- NE PAS dupliquer, retourner liste vide
- Le systeme consolidera automatiquement

### 5. CONFIANCE MINIMALE:
- Ne jamais extraire avec confiance < 0.6
```

#### Format de Sortie

```json
[
  {
    "topic": "description courte (max 50 caracteres)",
    "category": "technology|science|culture|...",
    "confidence": 0.0-1.0
  }
]
```

#### Exemples du Prompt

Les exemples utilisent le format `USER:` pour correspondre au format reel de la conversation :

```
USER: J'adore l'astronomie, j'ai passe des heures hier soir a observer Jupiter
Sortie: [{"topic": "astronomie, observation des planetes", "category": "science", "confidence": 0.95}]

USER: Quelle heure est-il a Tokyo ?
Sortie: [] (question pratique, pas d'interet authentique)

USER: Recherche des information sur le langage Python
Sortie: [{"topic": "developpement Python", "category": "technology", "confidence": 0.95}]
```

---

## 6. API Endpoints

### 6.1 Router

**Fichier** : `apps/api/src/domains/interests/router.py`

| Endpoint | Methode | Description |
|----------|---------|-------------|
| `/interests` | GET | Liste interets utilisateur (avec poids calcule) |
| `/interests` | POST | Creer interet manuellement |
| `/interests/{id}` | GET | Recuperer un interet par ID |
| `/interests/{id}` | DELETE | Supprimer un interet |
| `/interests/{id}/feedback` | POST | Soumettre feedback (thumbs_up/thumbs_down/block) |
| `/interests/settings` | GET | Recuperer parametres notifications |
| `/interests/settings` | PATCH | Modifier parametres |
| `/interests/categories` | GET | Liste categories disponibles |

### 6.2 Exemples de Reponses

**GET /interests**

```json
{
  "interests": [
    {
      "id": "uuid",
      "topic": "developpement Python",
      "category": "technology",
      "weight": 0.85,
      "status": "active",
      "positive_signals": 5,
      "negative_signals": 0,
      "last_mentioned_at": "2026-01-27T10:30:00Z",
      "created_at": "2026-01-20T14:00:00Z"
    }
  ],
  "total": 1,
  "active": 1,
  "blocked": 0
}
```

**POST /interests/{id}/feedback**

```json
{
  "feedback": "thumbs_up"
}
```

Effets du feedback :
- `thumbs_up` : +2 positive_signals
- `thumbs_down` : +2 negative_signals
- `block` : status = "blocked"

---

## 7. Frontend

### 7.1 InterestsSettings (Admin)

**Fichier** : `apps/web/src/components/settings/InterestsSettings.tsx`

Composant de gestion des interets dans la page Settings :

- **Toggle global** : Activer/desactiver les notifications proactives
- **Plage horaire** : Definir les heures de notification (9h-22h par defaut)
- **Frequence** : Min/max notifications par jour (1-5)
- **Liste des interets** : Affichage avec badge poids (couleur selon niveau)
- **Actions disponibles** : Bloquer, Supprimer (pas de feedback thumbs up/down)
- **Ajout manuel** : Formulaire pour creer un interet
- **Filtre par categorie** : Navigation par type d'interet

> **Note** : Les boutons thumbs up/down n'apparaissent pas ici car ils n'ont de sens que dans le contexte d'une notification recue.

### 7.2 InterestNotificationCard (Chat)

**Fichier** : `apps/web/src/components/chat/InterestNotificationCard.tsx`

Carte speciale pour afficher les notifications proactives dans le chat :

- **Style distinct** : Gradient ambre/orange, icone Sparkles
- **Badge source** : Wikipedia, Perplexity, ou Reflexion LLM
- **Contenu Markdown** : Rendu riche du message
- **Boutons feedback** : 👍 J'aime, 👎 Moins interesse, 🚫 Ne plus suggerer
- **Timestamp** : Date et heure de reception

**Detection automatique** : Le composant ChatMessage detecte les messages proactifs via `isInterestNotificationMetadata(message.metadata)` et rend InterestNotificationCard au lieu du message standard.

### 7.3 useNotifications Hook

**Fichier** : `apps/web/src/hooks/useNotifications.ts`

Hook pour les notifications temps reel via SSE :

- **Types supportes** : `reminder`, `proactive_interest`, `oauth_health_warning`, etc.
- **Callback `onProactiveNotification`** : Appele quand notification proactive recue (interest, heartbeat, etc.)
- **Metadata transmis** : `target_id`, `source`, `article_url`, `feedback_enabled`, `run_id`, `tokens_in`, `tokens_out`, `tokens_cache`, `cost_eur`, `model_name`

### 7.4 handleProactiveNotification (chat/page.tsx)

Handler dans la page chat qui :

1. Affiche un toast avec le topic
2. Extrait les donnees de tokens depuis `metadata` (`tokens_in`, `tokens_out`, `tokens_cache`, `cost_eur`)
3. Appelle `appendMessage()` pour ajouter instantanement au chat avec les champs token remplis
4. Le message apparait avec InterestNotificationCard et les badges de tokens

### 7.5 Debug Panel - InterestProfileSection

**Fichier** : `apps/web/src/components/debug/components/sections/InterestProfileSection.tsx`

Section du debug panel affichant :

- Interets extraits du message courant avec confiance
- Decisions de matching (consolidation vs creation)
- Interets existants pour comparaison
- Metadonnees LLM (tokens, modele)

---

## 8. Configuration

### 8.1 Variables d'Environnement

```bash
# Feature toggles
INTEREST_EXTRACTION_ENABLED=true
INTEREST_NOTIFICATIONS_ENABLED=false  # Phase future

# LLM Configuration (default: openai/gpt-5.4-mini, reasoning_effort: low)
INTEREST_EXTRACTION_LLM_PROVIDER=openai
INTEREST_EXTRACTION_LLM_MODEL=gpt-5.4-mini
INTEREST_EXTRACTION_LLM_TEMPERATURE=0.5
INTEREST_EXTRACTION_LLM_MAX_TOKENS=500
INTEREST_EXTRACTION_LLM_REASONING_EFFORT=low

# Weight Evolution
INTEREST_DECAY_RATE_PER_DAY=0.01
INTEREST_DORMANT_THRESHOLD_DAYS=30
INTEREST_DELETION_THRESHOLD_DAYS=90

# Deduplication
INTEREST_DEDUP_SIMILARITY_THRESHOLD=0.89
```

### 8.2 Constantes

**Fichier** : `apps/api/src/core/constants.py`

```python
# Interest Learning System
INTEREST_EXTRACTION_QUERY_TRUNCATION_LENGTH = 500
INTEREST_DEDUP_SEARCH_LIMIT = 20
INTEREST_ACTIVE_LIST_LIMIT = 50
INTEREST_EXTRACTION_MIN_CONFIDENCE = 0.6
INTEREST_ANALYSIS_CACHE_TTL = 300  # 5 minutes
REDIS_KEY_INTEREST_ANALYSIS_PREFIX = "interest:analysis:"
```

---

## 9. Observabilite

### 9.1 Metriques Prometheus

```python
# Extraction
interest_extraction_total{status="success|failed|skipped"}
interest_extraction_duration_seconds
interest_extraction_tokens_total{type="in|out|cache"}

# Actions
interest_created_total
interest_consolidated_total
interest_feedback_total{type="thumbs_up|thumbs_down|block"}

# Debug
interest_extraction_debug_total
```

### 9.2 Logs Structures

```python
# Extraction scheduled
logger.info("interest_extraction_scheduled", user_id=..., message_count=...)

# LLM input/output
logger.info("interest_extraction_llm_input", conversation_preview=..., existing_interests_preview=...)
logger.info("interest_extraction_llm_output", result_content=...)

# Results
logger.info("interest_created", user_id=..., topic=..., category=..., confidence=...)
logger.info("interest_consolidated", user_id=..., interest_id=..., topic=..., positive_signals=...)
logger.info("interest_tokens_persisted", input_tokens=..., output_tokens=..., model_name=...)
```

---

## 10. Tests

### 10.1 Tests Unitaires

```bash
# Repository
pytest tests/domains/interests/test_repository.py -v

# Extraction service
pytest tests/domains/interests/test_extraction_service.py -v

# Schemas
pytest tests/domains/interests/test_schemas.py -v
```

### 10.2 Tests Integration

```bash
# API endpoints
pytest tests/integration/test_interests_api.py -v
```

### 10.3 Tests Manuels

**Extraction**:
1. Discuter d'un sujet ("je m'interesse beaucoup a l'IA") → verifier creation interet
2. Reparler du meme sujet → verifier augmentation positive_signals (consolidation)
3. Parler de sujets similaires → verifier pas de doublons

**Notifications proactives**:
4. Attendre une notification (ou forcer via scheduler) → verifier apparition dans chat
5. Verifier que le message utilise InterestNotificationCard (style ambre/orange)
6. Verifier les boutons feedback visibles (thumbs up, thumbs down, block)

**Injection contexte LangGraph**:
18. Recevoir une notification proactive → repondre dans le chat
19. Verifier les logs API : `proactive_messages_injected` avec `injected_count >= 1`
20. Verifier que la reponse du LLM prend en compte le contenu de la notification

**Feedback (dans le chat)**:
7. Cliquer thumbs up sur notification → verifier augmentation poids
8. Cliquer thumbs down sur notification → verifier diminution poids
9. Cliquer block sur notification → verifier status = blocked

**Admin (Settings)**:
10. Toggle activer/desactiver → verifier effect sur notifications
11. Modifier plage horaire → verifier respect
12. Bloquer un interet via admin → plus de notifications sur ce topic
13. Supprimer un interet → verification suppression
14. Creer interet manuellement → verification creation

**Real-time**:
15. Avoir la page chat ouverte → notification doit apparaitre instantanement via SSE
16. Verifier toast popup avec le topic
17. Refresh page → verifier que le message est bien archive et reapparait

---

## Phases d'Implementation

| Phase | Description | Statut |
|-------|-------------|--------|
| **Phase 0** | Infrastructure proactive generique | ✅ Complete |
| **Phase 1** | Core Backend - Modeles & Extraction | ✅ Complete |
| **Phase 2** | Evolution des poids & Repository | ✅ Complete |
| **Phase 3** | Sources de contenu (Wikipedia, Perplexity, LLM) | ✅ Complete |
| **Phase 4** | Notifications proactives (FCM + SSE + Archive) | ✅ Complete |
| **Phase 5** | API Backend & Frontend Settings | ✅ Complete |
| **Phase 6** | InterestNotificationCard & Feedback | ✅ Complete |
| **Phase 7** | Real-time SSE → Chat integration | ✅ Complete |
| **Phase 8** | Token tracking & Observabilite | ✅ Complete |

---

## References

- **Pattern** : `apps/api/src/domains/memory/memory_extractor.py`
- **ADR** : `docs/architecture/ADR-053-Interest-Learning-System.md`

---

**Fin de la documentation**
