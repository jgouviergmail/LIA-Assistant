# Smart Services - Architecture v3

> **Version**: 1.2 (Architecture v3 - Text Compaction + Semantic Expansion)
> **Date**: 2026-01-22
> **Fichiers**:
> - [query_analyzer_service.py](../../apps/api/src/domains/agents/services/query_analyzer_service.py)
> - [smart_planner_service.py](../../apps/api/src/domains/agents/services/smart_planner_service.py)
> - [smart_catalogue_service.py](../../apps/api/src/domains/agents/services/smart_catalogue_service.py)
> - [text_compaction.py](../../apps/api/src/domains/agents/orchestration/text_compaction.py)

## Vue d'ensemble

Les **Smart Services** constituent le coeur de l'Architecture v3 de LIA. Ils externalisent l'intelligence des nodes LangGraph pour permettre :

1. **Separation of Concerns** : Nodes simples (~80 lignes) + Services intelligents
2. **Token Efficiency** : 89% d'economie vs architecture legacy
3. **Resilience** : PANIC MODE pour retry automatique

```
┌─────────────────────────────────────────────────────────────────┐
│                    Architecture v3 Smart Services               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Query ───> QueryAnalyzerService ───> QueryIntelligence         │
│                    │                        │                   │
│                    │ analyze_full()         │ route_to          │
│                    v                        v                   │
│            SmartCatalogueService     ┌─────────────┐            │
│                    │                 │  planner    │            │
│                    │ filter()        │  response   │            │
│                    v                 └─────────────┘            │
│            SmartPlannerService                                  │
│                    │                                            │
│                    │ plan()                                     │
│                    v                                            │
│              ExecutionPlan ───> Orchestration                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. QueryAnalyzerService

> **Fichier**: [query_analyzer_service.py:362](../../apps/api/src/domains/agents/services/query_analyzer_service.py#L362)
> **Performance Target**: P95 < 800ms

### Responsabilite

Service unifie combinant (anciennement 2 services separes) :

- **LLM Intent/Domain Detection** : Detection intent + domaines via LLM
- **Context Resolution** : Resolution des references contextuelles
- **User Goal Inference** : Inference du but utilisateur (pattern matching)
- **Routing Decision** : Decision planner vs response

### API Principale

```python
from src.domains.agents.services.query_analyzer_service import (
    get_query_analyzer_service,
)

analyzer = get_query_analyzer_service()
intelligence = await analyzer.analyze_full(
    query="Quel temps fait-il chez mon frere ?",
    messages=messages,
    state=state,
    config=config,
)
# intelligence.route_to = "planner"
# intelligence.domains = ["weather", "contacts"]
```

### Flow de `analyze_full()`

```
1. Memory Facts Retrieval (if enabled)
         │
         v
2. Memory Reference Resolution (MemoryReferenceResolutionService)
         │ "ma femme" → "marie dupond"
         v
3. LLM Analysis (single call)
         │ intent, domains, confidence, english_query
         v
4. Semantic Domain Expansion (if person reference)
         │ routes → routes + contacts (for address)
         v
5. Chat Override (if conversation intent + high confidence)
         │ Clear domains → route to response
         v
6. Context Resolution (ContextResolutionService)
         │ "le premier" → resolved item
         v
7. User Goal Inference (fast pattern matching)
         │ UserGoal enum
         v
8. Routing Decision
         │ "planner" | "response"
         v
9. Return QueryIntelligence
```

### QueryIntelligence Output

```python
@dataclass
class QueryIntelligence:
    # Query processing
    original_query: str
    english_query: str
    english_enriched_query: str | None  # With resolved names

    # Intent
    immediate_intent: str  # search, create, update, delete, send, chat
    immediate_confidence: float
    user_goal: UserGoal

    # Domains
    domains: list[str]
    primary_domain: str
    domain_scores: dict[str, float]

    # Context
    turn_type: str  # ACTION, REFERENCE_PURE, REFERENCE_ACTION
    resolved_context: ResolvedContext | None
    resolved_references: dict[str, str] | None

    # Routing
    route_to: str  # "planner" | "response"
    confidence: float
    bypass_llm: bool

    # Validation hints (LLM-detected)
    is_mutation_intent: bool  # create/update/delete/send
    has_cardinality_risk: bool  # "all/every/each"
    is_app_help_query: bool  # Detected by LLM when user asks about the app itself. Used by RoutingDecider Rule 0.
