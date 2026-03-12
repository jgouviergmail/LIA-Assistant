# Plan Pattern Learner

> **Documentation Technique & Fonctionnelle** - Apprentissage Dynamique des Patterns de Planification
>
> Version: 1.1
> Date: 2026-01-22
> Related: [PLANNER.md](PLANNER.md) | [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md) | [SMART_SERVICES.md](SMART_SERVICES.md) (Golden Patterns)

---

## Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Modèle Bayésien](#modèle-bayésien)
4. [Stockage Redis](#stockage-redis)
5. [Points d'intégration](#points-dintégration)
6. [Configuration](#configuration)
7. [Golden Patterns](#golden-patterns)
8. [CLI Maintenance](#cli-maintenance)
9. [API Reference](#api-reference)
10. [Performance](#performance)
11. [Monitoring & Observabilité](#monitoring--observabilité)
12. [Troubleshooting](#troubleshooting)

---

## Vue d'ensemble

### Objectif

Le **Plan Pattern Learner** est un système d'apprentissage automatique qui réduit les replanifications coûteuses en apprenant des succès et échecs de validation des plans générés par le Planner Node.

### Problème Résolu

```
Situation actuelle:
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Planner   │────▶│  Validator  │────▶│   Replan?   │
│ (LLM ~500ms)│     │ (LLM ~300ms)│     │ (LLM ~500ms)│
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ~2300 tokens/replan

Avec Pattern Learner:
┌─────────────┐     ┌─────────────┐
│   Planner   │────▶│  Patterns   │ → Skip validation si 90% confiance
│ + patterns  │     │  (Redis)    │ → Guide planner vers patterns validés
└─────────────┘     └─────────────┘
       │
       └── +45 tokens (3 patterns suggérés)
           -2300 tokens (replan évité)
```

### Bénéfices Quantifiés

| Métrique | Sans Patterns | Avec Patterns |
|----------|---------------|---------------|
| Tokens/replan | ~2300 | 0 (bypass) |
| Tokens prompt | 0 | ~45 (3 suggestions) |
| **ROI** | - | **+2255 tokens économisés** |
| Latence validation | ~300ms | ~5ms (Redis) |
| Taux replan | Variable | ↓ progressif |

### Principes Fondamentaux

| Principe | Description |
|----------|-------------|
| **100% Dynamique** | Aucun pattern hardcodé, tout est appris |
| **Anonymisation Stricte** | Seule la séquence d'outils est stockée |
| **Cross-User** | Redis partagé pour apprentissage global |
| **Zero Latence** | Fire-and-forget async, < 1ms d'impact |
| **Montée Rapide** | Bayesian Beta(2,1), 3 succès = suggérable |
| **Filtrage Exact** | Domaines = exact match, max 3 patterns |

---

## Architecture

### Flow Global

```
                                    ┌─────────────────────┐
                                    │    SMART PLANNER    │
                                    │    SERVICE          │
                                    └─────────┬───────────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         │                    │                    │
                         ▼                    ▼                    ▼
              ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
              │ get_learned_     │ │   BUILD PROMPT   │ │    SEMANTIC      │
              │ patterns_prompt()│ │   (inject into)  │ │    VALIDATOR     │
              └────────┬─────────┘ └──────────────────┘ └────────┬─────────┘
                       │                                         │
                       ▼                                         ▼
              ┌──────────────────┐                    ┌──────────────────┐
              │ PLAN PATTERN     │                    │  can_skip_       │
              │ LEARNER SERVICE  │                    │  validation()    │
              └────────┬─────────┘                    └────────┬─────────┘
                       │                                       │
                       │         ┌─────────────────────┐       │
                       └────────▶│      REDIS          │◀──────┘
                                 │   Hash Storage      │
                                 │   plan:patterns:*   │
                                 └─────────────────────┘
                                          ▲
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
          ┌─────────┴────────┐  ┌─────────┴────────┐  ┌────────┴────────┐
          │ record_success() │  │ record_failure() │  │ Admin CLI       │
          │ (async)          │  │ (async)          │  │ (Taskfile)      │
          └──────────────────┘  └──────────────────┘  └─────────────────┘
```

### Composants

```
apps/api/src/domains/agents/services/
└── plan_pattern_learner.py    # Service principal (~1000 lignes)

apps/api/src/core/
├── constants.py               # PLAN_PATTERN_* constantes
└── config/agents.py           # Pydantic settings

apps/api/scripts/
└── manage_plan_patterns.py    # CLI maintenance

Taskfile.yml                   # Tâches patterns:*
```

### Data Structures

```python
@dataclass(frozen=True, slots=True)
class PatternStats:
    """Statistiques d'un pattern - immutable pour cohérence."""
    key: str                      # "get_contacts→send_email"
    successes: int                # Validations réussies
    failures: int                 # Validations échouées
    domains: frozenset[str]       # {"contacts", "emails"}
    intent: str                   # "read" | "mutation"
    last_update: int              # Unix timestamp

    @property
    def confidence(self) -> float:
        """Bayesian confidence: (α+s)/(α+β+s+f)"""

    @property
    def is_suggerable(self) -> bool:
        """total >= 3 AND confidence >= 75%"""

    @property
    def can_bypass_validation(self) -> bool:
        """total >= 10 AND confidence >= 90%"""
```

---

## Modèle Bayésien

### Prior Beta(2,1)

Le système utilise une distribution **Beta** pour la confiance:

```
Posterior = Beta(α + successes, β + failures)

Avec prior β(2,1):
- α = 2 (prior successes)
- β = 1 (prior failures)
- Prior mean = α/(α+β) = 2/3 = 67%
```

### Pourquoi Beta(2,1) ?

| Prior | Initial Conf | Comportement |
|-------|--------------|--------------|
| Beta(1,1) | 50% | Neutre, monte lentement |
| Beta(2,1) | 67% | **Optimiste, monte vite** |
| Beta(1,2) | 33% | Pessimiste, lent |
| Beta(5,1) | 83% | Trop confiant |

**Choix rationnel**: Un pattern généré par le planner LLM a une probabilité a priori élevée d'être correct. Beta(2,1) encode cette croyance.

### Évolution de la Confiance

```
Observations    Succès    Échecs    Confidence
─────────────────────────────────────────────
0               0         0         67% (prior)
1               1         0         75% ✓ suggérable
2               2         0         80%
3               3         0         83% ✓ suggérable
5               5         0         87%
10              10        0         92% ✓ bypass
15              15        0         94%

Avec échecs:
5               4         1         75% ✓ suggérable
10              8         2         77% ✓ suggérable
10              7         3         69% ✗ non suggérable
```

### Formules

```python
# Confidence Bayésienne
confidence = (α + successes) / (α + β + successes + failures)

# Avec α=2, β=1:
confidence = (2 + s) / (3 + s + f)

# Seuils de décision
is_suggerable = (total >= 3) AND (confidence >= 0.75)
can_bypass = (total >= 10) AND (confidence >= 0.90)
```

### K-Anonymity

Pour protéger contre les patterns outliers:

- **MIN_OBS_SUGGEST = 3**: Au moins 3 observations avant suggestion
- **MIN_OBS_BYPASS = 10**: Au moins 10 observations avant bypass

Cela garantit que les décisions sont basées sur des échantillons statistiquement significatifs.

---

## Stockage Redis

### Structure Hash

Chaque pattern est stocké comme un Hash Redis:

```
Key: plan:patterns:get_contacts→send_email

Fields:
  s: "15"              # successes (int as string)
  f: "2"               # failures (int as string)
  d: "contacts,emails" # domains (sorted, comma-separated)
  i: "mutation"        # intent ("read" | "mutation")
  t: "1736697600"      # last_update (Unix timestamp)
```

### Avantages de cette Structure

1. **Atomicité**: `HINCRBY` pour updates atomiques sans race conditions
2. **Compacité**: Noms de champs courts (s, f, d, i, t)
3. **Requêtes efficaces**: `HGETALL` en O(n) où n = nombre de champs (5)
4. **TTL**: Expiration automatique après 30 jours d'inactivité

### Opérations Redis

```python
# Recording (fire-and-forget)
async with redis.pipeline() as pipe:
    pipe.hincrby(key, "s", 1)  # Incrément atomique
    pipe.hsetnx(key, "d", domains)  # Set if not exists
    pipe.hset(key, "t", timestamp)
    pipe.expire(key, 30*24*3600)  # 30 days TTL
    await pipe.execute()

# Lookup (avec timeout strict)
data = await asyncio.wait_for(
    redis.hgetall(key),
    timeout=0.005  # 5ms max
)

# Scan (admin)
async for key in redis.scan_iter("plan:patterns:*"):
    ...
```

### Cache Local

Pour réduire les appels Redis:

```python
# Cache TTL: 1 seconde
if now - self._cache_time < 1.0:
    return self._cache.get(cache_key)

# Invalidation après chaque write
self._cache.clear()
self._cache_time = 0
```

---

## Points d'intégration

### 1. Smart Planner Service (Injection)

```python
# apps/api/src/domains/agents/services/smart_planner_service.py

async def _build_prompt(self, qi: QueryIntelligence, ...) -> str:
    # Récupérer les patterns appris
    learned_patterns = await get_learned_patterns_prompt(
        domains=qi.domains,
        is_mutation=qi.is_mutation_intent,
    )

    return single_domain_prompt(
        ...,
        learned_patterns=learned_patterns,  # Injecté dans le prompt
    )
```

**Résultat dans le prompt**:
```
VALIDATED PATTERNS (high success rate - PREFER these structures):
  1. get_contacts → send_email (92% success, 15 samples)
  2. get_contacts (87% success, 8 samples)
  3. search_contacts → get_contacts (80% success, 5 samples)
```

### 2. Semantic Validator (Bypass)

```python
# apps/api/src/domains/agents/orchestration/semantic_validator.py

async def validate_plan(self, plan: ExecutionPlan, qi: QueryIntelligence) -> ...:
    # Check bypass AVANT validation LLM
    if await can_skip_validation(plan):
        logger.info("validation_bypassed_high_confidence")
        return ValidationResult(is_valid=True, confidence=0.95)

    # Sinon: validation LLM normale
    ...
```

### 3. Semantic Validator Node (Recording)

```python
# apps/api/src/domains/agents/nodes/semantic_validator_node.py

async def semantic_validator_node(state: State) -> State:
    result = await validator.validate_plan(plan, qi)

    # Recording fire-and-forget
    if result.is_valid:
        record_plan_success(plan, qi)
    else:
        record_plan_failure(plan, qi)

    return state
```

### 4. Prompts (Placeholder)

```txt
# smart_planner_prompt.txt / smart_planner_multi_domain_prompt.txt

{learned_patterns}

AVAILABLE TOOLS:
{catalogue}
```

---

## Configuration

### Variables d'Environnement

```bash
# .env / .env.prod

# =============================================================================
# PLAN PATTERN LEARNING
# Apprentissage dynamique des patterns de planification validés
# Réduit les replanifications coûteuses en guidant le planner
# =============================================================================

# Feature flag global
PLAN_PATTERN_LEARNING_ENABLED=true

# Prior Bayésien Beta(alpha, beta) - défini la confiance initiale
# Beta(2,1) = 67% confiance initiale, montée rapide
PLAN_PATTERN_PRIOR_ALPHA=2
PLAN_PATTERN_PRIOR_BETA=1

# Seuils pour SUGGESTION dans le prompt planner
PLAN_PATTERN_MIN_OBS_SUGGEST=3       # Min observations pour suggérer
PLAN_PATTERN_MIN_CONF_SUGGEST=0.75   # Confiance min 75%

# Seuils pour BYPASS de validation LLM
PLAN_PATTERN_MIN_OBS_BYPASS=10       # Min observations pour bypass
PLAN_PATTERN_MIN_CONF_BYPASS=0.90    # Confiance min 90%

# Limites de tokens
PLAN_PATTERN_MAX_SUGGESTIONS=3       # Max patterns injectés (~15 tokens chacun)

# Performance
PLAN_PATTERN_SUGGESTION_TIMEOUT_MS=5 # Timeout strict Redis
PLAN_PATTERN_LOCAL_CACHE_TTL_S=1.0   # Cache local TTL

# Redis
PLAN_PATTERN_REDIS_PREFIX=plan:patterns  # Préfixe des clés
PLAN_PATTERN_REDIS_TTL_DAYS=30           # Expiration patterns inactifs
```

### Pydantic Settings

```python
# apps/api/src/core/config/agents.py

class Settings(BaseSettings):
    # Plan Pattern Learning
    plan_pattern_learning_enabled: bool = True
    plan_pattern_prior_alpha: int = Field(default=2, ge=1, le=10)
    plan_pattern_prior_beta: int = Field(default=1, ge=1, le=10)
    plan_pattern_min_obs_suggest: int = Field(default=3, ge=1, le=100)
    plan_pattern_min_conf_suggest: float = Field(default=0.75, ge=0.5, le=0.99)
    plan_pattern_min_obs_bypass: int = Field(default=10, ge=5, le=100)
    plan_pattern_min_conf_bypass: float = Field(default=0.90, ge=0.80, le=0.99)
    plan_pattern_max_suggestions: int = Field(default=3, ge=1, le=10)
    plan_pattern_suggestion_timeout_ms: int = Field(default=5, ge=1, le=100)
    plan_pattern_local_cache_ttl_s: float = Field(default=1.0, ge=0.1, le=60.0)
    plan_pattern_redis_prefix: str = "plan:patterns"
    plan_pattern_redis_ttl_days: int = Field(default=30, ge=1, le=365)
```

### Tuning Recommandé

| Scénario | Alpha | Beta | Min Obs Suggest | Min Conf Suggest |
|----------|-------|------|-----------------|------------------|
| **Standard** | 2 | 1 | 3 | 0.75 |
| Conservateur | 1 | 1 | 5 | 0.80 |
| Agressif | 3 | 1 | 2 | 0.70 |
| Production haute | 2 | 1 | 5 | 0.80 |

---

## Golden Patterns

> **Version 1.1** : Patterns prédéfinis pour bootstrapper le système avec haute confiance.

### Objectif

Les **Golden Patterns** sont des patterns prédéfinis (50+) injectés au démarrage du système pour :
- Éviter la phase de "cold start" sans historique
- Garantir des suggestions de qualité dès le premier jour
- Établir une confiance initiale de 95%+ sur les patterns communs

### Fichier Source

**Fichier** : `apps/api/src/domains/agents/services/golden_patterns.py`

### API

```python
from src.domains.agents.services.golden_patterns import (
    initialize_golden_patterns,   # Charge 50+ patterns au startup
    reset_all_patterns,           # Reset complet (dev/test uniquement)
)

# Au démarrage de l'application
await initialize_golden_patterns()
```

### Patterns Inclus

| Catégorie | Exemples | Count |
|-----------|----------|-------|
| **Single-domain reads** | search_contacts → response, get_events → response | 12+ |
| **Single-domain mutations** | send_email, create_event, create_contact | 8+ |
| **Multi-domain queries** | calendar+contacts, emails+drive | 15+ |
| **Weather+Location** | weather+places, weather+contacts | 6+ |
| **Search+Details** | search_contacts → get_contact_details | 10+ |

### Confiance Prédéfinie

Chaque Golden Pattern est initialisé avec :
- **20 succès / 0 échecs** → **95.7% confiance**
- Dépasse le seuil de suggestion (75%) dès le premier appel
- Proche du seuil de bypass (90%) après quelques observations

### Intégration Startup

```python
# apps/api/src/main.py (ou lifespan)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize golden patterns at startup
    from src.domains.agents.services.golden_patterns import initialize_golden_patterns
    await initialize_golden_patterns()

    yield  # Application runs

    # Cleanup
```

### Maintenance

```bash
# Réinitialiser tous les patterns (dev uniquement)
task patterns:reset

# Lister les golden patterns
task patterns:list --golden-only
```

> **Note** : Pour plus de détails sur l'implémentation, voir [SMART_SERVICES.md](SMART_SERVICES.md) Section 7.

---

## CLI Maintenance

### Commandes Taskfile

```bash
# Lister tous les patterns
task patterns:list

# Lister uniquement les suggérables (conf >= 75%)
task patterns:list:suggerable

# Lister uniquement ceux pouvant bypass (conf >= 90%)
task patterns:list:bypassable

# Statistiques globales
task patterns:stats

# Détails d'un pattern spécifique
task patterns:show PATTERN="get_contacts→send_email"

# Supprimer un pattern
task patterns:delete PATTERN="get_contacts" CONFIRM=true

# Reset complet (DANGER)
task patterns:reset CONFIRM=true

# Export JSON
task patterns:export OUTPUT=patterns.json

# Import JSON
task patterns:import INPUT=patterns.json CONFIRM=true

# Seeding manuel
task patterns:seed \
  PATTERN="get_contacts→send_email" \
  DOMAINS="contacts,emails" \
  INTENT="mutation" \
  SUCCESSES=10 \
  FAILURES=1
```

### Exemple de Sortie

```
$ task patterns:list

Pattern Key                              S/F      Conf         Domains              Intent
------------------------------------------------------------------------------------------
get_contacts→send_email                  15/2     88% [SUGGEST] contacts,emails     mutation
get_events                               12/0     93% [BYPASS]  calendar            read
search_contacts                          8/1      82% [SUGGEST] contacts            read
get_contacts→create_event                5/0      83% [SUGGEST] contacts,calendar   mutation
------------------------------------------------------------------------------------------
Total: 4 patterns

$ task patterns:stats

==================================================
Plan Pattern Learner - Statistics
==================================================

  Total patterns:       4
  Suggerable patterns:  3
  Bypassable patterns:  1

  Total observations:   43
  Total successes:      40
  Total failures:       3

  Global success rate:  93.0%
  Avg confidence:       86.5%

  Status: 1 patterns can bypass validation!
```

---

## API Reference

### Fonctions Publiques

```python
from src.domains.agents.services.plan_pattern_learner import (
    # Recording (fire-and-forget)
    record_plan_success,
    record_plan_failure,
    # Prompt injection
    get_learned_patterns_prompt,
    # Validation bypass
    can_skip_validation,
    # Service direct
    get_pattern_learner,
)
```

#### `record_plan_success(plan, qi)`

```python
def record_plan_success(plan: ExecutionPlan, qi: QueryIntelligence) -> None:
    """
    Enregistre un succès de validation. Fire-and-forget.

    Args:
        plan: Plan validé avec succès
        qi: QueryIntelligence avec domains et intent

    Notes:
        - Retourne immédiatement (< 1ms)
        - Enregistrement async en background
        - Silently fails si Redis indisponible
    """
```

#### `record_plan_failure(plan, qi)`

```python
def record_plan_failure(plan: ExecutionPlan, qi: QueryIntelligence) -> None:
    """
    Enregistre un échec de validation. Fire-and-forget.

    Comportement identique à record_plan_success.
    """
```

#### `get_learned_patterns_prompt(domains, is_mutation)`

```python
async def get_learned_patterns_prompt(
    domains: list[str],
    is_mutation: bool,
) -> str:
    """
    Retourne la section formatée pour injection dans le prompt.

    Args:
        domains: Domaines de la requête (exact match)
        is_mutation: True si intent mutation

    Returns:
        str: Section formatée ou "" si aucun pattern

    Example:
        >>> await get_learned_patterns_prompt(["contacts", "emails"], True)
        "VALIDATED PATTERNS (high success rate - PREFER these structures):
          1. get_contacts → send_email (92% success, 15 samples)"

    Notes:
        - Max 3 patterns retournés (~45 tokens)
        - Timeout 5ms, retourne "" si timeout
        - Exact domain match requis
    """
```

#### `can_skip_validation(plan)`

```python
async def can_skip_validation(plan: ExecutionPlan) -> bool:
    """
    Vérifie si le pattern permet de bypasser la validation LLM.

    Args:
        plan: Plan à vérifier

    Returns:
        True si confidence >= 90% ET observations >= 10

    Example:
        >>> if await can_skip_validation(plan):
        ...     return ValidationResult(is_valid=True)

    Notes:
        - Timeout 5ms, retourne False si timeout
        - Log info si bypass activé
    """
```

### Classe PlanPatternLearner

```python
class PlanPatternLearner:
    """Service complet pour usage avancé."""

    # Recording
    def record_success(plan, qi) -> None
    def record_failure(plan, qi) -> None

    # Suggestions
    async def get_suggestions(domains, is_mutation) -> list[PatternStats]
    async def get_prompt_section(domains, is_mutation) -> str

    # Validation bypass
    async def should_bypass_validation(plan) -> bool

    # Admin
    async def list_all_patterns() -> list[PatternStats]
    async def get_pattern(key) -> PatternStats | None
    async def delete_pattern(key) -> bool
    async def delete_all_patterns() -> int
    async def seed_pattern(key, domains, intent, successes, failures) -> bool
    async def get_stats_summary() -> dict

    # Helpers
    @staticmethod
    def make_pattern_key(plan) -> str  # "get_contacts→send_email"
```

---

## Performance

### Latence Garantie

| Opération | Target | Mécanisme |
|-----------|--------|-----------|
| Recording | < 1ms | Fire-and-forget async |
| Suggestion | < 5ms | Timeout strict + cache local |
| Bypass check | < 5ms | Timeout strict |
| Cache local | 1s TTL | Évite Redis répétitifs |

### Consommation Tokens

| Élément | Tokens |
|---------|--------|
| 1 pattern suggéré | ~15 tokens |
| 3 patterns (max) | ~45 tokens |
| Header section | ~10 tokens |
| **Total max** | **~55 tokens** |

Comparé à un replan évité: **~2300 tokens économisés**.

### Scalabilité Redis

| Métrique | Valeur Typique |
|----------|----------------|
| Patterns stockés | < 100 |
| Taille par pattern | ~50 bytes |
| Total Redis | < 5 KB |
| Scan time | < 2ms |

---

## Monitoring & Observabilité

### Logs Structurés

```python
# Success recording
logger.debug("pattern_recorded", pattern="get_contacts→send_email", success=True, domains="contacts,emails", intent="mutation")

# Bypass activé
logger.info("pattern_bypass_validation", pattern="get_contacts→send_email", confidence=0.92, total=15)

# Erreurs (silencieuses, debug niveau)
logger.debug("pattern_recording_failed", error="Redis timeout", pattern="...")
logger.debug("pattern_suggestion_timeout")
```

### Métriques Prometheus

```python
# Compteurs suggérés
pattern_suggestions_total{domains, intent}
pattern_bypass_total{pattern}
pattern_recording_total{success}

# Latence
pattern_suggestion_latency_ms{quantile}
pattern_bypass_check_latency_ms{quantile}
```

### Dashboard Grafana

```
┌─────────────────────────────────────────────────────────────────┐
│                    PLAN PATTERN LEARNER                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Total Patterns: 47    Suggerable: 32    Bypassable: 8          │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ Global Success  │  │ Bypass Rate     │  │ Tokens Saved    │  │
│  │     93.2%       │  │     12.4%       │  │   18,400/day    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                                                                  │
│  Confidence Distribution:                                        │
│  ██████████████████████████░░░░░░ 67-75%: 15 patterns           │
│  ████████████████████░░░░░░░░░░░░ 75-90%: 24 patterns           │
│  ████████░░░░░░░░░░░░░░░░░░░░░░░░ 90%+:   8 patterns            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Pattern non suggéré

**Symptôme**: Un pattern attendu n'apparaît pas dans les suggestions.

**Vérifications**:
```bash
# 1. Vérifier existence
task patterns:show PATTERN="get_contacts→send_email"

# 2. Vérifier seuils
# total >= 3 ?
# confidence >= 75% ?

# 3. Vérifier domaines (EXACT MATCH)
# Requête: ["contacts", "emails"]
# Pattern doit avoir exactement: ["contacts", "emails"]
# Pattern ["contacts"] ne matchera PAS

# 4. Vérifier intent
# Requête: is_mutation=True
# Pattern doit avoir intent="mutation"
```

### Bypass non déclenché

**Symptôme**: Pattern à 90%+ mais validation LLM toujours exécutée.

**Vérifications**:
```bash
# 1. Vérifier observations
task patterns:show PATTERN="..."
# total >= 10 requis

# 2. Vérifier feature flag
grep PLAN_PATTERN_LEARNING_ENABLED .env

# 3. Vérifier logs
# Chercher "validation_bypassed_high_confidence"
```

### Redis indisponible

**Symptôme**: Aucun pattern stocké/récupéré.

**Comportement attendu**:
- Recording: silently fails, log debug
- Suggestions: retourne []
- Bypass: retourne False
- **Le système continue à fonctionner normalement**

**Vérification**:
```bash
redis-cli PING
redis-cli KEYS "plan:patterns:*"
```

### Reset en production

**Procédure de reset contrôlé**:

```bash
# 1. Export backup
task patterns:export OUTPUT=backup_$(date +%Y%m%d).json

# 2. Reset
task patterns:reset CONFIRM=true

# 3. Optionnel: seed patterns connus
task patterns:seed PATTERN="get_events" DOMAINS="calendar" INTENT="read" SUCCESSES=10
```

---

## Related Documentation

- [PLANNER.md](PLANNER.md) - Documentation du Planner Node
- [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md) - Routing sémantique
- [OBSERVABILITY_AGENTS.md](OBSERVABILITY_AGENTS.md) - Métriques et monitoring
- [GUIDE_PERFORMANCE_TUNING.md](../guides/GUIDE_PERFORMANCE_TUNING.md) - Optimisation performance
