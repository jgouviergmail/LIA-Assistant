# Guide Prompts - LIA

> Guide pratique pour créer, versionner et optimiser les prompts LLM

Version: 1.1
Date: 2025-12-27

---

## 📋 Table des Matières

- [Introduction](#introduction)
- [Architecture Prompts](#architecture-prompts)
- [Créer un Nouveau Prompt](#créer-un-nouveau-prompt)
- [Versionning et Évolution](#versionning-et-évolution)
- [Optimisation](#optimisation)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Introduction

### Qu'est-ce qu'un Prompt ?

Un **prompt** est le texte d'instructions fourni à un LLM (Large Language Model) pour guider son comportement. Dans LIA, les prompts définissent les responsabilités de chaque node du graph LangGraph.

### Prompts Actifs

| Node | Version | Fichier | Rôle |
|------|---------|---------|------|
| **Router** | v1 | `v1/router_system_prompt_template.txt` | Classification intent + domain detection |
| **Planner** | v1 | `v1/planner_system_prompt.txt` | Orchestration multi-agents |
| **Response** | v1 | `v1/response_system_prompt_base.txt` | Génération réponse utilisateur |
| **HITL Classifier** | v1 | `v1/hitl_classifier_prompt.txt` | Classification HITL |
| **HITL Question Generator** | v1 | `v1/hitl_question_generator_prompt.txt` | Génération questions clarification |

> **Note**: Tous les prompts sont actuellement en version v1. Le versionning futur sera géré via Langfuse.

### Arborescence Fichiers

```
apps/api/src/domains/agents/prompts/
├── prompt_loader.py                            # Loader utilitaire
└── v1/                                         # Version actuelle (unique)
    ├── router_system_prompt_template.txt       # Router node
    ├── planner_system_prompt.txt               # Planner node
    ├── response_system_prompt_base.txt         # Response node
    ├── semantic_validator_prompt.txt           # Semantic validator
    │
    ├── contacts_agent_prompt.txt               # Domain agents
    ├── emails_agent_prompt.txt
    ├── calendar_agent_prompt.txt
    ├── drive_agent_prompt.txt
    ├── tasks_agent_prompt.txt
    ├── weather_agent_prompt.txt
    ├── wikipedia_agent_prompt.txt
    ├── perplexity_agent_prompt.txt
    ├── places_agent_prompt.txt
    ├── query_agent_prompt.txt
    │
    ├── hitl_classifier_prompt.txt              # HITL prompts
    ├── hitl_question_generator_prompt.txt
    ├── hitl_plan_approval_question_prompt.txt
    ├── hitl_draft_critique_prompt.txt
    ├── draft_modifier_prompt.txt               # Draft modification during HITL edit
    │
    ├── hierarchical_stage1_routing_prompt.txt  # Hierarchical planner
    ├── hierarchical_stage2_subplanning_prompt.txt
    ├── hierarchical_stage3_composition_prompt.txt
    │
    └── fewshot/                                # Few-shot examples
        ├── contacts_search.txt
        ├── contacts_details.txt
        ├── emails_search.txt
        ├── emails_details.txt
        ├── calendar_search.txt
        ├── calendar_details.txt
        ├── drive_search.txt
        ├── drive_details.txt
        ├── tasks_search.txt
        ├── tasks_details.txt
        ├── weather_search.txt
        ├── perplexity_search.txt
        ├── wikipedia_search.txt
        ├── places_search.txt
        └── places_details.txt
```

---

## 🏗️ Architecture Prompts

### Loader Utilitaire

**Fichier**: `apps/api/src/domains/agents/prompts/prompt_loader.py`

```python
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

def load_prompt(filename: str, version: str = "v1") -> str:
    """
    Load prompt from versioned file.

    Args:
        filename: Prompt filename (e.g., "router_system_prompt.txt")
        version: Version folder (e.g., "v8")

    Returns:
        Prompt content as string

    Raises:
        FileNotFoundError: If prompt file not found

    Example:
        >>> router_prompt = load_prompt("router_system_prompt.txt", version="v8")
        >>> print(router_prompt[:100])
        # Router System Prompt v8...
    """
    prompt_path = PROMPTS_DIR / version / filename

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    return prompt_path.read_text(encoding="utf-8")
```

### Utilisation dans Nodes

**Exemple - Router Node** :

```python
# apps/api/src/domains/agents/nodes/router.py
from src.domains.agents.prompts.prompt_loader import load_prompt
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate

# Load prompt v8
ROUTER_SYSTEM_PROMPT = load_prompt("router_system_prompt.txt", version="v8")

# Create LLM with structured output (Router uses fastest model)
router_llm = ChatOpenAI(
    model="gpt-4.1-nano",  # Router uses gpt-4.1-nano for speed
    temperature=0.0,
).with_structured_output(RouterOutput)

# Create prompt template
router_prompt = ChatPromptTemplate.from_messages([
    ("system", ROUTER_SYSTEM_PROMPT),
    ("human", "{user_message}"),
])

# Chain
router_chain = router_prompt | router_llm

# Invoke
async def router_node(state: MessagesState) -> dict:
    """Router node: classify intent and detect domains."""
    result = await router_chain.ainvoke({
        "user_message": state["messages"][-1].content
    })
    return {"routing_decision": result.model_dump()}
```

---

## ✍️ Créer un Nouveau Prompt

### Étape 1 : Définir le Rôle

**Questions à se poser** :
- Quelle est la responsabilité de ce node ?
- Quel est l'input attendu ?
- Quel est l'output attendu (JSON schema ?) ?
- Quelles sont les contraintes (pas d'hallucination, limites, etc.) ?

**Exemple - Nouveau Node "Summarizer"** :

```markdown
# Summarizer System Prompt v1

Tu es un expert en synthèse de conversations.

**Ton rôle** : Analyser l'historique conversationnel et générer un résumé concis.

**Input** : Liste de messages (user + assistant)
**Output** : JSON avec résumé structuré

**Contraintes** :
- Maximum 3 phrases
- Pas d'hallucination (seulement faits mentionnés)
- Highlight actions clés (recherches, affichages)
```

### Étape 2 : Définir le JSON Schema

```python
# src/domains/agents/schemas.py
from pydantic import BaseModel, Field

class SummarizerOutput(BaseModel):
    """Summarizer structured output."""

    summary: str = Field(
        ...,
        description="Résumé de la conversation (max 3 phrases)",
        min_length=10,
        max_length=500
    )
    key_actions: list[str] = Field(
        default_factory=list,
        description="Actions clés effectuées (recherches, affichages)"
    )
    entities_mentioned: list[str] = Field(
        default_factory=list,
        description="Entités mentionnées (noms, filtres)"
    )
```

### Étape 3 : Rédiger le Prompt

**Template** :

```markdown
# [Node Name] System Prompt v1
# Purpose: [Describe role]
# Created: [Date]

[Rôle et contexte]

## JSON SCHEMA ATTENDU

```json
{
  "field1": "value",
  "field2": 123
}
```

### Champs

**field1** :
- Description
- Valeurs possibles

**field2** :
- Description
- Range

## RÈGLES

### Règle #1 : [Nom règle]
[Description détaillée]

### Règle #2 : [Nom règle]
[Description détaillée]

## EXEMPLES

### Ex1: [Scénario]
Input: [Input example]

Output:
```json
{
  "field1": "value",
  "field2": 123
}
```

### Ex2: [Scénario]
...

## PRINCIPES

- **[Principe 1]** : [Description]
- **[Principe 2]** : [Description]

---

Note: [Notes optionnelles sur caching, optimisation, etc.]

# Version 1.0 - Initial Release ([Date])
# - ADDED: [Feature 1]
# - ADDED: [Feature 2]
# - Cache marker: v1.0_[date]_[identifier]
```

### Étape 4 : Créer le Fichier

```bash
# Créer répertoire v1 si nouveau prompt
mkdir -p apps/api/src/domains/agents/prompts/v1

# Créer fichier prompt
touch apps/api/src/domains/agents/prompts/v1/summarizer_system_prompt.txt

# Éditer avec votre prompt
vim apps/api/src/domains/agents/prompts/v1/summarizer_system_prompt.txt
```

### Étape 5 : Implémenter le Node

```python
# apps/api/src/domains/agents/nodes/summarizer.py
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.schemas import SummarizerOutput
from src.domains.agents.domain_schemas import MessagesState

# Load prompt
SUMMARIZER_SYSTEM_PROMPT = load_prompt("summarizer_system_prompt.txt", version="v1")

# Create LLM
summarizer_llm = ChatOpenAI(
    model="gpt-4.1-mini-mini",
    temperature=0.0,
).with_structured_output(SummarizerOutput)

# Create prompt template
summarizer_prompt = ChatPromptTemplate.from_messages([
    ("system", SUMMARIZER_SYSTEM_PROMPT),
    ("placeholder", "{messages}"),  # All messages
])

# Chain
summarizer_chain = summarizer_prompt | summarizer_llm

# Node function
async def summarizer_node(state: MessagesState) -> dict:
    """
    Summarizer node: generate conversation summary.

    Args:
        state: Current graph state with messages

    Returns:
        dict with summary metadata
    """
    result = await summarizer_chain.ainvoke({
        "messages": state["messages"]
    })

    return {
        "metadata": {
            **state.get("metadata", {}),
            "conversation_summary": result.summary,
            "key_actions": result.key_actions,
            "entities_mentioned": result.entities_mentioned,
        }
    }
```

### Étape 6 : Tester

```python
# tests/agents/test_summarizer_node.py
import pytest
from langchain_core.messages import HumanMessage, AIMessage
from src.domains.agents.nodes.summarizer import summarizer_node
from src.domains.agents.domain_schemas import MessagesState

@pytest.mark.asyncio
async def test_summarizer_generates_summary():
    """Test summarizer generates valid summary."""
    state: MessagesState = {
        "messages": [
            HumanMessage(content="Recherche Jean"),
            AIMessage(content="J'ai trouvé 3 contacts nommés Jean."),
            HumanMessage(content="Affiche le premier"),
            AIMessage(content="Jean Dupont, email: jean@example.com"),
        ],
        "conversation_id": "test-conv",
        "user_id": UUID("..."),
        # ... autres champs
    }

    result = await summarizer_node(state)

    assert "metadata" in result
    assert "conversation_summary" in result["metadata"]
    assert len(result["metadata"]["conversation_summary"]) > 0
    assert "Jean" in result["metadata"]["conversation_summary"]

@pytest.mark.asyncio
async def test_summarizer_identifies_key_actions():
    """Test summarizer identifies key actions."""
    state: MessagesState = {...}  # State avec actions

    result = await summarizer_node(state)

    key_actions = result["metadata"]["key_actions"]
    assert "Recherche Jean" in key_actions or "recherche" in str(key_actions).lower()
```

---

## 🔄 Versionning et Évolution

### Quand Créer une Nouvelle Version ?

**Critères pour nouvelle version** :
- ✅ **Changement de comportement majeur** (ex: ajout domain detection)
- ✅ **Fix bug critique** (ex: anti-hallucination hardening)
- ✅ **Optimisation significative** (ex: réduction 50% tokens)
- ✅ **Changement JSON schema** (ajout/suppression champs)
- ❌ **Typos, rewording mineurs** → Modifier version existante

### Process de Versionning

**Exemple - Modification du Router prompt** :

```bash
# 1. Éditer le prompt dans le dossier consolidé v1
vim apps/api/src/domains/agents/prompts/v1/router_system_prompt_template.txt

# Note: Tous les prompts sont désormais consolidés dans le dossier v1.
# Le versioning se fait via le header changelog dans chaque fichier.

# 3. Ajouter header changelog
```

**Header changelog** :

```markdown
# Router System Prompt v8 (Anti-Hallucination Hardening)
# Purpose: Binary routing + Domain Detection
# Created: 2025-11-13
# Base: v7 (Multi-Domain) + ENHANCED: Règle #5 reinforced
# Fix: #BUG-2025-11-13 - Router data presumption hallucination

...

# Version 8.0 - Anti-Hallucination Hardening (2025-11-13)
# - FIX: #BUG-2025-11-13 - Router data presumption causing hallucinations
# - ENHANCED: Règle #5 "NE PAS présumer des résultats" with explicit anti-patterns
# - ADDED: Auto-validation rule for reasoning patterns
# - ADDED: Detailed examples of syntax-only analysis
# - BASE: v7.0 Multi-Domain Architecture
# - Cache marker: v8.0_20251113_antihallucination_hardening
```

**4. Mettre à jour code** :

```python
# apps/api/src/domains/agents/nodes/router.py

# Avant (v7)
ROUTER_SYSTEM_PROMPT = load_prompt("router_system_prompt.txt", version="v7")

# Après (v8)
ROUTER_SYSTEM_PROMPT = load_prompt("router_system_prompt.txt", version="v8")
```

**5. Tester A/B** :

```python
# tests/agents/test_router_ab.py
import pytest
from src.domains.agents.prompts.prompt_loader import load_prompt

@pytest.mark.asyncio
async def test_router_v7_vs_v8_hallucination_fix():
    """Test v8 fixes data presumption hallucination."""
    v7_prompt = load_prompt("router_system_prompt.txt", version="v7")
    v8_prompt = load_prompt("router_system_prompt.txt", version="v8")

    # Test case: User query with unlikely filter
    # v7 might reduce confidence assuming no results
    # v8 should maintain high confidence (syntax-only analysis)

    # ... implement A/B test ...
```

**6. Rollback strategy** :

```python
# apps/api/src/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Prompt versions (rollback via env vars)
    router_prompt_version: str = "v8"
    planner_prompt_version: str = "v5"
    response_prompt_version: str = "v3"

settings = Settings()

# Usage
ROUTER_SYSTEM_PROMPT = load_prompt(
    "router_system_prompt.txt",
    version=settings.router_prompt_version
)
```

### Évolution Majeure - Cas d'Usage

**Exemple 1 - Router v7: Multi-Domain Architecture** :

**Problème** : Router v6 → Planner recevait TOUS les outils (40K+ tokens avec 5 domaines)

**Solution v7** :
1. Router détecte domaines pertinents (`domains: ["contacts"]`)
2. Planner ne charge que outils des domaines détectés (4K tokens)
3. **Réduction** : 90% tokens pour queries single-domain

**Changements** :
- ✅ Ajout champ `domains: list[str]` au RouterOutput schema
- ✅ Ajout section "DOMAIN DETECTION" dans prompt
- ✅ Ajout keywords par domaine
- ✅ Exemples single-domain vs multi-domain

**Exemple 2 - Router v8: Anti-Hallucination Hardening** :

**Problème** : Router v7 consultait historique conversationnel et présumait absence de données → routait vers Response au lieu de Planner → hallucinations

**Solution v8** :
1. Règle #5 renforcée : "Router = analyseur syntaxique, PAS validateur de données"
2. Anti-patterns interdits dans `reasoning` : "aucun", "pas trouvé", "n'existe pas"
3. Auto-validation : Relire reasoning avant finalisation
4. Exemples génériques (domain-agnostic) pour pattern correct

**Changements** :
- ✅ Règle #5 expanded (200 → 800 tokens)
- ✅ Ajout 2 anti-patterns + 2 patterns corrects
- ✅ Auto-validation checklist
- ✅ Exemples génériques applicables à tous domaines futurs

---

## ⚡ Optimisation

### 1. Token Reduction

**Techniques** :

#### a) Prompt Compression

```markdown
# Avant (verbose)
Vous êtes un assistant intelligent et polyvalent capable de comprendre
les requêtes utilisateur dans de multiples domaines incluant mais non
limité à la gestion de contacts, l'envoi d'emails, la planification
de calendrier, et bien plus encore.

# Après (concis)
Tu es un routeur intelligent pour assistant conversationnel multi-agents.
Rôle: distinguer conversation vs tâche actionnable + détecter domaines.
```

**Réduction** : 60% tokens (45 → 18 tokens)

#### b) Exemples Génériques

```markdown
# Avant (spécifique à chaque domaine)
### Ex1: Recherche contact
User: "Recherche Jean"
Output: {"domains": ["contacts"], ...}

### Ex2: Recherche email
User: "Cherche emails de Marie"
Output: {"domains": ["email"], ...}

### Ex3: Recherche événement
User: "Trouve meeting demain"
Output: {"domains": ["calendar"], ...}

# Après (générique)
### Ex: Recherche [ENTITÉ]
User: "Recherche [ENTITÉ]" / "Cherche [ENTITÉ]" / "Trouve [ENTITÉ]"
Output: {"domains": ["[DOMAINE_PERTINENT]"], ...}

Note: [ENTITÉ] = contact/email/event, [DOMAINE] = contacts/email/calendar
```

**Réduction** : 70% tokens (90 → 27 tokens)

#### c) Structured Output (Pydantic)

```python
# Avant - Prompt includes JSON schema definition (100+ tokens)
"""
Output JSON avec ces champs:
- intention: string ("conversation"|"actionable"|"unclear")
- confidence: float entre 0.0 et 1.0
- context_label: string ("general"|"contact"|"email"|"calendar")
- next_node: string ("response"|"planner")
- domains: array de strings (ex: ["contacts"])
- reasoning: string expliquant la décision
"""

# Après - Pydantic schema (0 tokens in prompt, handled by .with_structured_output())
class RouterOutput(BaseModel):
    intention: Literal["conversation", "actionable", "unclear"]
    confidence: float = Field(ge=0.0, le=1.0)
    context_label: Literal["general", "contact", "email", "calendar"]
    next_node: Literal["response", "planner"]
    domains: list[str] = Field(default_factory=list)
    reasoning: str
```

**Réduction** : 100 tokens (schema déplacé vers code Python)

### 2. Caching OpenAI

**Principe** : OpenAI cache les prompts ≥ 1024 tokens automatiquement (50% cost reduction, 80% latency reduction)

**Optimisation** :

```python
# ✅ BON - Prompt stable ≥ 1024 tokens
ROUTER_SYSTEM_PROMPT = load_prompt("router_system_prompt.txt", version="v8")
# → Prompt = 3500 tokens → Cached après 1er call

router_prompt = ChatPromptTemplate.from_messages([
    ("system", ROUTER_SYSTEM_PROMPT),  # Static (cached)
    ("human", "{user_message}"),        # Dynamic (not cached)
])

# ❌ MAUVAIS - Prompt dynamique < 1024 tokens
router_prompt = ChatPromptTemplate.from_messages([
    ("system", f"You are a router. Current time: {datetime.now()}"),  # Dynamic → no cache
    ("human", "{user_message}"),
])
```

**Cache marker** : Ajouter marker unique dans prompt pour invalider cache si changement

```markdown
# Version 8.0 - Anti-Hallucination Hardening (2025-11-13)
# ...
# Cache marker: v8.0_20251113_antihallucination_hardening
```

**Bénéfices** :
- **Cost** : -50% (cached tokens coûtent 50% moins cher)
- **Latency** : -80% (pas de re-processing LLM)

### 3. Exemple Complet - Evolution Router v1 → v8

| Version | Tokens | Cost/call | Latency P95 | Optimisation |
|---------|--------|-----------|-------------|--------------|
| v1 | 1200 | $0.0012 | 800ms | Initial |
| v3 | 900 | $0.0009 | 700ms | Compression 25% |
| v7 | 3500 | $0.0018 | 500ms | +Domain detection, caching enabled |
| v8 | 3500 | $0.0009 | 100ms | Anti-hallucination, caching hits 90% |

**Réduction totale v1 → v8** :
- Cost: -25% (caching)
- Latency: -87% (caching)
- Quality: +40% (anti-hallucination fix)

---

## 📚 Best Practices

### 1. Structure de Prompt

**Template recommandé** :

```markdown
# [Node Name] System Prompt v[X]
# Purpose: [One-liner]
# Created: [Date]
# Base: v[X-1] + [Changes summary]

[Contexte et rôle - 2-3 phrases]

## JSON SCHEMA ATTENDU

[Schéma JSON exemple]

### Champs

[Description de chaque champ]

## RÈGLES

### Règle #1: [Nom]
[Description]

### Règle #2: [Nom]
[Description]

## EXEMPLES

[3-5 exemples concrets]

## PRINCIPES

[Principes directeurs]

---

Note: [Notes caching, optimisation]

# Version [X].0 - [Title] ([Date])
# - ADDED/FIXED/ENHANCED: [Change 1]
# - Cache marker: v[X].0_[date]_[identifier]
```

### 2. Rédaction Efficace

**DOs** ✅ :
- **Ton impératif** : "Tu es...", "Analyse...", "Génère..."
- **Exemples concrets** : Montrer input/output attendu
- **Anti-patterns explicites** : Montrer ce qu'il NE FAUT PAS faire
- **Règles numérotées** : Facile à référencer (Règle #5)
- **Sections claires** : Markdown headers (##, ###)
- **Concision** : 1 règle = 1 paragraphe max (sauf règles critiques)

**DON'Ts** ❌ :
- **Verbosité** : "Il est important de noter que..." → Supprimer
- **Ambiguïté** : "Généralement..." → Être spécifique
- **Redondance** : Répéter mêmes infos → Consolider
- **Jargon inutile** : Si technique nécessaire, expliquer
- **Exemples abstraits** : "[EXEMPLE]" → Donner vrais exemples

### 3. Testing et Validation

**Checklist avant déploiement** :

```python
# tests/agents/test_new_prompt_validation.py
import pytest
from src.domains.agents.nodes.new_node import new_node
from src.domains.agents.domain_schemas import MessagesState

@pytest.mark.asyncio
class TestNewPromptValidation:
    """Validation suite for new prompt."""

    async def test_happy_path(self):
        """Test standard use case works."""
        state = {...}  # Typical input
        result = await new_node(state)
        assert result["expected_field"] == "expected_value"

    async def test_edge_case_empty_input(self):
        """Test behavior with empty input."""
        state = {"messages": [], ...}
        result = await new_node(state)
        # Should handle gracefully, not crash

    async def test_edge_case_long_input(self):
        """Test behavior with very long input (10k+ tokens)."""
        state = {"messages": [HumanMessage(content="x" * 50000)], ...}
        result = await new_node(state)
        # Should truncate or summarize

    async def test_anti_hallucination(self):
        """Test prompt doesn't hallucinate (make up data)."""
        state = {...}  # Input without certain data
        result = await new_node(state)
        # Verify output doesn't invent missing info

    async def test_consistency_100_runs(self):
        """Test output is consistent across 100 runs (temperature=0)."""
        state = {...}
        results = [await new_node(state) for _ in range(100)]
        # All results should be identical (determinism)
        assert len(set(r["output"] for r in results)) == 1

    async def test_performance_latency(self):
        """Test latency is acceptable (<500ms P95)."""
        import time
        state = {...}
        latencies = []

        for _ in range(100):
            start = time.time()
            await new_node(state)
            latencies.append(time.time() - start)

        p95 = sorted(latencies)[94]  # 95th percentile
        assert p95 < 0.5, f"P95 latency {p95:.2f}s exceeds 500ms"

    async def test_cost_per_call(self):
        """Test cost per call is acceptable (<$0.01)."""
        # Mock token counter
        # Verify tokens input + output < threshold
        pass
```

### 4. Documentation

**Documenter dans ADR si** :
- Changement architectural majeur (ex: v7 domain filtering)
- Fix bug critique impactant prod (ex: v8 anti-hallucination)
- Trade-offs significatifs (ex: latency vs cost)

**Exemple ADR** :

```markdown
# ADR-009: Router Domain Detection for Dynamic Catalogue Loading

**Status**: ✅ Accepted
**Date**: 2025-11-10
**Authors**: @maintainers

## Context

Router v6 → Planner received ALL tools (40K+ tokens with 5 domains).
With 10+ planned domains, prompt would exceed 100K tokens (cost + latency explosion).

## Decision

Router v7 detects relevant domains → Planner loads filtered catalogue.

**Implementation**:
1. Add `domains: list[str]` field to RouterOutput schema
2. Router analyzes keywords → detects 1-3 domains
3. Planner loads only tools from detected domains

## Consequences

**Positives**:
- ✅ Token reduction: 90% (single-domain), 70% (dual-domain)
- ✅ Scalable: Linear O(n) instead of exponential
- ✅ Cost: -80% per Planner call
- ✅ Latency: -60% (smaller prompt = faster)

**Negatives**:
- ❌ Complexity: +1 field in schema, +domain detection logic
- ❌ Risk: Router might miss relevant domain (false negative)

**Mitigation**:
- Comprehensive keyword lists per domain
- Fallback: If Router unclear → load full catalogue
- Monitoring: Track domain detection accuracy in Grafana
```

---

## 🔍 Troubleshooting

### Problème 1 : LLM n'respecte pas le JSON schema

**Symptômes** :
```python
# Output attendu
{"intention": "actionable", "confidence": 0.9, ...}

# Output réel
"Intention: actionable, confidence: 0.9"  # String, pas JSON
```

**Causes** :
1. Prompt ne spécifie pas clairement "OUTPUT JSON UNIQUEMENT"
2. `.with_structured_output()` pas utilisé
3. Temperature trop élevée (>0.2)

**Solutions** :

```python
# ✅ Solution 1 - Pydantic structured output (recommandé)
llm = ChatOpenAI(model="gpt-4.1-mini-mini", temperature=0.0)
llm_with_schema = llm.with_structured_output(MySchema)

# ✅ Solution 2 - Explicit JSON instruction in prompt
"""
CRITICAL: Your output MUST be valid JSON matching this schema exactly:
```json
{"field1": "value", "field2": 123}
```

NO additional text, NO explanations, ONLY the JSON object.
"""

# ✅ Solution 3 - Response format parameter
llm = ChatOpenAI(
    model="gpt-4.1-mini-mini",
    temperature=0.0,
    model_kwargs={"response_format": {"type": "json_object"}}
)
```

### Problème 2 : Hallucinations (LLM invente des données)

**Symptômes** :
```python
# Input: "Recherche Jean" (aucun contact trouvé)
# Output Response: "Jean Dupont habite à Paris et travaille chez Acme Inc."
# → HALLUCINATION (données inventées)
```

**Causes** :
1. Prompt ne dit pas "NE PAS inventer"
2. LLM reçoit historique incomplet sans résultats d'API
3. Temperature trop élevée (>0.5)

**Solutions** :

```markdown
# ✅ Ajouter règle anti-hallucination explicite
## Règle #X: ZÉRO HALLUCINATION

**INTERDICTIONS ABSOLUES** :
- ❌ Inventer données non présentes dans le contexte fourni
- ❌ Extrapoler informations à partir de noms/prénoms
- ❌ Utiliser connaissances pré-entraînement pour compléter infos manquantes

**SI données manquantes** :
- ✅ Indiquer explicitement : "Aucune information disponible sur [X]"
- ✅ Proposer action alternative : "Voulez-vous effectuer une recherche ?"
- ✅ NE PAS combler les vides avec suppositions

**Validation avant output** :
1. Chaque affirmation factuelle provient-elle du contexte fourni ?
2. Si doute → NE PAS inclure l'affirmation
```

```python
# ✅ Température basse pour déterminisme
llm = ChatOpenAI(model="gpt-4.1-mini-mini", temperature=0.0)  # Pas 0.7

# ✅ Fournir contexte complet (résultats API)
prompt_with_context = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("human", "User query: {query}"),
    ("human", "API Results: {api_results}"),  # CRITIQUE
])

# Si api_results vide → LLM sait qu'il n'y a aucun résultat
```

### Problème 3 : Latence élevée (>1s)

**Symptômes** :
- Latence P95 > 1000ms
- Utilisateurs se plaignent de lenteur

**Causes** :
1. Prompt trop long (>10k tokens)
2. Pas de caching OpenAI (prompt <1024 tokens ou dynamique)
3. Model trop lent (gpt-4 au lieu de gpt-4.1-mini-mini)
4. Pas de parallélisation (calls séquentiels)

**Solutions** :

```python
# ✅ Optimiser prompt (compression, exemples génériques)
# Voir section "Optimisation" ci-dessus

# ✅ Activer caching OpenAI (prompt ≥ 1024 tokens)
# Vérifier que prompt est statique (pas de timestamps dynamiques)

# ✅ Utiliser model rapide pour tâches simples
# Router → gpt-4.1-nano (ultra-fast, 50ms)
# Response → gpt-4.1-mini (good quality)
# Planner complexe → gpt-4.1-mini (200ms)

llm_fast = ChatOpenAI(model="gpt-4.1-nano", temperature=0.0)
llm_smart = ChatOpenAI(model="gpt-4.1-mini", temperature=0.0)

# ✅ Paralléliser calls indépendants
import asyncio

results = await asyncio.gather(
    router_chain.ainvoke(input1),
    classifier_chain.ainvoke(input2),
    # Pas de dépendances → parallel execution
)
```

### Problème 4 : Coût élevé (>$0.10 par conversation)

**Symptômes** :
- Facture OpenAI explose
- Dashboard Grafana montre coût élevé

**Causes** :
1. Model trop cher (gpt-4.1-mini au lieu de gpt-4.1-mini-mini)
2. Pas de caching (prompt non optimisé)
3. Trop d'appels LLM (pourrait être remplacé par heuristiques)

**Solutions** :

```python
# ✅ Downgrade model si possible
# gpt-4.1-nano = 10x moins cher que gpt-4.1-mini
# Pour Router → gpt-4.1-nano suffit (95% accuracy)

# ✅ Activer caching (50% cost reduction)
# Prompt ≥ 1024 tokens + cache marker

# ✅ Réduire appels LLM via heuristiques
# Ex: Router pourrait utiliser regex pour "Bonjour" au lieu de LLM

def fast_heuristic_router(message: str) -> RouterOutput | None:
    """Fast heuristic router for common patterns."""
    message_lower = message.lower().strip()

    # Salutations
    if message_lower in ["bonjour", "hello", "salut", "hi", "hey"]:
        return RouterOutput(
            intention="conversation",
            confidence=0.99,
            next_node="response",
            domains=[],
            reasoning="Salutation simple (heuristique)"
        )

    # Pas de match → fallback LLM
    return None

async def router_node(state):
    # Try heuristic first
    heuristic_result = fast_heuristic_router(state["messages"][-1].content)
    if heuristic_result:
        return {"routing_decision": heuristic_result.model_dump()}

    # Fallback: LLM call
    result = await router_chain.ainvoke(...)
    return {"routing_decision": result.model_dump()}
```

**Monitoring** :

```python
# Grafana dashboard - Track cost per call
from prometheus_client import Histogram

llm_cost_histogram = Histogram(
    "llm_call_cost_usd",
    "Cost per LLM call in USD",
    ["node", "model"],
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1]
)

# After LLM call
llm_cost_histogram.labels(node="router", model="gpt-4.1-nano").observe(cost_usd)
```

---

## 📚 Ressources

### Documentation Interne

- [docs/technical/PROMPTS.md](../technical/PROMPTS.md) - Évolution prompts v1→v8
- [docs/technical/ROUTER.md](../technical/ROUTER.md) - Router Node détails
- [docs/technical/PLANNER.md](../technical/PLANNER.md) - Planner Node détails
- [docs/technical/RESPONSE.md](../technical/RESPONSE.md) - Response Node détails

### Ressources Externes

**Prompt Engineering** :
- [OpenAI Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
- [Anthropic Prompt Library](https://docs.anthropic.com/claude/prompt-library)
- [LangChain Prompt Templates](https://python.langchain.com/docs/modules/model_io/prompts/)

**Best Practices** :
- [Prompting Guide](https://www.promptingguide.ai/)
- [Learn Prompting](https://learnprompting.org/)

**Optimisation** :
- [OpenAI Caching](https://platform.openai.com/docs/guides/prompt-caching)
- [Token Counting](https://github.com/openai/tiktoken)

---

**Fin de GUIDE_PROMPTS.md**

*Document généré le 2025-11-14, mis à jour le 2025-12-27 dans le cadre du projet LIA*

**Version** : 1.1
**Dernière mise à jour** : 2025-12-27