```

### Thresholds de Routing

| Threshold | Valeur | Usage |
|-----------|--------|-------|
| `chat_override_threshold` | 0.85 | Si conversation intent + confidence >= threshold → route response |
| `chat_semantic_threshold` | 0.5 | Si chat intent + semantic_score < threshold → route response |
| `high_semantic_threshold` | 0.8 | Si semantic_score >= threshold → route planner |
| `min_confidence` | 0.6 | Confidence minimale pour planner |

### Mecanismes Intelligents

Le service expose `intelligent_mechanisms` dans QueryIntelligence pour le debug panel :

```python
intelligent_mechanisms = {
    "llm_query_analysis": {
        "applied": True,
        "intent": "action",
        "mapped_intent": "search",
        "primary_domain": "contacts",
        "confidence": 0.92,
    },
    "memory_resolution_service": {
        "applied": True,
        "mappings": {"ma femme": "marie dupond"},
    },
    "semantic_expansion": {
        "applied": True,
        "added_domains": ["contacts"],
        "reasons": ["contacts provides email_address for person reference"],
    },
    "chat_override": {
        "applied": False,
    },
}
```

---

## 2. SmartPlannerService

> **Fichier**: [smart_planner_service.py:65](../../apps/api/src/domains/agents/services/smart_planner_service.py#L65)
> **Token Efficiency**: 89% savings vs legacy

### Differences avec HierarchicalPlannerService (Legacy)

| Aspect | Legacy (HierarchicalPlanner) | v3 (SmartPlanner) |
|--------|------------------------------|-------------------|
| LLM Calls | 3 stages | 1 single call |
| Catalogue | Full (~14,100 tokens) | Filtered (~1,500 tokens) |
| Multi-domain | Templates pre-definis | Generative planning |
| Failure handling | N/A | PANIC MODE retry |

### Token Efficiency

```
Legacy:
  Stage1 (catalogue selection):  1,600 tokens
  Stage2 (full catalogue):      12,000 tokens
  Stage3 (validation):             500 tokens
  TOTAL:                        14,100 tokens

SmartPlanner:
  Single call + filtered catalogue: ~1,500 tokens

SAVINGS: 89%
```

### API Principale

```python
from src.domains.agents.services.smart_planner_service import (
    get_smart_planner_service,
)

planner = get_smart_planner_service()
result = await planner.plan(
    intelligence=intelligence,
    config=config,
    validation_feedback=None,  # Optional feedback from semantic validator
)

if result.success:
    plan = result.plan
    # plan.steps[0].tool_name = "get_contacts_tool"
```

### Flow de `plan()`

```
STEP 0: FAST PATH - Reference Bypass
         │ REFERENCE_PURE + search intent + resolved context
         │ → Direct plan without LLM
         v
STEP 0b: Cross-Domain Bypass
         │ REFERENCE_ACTION + mappable field
         │ "restaurant de ce rdv" → search_places(location)
         v
STEP 1: Filter Catalogue
         │ SmartCatalogueService.filter_for_intelligence()
         v
STEP 2: Generate Plan
         │ Single domain: _plan_single_domain()
         │ Multi domain: _plan_multi_domain() (generative)
         v
STEP 3: PANIC MODE (if failure)
         │ Retry with expanded catalogue (all tools)
         v
Return PlanningResult
```

### PANIC MODE

```
Normal Flow:
  Filtered catalogue (~200 tokens per domain)
         │
         v
  LLM Planning
         │
         v
  FAILURE? ──yes──> PANIC MODE
         │                │
         no               v
         │         Expanded catalogue (all tools)
         v                │
  Return Plan             v
                    LLM Planning (retry)
                          │
                          v
                    Return Plan (or final failure)
```

**Important**: PANIC MODE is ONE-TIME ONLY per request (prevents infinite loops).

### Reference Bypass

Pour les requetes avec contexte resolu (ex: "detail du premier"), le planner bypasse le LLM :

```python
# Conditions for bypass:
# 1. turn_type == "REFERENCE_PURE"
# 2. intent == "search" (unified)
# 3. resolved_context has items with valid IDs
# 4. source_domain supported (contacts, emails, calendar, etc.)
# 5. NOT cross-domain

# Direct plan generation:
ExecutionStep(
    tool_name="get_contacts_tool",  # Based on domain
    parameters={"resource_name": "people/123456"},  # From resolved item
)
```

### Cross-Domain Bypass

Pour les requetes cross-domain simples avec champ mappable :

```python
# "recherche le restaurant de ce rendez-vous"
# → resolved_context = calendar event with location="Restaurant La Table"
# → primary_domain = places

# Mapping:
CROSS_DOMAIN_MAPPINGS = {
    "location": ("places", "get_places_tool", "query"),
    "address": ("places", "get_places_tool", "query"),
}

# Direct plan:
ExecutionStep(
    tool_name="get_places_tool",
    parameters={"query": "Restaurant La Table"},
)
```

### Insufficient Content Detection (Early HITL)

Pour les requetes avec parametres obligatoires manquants (ex: email sans subject), le planner declenche une clarification AVANT d'appeler le LLM :

```python
# Dans SmartPlannerService.plan()
early_detection = await self.detect_early_insufficient_content(
    intelligence=intelligence,
    config=config,
)

if early_detection and early_detection.requires_clarification:
    # Return SemanticValidationResult avec clarification needed
    # → Route to clarification_node SANS appel LLM
    return PlanningResult(
        plan=None,
        success=False,
        error="insufficient_content",
        semantic_validation=early_detection,
    )
```

**Conditions de detection** :

| Domaine | Intent | Champs Verifies |
|---------|--------|-----------------|
| emails | send/create | to, subject, body |
| calendar | create | title, start_time |

**Flow Multi-Turn** :

```
Turn 1: "envoie un email a ma femme"
        → Reference resolved: "ma femme" → "Marie Dupont"
        → Email resolved: "Marie Dupont" → "marie@example.com" (via resolve_contact_to_email)
        → Missing: subject, body
        → clarification_field: "subject"
        → Ask: "Quel est le sujet de l'email?"

