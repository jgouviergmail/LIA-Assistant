# PROMPTS - Système de Prompts et Versioning

> **Documentation complète du système de prompts LLM - Architecture centralisée v1**
>
> Version: 2.1
> Date: 2026-01-12
> Updated: Architecture v3 Smart Services prompts (query_analyzer, smart_planner)

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture Prompts](#architecture-prompts)
3. [Prompt Loader Avancé](#prompt-loader-avancé)
4. [Domain Agent Prompts](#domain-agent-prompts)
5. [Hierarchical Planning Prompts](#hierarchical-planning-prompts)
6. [Few-Shot System](#few-shot-system)
7. [Voice & Memory Prompts](#voice--memory-prompts)
8. [Best Practices](#best-practices)

---

## 📖 Vue d'ensemble

### Architecture Centralisée v1 (Consolidée)

> **Note importante** : Les versions v2-v8 ont été consolidées dans v1 en décembre 2025.
> Le versioning historique des prompts est maintenant intégré dans le contenu des fichiers.

### Fichiers Prompts (45 total)

```
apps/api/src/domains/agents/prompts/
├── __init__.py
├── prompt_loader.py                            # Loader avancé avec caching + hash validation
└── v1/
    ├── router_system_prompt_template.txt       # Router (version consolidée)
    ├── planner_system_prompt.txt               # Planner (version consolidée)
    ├── response_system_prompt_base.txt         # Response base prompt
    │
    │   # DOMAIN AGENT PROMPTS (10)
    ├── contacts_agent_prompt.txt               # Google Contacts
    ├── emails_agent_prompt.txt                 # Gmail
    ├── calendar_agent_prompt.txt               # Google Calendar
    ├── tasks_agent_prompt.txt                  # Google Tasks
    ├── drive_agent_prompt.txt                  # Google Drive
    ├── places_agent_prompt.txt                 # Google Places
    ├── weather_agent_prompt.txt                # OpenWeatherMap
    ├── wikipedia_agent_prompt.txt              # Wikipedia API
    ├── perplexity_agent_prompt.txt             # Perplexity AI Search
    ├── query_agent_prompt.txt                  # Generic query agent
    │
    │   # HITL PROMPTS (4)
    ├── hitl_classifier_prompt.txt              # User response classification
    ├── hitl_question_generator_prompt.txt      # Question generation
    ├── hitl_plan_approval_question_prompt.txt  # Plan approval questions
    ├── hitl_draft_critique_prompt.txt          # Draft review (email, etc.)
    │
    │   # HIERARCHICAL PLANNING (3)
    ├── hierarchical_stage1_routing_prompt.txt  # Stage 1: High-level routing
    ├── hierarchical_stage2_subplanning_prompt.txt  # Stage 2: Subplan generation
    ├── hierarchical_stage3_composition_prompt.txt  # Stage 3: Plan composition
    │
    │   # SMART SERVICES (3) - Architecture v3
    ├── query_analyzer_prompt.txt               # QueryAnalyzerService LLM analysis
    ├── smart_planner_prompt.txt                # SmartPlannerService single domain
    ├── smart_planner_multi_domain_prompt.txt   # SmartPlannerService multi-domain
    ├── app_identity_prompt.txt                 # App self-knowledge identity prompt (~200 tokens), loaded conditionally when is_app_help_query=True. Includes admin-boundary directive (v1.9.2): instructs LLM to never mention admin-only features to regular users.
    │
    │   # SEMANTIC & MEMORY (4)
    ├── semantic_validator_prompt.txt           # Plan semantic validation
    ├── semantic_pivot_prompt.txt               # Semantic pivot detection
    ├── memory_extraction_prompt.txt            # Long-term memory extraction
    ├── memory_extraction_personality_addon.txt # Personality traits extraction
    ├── memory_reference_resolution_prompt.txt  # Reference resolution (qui est "mon père"?)
    │
    │   # VOICE (1)
    ├── voice_comment_prompt.txt                # Voice comment generation
    │
    │   # FEW-SHOT EXAMPLES (16)
    └── fewshot/
        ├── contacts_search.txt
        ├── contacts_details.txt
        ├── emails_search.txt
        ├── emails_details.txt
        ├── calendar_search.txt
        ├── calendar_details.txt
        ├── tasks_search.txt
        ├── tasks_details.txt
        ├── drive_search.txt
        ├── drive_details.txt
        ├── places_search.txt
        ├── places_details.txt
        ├── places_location.txt
        ├── weather_search.txt
        ├── wikipedia_search.txt
        └── perplexity_search.txt
```

### Prompts Actifs par Node

| Node/Service | Prompt | Description |
|--------------|--------|-------------|
| **Router** | router_system_prompt_template.txt | Binary routing + domain detection |
| **Planner** | planner_system_prompt.txt | ExecutionPlan generation |
| **Response** | response_system_prompt_base.txt | Conversational response (placeholder: `{app_knowledge_context}`) |
| **Contacts Agent** | contacts_agent_prompt.txt | Google Contacts domain |
| **Emails Agent** | emails_agent_prompt.txt | Gmail domain |
| **Calendar Agent** | calendar_agent_prompt.txt | Google Calendar domain |
| **Tasks Agent** | tasks_agent_prompt.txt | Google Tasks domain |
| **Drive Agent** | drive_agent_prompt.txt | Google Drive domain |
| **Places Agent** | places_agent_prompt.txt | Google Places domain |
| **Weather Agent** | weather_agent_prompt.txt | OpenWeatherMap domain |
| **Wikipedia Agent** | wikipedia_agent_prompt.txt | Wikipedia domain |
| **Perplexity Agent** | perplexity_agent_prompt.txt | AI Web Search domain |
| **Voice Comment** | voice_comment_prompt.txt | TTS comment generation |
| **Semantic Validator** | semantic_validator_prompt.txt | Plan validation |
| **Memory Extractor** | memory_extraction_prompt.txt | Long-term memory |
| **QueryAnalyzer** | query_analyzer_prompt.txt | Smart routing analysis |
| **SmartPlanner** | smart_planner_prompt.txt | Smart planning |

---

## 🏗️ Architecture Prompts

### Prompt Loader Avancé

**Fichier source**: `apps/api/src/domains/agents/prompts/prompt_loader.py`

Le prompt loader moderne inclut :
- **LRU caching** (maxsize=32) pour performance
- **Hash validation** pour intégrité
- **Version detection** dynamique depuis filesystem
- **Few-shot loading** dynamique par domaine

```python
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=32)
def load_prompt(
    name: str,
    version: str = "v1",
    validate_hash: bool = False,
    expected_hash: str | None = None,
) -> str:
    """
    Load a versioned prompt from file with optional hash validation.

    Optimizations (Phase 3.2.9):
    - LRU cache (maxsize=32) for prompt reuse across requests
    - Reduces disk I/O from ~1000s reads/min to ~10 reads at startup
    """
    prompt_file = PROMPTS_DIR / version / f"{name}.txt"
    content = prompt_file.read_text(encoding="utf-8")

    if validate_hash and expected_hash:
        actual_hash = hashlib.sha256(content.encode()).hexdigest()
        if actual_hash != expected_hash:
            raise PromptIntegrityError(f"Hash mismatch for {name}")

    return content
```

### Usage dans Nodes

```python
# router_node_v3.py
from src.domains.agents.prompts.prompt_loader import load_prompt

router_prompt = load_prompt("router_system_prompt_template")

async def router_node(state: MessagesState) -> dict:
    """Router node with consolidated prompt."""
    llm_structured = llm.with_structured_output(RouterOutput)

    messages = [
        SystemMessage(content=router_prompt),
        *state["messages"]
    ]

    response = await llm_structured.ainvoke(messages)
    return {"routing_decision": response.model_dump()}
```

---

## 📁 Domain Agent Prompts

### Structure Standard

Chaque domain agent a un prompt dédié suivant le pattern :

```
# {DOMAIN}_agent_prompt.txt

Tu es un agent spécialisé pour le domaine {DOMAIN}.

## Ton Rôle
[Description du rôle]

## Outils Disponibles
[Liste des tools du domaine]

## Règles de Formatage
[Guidelines de formatage pour le LLM Response]

## Exemples
[Few-shot examples inline ou via fewshot loader]
```

### Domaines Couverts

| Domaine | Prompt | Tools | API Backend |
|---------|--------|-------|-------------|
| **contacts** | contacts_agent_prompt.txt | search, get_details | Google People API |
| **emails** | emails_agent_prompt.txt | search, get_details, send, reply | Gmail API |
| **calendar** | calendar_agent_prompt.txt | search, create_event | Google Calendar API |
| **tasks** | tasks_agent_prompt.txt | list, create, update, delete | Google Tasks API |
| **drive** | drive_agent_prompt.txt | search, get_content | Google Drive API |
| **places** | places_agent_prompt.txt | search_text, search_nearby, details | Google Places API |
| **weather** | weather_agent_prompt.txt | current, forecast | OpenWeatherMap API |
| **wikipedia** | wikipedia_agent_prompt.txt | search, article | Wikipedia API |
| **perplexity** | perplexity_agent_prompt.txt | search | Perplexity Sonar API |

---

## 📊 Hierarchical Planning Prompts

### Architecture 3 Stages

Le système de planification hiérarchique utilise 3 prompts distincts :

```mermaid
graph LR
    A[User Query] --> B[Stage 1: Routing]
    B --> C[Stage 2: Subplanning]
    C --> D[Stage 3: Composition]
    D --> E[ExecutionPlan]
```

### Stage 1: Routing (`hierarchical_stage1_routing_prompt.txt`)

```
Analyse la requête utilisateur et détermine:
1. Domaines impliqués (contacts, emails, calendar...)
2. Complexité (simple/multi-step)
3. Dépendances inter-domaines
```

### Stage 2: Subplanning (`hierarchical_stage2_subplanning_prompt.txt`)

```
Pour chaque domaine identifié, génère un sous-plan:
1. Tools nécessaires
2. Paramètres
3. Dépendances internes
```

### Stage 3: Composition (`hierarchical_stage3_composition_prompt.txt`)

```
Compose les sous-plans en ExecutionPlan final:
1. Ordonne les étapes
2. Assigne parallel_groups
3. Valide les dépendances cross-domain
```

---

## 🎯 Few-Shot System

### Architecture Dynamique

Le système few-shot charge **uniquement les exemples pertinents** pour la requête courante, réduisant les tokens de ~80%.

**Fichier** : `prompt_loader.py` - fonctions `load_fewshot_examples()`

```python
# Mapping domain → file prefix
DOMAIN_FILE_MAP = {
    "contacts": "contacts",
    "emails": "emails",
    "calendar": "calendar",
    "tasks": "tasks",
    "places": "places",
    "drive": "drive",
    "weather": "weather",
    "wikipedia": "wikipedia",
    "perplexity": "perplexity",
}

# Mapping operation → file suffix
OPERATION_FILE_MAP = {
    "search": "search",
    "list": "search",
    "details": "details",
    "location": "location",
}

@lru_cache(maxsize=64)
def _load_fewshot_file(domain: str, operation: str, version: str = "v1") -> str | None:
    """Load fewshot example with caching."""
    fewshot_file = PROMPTS_DIR / version / "fewshot" / f"{domain}_{operation}.txt"
    if fewshot_file.exists():
        return fewshot_file.read_text(encoding="utf-8")
    return None

def load_fewshot_examples(domain_operations: list[tuple[str, str]]) -> str:
    """
    Load and concatenate fewshot examples for specified domains.

    Args:
        domain_operations: [("contacts", "search"), ("emails", "details")]

    Returns:
        Concatenated examples string
    """
```

### Exemples Few-Shot Disponibles

| Fichier | Domaine | Opération | Tokens |
|---------|---------|-----------|--------|
| contacts_search.txt | contacts | search | ~500 |
| contacts_details.txt | contacts | details | ~400 |
| emails_search.txt | emails | search | ~600 |
| emails_details.txt | emails | details | ~500 |
| calendar_search.txt | calendar | search | ~400 |
| tasks_search.txt | tasks | search | ~350 |
| drive_search.txt | drive | search | ~450 |
| places_search.txt | places | search | ~550 |
| places_location.txt | places | location | ~300 |
| weather_search.txt | weather | search | ~400 |
| wikipedia_search.txt | wikipedia | search | ~450 |
| perplexity_search.txt | perplexity | search | ~500 |

### Bénéfices Performance

| Scénario | Avant (tous) | Après (dynamique) | Réduction |
|----------|--------------|-------------------|-----------|
| Single domain | ~5K tokens | ~500 tokens | **90%** |
| Dual domain | ~5K tokens | ~1K tokens | **80%** |
| Triple domain | ~5K tokens | ~1.5K tokens | **70%** |

---

## 🎙️ Voice & Memory Prompts

### Voice Comment Prompt

**Fichier** : `v1/voice_comment_prompt.txt`

Génère des commentaires vocaux naturels (1-6 phrases) pour la synthèse TTS.

```
Tu génères un commentaire vocal bref et naturel.

Règles:
- 1-6 phrases maximum
- Langage oral naturel (pas écrit)
- Pas de markdown, pas d'emoji
- Ton conversationnel, chaleureux
- Résume l'essentiel de la réponse

Exemple:
Input: "Voici les 3 contacts trouvés: Marie Dupont, Jean Martin, Pierre Durand"
Output: "J'ai trouvé trois contacts pour toi. Marie Dupont, Jean Martin et Pierre Durand."
```

### Memory Prompts

#### `memory_extraction_prompt.txt`
Extrait les informations à mémoriser long-terme depuis la conversation.

```
Analyse cette conversation et extrait:
1. Faits sur l'utilisateur (préférences, habitudes)
2. Relations personnelles (famille, amis, collègues)
3. Événements importants (anniversaires, rendez-vous récurrents)
4. Préférences de communication
```

#### `memory_extraction_personality_addon.txt`
Addon pour extraire les traits de personnalité.

#### `memory_reference_resolution_prompt.txt`
Résout les références implicites ("mon père", "ma sœur") vers des contacts réels.

```
L'utilisateur dit: "envoie un message à mon père"
Mémoire disponible: father=Jean dupond, mother=Marie dupond

Résolution: "mon père" → Jean dupond
```

---

## 📐 Semantic Validation Prompts

### `semantic_validator_prompt.txt`

Valide que le plan généré correspond à l'intention utilisateur.

**Détecte** :
- Cardinality mismatch (demande 1 contact, plan retourne 10)
- Missing dependencies (tool requires data not available)
- Scope overflow (plan exceeds user request)

```python
# Usage
validator_prompt = load_prompt("semantic_validator_prompt")
validation_result = await validate_plan_semantically(plan, user_query, validator_prompt)

if not validation_result.is_valid:
    # Trigger clarification or replan
```

### `semantic_pivot_prompt.txt`

Détecte les pivots sémantiques (changement de sujet) dans la conversation.

---

## 🔄 Evolution Router (Historique)

### v1 - Router Basique (Deprecated)

**Date**: 2025-10
**Objectif**: Routing simple conversation vs. actionnable

**Problèmes**:
- Pas de domain detection
- Over-planning sur queries simples
- Prompt trop long (5K tokens)

### v3 - Refactoring

**Date**: 2025-10
**Améliorations**:
- Binary routing clair (conversation/actionnable)
- Confidence scoring
- Reasoning obligatoire

### v4-v6 - Itérations

Optimisations progressives sur:
- Clarté instructions
- Exemples plus précis
- Réduction verbosité

### v7 - Multi-Domain Architecture ⭐

**Date**: 2025-11-12
**Changement majeur**: Domain detection

**Nouveau champ `domains`**:
```json
{
  "intention": "actionnable",
  "confidence": 0.90,
  "next_node": "planner",
  "domains": ["contacts"],  // NEW!
  "reasoning": "..."
}
```

**Bénéfices**:
- **90% token reduction** pour queries single-domain
- Planner charge seulement catalogue filtré
- Scalabilité: prêt pour 10+ domaines

**Exemple**:
```
User: "Trouve Marie"
Router → domains: ["contacts"]
Planner → Charge UNIQUEMENT tools contacts (4K tokens vs 40K)
```

### v8 - Anti-Hallucination Hardening ⭐⭐

**Date**: 2025-11-13
**Fix**: Bug critique #BUG-2025-11-13

**Problème v7**:
```
User: "recherche contacts avec critère X"
Router v7: Consulte historique → "aucun contact avec critère X"
         → confidence=0.45 → next_node="response" ❌
Response: Pas d'API call → Invente données depuis historique ❌
         → HALLUCINATION
```

**Solution v8**: **Règle #5 renforcée**

```
PRINCIPE FONDAMENTAL: Router = ANALYSEUR SYNTAXIQUE
✅ Analyser SYNTAXE et STRUCTURE de la requête
✅ Détecter VERBES D'ACTION (recherche, trouve, liste)
✅ Identifier ENTITÉS et CRITÈRES
❌ NE JAMAIS présumer disponibilité des données
❌ NE JAMAIS consulter historique pour évaluer résultats
```

**Patterns INTERDITS dans reasoning**:
- "aucun", "aucune", "pas de", "pas trouvé"
- "correspondance", "résultat", "données disponibles"
- "improbable", "peu probable"

**Auto-validation**:
```
1. Relis ton `reasoning`
2. Cherche patterns interdits
3. SI trouvé → VIOLATION Règle #5
4. ALORS → CORRIGE: base décision sur SYNTAXE uniquement
```

**Résultat**:
```
User: "recherche contacts avec critère X"
Router v8: Analyse syntaxe → verbe "recherche" + entité "contacts"
         → intention="actionnable" + confidence=0.90
         → next_node="planner" ✅
Planner: Appelle search_contacts_tool
Tool: Retourne résultats réels (ou liste vide si aucun)
Response: Formate résultats API (pas d'hallucination)
```

**Impact**:
- ✅ Élimine hallucinations router
- ✅ Toutes queries actionnables passent par tools
- ✅ Séparation responsabilités claire

---

## 📋 Evolution Planner (v1→v5)

### v1 - Planner Initial

**Date**: 2025-10
**Format**: Structured output ExecutionPlan

**Problèmes**:
- Prompt verbeux (8K tokens)
- Over-planning fréquent
- Pas de gestion parallélisme

### v2 - Simplification

**Améliorations**:
- Instructions plus concises
- Exemples réduits
- Tokens: 8K → 6K

### v3-v4 - Optimisations

- Clarté enhanced
- Edge cases documentés
- Validation rules explicites

### v5 - Wave-Based Execution ⭐

**Date**: 2025-11
**Changement majeur**: Support exécution parallèle

**Nouveau concept `parallel_group`**:
```python
ExecutionPlan(
    steps=[
        Step(
            step_id="step_1",
            tool_name="search_contacts",
            parameters={"query": "john"},
            dependencies=[],
            parallel_group=1  // Wave 1
        ),
        Step(
            step_id="step_2",
            tool_name="get_contact_details",
            parameters={"contact_id": "{step_1.result[0].id}"},
            dependencies=["step_1"],
            parallel_group=2  // Wave 2 (après Wave 1)
        )
    ]
)
```

**Bénéfices**:
- Exécution parallèle steps indépendants
- Performance: 2-3x plus rapide
- Architecture prête pour complexité

---

## 🎨 Optimisations

### Token Reduction

**Techniques appliquées**:

1. **Prompt caching (OpenAI)**:
   - Prompts > 1024 tokens → cached automatiquement
   - Router v8: 4.5K tokens → 90% cached
   - Cost: $0.50/1M → $0.05/1M (10x cheaper)

2. **Domain filtering (Router v7+)**:
   - Single domain: 4K tokens vs 40K
   - Dual domain: 12K tokens vs 40K
   - Réduction: 70-90%

3. **Message windowing**:
   - Reducer `add_messages_with_truncate`
   - 100K tokens → 7K tokens (93% reduction)
   - Preserve SystemMessage

4. **Prompt compression**:
   - Remove verbosité
   - Exemples concis
   - Instructions directes

**Résultats**:

| Optimization | Before | After | Reduction |
|--------------|--------|-------|-----------|
| Caching | $0.50/1M | $0.05/1M | 90% |
| Domain filtering | 40K | 4K | 90% |
| Message windowing | 100K | 7K | 93% |
| **Total** | **~150K tokens** | **~11K tokens** | **~93%** |

### Performance

**Latency optimizations**:
- Prompt caching: -50% latency (cache hit)
- Smaller prompts: -30% latency
- Total: -60-70% P95 latency

**Cost optimizations**:
- Router v8 (4.5K tokens cached): ~$0.0002 per call
- Planner v5 (6K tokens): ~$0.0015 per call
- Response v3 (3K tokens): ~$0.0007 per call
- **Total per conversation**: ~$0.002-0.005

---

## ✅ Best Practices

### Prompt Engineering

1. **Structured output obligatoire**:
```python
# ✅ Good
llm.with_structured_output(RouterOutput)

# ❌ Bad (parsing errors)
llm.invoke(messages) → parse JSON manuellement
```

2. **Instructions claires et concises**:
```
✅ "Analyze query syntax. Detect action verbs."
❌ "You should probably try to maybe look at the query..."
```

3. **Exemples concrets**:
```
✅ 10 exemples couvrant edge cases
❌ 2 exemples génériques
```

4. **Anti-patterns explicites**:
```
Router v8: Liste patterns INTERDITS
→ Prévention proactive des erreurs
```

### Versioning

1. **Semantic versioning**:
   - v1, v2, v3... (major changes)
   - Pas de v1.1, v1.2 (keep simple)

2. **Changelog dans prompt**:
```txt
# Version 8.0 - Anti-Hallucination Hardening (2025-11-13)
# - FIX: #BUG-2025-11-13 - Router data presumption
# - ENHANCED: Règle #5 with anti-patterns
# - ADDED: Auto-validation rule
```

3. **Backward compatibility**:
   - Garder anciennes versions (v1-v7)
   - Permet rollback si régression

4. **A/B testing**:
```python
# Test v8 vs v7
if user_id % 2 == 0:
    prompt = load_router_prompt(version="v8")
else:
    prompt = load_router_prompt(version="v7")

# Metrics comparison
```

### Testing

1. **Unit tests prompts**:
```python
@pytest.mark.asyncio
async def test_router_v8_anti_hallucination():
    """Test router v8 doesn't hallucinate on unclear data."""

    prompt = load_router_prompt(version="v8")

    llm = ChatOpenAI(model="gpt-4.1-mini")
    llm_structured = llm.with_structured_output(RouterOutput)

    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content="recherche contacts avec critère improbable")
    ]

    response = await llm_structured.ainvoke(messages)

    # v8 should route to planner (syntax-based)
    assert response.next_node == "planner"
    assert response.intention == "actionable"
    assert response.confidence >= 0.7

    # Check no forbidden patterns in reasoning
    forbidden = ["aucun", "pas de", "improbable", "résultat"]
    assert not any(word in response.reasoning.lower() for word in forbidden)
```

2. **Regression tests**:
   - Test suite pour chaque version
   - Garantir pas de régression v7→v8

3. **Golden dataset**:
   - 100+ queries typiques
   - Expected outputs
   - Run sur chaque nouvelle version

---

## 📚 Annexes

### Metrics Prometheus

```python
# Prompt version usage
prompt_version_usage_total = Counter(
    'prompt_version_usage_total',
    'Prompt version usage',
    ['node', 'version']
)

# Track v8 adoption
prompt_version_usage_total.labels(node="router", version="v8").inc()
```

### Configuration

```python
# apps/api/src/core/config.py

class Settings(BaseSettings):
    # Prompt versions
    router_prompt_version: str = "v8"
    planner_prompt_version: str = "v5"
    response_prompt_version: str = "v3"

    # Feature flags
    enable_domain_filtering: bool = True  # Router v7+
    enable_anti_hallucination: bool = True  # Router v8
```

### Roadmap

**v9 - Tool Selection Optimization**:
- Router detect tools nécessaires (pas juste domains)
- Réduction tokens: 4K → 2K
- ETA: 2025-12

**Planner v6 - Conditional Execution**:
- Support if/else dans plan
- Gestion erreurs robuste
- ETA: 2025-12

---

## 📚 Ressources

### Documentation Liée

- [PLANNER.md](./PLANNER.md) - Architecture du planner avec prompts
- [ROUTER.md](./ROUTER.md) - Router node et binary routing
- [RESPONSE.md](./RESPONSE.md) - Response node et synthèse
- [SMART_SERVICES.md](./SMART_SERVICES.md) - QueryAnalyzerService, SmartPlannerService
- [VOICE.md](./VOICE.md) - Voice domain et TTS
- [LONG_TERM_MEMORY.md](./LONG_TERM_MEMORY.md) - Mémoire long-terme

### Fichiers Source

- `apps/api/src/domains/agents/prompts/` - Tous les prompts
- `apps/api/src/domains/agents/prompts/prompt_loader.py` - Loader avec caching

---

**PROMPTS.md** - Version 2.1 - Janvier 2026

*Architecture prompts centralisee avec 45 fichiers, fewshot dynamique, voice, memory et Smart Services*
