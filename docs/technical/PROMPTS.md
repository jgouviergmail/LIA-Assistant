# PROMPTS - Système de Prompts et Versioning

> **Documentation complète du système de prompts LLM - Architecture centralisée v1**
>
> Version: 2.3
> Date: 2026-07-16
> Updated: prompt-cache convention (DYNAMIC CONTEXT marker), PromptName↔files sync guard, orphan cleanup

---

## 📋 Table des Matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture Prompts](#architecture-prompts)
3. [Prompt Loader Avancé](#prompt-loader-avancé)
4. [Domain Agent Prompts](#domain-agent-prompts)
5. [Prompt Caching — la convention DYNAMIC CONTEXT](#-prompt-caching--la-convention-dynamic-context)
6. [Voice & Memory Prompts](#voice--memory-prompts)
7. [Best Practices](#best-practices)

---

## 📖 Vue d'ensemble

### Architecture Centralisée v1 (Consolidée)

> **Note importante** : Les versions v2-v8 ont été consolidées dans v1 en décembre 2025.
> Le versioning historique des prompts est maintenant intégré dans le contenu des fichiers.

### Fichiers Prompts (78 fichiers, source de vérité vivante)

Tous les prompts vivent dans `apps/api/src/domains/agents/prompts/v1/*.txt`
(plus `apps/api/src/domains/telephony/prompts/v1/` pour la téléphonie, chargée
par son propre loader). La liste exhaustive n'est plus dupliquée ici : la
source de vérité est le Literal `PromptName` dans `prompt_loader.py`, maintenu
en synchronisation bidirectionnelle avec les fichiers par le test CI
`tests/unit/domains/agents/prompts/test_prompt_name_literal_sync.py`
(une entrée sans fichier ou un fichier sans entrée fait échouer la CI).

Grandes familles :

| Famille | Exemples | Notes |
|---------|----------|-------|
| Pipeline core | `query_analyzer_prompt`, `smart_planner_prompt`, `response_system_prompt_base`, `semantic_validator_prompt`, `compaction_prompt` | Routing = QueryAnalyzer (l'ancien `router_system_prompt_template` a été supprimé, orphelin depuis l'optim R1) |
| Boucles ReAct | `react_agent_prompt`, `subagent_react_prompt`, `skill_react_agent_prompt`, `mcp_react_agent_prompt` | ADR-070 / ADR-083 |
| Agents domaine | `emails_agent_prompt`, `calendar_agent_prompt`, `browser_agent_prompt`, … (17) | Structure standard `<Role>/<StrictLogic>/<Strategies>/<Context>` |
| HITL | `hitl_classifier_prompt` (+ `hitl_classifier_examples`), `hitl_question_generator_prompt`, `hitl_plan_approval_question_prompt`, `hitl_draft_critique_prompt` (+ fallback), `draft_modifier_prompt` | Les few-shot du classificateur sont sectionnés par action-type dans `hitl_classifier_examples.txt` et injectés via la sentinelle `[[EXAMPLES_PLACEHOLDER]]` (APRÈS `.format()` — les exemples contiennent des accolades) |
| Mémoire & psyché | `memory_extraction_prompt`, `memory_reference_*`, `memory_danger_directive`/`memory_normal_directive` (scaffolding d'injection du profil), `psyche_*` | Le header de `memory_danger_directive` est une sentinelle matchée littéralement par `response_system_prompt_base` — verrouillé par `test_memory_directive_sentinel.py` |
| Proactif & background | `heartbeat_*`, `initiative_prompt`, `interest_*`, `journal_*`, `briefing_*`, `reminder_prompt`, `voice_comment_prompt` | |
| Directives injectées | `html_response_directive`, `psyche_usage_directive*`, `response_directive_*`, `skill_contract_prefix_prompt`, `initiative_suggestion_directive`, `proactive_findings_directive` | Fragments appendés à d'autres system prompts, pas des prompts autonomes |
| Traductions & divers | `broadcast_translation_prompt`, `personality_translation_prompt`, `skill_description_translation_prompt`, `mcp_description_prompt`, `app_identity_prompt`, `default_personality_prompt`, `fallback_response_prompt` | |
### Prompts Actifs par Node

| Node/Service | Prompt | Description |
|--------------|--------|-------------|
| **Router (QueryAnalyzer)** | query_analyzer_prompt.txt | Intent routing + domain detection + reference resolution |
| **Planner** | smart_planner_prompt.txt | ExecutionPlan generation |
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
| **MemoryResolver** | memory_reference_extraction_prompt.txt | Phase 1: reference extraction |

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
# query_analyzer_service.py (le routing vit dans QueryAnalyzerService)
from src.domains.agents.prompts.prompt_loader import load_prompt

analyzer_prompt = load_prompt("query_analyzer_prompt")

async def analyze_full(state: MessagesState) -> dict:
    """Unified routing analysis with structured output."""
    llm_structured = llm.with_structured_output(QueryIntelligence)

    messages = [
        SystemMessage(content=analyzer_prompt),
        *state["messages"]
    ]

    response = await llm_structured.ainvoke(messages)
    return {"routing_decision": response.model_dump()}
```

### Psyche Context via Template Variables

All user-facing prompts inject the psyche state through a `{psyche_context}` template placeholder:

```python
# Example: reminder_prompt.txt contains a {psyche_context} placeholder
from src.domains.psyche.service import build_psyche_prompt_block

psyche_block = await build_psyche_prompt_block(user_id, user_timezone)
prompt = load_prompt("reminder_prompt").format(
    reminder_info=reminder_data,
    psyche_context=psyche_block,
)
```

As of [ADR-105](../architecture/ADR-105-Psyche-Embodied-Expression.md) (embodied expression, default on behind `PSYCHE_EMBODIED_INJECTION`), `{psyche_context}` is a **self-framing `<InnerVoice>` block** carrying a concrete voice grammar (per-mood form moves) plus its own anti-tell guardrails — so the prompts no longer wrap it in an `<InnerState purpose="tone-calibration">` block. The main response uses `PsycheEngine.format_embodied_prompt_injection` + the versioned `psyche_embodied_frame.txt` / `psyche_embodied_faint.txt`; the proactive channels (`reminder_prompt`, `heartbeat_message_prompt`, `voice_comment_prompt`, `interest_content_prompt`, `fallback_response_prompt`) use `build_psyche_prompt_block` + `psyche_embodied_proactive.txt`. With the flag off, the legacy graduated `<PsycheContext>` format is used instead (rollback path).

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

## ⚡ Prompt Caching — la convention `DYNAMIC CONTEXT`

Tous les providers utilisés (OpenAI, Anthropic, DeepSeek, Qwen, Gemini) cachent
les prompts par **préfixe exact** : le moindre octet variable (datetime, requête,
catalogue filtré) invalide tout ce qui le suit. La convention du repo est
**provider-agnostique** — les templates déclarent la frontière, la couche infra
gère les spécificités de chaque provider :

1. **Dans le template** : tout le contenu statique (rôle, règles, exemples,
   format de sortie) vient EN PREMIER ; le marqueur
   `--- DYNAMIC CONTEXT (all variable data below) ---` sépare ; tout le contenu
   par-requête (datetime, requête, contexte, catalogue, données) vient APRÈS.
   Le marqueur canonique est `DYNAMIC_CONTEXT_MARKER` (`core/constants.py`).
2. **Anthropic** (`infrastructure/llm/factory.py`) : split au marqueur en deux
   blocs system, `cache_control: ephemeral` sur le bloc statique uniquement.
   Sans marqueur, AUCUN `cache_control` n'est posé (un prompt dynamique non
   marqué paierait l'écriture cache à 125 % à chaque appel sans jamais de hit).
   Un prompt 100 % statique opte en TERMINANT par le marqueur
   (ex. `compaction_prompt.txt`, `semantic_validator_prompt.txt`).
3. **OpenAI** (`infrastructure/llm/providers/responses_adapter.py`) :
   `prompt_cache_key` dérivée du préfixe avant le marqueur (routage du cache) ;
   le préfixe stable maximise le hit du prefix caching automatique.
4. **DeepSeek / Qwen / Gemini** : prefix caching implicite — le préfixe stable
   suffit, aucun code spécifique.

Exceptions assumées (fragmentation par valeur stable) : les blocs d'identité
peuvent précéder le marqueur quand leur valeur est stable pour un même
utilisateur (`{personnalite}`, `{expertise}`, `{server_name}`) ou invariante
par déploiement (`{result_keys_list}`, `{max_actions}`). La table
`ALLOWED_BEFORE_MARKER` du test de garde documente chaque exception.

**Gardes CI** (`tests/unit/domains/agents/prompts/test_prompt_cache_hygiene.py`) :
- `MARKER_REQUIRED` : tout system prompt dynamique doit porter le marqueur
  (liste shrink-only) ;
- aucun placeholder actif avant le marqueur hors exceptions justifiées ;
- le préfixe statique du planner est byte-identique entre deux requêtes.

Few-shot réels restants : `hitl_classifier_examples.txt` (sectionné par
action-type via `=== <key> ===`, injecté par `.replace()` de la sentinelle
`[[EXAMPLES_PLACEHOLDER]]` APRÈS le `.format()` du template).

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
Extracts long-term memory facts from the user's last message. 7 mandatory rules:

1. **First person** — Write as the user speaks ("I like X", "My son is named Y")
2. **Exact words only** — Extract only explicitly stated facts, never infer
3. **Atomic** — One fact per memory, split compound statements
4. **Name relationships** — Resolve known relationships to full names
5. **Absolute temporal references** (v1.16.2) — ALL relative dates/times must be converted to absolute using current datetime. Exhaustive examples for days, periods, times, months. Explicit blacklist: "today", "tomorrow", "yesterday", "next/last [day]", "this [period]", "in [duration]", "soon", "recently"
6. **Qualify** — emotional_weight (-10 to +10) and importance (0.0-1.0)
7. **Categorize** — preference | personal | relationship | event | pattern | sensitivity

Supports 3 actions: `create`, `update` (with existing UUID), `delete` (with existing UUID).

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
# apps/api/src/core/config/

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

**PROMPTS.md** - Version 2.2 - Avril 2026

*Architecture prompts centralisee avec 46 fichiers, fewshot dynamique, voice, memory et Smart Services*