Turn 2: "pour son anniversaire"
        → clarification_response: "pour son anniversaire"
        → clarification_field was: "subject"
        → Inject into plan context as subject
        → Missing: body
        → clarification_field: "body"
        → Ask: "Quel est le contenu de l'email?"

Turn 3: "Joyeux anniversaire mon amour"
        → clarification_response: "Joyeux anniversaire mon amour"
        → clarification_field was: "body"
        → All params complete
        → Generate ExecutionPlan → Execute
```

**Clarification Field Tracking** :

```python
# State key pour tracker quel champ a ete demande
STATE_KEY_CLARIFICATION_FIELD = "clarification_field"

# Dans semantic_validation result:
{
    "requires_clarification": True,
    "clarification_questions": ["Quel est le sujet?"],
    "clarification_field": "subject",  # <- Field being asked
    "issues": ["missing_parameter"],
}

# Apres clarification_node, dans state:
{
    "clarification_response": "pour son anniversaire",
    "clarification_field": "subject",  # Field that was answered
    "needs_replan": True,
}
```

**Integration avec resolve_contact_to_email** :

Le helper `resolve_contact_to_email` (runtime_helpers.py) permet de resoudre un nom de contact vers une adresse email via Google Contacts API avant d'evaluer si 'to' est manquant :

```python
# Dans detect_early_insufficient_content()
if "emails" in intelligence.domains:
    recipient = intelligence.resolved_references.get("recipient")
    if recipient:
        # Resolve via Google Contacts API
        email = await resolve_contact_to_email(runtime, recipient)
        if email:
            # 'to' is resolved, check next param
            ...
        else:
            # Cannot resolve → ask for email
            return _build_clarification_result(
                field="to",
                question="Je n'ai pas trouve d'email pour ce contact."
            )
```

---

### PlanningResult

```python
@dataclass
class PlanningResult:
    plan: ExecutionPlan | None
    success: bool
    error: str | None = None
    tokens_used: int = 0
    tokens_saved: int = 0  # vs full catalogue
    used_template: bool = False  # Bypass used
    used_panic_mode: bool = False
    used_generative: bool = False  # Multi-domain generative
    filtered_catalogue: FilteredCatalogue | None = None  # For debug panel
```

---

## 3. SmartCatalogueService

> **Fichier**: [smart_catalogue_service.py:72](../../apps/api/src/domains/agents/services/smart_catalogue_service.py#L72)
> **Token Reduction**: 96% for filtered vs full

### Principe

**Inject ONLY the tools that are needed.**

```
FULL contacts catalogue:     ~5,500 tokens
FILTERED (search only):        ~200 tokens
REDUCTION: 96%
```

### Strategies de Filtrage

1. **By INTENT** : search → get_* tools, create → create_* tools
2. **By DOMAIN** : contacts, emails, calendar, etc.
3. **By CONTEXT** : context tools si reference turn

### API Principale

```python
from src.domains.agents.services.smart_catalogue_service import (
    get_smart_catalogue_service,
)

service = get_smart_catalogue_service()

# Normal filtering
filtered = service.filter_for_intelligence(intelligence)
# filtered.tool_count = 3
# filtered.token_estimate = 450

# PANIC MODE (expanded)
expanded = service.filter_for_intelligence(intelligence, panic_mode=True)
# expanded.tool_count = 15
# expanded.categories_included = ["ALL_PANIC_MODE"]
```

### FilteredCatalogue

```python
@dataclass
class FilteredCatalogue:
    tools: list[dict[str, Any]]
    tool_count: int
    token_estimate: int
    domains_included: list[str]
    categories_included: list[str]
    is_panic_mode: bool = False

    def to_prompt_string(self) -> str:
        """Format for LLM prompt injection."""
        return json.dumps(self.tools, indent=2)
```

### Token Estimates par Categorie

| Category | Tokens |
|----------|--------|
| search | 200 |
| create | 400 |
| update | 350 |
| delete | 150 |
| send | 450 |
| utility | 100 |

### PANIC MODE Catalogue

```python
# Normal: filtered by intent + categories
ToolFilter(
    domains=["contacts"],
    categories=["search"],
    max_tools=5,
)

# PANIC MODE: all tools for domains
ToolFilter(
    domains=["contacts"],
    categories=[],  # Empty = ALL categories
    max_tools=15,   # Higher limit
    include_context_tools=True,
)
```

### Compact Manifest Format

Le service convertit les manifests en format compact pour economiser des tokens :

```python
# OLD FORMAT (~900 tokens per tool):
{
    "name": "get_contacts_tool",
    "description": "...",
    "parameters": [
        {"name": "...", "type": "...", "required": True, "description": "..."},
        ...
    ],
    "outputs": [
        {"path": "...", "type": "...", "description": "...", "semantic_type": "..."},
        ...
    ],
    "reference_examples": ["...", "..."],
}

