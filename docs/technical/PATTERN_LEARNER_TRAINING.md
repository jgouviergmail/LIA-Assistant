# Pattern Learner Training System

## Vue d'ensemble

Le système de training du Pattern Learner permet d'entraîner le modèle d'apprentissage des patterns de planification en exécutant automatiquement des requêtes utilisateur via l'API. Chaque exécution réussie enregistre le pattern dans Redis, améliorant progressivement les suggestions du planner.

**Créé:** 2026-01-12
**Statut:** Production-ready
**Prérequis:** Session OAuth authentifiée

---

## Table des matières

1. [Architecture](#architecture)
2. [Composants](#composants)
3. [Flux d'exécution](#flux-dexécution)
4. [Configuration](#configuration)
5. [Commandes Taskfile](#commandes-taskfile)
6. [Fichiers de tests](#fichiers-de-tests)
7. [Authentification](#authentification)
8. [Métriques et monitoring](#métriques-et-monitoring)
9. [Limitations et risques](#limitations-et-risques)
10. [Troubleshooting](#troubleshooting)

---

## Architecture

### Diagramme de flux

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PATTERN LEARNER TRAINING SYSTEM                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐ │
│  │   Taskfile   │────▶│    Script    │────▶│         API Docker           │ │
│  │  (commands)  │     │   Python     │     │     (localhost:8000)         │ │
│  └──────────────┘     └──────────────┘     └──────────────────────────────┘ │
│                              │                          │                    │
│                              │                          ▼                    │
│                              │              ┌──────────────────────────────┐ │
│                              │              │       LangGraph Flow          │ │
│                              │              │  Router → Planner → Executor  │ │
│                              │              │         → Response            │ │
│                              │              └──────────────────────────────┘ │
│                              │                          │                    │
│                              │                          ▼                    │
│                              │              ┌──────────────────────────────┐ │
│                              │              │      response_node.py         │ │
│                              │              │  Pattern Learning Recording   │ │
│                              │              │    (fire-and-forget async)    │ │
│                              │              └──────────────────────────────┘ │
│                              │                          │                    │
│                              ▼                          ▼                    │
│                    ┌──────────────────────────────────────────────────────┐  │
│                    │                    Redis (db=2)                       │  │
│                    │           plan:patterns:{pattern_key}                 │  │
│                    │     {s: successes, f: failures, d: domains, i: intent}│  │
│                    └──────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Intégration dans le graphe LangGraph

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
                    │ Router  │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
                    │ Planner │ ──────────────────────────────────┐
                    └────┬────┘                                    │
                         │                                         │
            ┌────────────┴────────────┐                           │
            │                         │                           │
            ▼                         ▼                           │
   ┌─────────────────┐      ┌─────────────────┐                  │
   │ approval_gate   │      │ task_orchestrator│ ◀── Plans simples│
   │ (multi-domain)  │      │  (mono-domain)   │     (bypass)     │
   └────────┬────────┘      └────────┬────────┘                  │
            │                         │                           │
            ▼                         │                           │
   ┌─────────────────┐               │                           │
   │semantic_validator│               │                           │
   │  ⚡ Recording A  │               │                           │
   └────────┬────────┘               │                           │
            │                         │                           │
            └────────────┬────────────┘                           │
                         │                                         │
                         ▼                                         │
                  ┌─────────────┐                                 │
                  │response_node│                                 │
                  │ ⚡ Recording B│ ◀──────────────────────────────┘
                  └─────────────┘
                         │
                         ▼
                    ┌─────────┐
                    │   END   │
                    └─────────┘

⚡ Recording A: semantic_validator_node.py (plans complexes validés)
⚡ Recording B: response_node.py (plans simples qui ont bypassé la validation)
```

---

## Composants

### 1. Script de training (`train_pattern_learner.py`)

**Localisation:** `apps/api/scripts/train_pattern_learner.py`

**Responsabilités:**
- Lecture des fichiers de queries
- Authentification via cookie de session
- Envoi séquentiel des requêtes à l'API
- Collecte des statistiques d'exécution
- Rapport de progression en temps réel

**Classes principales:**

```python
class PatternLearnerTrainer:
    """
    Trainer for pattern learner via API requests.

    Attributes:
        base_url: URL de l'API (default: http://localhost:8000/api/v1)
        session_cookie: Cookie de session pour l'authentification
        repeat: Nombre de répétitions par query
        delay: Délai entre les requêtes (secondes)
        timeout: Timeout par requête (secondes)
        user_id: ID utilisateur récupéré de la session
    """

    async def train(self, queries: list[str]) -> dict:
        """Execute training with given queries."""

    async def _fetch_user_id(self, client) -> bool:
        """Authenticate and retrieve user_id from session."""

    async def _send_query(self, client, query, iteration, idx) -> bool:
        """Send a single query to the API."""
```

### 2. Fichiers de tests

**Localisation:** `apps/api/scripts/training/`

| Fichier | Type | Queries | Description |
|---------|------|---------|-------------|
| `contacts_safe.txt` | READ | 6 | Recherche contacts |
| `contacts_unsafe.txt` | MUTATION | 3 | Création/modification/suppression |
| `emails_safe.txt` | READ | 7 | Recherche emails |
| `calendar_safe.txt` | READ | 7 | Consultation agenda |
| `calendar_unsafe.txt` | MUTATION | 9 | Création/modification événements |
| `tasks_safe.txt` | READ | 4 | Liste tâches |
| `tasks_unsafe.txt` | MUTATION | 5 | Création/modification tâches |
| `drive.txt` | READ | 4 | Recherche fichiers |
| `places.txt` | READ | 10 | Recherche lieux |
| `routes.txt` | READ | 8 | Calcul itinéraires |
| `weather.txt` | READ | 13 | Météo |
| `perplexity.txt` | READ | 11 | Recherche web |
| `wikipedia.txt` | READ | 8 | Recherche Wikipedia |
| `multi_domain_safe.txt` | READ | 10 | Requêtes multi-domaines |
| `multi_domain_unsafe.txt` | MUTATION | 7 | Multi-domaines avec mutations |

### 3. Pattern Learning dans response_node.py

**Localisation:** `apps/api/src/domains/agents/nodes/response_node.py` (lignes 1908-1970)

```python
# ===================================================================
# PLAN PATTERN LEARNING (fire-and-forget, post-execution)
# ===================================================================
# Record plan execution success/failure for pattern learning.
# Complements semantic_validator_node recording by capturing:
# - Patterns that bypassed semantic validation (simple read queries)
# - Execution outcomes (not just validation outcomes)
#
# Only records if:
# 1. turn_type is ACTION (not CONVERSATIONAL/REFERENCE)
# 2. execution_plan exists (planner was invoked)
# 3. semantic_validation NOT in state (avoid double-recording)
# ===================================================================
try:
    from src.domains.agents.analysis.query_intelligence_helpers import (
        get_query_intelligence_from_state,
    )
    from src.domains.agents.services.plan_pattern_learner import (
        record_plan_failure,
        record_plan_success,
    )

    execution_plan = state.get(STATE_KEY_EXECUTION_PLAN)
    semantic_validation = state.get(STATE_KEY_SEMANTIC_VALIDATION)

    if (
        turn_type == TURN_TYPE_ACTION
        and execution_plan
        and semantic_validation is None  # Avoid double-recording
    ):
        qi_object = get_query_intelligence_from_state(state)

        if qi_object:
            planner_error = state.get(STATE_KEY_PLANNER_ERROR)
            plan_rejected = state.get(STATE_KEY_PLAN_REJECTION_REASON)

            if planner_error or plan_rejected:
                record_plan_failure(execution_plan, qi_object)
            else:
                record_plan_success(execution_plan, qi_object)

except (ValueError, KeyError, RuntimeError, AttributeError, ImportError) as e:
    logger.debug("pattern_learning_recording_failed", ...)
```

### 4. Plan Pattern Learner Service

**Localisation:** `apps/api/src/domains/agents/services/plan_pattern_learner.py`

**Fonctions clés:**

```python
def record_plan_success(plan: ExecutionPlan, qi: QueryIntelligence) -> None:
    """Fire-and-forget: enregistre un succès dans Redis."""

def record_plan_failure(plan: ExecutionPlan, qi: QueryIntelligence) -> None:
    """Fire-and-forget: enregistre un échec dans Redis."""

async def get_learned_patterns_prompt(domains: list[str], is_mutation: bool) -> str:
    """Génère la section de patterns à injecter dans le prompt planner."""

async def can_skip_validation(plan: ExecutionPlan) -> bool:
    """Vérifie si le pattern peut bypasser la validation (≥90% confiance, ≥10 obs)."""
```

---

## Flux d'exécution

### 1. Initialisation

```
1. Utilisateur exécute: task patterns:train:contacts
2. Taskfile lance: python train_pattern_learner.py --file contacts_safe.txt
3. Script lit la variable d'environnement LIA_SESSION
4. Script charge les queries depuis le fichier
```

### 2. Authentification

```
1. Script appelle GET /api/v1/users/me avec cookie
2. API valide la session dans Redis
3. API retourne les infos utilisateur (id, email, etc.)
4. Script stocke le user_id pour les requêtes suivantes
```

### 3. Boucle de training

```
Pour chaque itération (1 à repeat):
    Pour chaque query dans le fichier:
        1. Construire le payload: {message, user_id, session_id}
        2. POST /api/v1/agents/chat/stream avec cookie
        3. Consommer le stream SSE jusqu'à "done" ou "error"
        4. Compter succès/échec
        5. Attendre {delay} secondes
```

### 4. Enregistrement du pattern (côté API)

```
1. LangGraph exécute: Router → Planner → task_orchestrator
2. Planner génère ExecutionPlan avec steps: [get_contacts]
3. task_orchestrator exécute le plan
4. response_node vérifie les conditions:
   - turn_type == ACTION? ✓
   - execution_plan exists? ✓
   - semantic_validation is None? ✓ (plan simple)
5. record_plan_success(plan, query_intelligence) appelé
6. Async task créé: Redis HINCRBY plan:patterns:get_contacts s 1
```

### 5. Stockage Redis

```
Key: plan:patterns:get_contacts
Type: Hash
Fields:
  s: 1          # successes (incrémenté)
  f: 0          # failures
  d: "contacts" # domains (set once)
  i: "read"     # intent (set once)
  t: 1736715600 # timestamp (updated)
TTL: 30 days (refreshed on each update)
```

---

## Configuration

### Variables d'environnement

| Variable | Description | Default |
|----------|-------------|---------|
| `LIA_SESSION` | Cookie de session (REQUIS) | - |
| `PLAN_PATTERN_LEARNING_ENABLED` | Activer/désactiver le learning | `true` |
| `PLAN_PATTERN_PRIOR_ALPHA` | Prior Beta alpha | `2` |
| `PLAN_PATTERN_PRIOR_BETA` | Prior Beta beta | `1` |
| `PLAN_PATTERN_MIN_OBS_SUGGEST` | Min observations pour suggestion | `3` |
| `PLAN_PATTERN_MIN_CONF_SUGGEST` | Min confiance pour suggestion | `0.75` |
| `PLAN_PATTERN_MIN_OBS_BYPASS` | Min observations pour bypass | `10` |
| `PLAN_PATTERN_MIN_CONF_BYPASS` | Min confiance pour bypass | `0.90` |
| `PLAN_PATTERN_REDIS_PREFIX` | Préfixe des clés Redis | `plan:patterns` |
| `PLAN_PATTERN_REDIS_TTL_DAYS` | TTL des patterns | `30` |

### Paramètres du script

| Paramètre | Description | Default |
|-----------|-------------|---------|
| `-f, --file` | Fichier de queries | - |
| `-q, --queries` | Queries inline | - |
| `-i, --interactive` | Mode interactif | - |
| `-s, --session` | Cookie de session | `$LIA_SESSION` |
| `-r, --repeat` | Répétitions | `20` |
| `-d, --delay` | Délai entre requêtes (s) | `1.0` |
| `--base-url` | URL de l'API | `http://localhost:8000/api/v1` |
| `--timeout` | Timeout requête (s) | `120` |

---

## Commandes Taskfile

### Vérification

```bash
# Vérifier l'authentification
task patterns:train:auth

# Lister les patterns actuels
task patterns:list

# Statistiques globales
task patterns:stats
```

### Training par domaine (SAFE)

```bash
# Tous les domaines safe
task patterns:train:all

# Mono-domaines uniquement
task patterns:train:mono

# Par domaine spécifique
task patterns:train:contacts
task patterns:train:emails
task patterns:train:calendar
task patterns:train:tasks
task patterns:train:drive
task patterns:train:places
task patterns:train:routes
task patterns:train:weather
task patterns:train:perplexity
task patterns:train:wikipedia

# Multi-domaines safe
task patterns:train:multi
```

### Training avec mutations (UNSAFE)

```bash
# ⚠️ ATTENTION: Ces commandes exécutent des mutations réelles!

# Tous les unsafe (avec confirmation 5s)
task patterns:train:all:unsafe

# Par domaine
task patterns:train:contacts:unsafe
task patterns:train:calendar:unsafe
task patterns:train:tasks:unsafe
task patterns:train:multi:unsafe  # ⚠️ ENVOIE DES EMAILS!
```

### Options

```bash
# Répéter 10 fois au lieu de 20
task patterns:train:contacts -- --repeat 10

# Délai de 2 secondes entre requêtes
task patterns:train:contacts -- --delay 2.0
```

---

## Fichiers de tests

### Format

```text
# Commentaire (ignoré)
# Ligne vide (ignorée)

query 1
query 2
query 3
```

### Catégories

#### SAFE (répétables sans effet de bord)

- Recherches (`recherche les contacts...`)
- Listes (`liste mes emails...`)
- Consultations (`météo paris`, `itinéraire vers...`)
- Requêtes d'information (`qu'est-ce que j'ai prévu...`)

#### UNSAFE (mutations - à utiliser avec précaution)

- Création (`crée un contact...`, `ajoute un événement...`)
- Modification (`modifie le téléphone...`, `déplace la réunion...`)
- Suppression (`supprime le contact...`, `annule la réunion...`)
- Envoi (`envoie un email...`, `transfère le message...`)

---

## Authentification

### Récupération du cookie

1. Ouvrir l'application dans le navigateur
2. Se connecter avec votre compte
3. Ouvrir DevTools (F12)
4. Aller dans Application > Cookies
5. Copier la valeur de `lia_session`

### Configuration

```bash
# Windows (CMD)
set LIA_SESSION=votre_cookie_ici

# Windows (PowerShell)
$env:LIA_SESSION="votre_cookie_ici"

# Linux/Mac
export LIA_SESSION="votre_cookie_ici"
```

### Vérification

```bash
task patterns:train:auth
# ✅ LIA_SESSION is set (first 20 chars: abc123def456...)
```

### Durée de vie

Le cookie de session a une durée de vie limitée (selon configuration serveur). Si le training échoue avec "Session expired":

1. Se reconnecter dans le navigateur
2. Récupérer le nouveau cookie
3. Mettre à jour `LIA_SESSION`

---

## Métriques et monitoring

### Statistiques de training (script)

```
============================================================
📊 Training Summary
============================================================
   Total queries sent: 120
   Successful: 118 (98.3%)
   Failed: 2 (1.7%)
   Duration: 145.2s
   Throughput: 0.83 q/s

   Errors by type:
     - HTTP_500: 1
     - Timeout: 1

✨ Run 'task patterns:list' to see learned patterns
```

### Patterns appris (Redis)

```bash
task patterns:list
```

```
Pattern Key                              S/F      Conf         Domains         Intent
---------------------------------------------------------------------------------------
get_contacts                             20/0     96% [BYPASS] contacts        read
get_emails                               20/0     96% [BYPASS] emails          read
get_weather_forecast                     18/2     90% [BYPASS] weather         read
get_contacts→send_email                  10/0     92% [BYPASS] contacts,emails mutation
---------------------------------------------------------------------------------------
Total: 4 patterns
```

### Métriques Prometheus

Le Pattern Learner n'expose pas de métriques Prometheus dédiées pour le moment. Les métriques existantes de l'API (latence, erreurs) s'appliquent.

---

## Limitations et risques

### Limitations techniques

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Pas de retry automatique | Requêtes échouées non re-tentées | Augmenter `--repeat` |
| Pas de mode dry-run | Impossible de simuler | Utiliser `--repeat 1` pour tester |
| Session unique par query | Pas de contexte conversationnel | Intentionnel pour isoler les patterns |
| Authentification requise | Impossible de tester en batch sans session | Utiliser une session longue durée |
| Pas de parallélisation | Training séquentiel lent | Délai réduit possible (`--delay 0.5`) |

### Risques

| Risque | Niveau | Mitigation |
|--------|--------|------------|
| Envoi d'emails réels | 🔴 CRITIQUE | Fichiers `*_unsafe.txt` séparés |
| Création de données parasites | 🔴 CRITIQUE | Default `--repeat 1` pour unsafe |
| Suppression de données | 🔴 CRITIQUE | Sauvegarde préalable |
| Coûts LLM | 🟡 MOYEN | ~$0.01-0.05 par requête |
| Rate limiting Google | 🟡 MOYEN | Délai entre requêtes |
| Session expirée | 🟢 FAIBLE | Renouveler le cookie |
| Patterns incorrects | 🟢 FAIBLE | `task patterns:reset` |

### Coûts estimés

| Scénario | Requêtes | Coût LLM estimé | Temps |
|----------|----------|-----------------|-------|
| 1 domaine × 20 | ~120 | ~$1-2 | ~2 min |
| Tous safe × 20 | ~1740 | ~$15-30 | ~30 min |
| Tous safe × 10 | ~870 | ~$8-15 | ~15 min |

---

## Troubleshooting

### Erreur: "Session expired or invalid"

```
❌ Session expired or invalid. Please login again and get a new session cookie.
```

**Cause:** Le cookie de session a expiré.

**Solution:**
1. Se reconnecter dans le navigateur
2. Récupérer le nouveau cookie
3. `set LIA_SESSION=nouveau_cookie`

### Erreur: "HTTP 401"

```
⚠️  [recherche contacts...] HTTP 401
```

**Cause:** Cookie invalide ou mal formaté.

**Solution:** Vérifier que le cookie est correctement copié (sans guillemets supplémentaires).

### Erreur: "Connection refused"

```
🔌 [recherche contacts...] Connection failed
```

**Cause:** L'API Docker n'est pas démarrée.

**Solution:**
```bash
docker compose -f docker-compose.dev.yml up -d api
docker compose -f docker-compose.dev.yml ps  # Vérifier status
```

### Erreur: "Timeout"

```
⏱️  [recherche contacts...] Timeout
```

**Cause:** Requête trop longue (>120s).

**Solution:** Augmenter le timeout: `--timeout 300`

### Patterns non enregistrés

```bash
task patterns:list
# Total: 0 patterns
```

**Causes possibles:**
1. Redis non accessible
2. `PLAN_PATTERN_LEARNING_ENABLED=false`
3. Requêtes conversationnelles (pas d'ExecutionPlan)

**Diagnostic:**
```bash
# Vérifier les logs Docker
docker compose -f docker-compose.dev.yml logs api | grep pattern

# Vérifier la config
docker compose -f docker-compose.dev.yml exec api env | grep PATTERN
```

---

## Références

- [ADR-039: Cost Optimization Token Management](../architecture/ADR-039-Cost-Optimization-Token-Management.md)
- [Plan Pattern Learner](./PLAN_PATTERN_LEARNER.md)
- [Semantic Validation](../architecture/ADR-044-Draft-HITL-Approval-Flow.md)
- [LangGraph Architecture](../ARCHITECTURE_LANGRAPH.md)