# NEW COMPACT FORMAT (~200 tokens per tool):
{
    "name": "get_contacts_tool",
    "description": "...",
    "parameters": [
        {"name": "...", "type": "...", "required": True},  # description only if required
    ],
    "outputs": ["result[*].email:string:email_address"],  # Compact "path:type:semantic"
    # No reference_examples (LLM infers from outputs)
}
```

---

## Integration avec les Nodes

### router_node_v3.py

```python
async def router_node_v3(state: AgentState, config: RunnableConfig):
    analyzer = get_query_analyzer_service()
    intelligence = await analyzer.analyze_full(
        query=state["input"],
        messages=state["messages"],
        state=state,
        config=config,
    )

    # Route based on intelligence
    return {
        "next": intelligence.route_to,  # "planner" | "response"
        "query_intelligence": intelligence,
    }
```

### planner_node_v3.py

```python
async def planner_node_v3(state: AgentState, config: RunnableConfig):
    planner = get_smart_planner_service()
    result = await planner.plan(
        intelligence=state["query_intelligence"],
        config=config,
    )

    if result.success:
        return {"execution_plan": result.plan}
    else:
        # Fallback to response node
        return {"next": "response", "error": result.error}
```

---

## Metriques et Observabilite

### Logs Structures

```python
# QueryAnalyzerService
logger.info(
    "query_analysis_complete",
    query_preview=query[:50],
    intent=result.intent,
    primary_domain=result.primary_domain,
    confidence=round(result.confidence, 2),
    is_mutation_intent=result.is_mutation_intent,
)

# SmartPlannerService
logger.info(
    "smart_planner_start",
    domains=intelligence.domains,
    intent=intelligence.immediate_intent,
    tools_count=filtered.tool_count,
    token_estimate=filtered.token_estimate,
)

# SmartCatalogueService
logger.debug(
    "catalogue_filtered",
    original=len(all_manifests),
    filtered=len(filtered_tools),
    tokens_saved=self._metrics.tokens_saved,
)
```

### Prometheus Metrics

```python
# Token savings (Grafana dashboard)
smart_planner_tokens_saved_total
smart_planner_panic_mode_count
catalogue_filter_reduction_ratio
```

---

## 4. PlanPatternLearner

> **Fichier**: [plan_pattern_learner.py](../../apps/api/src/domains/agents/services/plan_pattern_learner.py)
> **Date creation**: 2026-01-12

### Objectif

Service d'**apprentissage dynamique** des patterns de planification qui :

1. **Apprend** des succes/echecs de validation pour guider le planner
2. **Reduit** les replanifications couteuses
3. **Optimise** la latence via bypass de validation pour patterns connus

### Architecture

```
Success/Failure Feedback
        │
        v
┌─────────────────────────────────────────────────────────────────┐
│                   PlanPatternLearner                            │
├─────────────────────────────────────────────────────────────────┤
│  • Bayesian confidence: Beta(α=2, β=1) prior                    │
│  • Fire-and-forget async (zero impact latence)                  │
│  • Redis partage cross-users (apprentissage global)             │
│  • Anonymisation stricte (seule sequence d'outils stockee)      │
└─────────────────────────────────────────────────────────────────┘
        │
        v
   Suggestions pour Planner  /  Bypass validation si haute confiance
```

### API Principale

```python
from src.domains.agents.services.plan_pattern_learner import (
    record_plan_success,
    record_plan_failure,
    get_learned_patterns_prompt,
    can_skip_validation,
)

# Apres validation semantique
if is_valid:
    record_plan_success(plan, query_intelligence)  # Fire-and-forget
else:
    record_plan_failure(plan, query_intelligence)

# Injection dans prompt planner
learned = await get_learned_patterns_prompt(
    domains=intelligence.domains,
    is_mutation=intelligence.is_mutation_intent,
)

# Bypass validation LLM si haute confiance
if await can_skip_validation(plan):
    return plan  # Skip semantic validation
```

### Variables .env - PlanPatternLearner

| Variable | Default | Description |
|----------|---------|-------------|
| `PLAN_PATTERN_LEARNING_ENABLED` | true | Active l'apprentissage des patterns |
| `PLAN_PATTERN_PRIOR_ALPHA` | 2 | Bayesian prior alpha (Beta(2,1) = 67% initial) |
| `PLAN_PATTERN_PRIOR_BETA` | 1 | Bayesian prior beta |
| `PLAN_PATTERN_MIN_OBS_SUGGEST` | 3 | Min observations pour suggestion (K-anonymity) |
| `PLAN_PATTERN_MIN_CONF_SUGGEST` | 0.75 | Min confidence pour suggestion |
| `PLAN_PATTERN_MIN_OBS_BYPASS` | 10 | Min observations pour bypass validation |
| `PLAN_PATTERN_MIN_CONF_BYPASS` | 0.90 | Min confidence pour bypass |
| `PLAN_PATTERN_MAX_SUGGESTIONS` | 3 | Max patterns injectes dans prompt |
| `PLAN_PATTERN_SUGGESTION_TIMEOUT_MS` | 5 | Timeout Redis lookup (fail-open) |
| `PLAN_PATTERN_LOCAL_CACHE_TTL_S` | 1.0 | TTL cache local (reduire appels Redis) |
| `PLAN_PATTERN_REDIS_PREFIX` | plan:patterns | Prefix cles Redis |
| `PLAN_PATTERN_REDIS_TTL_DAYS` | 30 | TTL expiration patterns (jours) |

### Seuils de Decision (Resume)

| Seuil | Valeur | Usage |
|-------|--------|-------|
| `MIN_OBSERVATIONS_SUGGEST` | 3 | Minimum pour suggerer un pattern |
| `MIN_CONFIDENCE_SUGGEST` | 0.75 | Seuil pour inclusion dans prompt |
| `MIN_OBSERVATIONS_BYPASS` | 10 | Minimum pour bypass validation |
| `MIN_CONFIDENCE_BYPASS` | 0.90 | Seuil bypass (tres haute confiance) |

### Pattern Storage (Redis)

```python
# Cle Redis
key = f"plan:patterns:{pattern_hash}"

# Valeur
{
    "key": "get_contacts→send_email",
    "successes": 15,
    "failures": 2,
    "domains": ["contacts", "emails"],
    "intent": "mutation",
    "last_update": 1736640000
}

# TTL: 30 jours
```

### Integration avec SmartPlannerService

Le `PlanPatternLearner` est appele dans `_build_prompt()` et `_build_multi_domain_prompt()` :

```python
# Dans SmartPlannerService._build_prompt()
learned_patterns = await get_learned_patterns_prompt(
    domains=intelligence.domains,
    is_mutation=intelligence.is_mutation_intent,
)

# Injection dans le prompt
prompt = self._format_prompt(
    ...
    learned_patterns=learned_patterns,  # "PREFERRED: get_contacts→filter"
)
```

### Metriques

```python
# Pattern learning
plan_pattern_suggestions_total      # Suggestions faites
plan_pattern_bypass_total           # Validations bypasses
plan_pattern_confidence_histogram   # Distribution confiances
```

---

## Configuration

> **Fichier**: [agents.py](../../apps/api/src/core/config/agents.py)
> **Type**: Pydantic Settings avec validation

L'Architecture v3 expose **toutes ses configurations** via variables d'environnement `.env`.
Les valeurs par defaut sont definies dans `constants.py` et peuvent etre surchargees.

### Modeles de Configuration V3

Six modeles Pydantic typesafe organisent la configuration :

| Modele | Usage | Factory Function |
|--------|-------|------------------|
| `V3RoutingConfig` | QueryAnalyzerService - seuils routing | `get_v3_routing_config()` |
| `V3ExecutorConfig` | AutonomousExecutor - circuit breaker | `get_v3_executor_config()` |
| `V3RelevanceConfig` | RelevanceEngine - ranking | `get_v3_relevance_config()` |
| `V3FeedbackLoopConfig` | FeedbackLoopService - learning | `get_v3_feedback_loop_config()` |
| `V3DisplayConfig` | Formatage reponses | `get_v3_display_config()` |
| `V3PromptConfig` | Versions prompts v3 | `get_v3_prompt_config()` |

### Variables .env - QueryAnalyzerService LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `QUERY_ANALYZER_LLM_PROVIDER` | openai | Provider LLM pour analyse intent/domain |
| `QUERY_ANALYZER_LLM_MODEL` | gpt-4.1-mini | Modele LLM (fast, cheap) |
| `QUERY_ANALYZER_LLM_TEMPERATURE` | 0.0 | Temperature (0 = deterministic) |
| `QUERY_ANALYZER_LLM_TOP_P` | 1.0 | Top-p sampling |
| `QUERY_ANALYZER_LLM_FREQUENCY_PENALTY` | 0.0 | Penalite frequence |
| `QUERY_ANALYZER_LLM_PRESENCE_PENALTY` | 0.0 | Penalite presence |
| `QUERY_ANALYZER_LLM_MAX_TOKENS` | 500 | Max tokens reponse |
| `QUERY_ANALYZER_LLM_REASONING_EFFORT` | (empty) | Effort raisonnement (o-series, optionnel) |

### Variables .env - V3 Routing (QueryAnalyzerService)

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_ROUTING_CHAT_SEMANTIC_THRESHOLD` | 0.4 | Score seuil sous lequel la requete route vers chat |
| `V3_ROUTING_HIGH_SEMANTIC_THRESHOLD` | 0.7 | Score seuil au-dessus duquel la requete route vers planner |
| `V3_ROUTING_MIN_CONFIDENCE` | 0.6 | Confidence minimale pour route planner |
| `V3_ROUTING_CHAT_OVERRIDE_THRESHOLD` | 0.85 | Si intent=chat + confidence>=seuil → force response (evite false-positive domains) |
| `V3_ROUTING_CROSS_DOMAIN_THRESHOLD` | 0.5 | Seuil detection references cross-domain |

### Variables .env - V3 Domain Selection

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_DOMAIN_SCORE_DELTA_MIN` | 0.05 | Delta minimum entre top domain et secondaires |
| `V3_DOMAIN_SECONDARY_THRESHOLD` | 0.80 | Score minimum absolu pour domaines secondaires |
| `V3_DOMAIN_SOFTMAX_TEMPERATURE` | 0.1 | Temperature softmax pour calibration scores |
| `V3_DOMAIN_MIN_RANGE_FOR_DISCRIMINATION` | 0.03 | Range minimale pour discrimination significative |
| `V3_DOMAIN_CALIBRATED_PRIMARY_MIN` | 0.15 | Score calibre minimum pour domaine primaire |
| `V3_DOMAIN_CALIBRATED_SECONDARY_RATIO` | 0.25 | Ratio score secondaire vs primaire |

### Variables .env - V3 Tool Selection

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_TOOL_SOFTMAX_TEMPERATURE` | 0.1 | Temperature softmax pour calibration scores outils |
| `V3_TOOL_CALIBRATED_PRIMARY_MIN` | 0.15 | Score calibre minimum pour outil primaire |
| `V3_TOOL_CALIBRATED_SECONDARY_RATIO` | 0.25 | Ratio score secondaire vs primaire |

### Variables .env - V3 Executor (Circuit Breaker)

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_EXECUTOR_MAX_RECOVERY_PER_STEP` | 3 | Max tentatives recovery par step |
| `V3_EXECUTOR_MAX_TOTAL_RECOVERIES` | 5 | Max recovery total sur le plan |
| `V3_EXECUTOR_RECOVERY_TIMEOUT_MS` | 30000 | Timeout global recovery (ms) |
| `V3_EXECUTOR_CIRCUIT_BREAKER_THRESHOLD` | 3 | Apres N echecs consecutifs → stop |

### Variables .env - V3 Relevance Engine

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_RELEVANCE_PRIMARY_THRESHOLD` | 0.7 | Seuil resultats haute pertinence |
| `V3_RELEVANCE_MINIMUM_THRESHOLD` | 0.3 | Seuil minimum (sous = filtre) |

### Variables .env - V3 Feedback Loop

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_FEEDBACK_LOOP_MAX_RECORDS` | 1000 | Max enregistrements patterns en memoire |
| `V3_FEEDBACK_LOOP_MIN_SAMPLES` | 3 | Min samples avant suggestion strategie |
| `V3_FEEDBACK_LOOP_CONFIDENCE_THRESHOLD` | 0.6 | Seuil confidence pour suggestions |

### Variables .env - V3 Display

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_DISPLAY_ENABLED` | true | Active formatage v3 sandwich pattern |
| `V3_DISPLAY_MAX_ITEMS_PER_DOMAIN` | 5 | Max items par domaine dans multi-domain |
| `V3_DISPLAY_VIEWPORT_MOBILE_MAX_WIDTH` | 430 | Largeur max viewport mobile (px) |
| `V3_DISPLAY_SHOW_ACTION_BUTTONS` | true | Affiche boutons action sous cards HTML |

### Variables .env - V3 Prompts

| Variable | Default | Description |
|----------|---------|-------------|
| `V3_ROUTER_PROMPT_VERSION` | "v1" | Version prompt router v3 |
| `V3_SMART_PLANNER_PROMPT_VERSION` | "v1" | Version prompt smart planner |

### Variables .env - Semantic Validator LLM

Le **Semantic Validator** valide semantiquement les plans generes avant execution.
Detecte cardinality mismatches, implicit assumptions, missing dependencies.

| Variable | Default | Description |
|----------|---------|-------------|
| `SEMANTIC_VALIDATION_ENABLED` | true | Active validation semantique |
| `SEMANTIC_VALIDATION_TIMEOUT_SECONDS` | 10.0 | Timeout (fail-open si depasse) |
| `SEMANTIC_VALIDATION_CONFIDENCE_THRESHOLD` | 0.7 | Seuil confidence clarification |
| `SEMANTIC_VALIDATOR_LLM_PROVIDER` | openai | Provider LLM |
| `SEMANTIC_VALIDATOR_LLM_MODEL` | gpt-4.1-mini | Modele LLM |
| `SEMANTIC_VALIDATOR_LLM_TEMPERATURE` | 0.2 | Temperature |
| `SEMANTIC_VALIDATOR_LLM_MAX_TOKENS` | 1000 | Max tokens reponse |
| `SEMANTIC_VALIDATOR_LLM_REASONING_EFFORT` | low | Effort raisonnement (o-series) |

### Exemple .env

```bash
# V3 Architecture - Routing
V3_ROUTING_CHAT_SEMANTIC_THRESHOLD=0.4
V3_ROUTING_HIGH_SEMANTIC_THRESHOLD=0.7
V3_ROUTING_MIN_CONFIDENCE=0.6
V3_ROUTING_CHAT_OVERRIDE_THRESHOLD=0.85
V3_ROUTING_CROSS_DOMAIN_THRESHOLD=0.5

# V3 Architecture - Executor Circuit Breaker
V3_EXECUTOR_MAX_RECOVERY_PER_STEP=3
V3_EXECUTOR_MAX_TOTAL_RECOVERIES=5
V3_EXECUTOR_CIRCUIT_BREAKER_THRESHOLD=3

# V3 Architecture - Display
V3_DISPLAY_ENABLED=true
V3_DISPLAY_MAX_ITEMS_PER_DOMAIN=5
V3_DISPLAY_SHOW_ACTION_BUTTONS=true
```

### Usage Programmatique

```python
from src.core.config.agents import (
    get_v3_routing_config,
    get_v3_executor_config,
    get_v3_display_config,
    get_debug_thresholds,
)

# Configuration routing
routing = get_v3_routing_config()
if score < routing.chat_semantic_threshold:
    return "response"

# Configuration executor
executor = get_v3_executor_config()
if failures >= executor.circuit_breaker_threshold:
    raise CircuitBreakerOpen()

# Debug panel - tous les seuils
thresholds = get_debug_thresholds()
# → {"routing_decision": {...}, "executor": {...}, ...}
```

### constants.py - Token Estimates

```python
# Token estimates for catalogue filtering
V3_CATALOGUE_TOKEN_ESTIMATES = {
    "search": 200,
    "create": 400,
    "update": 350,
    "delete": 150,
    "send": 450,
    "utility": 100,
}

V3_CATALOGUE_DOMAIN_FULL_TOKENS = {
    "contacts": 5500,
    "emails": 4000,
    "calendar": 3500,
    "drive": 2500,
    "tasks": 2000,
    "places": 3000,
    "routes": 1500,
    "weather": 500,
    "wikipedia": 800,
    "perplexity": 600,
}
```

---

## Testing

### Unit Tests

```python
# test_query_analyzer_service.py
async def test_analyze_full_routing_to_planner():
    analyzer = get_query_analyzer_service()
    result = await analyzer.analyze_full(
        query="Recherche mes contacts nommes Jean",
        messages=[],
        state={},
        config={"configurable": {}},
    )
    assert result.route_to == "planner"
    assert "contacts" in result.domains

# test_smart_planner_service.py
async def test_plan_single_domain():
    planner = get_smart_planner_service()
    result = await planner.plan(
        intelligence=mock_intelligence,
        config=mock_config,
    )
    assert result.success
    assert result.tokens_saved > 0

# test_smart_catalogue_service.py
def test_filter_for_intelligence():
    service = get_smart_catalogue_service()
    filtered = service.filter_for_intelligence(mock_intelligence)
    assert filtered.tool_count < 10
    assert filtered.token_estimate < 1000
```

---

## 5. Infrastructure Services (Caching)

Les Smart Services s'appuient sur des services d'infrastructure pour optimiser les performances.

### 5.1 PricingCacheService

> **Fichier**: [pricing_cache.py](../../apps/api/src/infrastructure/cache/pricing_cache.py)

Service de cache Redis pour l'estimation des couts LLM dans les callbacks LangChain (sync-safe).

**Probleme resolu** : Les callbacks LangChain sont synchrones et ne peuvent pas acceder a la DB async.

```python
from src.infrastructure.cache.pricing_cache import (
    get_cached_cost,       # Lecture sync depuis Redis
    refresh_pricing_cache, # Async refresh depuis DB (startup)
)

# Usage dans callback LangChain (sync context)
cost = get_cached_cost("gpt-4.1-mini", input_tokens=1000, output_tokens=500)
```

**Architecture** :
```
DB (LLMModelPricing) → AsyncPricingService → Redis → Sync read in callbacks
                                                ↑
                                           Startup refresh
```

**Data Structure** :
```python
@dataclass
class CachedModelPrice:
    input_price_per_1m: float
    output_price_per_1m: float
    cached_input_price_per_1m: float  # Prompt cache hits
```

**Metrics** : `pricing_cache_fallback_total{reason="cache_not_initialized|model_not_found"}`

---

### 5.2 ConversationIdCache

> **Fichier**: [conversation_cache.py](../../apps/api/src/infrastructure/cache/conversation_cache.py)

Cache Redis pour le mapping `user_id → conversation_id` (optimisation HITL).

```python
from src.infrastructure.cache import (
    get_conversation_id_cached,       # Async get avec fallback DB
    invalidate_conversation_id_cache, # Invalidation manuelle
)

# Usage dans router
conversation_id = await get_conversation_id_cached(user_id)
```

**Performance** :
- Redis Cache (fast path) : ~1ms
- DB fallback : ~20-50ms

**Configuration** :
```bash
CONVERSATION_ID_CACHE_TTL_SECONDS=300  # 5 minutes default
```

**Metrics** : `conversation_id_cache_total{result="hit|miss|error"}`

---

### 5.3 SystemSettingsService

> **Fichier**: [service.py](../../apps/api/src/domains/system_settings/service.py)

Service de gestion des parametres systeme (admin-controlled).

```python
from src.domains.system_settings.service import (
    get_voice_tts_mode,              # Cached get
    SystemSettingsService,           # Admin CRUD
    invalidate_voice_tts_mode_cache, # Cache invalidation
)

# Usage
mode = await get_voice_tts_mode()  # "standard" | "hd"
```

**Architecture** :
```
Admin Request → PostgreSQL → Redis Cache (5min TTL)
                    ↓
             AdminAuditLog entry
```

**Endpoints** (superuser only) :
```bash
GET  /api/v1/admin/system-settings/voice-mode
PUT  /api/v1/admin/system-settings/voice-mode
```

**Voir** : [VOICE.md](./VOICE.md) pour details sur les modes TTS.

---

## 6. Plan Pattern Learning

> **Fichier**: [plan_pattern_learner.py](../../apps/api/src/domains/agents/services/plan_pattern_learner.py)

Systeme d'apprentissage bayesien pour reduire les replanifications.

```python
from src.domains.agents.services.plan_pattern_learner import (
    record_plan_success,         # Fire-and-forget async
    record_plan_failure,
    get_learned_patterns_prompt, # Injection prompt planner
    can_skip_validation,         # Bypass validation si 90%+ confiance
)
```

**Modele Bayesien** : Beta(2,1) prior → 67% confiance initiale

| Seuil | Observations | Confiance | Action |
|-------|--------------|-----------|--------|
| Suggerable | >= 3 | >= 75% | Inject dans prompt planner |
| Bypass | >= 10 | >= 90% | Skip validation LLM |

**Stockage** : Redis hash `plan:patterns:{tool→tool}` avec TTL 30 jours

**Voir** : [PLAN_PATTERN_LEARNER.md](./PLAN_PATTERN_LEARNER.md) pour details.

---

## 7. Golden Patterns

> **Fichier**: [golden_patterns.py](../../apps/api/src/domains/agents/services/golden_patterns.py)

Patterns predéfinis pour initialiser le Plan Pattern Learner.

```python
from src.domains.agents.services.golden_patterns import (
    initialize_golden_patterns,   # Charge 50+ patterns
    reset_all_patterns,           # Reset complet (dev/test)
)
```

**Patterns inclus** :
- Single-domain reads : contacts, emails, events, tasks, weather, places
- Single-domain mutations : send email, create event, create contact
- Multi-domain queries : calendar + contacts, emails + drive

**Confiance predefinie** : 20 succes / 0 echecs → 95.7% confiance

---

## 8. Text Compaction

> **Fichier**: [text_compaction.py](../../apps/api/src/domains/agents/orchestration/text_compaction.py)
> **Version**: 1.0 (Janvier 2026)

### Objectif

Le service **Text Compaction** optimise les tokens envoyés au LLM en compactant les résultats d'exécution avant la synthèse de réponse. Réduction moyenne de **~97% par entité** après évaluation Jinja.

### Principe

```
Tool Results (Jinja Templates)
    │
    v
Évaluation Templates
    │ Contacts: "Jean Dupont (jean@example.com) - Marketing"
    │ Events: "Réunion RH - 2026-01-22 14:00 - Salle A"
    v
Text Compaction
    │ Remove redundant whitespace
    │ Collapse empty lines
    │ Trim per-entity
    v
Compacted Text (97% smaller)
    │
    v
Response LLM
```

### API

```python
from src.domains.agents.orchestration.text_compaction import compact_for_llm

# Compaction de résultats tool
compacted = compact_for_llm(
    text=rendered_template,
    max_chars=8000,  # Limite caractères
    preserve_structure=True  # Garde headers markdown
)
```

### Méthodes Principales

```python
def compact_for_llm(
    text: str,
    max_chars: int = 8000,
    preserve_structure: bool = True
) -> str:
    """
    Compacte un texte pour optimiser les tokens LLM.

    Steps:
    1. Normalise whitespace (multiple spaces → single)
    2. Collapse empty lines (>2 → 2)
    3. Trim lines
    4. Truncate si > max_chars
    5. Preserve structure (headers markdown si enabled)

    Returns:
        Texte compacté
    """
    ...

def compact_tool_results(
    results: dict[str, Any],
    templates: dict[str, str]
) -> str:
    """
    Compacte les résultats de plusieurs tools.

    1. Render chaque template Jinja
    2. Compact chaque résultat
    3. Join avec headers
    """
    ...
```

### Gains Typiques

| Avant Compaction | Après Compaction | Réduction |
|------------------|------------------|-----------|
| Contact (500 chars) | 50 chars | 90% |
| Email (2000 chars) | 200 chars | 90% |
| Event (300 chars) | 80 chars | 73% |
| **Total 10 items** | **~97% reduction** | |

### Intégration Response Node

Le Response Node utilise automatiquement Text Compaction :

```python
# apps/api/src/domains/agents/nodes/response_node.py

async def response_node(state: MessagesState, config: RunnableConfig):
    # ...

    # Compact tool results before LLM synthesis
    if tool_results:
        compacted_results = compact_tool_results(
            results=tool_results,
            templates=get_display_templates()
        )
        # ~97% token reduction
        context_for_llm = compacted_results
```

---

## Voir aussi

- [ROUTER.md](./ROUTER.md) - Documentation du Router Node v3
- [PLANNER.md](./PLANNER.md) - Documentation du Planner Node v3
- [VOICE.md](./VOICE.md) - Voice TTS System avec Factory Pattern
- [HITL.md](./HITL.md) - Human-in-the-Loop Architecture
- [PLAN_PATTERN_LEARNER.md](./PLAN_PATTERN_LEARNER.md) - Pattern Learning
- [PROMPTS.md](./PROMPTS.md) - Prompts utilises par les Smart Services
