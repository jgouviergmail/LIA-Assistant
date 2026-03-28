# LIA — Guide Technique Complet

> Architecture, patterns et décisions d'ingénierie d'un assistant IA multi-agent de nouvelle génération.
>
> Documentation de présentation technique destinée aux architectes, ingénieurs et experts techniques.

**Version** : 2.1
**Date** : 2026-03-28
**Application** : LIA v1.13.0
**Licence** : AGPL-3.0 (Open Source)

---

## Table des matières

1. [Contexte et choix fondateurs](#1-contexte-et-choix-fondateurs)
2. [Stack technologique](#2-stack-technologique)
3. [Architecture backend : Domain-Driven Design](#3-architecture-backend--domain-driven-design)
4. [LangGraph : orchestration multi-agent](#4-langgraph--orchestration-multi-agent)
5. [Le pipeline d'exécution conversationnel](#5-le-pipeline-dexécution-conversationnel)
6. [Le système de planification (ExecutionPlan DSL)](#6-le-système-de-planification-executionplan-dsl)
7. [Smart Services : optimisation intelligente](#7-smart-services--optimisation-intelligente)
8. [Routage sémantique et embeddings locaux](#8-routage-sémantique-et-embeddings-locaux)
9. [Human-in-the-Loop : architecture à 6 couches](#9-human-in-the-loop--architecture-à-6-couches)
10. [Gestion du state et message windowing](#10-gestion-du-state-et-message-windowing)
11. [Système de mémoire et profil psychologique](#11-système-de-mémoire-et-profil-psychologique)
12. [Infrastructure LLM multi-provider](#12-infrastructure-llm-multi-provider)
13. [Connecteurs : abstraction multi-fournisseur](#13-connecteurs--abstraction-multi-fournisseur)
14. [MCP : Model Context Protocol](#14-mcp--model-context-protocol)
15. [Système de voix (STT/TTS)](#15-système-de-voix-stttts)
16. [Proactivité : Heartbeat et actions planifiées](#16-proactivité--heartbeat-et-actions-planifiées)
17. [RAG Spaces et recherche hybride](#17-rag-spaces-et-recherche-hybride)
18. [Browser Control et Web Fetch](#18-browser-control-et-web-fetch)
19. [Sécurité : defence in depth](#19-sécurité--defence-in-depth)
20. [Observabilité et monitoring](#20-observabilité-et-monitoring)
21. [Performance : optimisations et métriques](#21-performance--optimisations-et-métriques)
22. [CI/CD et qualité](#22-cicd-et-qualité)
23. [Patterns d'ingénierie transversaux](#23-patterns-dingénierie-transversaux)
24. [Architecture des décisions (ADR)](#24-architecture-des-décisions-adr)
25. [Potentiel d'évolution et extensibilité](#25-potentiel-dévolution-et-extensibilité)

---

## 1. Contexte et choix fondateurs

### 1.1. Pourquoi ces choix ?

Chaque décision technique de LIA répond à une contrainte concrète. Le projet vise un assistant IA multi-agent **auto-hébergeable sur hardware modeste** (Raspberry Pi 5, ARM64), avec une transparence totale, une souveraineté des données, et un support multi-fournisseur LLM. Ces contraintes ont guidé l'intégralité de la stack.

| Contrainte | Conséquence architecturale |
|------------|--------------------------|
| Auto-hébergement ARM64 | Docker multi-arch, embeddings locaux E5 (pas de dépendance API), Playwright chromium cross-platform |
| Souveraineté des données | PostgreSQL local (pas de SaaS DB), chiffrement Fernet au repos, sessions Redis locales |
| Multi-fournisseur LLM | Factory pattern avec 7 adaptateurs, configuration par nœud, pas de couplage fort à un provider |
| Transparence totale | 350+ métriques Prometheus, debug panel embarqué, suivi token par token |
| Fiabilité en production | 59 ADRs, 2 300+ tests, observabilité native, HITL à 6 niveaux |
| Coûts maîtrisés | Smart Services (89 % d'économie tokens), embeddings locaux, prompt caching, filtrage de catalogue |

### 1.2. Principes architecturaux

| Principe | Implémentation |
|----------|----------------|
| **Domain-Driven Design** | Bounded contexts dans `src/domains/`, agrégats explicites, couches Router/Service/Repository/Model |
| **Hexagonal Architecture** | Ports (protocols Python) et adaptateurs (clients concrets Google/Microsoft/Apple) |
| **Event-Driven** | SSE streaming, ContextVar propagation, fire-and-forget background tasks |
| **Defence in Depth** | 5 couches pour les usage limits, 6 niveaux HITL, 3 couches anti-hallucination |
| **Feature Flags** | Chaque sous-système activable/désactivable (`{FEATURE}_ENABLED`) |
| **Configuration as Code** | Pydantic BaseSettings composé via MRO, chaîne de priorité APPLICATION > .ENV > CONSTANT |

### 1.3. Métriques du codebase

| Métrique | Valeur |
|----------|--------|
| Tests | 2 300+ (unit, integration, agents, benchmark) |
| Fixtures réutilisables | 170+ |
| Documents de documentation | 190+ |
| ADRs (Architecture Decision Records) | 59 |
| Métriques Prometheus | 350+ définitions |
| Dashboards Grafana | 18 |
| Langues supportées (i18n) | 6 (fr, en, de, es, it, zh) |

---

## 2. Stack technologique

### 2.1. Backend

| Technologie | Version | Rôle | Pourquoi ce choix |
|-------------|---------|------|-------------------|
| Python | 3.12+ | Runtime | Écosystème ML/IA le plus riche, async natif, typing complet |
| FastAPI | 0.135.1 | API REST + SSE | Validation auto Pydantic, docs OpenAPI, async-first, performances |
| LangGraph | 1.1.2 | Orchestration multi-agent | Seul framework offrant state persistence + cycles + interrupts (HITL) natifs |
| LangChain Core | 1.2.19 | Abstractions LLM/tools | Décorateur `@tool`, formats de messages, callbacks standardisés |
| SQLAlchemy | 2.0.48 | ORM async | `Mapped[Type]` + `mapped_column()`, async sessions, `selectinload()` |
| PostgreSQL | 16 + pgvector | Database + vector search | Checkpoints LangGraph natifs, recherche sémantique HNSW, maturité |
| Redis | 7.3.0 | Cache, sessions, rate limiting | O(1) ops, sliding window atomique (Lua), SETNX leader election |
| Pydantic | 2.12.5 | Validation + sérialisation | `ConfigDict`, `field_validator`, composition de settings via MRO |
| structlog | latest | Logging structuré | JSON output avec filtrage PII automatique, snake_case events |
| sentence-transformers | 5.0+ | Embeddings locaux | E5-small multilingue (384d), zéro coût API, ~50 ms sur ARM64 |
| Playwright | latest | Browser automation | Chromium headless, CDP accessibility tree, cross-platform |
| APScheduler | 3.x | Background jobs | Cron/interval triggers, compatible leader election Redis |

### 2.2. Frontend

| Technologie | Version | Rôle |
|-------------|---------|------|
| Next.js | 16.1.7 | App Router, SSR, ISR |
| React | 19.2.4 | UI avec Server Components |
| TypeScript | 5.9.3 | Typage strict |
| TailwindCSS | 4.2.1 | Utility-first CSS |
| TanStack Query | 5.90 | Server state management, cache, mutations |
| Radix UI | v2 | Primitives UI accessibles |
| react-i18next | 16.5 | i18n (6 langues), namespace-based |
| Zod | 3.x | Validation runtime des schémas debug |

### 2.3. LLM Providers supportés

| Provider | Modèles | Spécificités |
|----------|---------|-------------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.x, GPT-4.1-x, o1, o3-mini | Prompt caching natif, Responses API, reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5/4, Sonnet 4.6/4.5/4, Haiku 4.5 | Extended thinking, prompt caching |
| Google | Gemini 3.1/3/2.5 Pro, Flash 3/2.5/2.0 | Multimodal, TTS HD |
| DeepSeek | V3 (chat), R1 (reasoner) | Coût réduit, reasoning natif |
| Perplexity | sonar-small/large-128k-online | Search-augmented generation |
| Qwen | qwen3-max, qwen3.5-plus, qwen3.5-flash | Thinking mode, tools + vision (Alibaba Cloud) |
| Ollama | Tout modèle local (découverte dynamique) | Zéro coût API, auto-hébergé |

**Pourquoi 7 providers ?** Le choix n'est pas la collection pour elle-même. C'est une stratégie de résilience : chaque nœud du pipeline peut être assigné à un provider différent. Si OpenAI augmente ses tarifs, le routeur passe sur DeepSeek. Si Anthropic a une panne, la réponse bascule sur Gemini. L'abstraction LLM (`src/infrastructure/llm/factory.py`) utilise le pattern Factory avec `init_chat_model()`, surchargé par des adaptateurs spécifiques (`ResponsesLLM` pour l'API Responses d'OpenAI, éligibilité par regex `^(gpt-4\.1|gpt-5|o[1-9])`).

---

## 3. Architecture backend : Domain-Driven Design

### 3.1. Structure des domaines

```
apps/api/src/
├── core/                         # Noyau technique transversal
│   ├── config/                   # 9 modules Pydantic BaseSettings composés via MRO
│   │   ├── __init__.py           # Classe Settings (MRO finale)
│   │   ├── agents.py, database.py, llm.py, mcp.py, voice.py, usage_limits.py, ...
│   ├── constants.py              # 1 000+ constantes centralisées
│   ├── exceptions.py             # Exceptions centralisées (raise_user_not_found, etc.)
│   └── i18n.py                   # Bridge i18n → settings
│
├── domains/                      # Bounded Contexts (DDD)
│   ├── agents/                   # DOMAINE PRINCIPAL — orchestration LangGraph
│   │   ├── nodes/                # 7+ nœuds du graphe
│   │   ├── services/             # Smart Services, HITL, context resolution
│   │   ├── tools/                # Outils par domaine (@tool + ToolResponse)
│   │   ├── orchestration/        # ExecutionPlan, parallel executor, validators
│   │   ├── registry/             # AgentRegistry, domain_taxonomy, catalogue
│   │   ├── semantic/             # Semantic router, expansion service
│   │   ├── middleware/           # Memory injection, personality injection
│   │   ├── prompts/v1/           # 57 fichiers .txt de prompts versionnés
│   │   ├── graphs/               # 15 builders d'agents (un par domaine)
│   │   ├── context/              # Context store (Data Registry), decorators
│   │   └── models.py             # MessagesState (TypedDict + custom reducer)
│   ├── auth/                     # OAuth 2.1, sessions BFF, RBAC
│   ├── connectors/               # Abstraction multi-provider (Google/Apple/Microsoft)
│   ├── rag_spaces/               # Upload, chunking, embedding, retrieval hybride
│   ├── journals/                 # Carnets de bord introspectifs
│   ├── interests/                # Apprentissage des centres d'intérêt
│   ├── heartbeat/                # Notifications proactives LLM-driven
│   ├── channels/                 # Multi-canal (Telegram)
│   ├── voice/                    # TTS Factory, STT Sherpa, Wake Word
│   ├── skills/                   # Standard agentskills.io
│   ├── sub_agents/               # Agents spécialisés persistants
│   ├── usage_limits/             # Quotas par utilisateur (5-layer defence)
│   └── ...                       # conversations, reminders, scheduled_actions, users, user_mcp
│
└── infrastructure/               # Couche transversale
    ├── llm/                      # Factory, providers, adapters, embeddings, tracking
    ├── cache/                    # Redis sessions, LLM cache, JSON helpers
    ├── mcp/                      # MCP client pool, auth, SSRF, tool adapters, Excalidraw
    ├── browser/                  # Playwright session pool, CDP, anti-détection
    ├── rate_limiting/            # Redis sliding window distribué
    ├── scheduler/                # APScheduler, leader election, locks
    └── observability/            # 17+ fichiers de métriques Prometheus, tracing OTel
```

### 3.2. Chaîne de priorité de configuration

Un invariant fondamental traverse tout le backend. Il a été systématiquement enforci en v1.9.4 avec ~291 corrections sur ~80 fichiers, parce que des divergences entre constantes et configuration réelle de production causaient des bugs silencieux :

```
APPLICATION (Admin UI / DB) > .ENV (settings) > CONSTANT (fallback)
```

**Pourquoi cette chaîne ?** Les constantes (`src/core/constants.py`) servent exclusivement de fallback pour les `Field(default=...)` Pydantic et les `server_default=` SQLAlchemy. Un administrateur qui change un modèle LLM depuis l'interface doit voir ce changement pris en compte immédiatement, sans redéploiement. En runtime, tout code lit `settings.field_name`, jamais directement une constante.

### 3.3. Patterns de couches

| Couche | Responsabilité | Pattern clé |
|--------|---------------|-------------|
| **Router** | Validation HTTP, auth, sérialisation | `Depends(get_current_active_session)`, `check_resource_ownership()` |
| **Service** | Logique métier, orchestration | Constructeur reçoit `AsyncSession`, crée repositories, exceptions centralisées |
| **Repository** | Accès données | Hérite `BaseRepository[T]`, pagination `tuple[list[T], int]` |
| **Model** | Schéma DB | `Mapped[Type]` + `mapped_column()`, `UUIDMixin`, `TimestampMixin` |
| **Schema** | Validation I/O | Pydantic v2, `Field()` avec description, request/response séparés |

---

## 4. LangGraph : orchestration multi-agent

### 4.1. Pourquoi LangGraph ? (ADR-001)

Le choix de LangGraph plutôt que LangChain seul, CrewAI, ou AutoGen repose sur trois besoins non négociables :

1. **State persistence** : `TypedDict` avec reducers custom, persisté via PostgreSQL checkpoints — permet de reprendre une conversation après interruption HITL
2. **Cycles et interrupts** : support natif des boucles (rejet HITL → re-planification) et du pattern `interrupt()` — sans lequel le HITL à 6 couches serait impossible
3. **Streaming SSE** : intégration native avec callback handlers — critique pour l'UX temps réel

CrewAI et AutoGen étaient plus simples à prendre en main, mais ni l'un ni l'autre ne supportait le pattern interrupt/resume nécessaire au HITL plan-level. Ce choix a un coût : la courbe d'apprentissage est plus raide (concepts de graphes, edges conditionnels, state schemas).

### 4.2. Le graphe principal

```
                    ┌──────────────────────────────────┐
                    │        Router Node (v3)            │
                    │  Binaire : conversation|actionable  │
                    │  Confiance : high > 0.85            │
                    └──────┬──────────┬─────────────────┘
                           │          │
              conversation │          │ actionable
                           │          │
                    ┌──────▼──┐  ┌───▼───────────────────┐
                    │ Response │  │  QueryAnalyzer          │
                    │  Node    │  │  + SmartPlanner          │
                    └──────────┘  └───┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Semantic Validator       │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Approval Gate           │
                                │   (HITL interrupt)        │
                                └─────┬───────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │  Task Orchestrator        │
                                │  (parallel executor)      │
                                └─────┬───────────────────┘
                                      │
                    ┌─────────────────▼────────────────────┐
                    │      15 Domain Agents                  │
                    │  + MCP dynamic agents                  │
                    │  + Sub-agent delegation                │
                    └─────────────────┬────────────────────┘
                                      │
                                ┌─────▼───────────────────┐
                                │   Response Node           │
                                │  (anti-hallucination)     │
                                └───────────────────────────┘
```

### 4.3. Nœuds du graphe

| Nœud | Fichier | Rôle | Windowing |
|------|---------|------|-----------|
| Router v3 | `router_node_v3.py` | Classification binaire conversation/actionable | 5 turns |
| QueryAnalyzer | `query_analyzer_service.py` | Détection de domaines, extraction d'intent | — |
| Planner v3 | `planner_node_v3.py` | Génération ExecutionPlan DSL | 10 turns |
| Semantic Validator | `semantic_validator.py` | Validation des dépendances et cohérence | — |
| Approval Gate | `hitl_dispatch_node.py` | HITL interrupt(), 6 niveaux d'approbation | — |
| Task Orchestrator | `task_orchestrator_node.py` | Exécution parallèle, passage de contexte | — |
| Response | `response_node.py` | Synthèse anti-hallucination, 3 couches de garde | 20 turns |

### 4.4. AgentRegistry et Domain Taxonomy

Le `AgentRegistry` centralise l'enregistrement des agents (`registry.register_agent()` dans `main.py`), le catalogue de `ToolManifest`, et la `domain_taxonomy.py` qui définit chaque domaine avec son `result_key` et ses alias.

**Pourquoi un registre centralisé ?** Sans lui, l'ajout d'un agent nécessitait de modifier 5+ fichiers. Avec le registre, un nouvel agent se déclare en un seul point et est automatiquement disponible pour le routage, la planification et l'exécution.

### 4.5. Domain Taxonomy

Chaque domaine est un `DomainConfig` déclaratif : nom, agents, `result_key` (clé canonique pour les références `$steps`), `related_domains`, priorité et routabilité. Le `DOMAIN_REGISTRY` est la source de vérité unique consommée par trois sous-systèmes : SmartCatalogue (filtrage), expansion sémantique (domaines adjacents) et phase Initiative (pré-filtre structurel).

### 4.6. Tool Manifests

Chaque tool déclare un `ToolManifest` via un `ToolManifestBuilder` fluide : paramètres, sorties, profil de coût, permissions et `semantic_keywords` multilingues pour le routage. Les manifestes sont consommés par le planner (injection de catalogue), le routeur sémantique (matching par mots-clés) et le builder d'agents (câblage des tools). Voir section 23 pour l'architecture complète des tools.

---

## 5. Le pipeline d'exécution conversationnel

### 5.1. Flux détaillé d'une requête actionnable

1. **Réception** : Message utilisateur → endpoint SSE `/api/v1/chat/stream`
2. **Contexte** : `request_tool_manifests_ctx` ContextVar construit une fois (ADR-061 : 3-layer defence)
3. **Router** : Classification binaire avec scoring de confiance (high > 0.85, medium > 0.65)
4. **QueryAnalyzer** : Identifie les domaines via LLM + validation post-expansion (gate-keeper qui filtre les domaines désactivés)
5. **SmartPlanner** : Génère un `ExecutionPlan` (DSL JSON structuré)
   - Pattern Learning : consulte le cache bayésien (bypass si confiance > 90 %)
   - Skill detection : les Skills déterministes sont protégés via `_has_potential_skill_match()`
6. **Semantic Validator** : Vérifie la cohérence des dépendances inter-étapes
7. **HITL Dispatch** : Classifie le niveau d'approbation, `interrupt()` si nécessaire
8. **Task Orchestrator** : Exécute les étapes en vagues parallèles via `asyncio.gather()`
   - Filtre les étapes skipped AVANT gather (ADR-005 — corrige un bug de double exécution plan+fallback)
   - Passage de contexte via Data Registry (InMemoryStore)
   - Pattern FOR_EACH pour itérations en masse
9. **Response Node** : Synthétise les résultats, injection mémoire + journaux + RAG
10. **SSE Stream** : Token par token vers le frontend
11. **Background tasks** (fire-and-forget) : extraction mémoire, extraction journal, détection d'intérêts

### 5.2. ContextVar : propagation implicite de l'état

Un mécanisme critique est l'utilisation des `ContextVar` Python pour propager l'état sans parameter threading :

| ContextVar | Rôle | Pourquoi |
|------------|------|----------|
| `current_tracker` | TrackingContext pour le suivi tokens LLM | Évite de passer un tracker à travers 15 couches de fonctions |
| `request_tool_manifests_ctx` | Manifestes d'outils filtrés par requête | Construit une fois, lu par 7+ consommateurs (élimine duplication ADR-061) |

Cette approche maintient une isolation par requête dans un contexte asyncio sans polluer les signatures de fonctions.

---

## 6. Le système de planification (ExecutionPlan DSL)

### 6.1. Structure du plan

```python
ExecutionPlan(
    steps=[
        ExecutionStep(
            step_id="get_meetings",
            tool_name="get_events",
            parameters={"date": "tomorrow"},
            dependencies=[]
        ),
        ExecutionStep(
            step_id="send_reminders",
            tool_name="send_email",
            parameters={"subject": "Rappel réunion"},
            dependencies=["get_meetings"],
            for_each="$steps.get_meetings.events",
            for_each_max=10
        )
    ]
)
```

### 6.2. Pattern FOR_EACH

**Pourquoi un pattern dédié ?** Les opérations en masse (envoyer un email à 12 contacts) ne peuvent pas être planifiées comme 12 étapes statiques — le nombre d'éléments est inconnu avant l'exécution de l'étape précédente. Le FOR_EACH résout ce problème avec des garde-fous :
- Seuil HITL : toute mutation >= 1 élément déclenche une approbation obligatoire
- Limite configurable : `for_each_max` prévient les exécutions non bornées
- Référence dynamique : `$steps.{step_id}.{field}` pour les résultats d'étapes précédentes

### 6.3. Exécution parallèle en vagues

Le `parallel_executor.py` organise les étapes en vagues (DAG) :
1. Identifie les étapes sans dépendances non résolues → vague suivante
2. Filtre les étapes skipped (conditions non remplies, branches fallback) — **avant** `asyncio.gather()`, pas après (ADR-005 : corrige un bug qui causait 2x appels API et 2x coûts)
3. Exécute la vague avec isolation d'erreur par étape
4. Alimente le Data Registry avec les résultats
5. Répète jusqu'à complétion du plan

### 6.4. Validateur Sémantique

Avant l'approbation HITL, un LLM dédié (distinct du planner, pour éviter le biais d'auto-validation) inspecte le plan selon 14 types d'anomalies répartis en quatre catégories : **Critique** (capacité hallucinée, dépendance fantôme, cycle logique), **Sémantique** (incohérence de cardinalité, débordement/sous-couverture de périmètre, paramètres incorrects), **Sécurité** (ambiguïté dangereuse, hypothèse implicite) et **FOR_EACH** (cardinalité manquante, référence invalide). Court-circuit pour les plans triviaux (1 étape), timeout optimiste de 1 s.

### 6.5. Validation des Références

Les références inter-étapes (`$steps.get_meetings.events[0].title`) sont validées au moment du plan avec des messages d'erreur structurés : champ invalide, alternatives disponibles et exemples corrigés — permettant au planner de s'auto-corriger lors d'un retry au lieu de produire des échecs silencieux.

### 6.6. Re-Planner Adaptatif (Panic Mode)

En cas d'échec d'exécution, un analyseur rule-based (sans LLM) classifie le pattern d'échec (résultats vides, échec partiel, timeout, erreur de référence) et sélectionne une stratégie de recovery : retry identique, replan avec périmètre élargi, escalade utilisateur ou abandon. En **Panic Mode**, le SmartCatalogue s'élargit pour inclure tous les outils lors d'un unique retry — résolvant les cas où le filtrage par domaine était trop agressif.

---

## 7. Smart Services : optimisation intelligente

### 7.1. Le problème résolu

Sans optimisation, le scaling à 10+ domaines faisait exploser les coûts : passer de 3 outils (contacts) à 30+ outils (10 domaines) multipliait par 10 la taille du prompt et donc le coût par requête (ADR-003). Les Smart Services ont été conçus pour ramener ce coût au niveau d'un système mono-domaine.

| Service | Rôle | Mécanisme | Gain mesuré |
|---------|------|-----------|-------------|
| `QueryAnalyzerService` | Décision de routage | Cache LRU (TTL 5 min) | ~35 % cache hit |
| `SmartPlannerService` | Génération de plans | Pattern Learning bayésien | Bypass > 90 % confiance |
| `SmartCatalogueService` | Filtrage d'outils | Filtrage par domaine | 96 % réduction tokens |
| `PlanPatternLearner` | Apprentissage | Scoring bayésien Beta(2,1) | ~2 300 tokens évités par replan |

### 7.2. PlanPatternLearner

**Fonctionnement** : Quand un plan est validé et exécuté avec succès, sa séquence d'outils est enregistrée dans Redis (hash `plan:patterns:{tool→tool}`, TTL 30 jours). Pour les futures requêtes, un score bayésien est calculé : `confiance = (α + succès) / (α + β + succès + échecs)`. Au-dessus de 90 %, le plan est réutilisé directement sans appel LLM.

**Garde-fous** : K-anonymité (minimum 3 observations pour suggestion, 10 pour bypass), matching exact de domaines, maximum 3 patterns injectés (~45 tokens overhead), timeout strict de 5 ms.

**Amorçage** : 50+ golden patterns prédéfinis au démarrage, chacun avec 20 succès simulés (= 95,7 % de confiance initiale).

### 7.3. QueryIntelligence

Le QueryAnalyzer produit bien plus qu'une détection de domaines — il génère une structure `QueryIntelligence` profonde : intent immédiat vs objectif final (`UserGoal` : FIND_INFORMATION, TAKE_ACTION, COMMUNICATE...), intents implicites (ex : « trouver un contact » signifie probablement « envoyer quelque chose »), stratégies de fallback anticipées, indices de cardinalité FOR_EACH et scores de confiance par domaine calibrés par softmax. Cela donne au planner une vision plus riche qu'une simple extraction de mots-clés.

### 7.4. Pivot Sémantique

Les requêtes en toute langue sont automatiquement traduites en anglais avant la comparaison d'embeddings, améliorant la précision cross-lingue. Cache Redis (TTL 5 min, ~5 ms en hit vs ~500 ms en miss), via un LLM rapide.

---

## 8. Routage sémantique et embeddings locaux

### 8.1. Pourquoi des embeddings locaux ? (ADR-049)

Le routage purement LLM avait deux problèmes : coût (chaque requête = un appel LLM) et précision (le LLM se trompait sur les domaines dans ~20 % des cas multi-domaines). Les embeddings locaux résolvent les deux :

| Propriété | Valeur |
|-----------|--------|
| Modèle | multilingual-e5-small |
| Dimensions | 384 |
| Latence | ~50 ms (ARM64 Pi 5) |
| Coût API | Zéro |
| Langues | 100+ |
| Gain précision | +48 % sur Q/A matching vs routage LLM seul |

### 8.2. Semantic Tool Router (ADR-048)

Chaque `ToolManifest` possède des `semantic_keywords` multilingues. La requête est transformée en embedding, puis comparée par similarité cosinus avec **max-pooling** (score = MAX par outil, pas moyenne — évite la dilution sémantique). Double seuil : >= 0.70 = haute confiance, 0.60-0.70 = incertitude.

### 8.3. Semantic Expansion

Le `expansion_service.py` enrichit les résultats en explorant les domaines adjacents. La validation post-expansion (ADR-061, Layer 1) filtre les domaines désactivés par l'administrateur — corrigeant un bug où le LLM ou l'expansion pouvaient réintroduire des domaines qui avaient été désactivés.

---

## 9. Human-in-the-Loop : architecture à 6 couches

### 9.1. Pourquoi au niveau du plan ? (Phase 7 → Phase 8)

L'approche initiale (Phase 7) interrompait l'exécution **pendant** les appels d'outils — chaque outil sensible générait une interruption. L'UX était médiocre (pauses inattendues) et le coût élevé (overhead par outil).

La Phase 8 (actuelle) soumet le **plan complet** à l'utilisateur **avant** toute exécution. Une seule interruption, une vision globale, la possibilité d'éditer les paramètres. Le compromis : il faut faire confiance au planificateur pour produire un plan fidèle.

### 9.2. Les 6 types d'approbation

| Type | Déclencheur | Mécanisme |
|------|-------------|-----------|
| `PLAN_APPROVAL` | Actions destructrices | `interrupt()` avec PlanSummary |
| `CLARIFICATION` | Ambiguïté détectée | `interrupt()` avec question LLM |
| `DRAFT_CRITIQUE` | Email/event/contact draft | `interrupt()` avec brouillon sérialisé + template markdown |
| `DESTRUCTIVE_CONFIRM` | Suppression >= 3 éléments | `interrupt()` avec avertissement irréversibilité |
| `FOR_EACH_CONFIRM` | Mutations en masse | `interrupt()` avec décompte opérations |
| `MODIFIER_REVIEW` | Modifications IA suggérées | `interrupt()` avec comparaison before/after |

### 9.3. Draft Critique enrichi

Pour les brouillons, un prompt dédié génère une critique structurée avec templates markdown par domaine, emojis de champs, comparaison before/after avec strikethrough pour les mises à jour, et avertissements d'irréversibilité. Les résultats post-HITL affichent labels i18n et liens cliquables.

### 9.4. Classification des Réponses

Lorsque l'utilisateur répond à un prompt d'approbation, un classifieur full-LLM (pas de regex) catégorise la réponse en 5 décisions : **APPROVE**, **REJECT**, **EDIT** (même action, paramètres différents), **REPLAN** (action entièrement différente) ou **AMBIGUOUS**. Une logique de démotion prévient les faux positifs : un EDIT avec paramètres manquants est rétrogradé en AMBIGUOUS, déclenchant une clarification.

### 9.5. Compaction Safety

4 conditions empêchent la compaction LLM (résumé des anciens messages) pendant les flux d'approbation actifs. Sans cette protection, un résumé pourrait supprimer le contexte critique d'une interruption en cours.

---

## 10. Gestion du state et message windowing

### 10.1. MessagesState et reducer custom

Le state LangGraph est un `TypedDict` avec un reducer `add_messages_with_truncate` qui gère le truncation basé sur les tokens, la validation des séquences de messages OpenAI, et la déduplication des messages tool.

### 10.2. Pourquoi le windowing par nœud ? (ADR-007)

**Le problème** : une conversation de 50+ messages générait 100k+ tokens de contexte, avec une latence > 10 s pour le routeur et une explosion des coûts.

**La solution** : chaque nœud opère sur une fenêtre différente, calibrée sur son besoin réel :

| Nœud | Turns | Justification |
|------|-------|---------------|
| Router | 5 | Décision rapide, contexte minimal suffit |
| Planner | 10 | Besoin de contexte pour planifier, mais pas de tout l'historique |
| Response | 20 | Contexte riche pour synthèse naturelle |

**Impact mesuré** : latence E2E -50 % (10 s → 5 s), coût -77 % sur les conversations longues, qualité préservée grâce au Data Registry qui stocke les résultats d'outils indépendamment des messages.

### 10.3. Context Compaction

Quand le nombre de tokens dépasse un seuil dynamique (ratio du context window du modèle de réponse), un résumé LLM est généré. Les identifiants critiques (UUIDs, URLs, emails) sont préservés. Ratio d'économie : ~60 % par compaction. Commande `/resume` pour déclenchement manuel.

### 10.4. Checkpointing PostgreSQL

State complet checkpointé après chaque nœud. P95 save < 50 ms, P95 load < 100 ms, taille moyenne ~15 KB/conversation.

---

## 11. Système de mémoire et profil psychologique

### 11.1. Architecture

```
AsyncPostgresStore + Semantic Index (pgvector)
├── Namespace: (user_id, "memories")        → Profil psychologique
├── Namespace: (user_id, "documents", src)  → RAG documentaire
└── Namespace: (user_id, "context", domain) → Contexte outils (Data Registry)
```

### 11.2. Schéma de mémoire enrichi

Chaque souvenir est un document structuré avec :
- `content`, `category` (préférence, fait, personnalité, relation, sensibilité...)
- `importance` (1-10), `emotional_weight` (-10 à +10)
- `usage_nuance` : comment utiliser cette information de manière bienveillante
- Embedding `text-embedding-3-small` (1536d) via pgvector HNSW

**Pourquoi un poids émotionnel ?** Un assistant qui sait que votre mère est malade mais traite ce fait comme n'importe quelle donnée est au mieux maladroit, au pire blessant. Le poids émotionnel permet d'activer la `DANGER_DIRECTIVE` (interdiction de plaisanter, minimiser, comparer, banaliser) quand un sujet sensible est touché.

### 11.3. Extraction et injection

**Extraction** : après chaque conversation, un processus background analyse le dernier message utilisateur, adapté à la personnalité active. Coût suivi via `TrackingContext`.

**Injection** : le middleware `memory_injection.py` recherche les mémoires sémantiquement proches, construit le profil psychologique injectable, et active la `DANGER_DIRECTIVE` si nécessaire. Injection dans le prompt système du Response Node.

### 11.4. Recherche hybride BM25 + sémantique

Combinaison avec alpha configurable (défaut 0.6 sémantique / 0.4 BM25). Boost de 10 % quand les deux signaux sont forts (> 0.5). Fallback gracieux vers sémantique seul si BM25 échoue. Performance : 40-90 ms avec cache.

### 11.5. Carnets de bord (Journals)

L'assistant tient des réflexions introspectives en quatre thèmes équilibrés (auto-réflexion, observations utilisateur, idées/analyses, apprentissages) avec un guide de classification neutre qui évite la surconcentration dans un seul thème. Deux déclencheurs : extraction post-conversation + consolidation périodique (4h). Embeddings OpenAI 1536d avec `search_hints` (mots-clés LLM dans le vocabulaire utilisateur). Injection dans le prompt du **Response Node et du Planner Node** — ce dernier utilise `intelligence.original_query` comme requête sémantique.

**Garde-fou sémantique de dédup** (v1.12.1) : Avant de créer une nouvelle entrée, le système vérifie la similarité sémantique avec les entrées existantes. Si un match dépasse le seuil configurable (`JOURNAL_DEDUP_SIMILARITY_THRESHOLD`, défaut 0.72), un LLM de fusion combine toutes les entrées correspondantes en une seule directive enrichie — consolidation N→1 avec suppression des entrées secondaires. Dégradation gracieuse en cas d'échec.

Anti-hallucination UUID : `field_validator`, table de référence d'IDs, filtrage par IDs connus dans extraction et consolidation.

### 11.6. Système d'intérêts

Détection par analyse des requêtes avec évolution bayésienne des poids (decay 0.01/jour). Notifications proactives multi-source (Wikipedia, Perplexity, LLM). Feedback utilisateur (thumbs up/down/block) ajuste les poids.

---

## 12. Infrastructure LLM multi-provider

### 12.1. Factory Pattern

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

Le `get_llm()` résout la configuration effective via `get_llm_config_for_agent(settings, agent_type)` (code defaults → DB admin overrides), instancie le modèle, et applique les adaptateurs spécifiques.

### 12.2. 34 types de configuration LLM

Chaque nœud du pipeline est configurable indépendamment via l'Admin UI — sans redéploiement :

| Catégorie | Types configurables |
|-----------|-------------------|
| Pipeline | router, query_analyzer, planner, semantic_validator, context_resolver |
| Réponse | response, hitl_question_generator |
| Background | memory_extraction, interest_extraction, journal_extraction, journal_consolidation |
| Agents | contacts_agent, emails_agent, calendar_agent, browser_agent, etc. |

### 12.3. Token Tracking

Le `TrackingContext` suit chaque appel LLM avec `call_type` ("chat"/"embedding"), `sequence` (compteur monotone), `duration_ms`, tokens (input/output/cache), et coût calculé depuis les tarifs DB. Les trackers partagent un `run_id` pour l'agrégation. Le debug panel affiche toutes les invocations (pipeline + background tasks) dans une vue unifiée chronologique.

---

## 13. Connecteurs : abstraction multi-fournisseur

### 13.1. Architecture par protocoles

```
ConnectorTool (base.py) → ClientRegistry → resolve_client(type) → Protocol
     ├── GoogleGmailClient       implements EmailClientProtocol
     ├── MicrosoftOutlookClient  implements EmailClientProtocol
     ├── AppleEmailClient        implements EmailClientProtocol
     └── PhilipsHueClient        implements SmartHomeClientProtocol
```

**Pourquoi des protocoles Python ?** Le duck typing structurel permet d'ajouter un nouveau provider sans modifier le code appelant. Le `ProviderResolver` garantit qu'un seul fournisseur est actif par catégorie fonctionnelle.

### 13.2. Normalizers

Chaque provider retourne des données dans son propre format. Des normalizers dédiés (`calendar_normalizer`, `contacts_normalizer`, `email_normalizer`, `tasks_normalizer`) convertissent les réponses spécifiques à chaque provider en modèles de domaine unifiés. Ajouter un nouveau provider nécessite uniquement d'implémenter le protocole et son normalizer — le code appelant reste inchangé.

### 13.3. Patterns réutilisables

`BaseOAuthClient` (template method avec 3 hooks), `BaseGoogleClient` (pagination via pageToken), `BaseMicrosoftClient` (OData). Circuit breaker, rate limiting Redis distribué, refresh token avec double-check pattern et Redis locking contre le thundering herd.

---

## 14. MCP : Model Context Protocol

### 14.1. Architecture

Le `MCPClientManager` gère le lifecycle des connexions (exit stacks), la découverte d'outils (`session.list_tools()`), et la génération automatique de descriptions de domaine par LLM. Le `ToolAdapter` normalise les outils MCP vers le format LangChain `@tool`, avec parsing structuré des réponses JSON en items individuels.

### 14.2. Sécurité MCP

HTTPS obligatoire, prévention SSRF (résolution DNS + blocklist IP), chiffrement Fernet des credentials, OAuth 2.1 (DCR + PKCE S256), rate limiting Redis par serveur/outil, API guard 403 sur endpoints proxy pour serveurs désactivés (ADR-061 Layer 3).

### 14.3. MCP Iterative Mode (ReAct)

Les serveurs MCP avec `iterative_mode: true` utilisent un agent ReAct dédié (boucle observe/think/act) au lieu du planner statique. L'agent lit d'abord la documentation du serveur, comprend le format attendu, puis appelle les outils avec les bons paramètres. Particulièrement efficace pour les serveurs à API complexe (ex : Excalidraw). Activable par serveur dans la configuration admin ou utilisateur. Alimenté par le `ReactSubAgentRunner` générique (partagé avec le browser agent).

---

## 15. Système de voix (STT/TTS)

### 15.1. STT

Wake word ("OK Guy") via Sherpa-onnx WASM dans le navigateur (zéro envoi externe). Transcription Whisper Small (99+ langues, offline) côté backend via ThreadPoolExecutor. Per-user STT language avec cache thread-safe de `OfflineRecognizer` par langue.

**Optimisations latence** : réutilisation du flux micro KWS → enregistrement (~200-800 ms économisé), pré-connexion WebSocket, `getUserMedia` + WS parallélisés via `Promise.allSettled`, cache Worklet AudioWorklet.

### 15.2. TTS

Factory pattern : `TTSFactory.create(mode)` avec fallback automatique HD → Standard. Standard = Edge TTS (gratuit), HD = OpenAI TTS ou Gemini TTS (premium).

---

## 16. Proactivité : Heartbeat et actions planifiées

### 16.1. Heartbeat : architecture en 2 phases

**Phase 1 — Décision** (coût-effective, gpt-4.1-mini) :
1. `EligibilityChecker` : opt-in, fenêtre horaire, cooldown (2h global, 30 min par type), activité récente
2. `ContextAggregator` : 7 sources en parallèle (`asyncio.gather`) : Calendar, Weather (détection de changements), Tasks, Emails, Interests, Memories, Journals
3. LLM structured output : `skip` | `notify` avec anti-redondance (historique récent injecté)

**Phase 2 — Génération** (si notify) : LLM réécrit avec personnalité + langue utilisateur. Dispatch multi-canal.

### 16.2. Agent Initiative (ADR-062)

Node LangGraph post-exécution : après chaque tour actionnable, l'initiative analyse les résultats et vérifie proactivement les informations cross-domain (read-only). Exemples : météo pluie → vérifier calendrier pour activités outdoor, email mentionnant un rdv → vérifier disponibilité, tâche deadline → rappeler le contexte. 100% prompt-driven (pas de logique hardcodée), pré-filtre structurel (domaines adjacents), injection mémoire + centres d'intérêt, champ suggestion pour proposer des actions write. Configurable via `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`.

### 16.3. Actions planifiées

APScheduler avec leader election Redis (SETNX, TTL 120s, recheck 5s). `FOR UPDATE SKIP LOCKED` pour isolation. Auto-approve des plans (`plan_approved=True` injecté dans le state). Auto-disable après 5 échecs consécutifs. Retry sur erreurs transitoires.

---

## 17. RAG Spaces et recherche hybride

### 17.1. Pipeline

Upload → Chunking → Embedding (text-embedding-3-small, 1536d) → pgvector HNSW → Recherche hybride (cosine + BM25 avec alpha fusion) → Injection contexte dans le **Response Node**.

Note : l'injection RAG se fait dans le nœud de réponse, pas dans le planificateur. Le planner reçoit en revanche l'injection des journaux personnels via `build_journal_context()`.

### 17.2. System RAG Spaces (ADR-058)

FAQ intégrée (119+ Q/A, 17 sections) indexée depuis `docs/knowledge/`. Détection `is_app_help_query` par QueryAnalyzer, Rule 0 override dans RoutingDecider, App Identity Prompt (~200 tokens, lazy loading). SHA-256 staleness detection, auto-indexation au démarrage.

---

## 18. Browser Control et Web Fetch

### 18.1. Web Fetch

URL → validation SSRF (DNS + IP blocklist + post-redirect recheck) → readability extraction (fallback full page) → HTML cleaning → Markdown → wrapping `<external_content>` (prévention prompt injection). Cache Redis 10 min.

### 18.2. Browser Control (ADR-059)

Agent ReAct autonome (Playwright Chromium headless). Session pool Redis-backed avec recovery cross-worker. CDP accessibility tree pour interaction par éléments. Anti-détection (Chrome UA, webdriver flag remove, locale/timezone dynamiques). Cookie banner auto-dismiss (20+ sélecteurs multilingues). Rate limiting séparé read/write (40 chacun par session).

---

## 19. Sécurité : defence in depth

### 19.1. Authentification BFF (ADR-002)

**Pourquoi BFF plutôt que JWT ?** JWT dans localStorage = vulnérable XSS, taille 90 % overhead, révocation impossible. Le pattern BFF avec HTTP-only cookies + sessions Redis élimine ces trois problèmes. Migration v0.3.0 : mémoire -90 % (1.2 MB → 120 KB), session lookup P95 < 5 ms, score OWASP B+ → A.

### 19.2. Usage Limits : 5-layer defence in depth

| Couche | Point d'interception | Pourquoi cette couche |
|--------|---------------------|-----------------------|
| Layer 0 | Chat router (HTTP 429) | Bloquer avant même le stream SSE |
| Layer 1 | Agent service (SSE error) | Couvrir les scheduled actions qui bypasent le router |
| Layer 2 | `invoke_with_instrumentation()` | Guard centralisé couvrant tous les services background |
| Layer 3 | Proactive runner | Skip pour utilisateurs bloqués |
| Layer 4 | Migration `.ainvoke()` directe | Couverture des appels non centralisés |

Design **fail-open** : les échecs d'infrastructure ne bloquent pas les utilisateurs.

### 19.3. Prévention des attaques

| Vecteur | Protection |
|---------|------------|
| XSS | HTTP-only cookies, CSP |
| CSRF | SameSite=Lax |
| SQL Injection | SQLAlchemy ORM (requêtes paramétrées) |
| SSRF | DNS resolution + IP blocklist (Web Fetch, MCP, Browser) |
| Prompt Injection | `<external_content>` safety markers |
| Rate Limiting | Redis sliding window distribué (Lua atomique) |
| Supply Chain | SHA-pinned GitHub Actions, Dependabot weekly |

---

## 20. Observabilité et monitoring

### 20.1. Stack

| Technologie | Rôle |
|-------------|------|
| Prometheus | 350+ métriques custom (RED pattern) |
| Grafana | 18 dashboards production-ready |
| Loki | Logs structurés JSON agrégés |
| Tempo | Traces distribuées cross-service (OTLP gRPC) |
| Langfuse | LLM-specific tracing (prompt versions, token usage) |
| structlog | Logging structuré avec PII filtering |

### 20.2. Debug Panel embarqué

Le debug panel dans l'interface chat fournit une introspection temps réel par conversation : intent analysis, execution pipeline, LLM pipeline (réconciliation chronologique de tous les appels LLM + embedding), context/mémoire, intelligence (cache hits, pattern learning), journaux (injection + extraction background), lifecycle timing.

Les métriques debug persistent dans `sessionStorage` (50 entrées max).

**Pourquoi un debug panel dans l'UI ?** Dans un écosystème où les agents IA sont notoirement difficiles à debugger (comportement non déterministe, chaînes d'appels opaques), rendre les métriques accessibles directement dans l'interface élimine la friction de devoir ouvrir Grafana ou lire des logs. L'opérateur voit immédiatement pourquoi une requête a coûté cher ou pourquoi le routeur a choisi tel domaine.

### 20.3. DevOps Claude CLI (v1.13.0 — admin uniquement)

Les administrateurs peuvent interagir avec Claude Code CLI directement depuis la conversation LIA pour diagnostiquer les problèmes serveur en langage naturel : *"Regarde les logs pour voir si tout fonctionne"*, *"Vérifie l'espace disque"*, *"Quel container utilise le plus de RAM ?"*. Claude CLI est installé dans le container Docker API et exécuté localement via subprocess, avec accès au Docker socket pour inspecter tous les containers. Les permissions sont configurables par environnement (`--allowedTools`/`--disallowedTools`) et l'accès est restreint aux superusers via un check DB direct. Les sessions sont persistantes pour permettre des investigations multi-tours.

---

## 21. Performance : optimisations et métriques

### 21.1. Métriques clés (P95)

| Métrique | Valeur | SLO |
|----------|--------|-----|
| API Latency | 450 ms | < 500 ms |
| TTFT (Time To First Token) | 380 ms | < 500 ms |
| Router Latency | 800 ms | < 2 s |
| Planner Latency | 2.5 s | < 5 s |
| E5 Embedding (local) | ~50 ms | < 100 ms |
| Checkpoint save | < 50 ms | P95 |
| Redis session lookup | < 5 ms | P95 |

### 21.2. Optimisations implémentées

| Optimisation | Gain mesuré | Compromis |
|-------------|-------------|-----------|
| Message Windowing | -50 % latence, -77 % coût | Perte de contexte ancien (compensé par Data Registry) |
| Smart Catalogue | 96 % réduction tokens | Panic mode nécessaire si filtrage trop agressif |
| Pattern Learning | 89 % économies LLM | Amorcage requis (golden patterns) |
| Prompt Caching | 90 % discount | Dépend du support provider |
| Local Embeddings | Zéro coût API | ~470 MB mémoire, 9s chargement initial |
| Parallel Execution | Latence = max(étapes) | Complexité de gestion des dépendances |
| Context Compaction | ~60 % par compaction | Perte d'information (atténuée par préservation IDs) |

---

## 22. CI/CD et qualité

### 22.1. Pipeline

```
Pre-commit (local)                GitHub Actions CI
========================          =========================
.bak files check                  Lint Backend (Ruff + Black + MyPy strict)
Secrets grep                      Lint Frontend (ESLint + TypeScript)
Ruff + Black + MyPy               Unit tests + coverage (43 %)
Unit tests rapides                Code Hygiene (i18n, Alembic, .env.example)
Détection patterns critiques      Docker build smoke test
Sync clés i18n                    Secret scan (Gitleaks)
Conflits migration Alembic        ─────────────────────────
Complétude .env.example           Security workflow (hebdomadaire)
ESLint + TypeScript check           CodeQL (Python + JS)
                                    pip-audit + pnpm audit
                                    Trivy filesystem scan
                                    SBOM generation
```

### 22.2. Standards

| Aspect | Outil | Configuration |
|--------|-------|---------------|
| Formatage Python | Black | line-length=100 |
| Linting Python | Ruff | E, W, F, I, B, C4, UP |
| Type checking | MyPy | strict mode |
| Commits | Conventional Commits | `feat(scope):`, `fix(scope):` |
| Tests | pytest | `asyncio_mode = "auto"` |
| Coverage | 43 % minimum | Enforci en CI |

---

## 23. Patterns d'ingénierie transversaux

### 23.1. Système de Tools : architecture en 5 couches

Le système de tools est construit en cinq couches composables, réduisant le boilerplate par tool de ~150 lignes à ~8 lignes (réduction de 94 %) :

| Couche | Composant | Rôle |
|--------|-----------|------|
| 1 | `ConnectorTool[ClientType]` | Base générique : OAuth auto-refresh, cache client, injection de dépendances |
| 2 | `@connector_tool` | Méta-décorateur composant `@tool` + métriques + rate limiting + sauvegarde contexte |
| 3 | Formatters | `ContactFormatter`, `EmailFormatter`... — normalisation des résultats par domaine |
| 4 | `ToolManifest` + Builder | Déclaration déclarative : params, sorties, coût, permissions, mots-clés sémantiques |
| 5 | Catalogue Loader | Introspection dynamique, génération de manifestes, regroupement par domaine |

Les limites de débit sont catégorisées : Read (20/min), Write (5/min), Expensive (2/5 min). Les tools peuvent produire soit une chaîne (legacy) soit un `UnifiedToolOutput` structuré (mode Data Registry).

### 23.2. Data Registry

Le Data Registry (`InMemoryStore`) découple les résultats des tools de l'historique de messages. Les résultats sont stockés par requête via `@auto_save_context` et survivent au windowing des messages — c'est ce qui rend le windowing agressif par nœud (5/10/20 tours) viable sans perdre le contexte des sorties de tools. Les références inter-étapes (`$steps.X.field`) résolvent contre le registry, pas contre les messages.

### 23.3. Architecture d'Erreurs

Tous les tools retournent `ToolResponse` (succès) ou `ToolErrorModel` (échec) avec un enum `ToolErrorCode` (18+ types : INVALID_INPUT, RATE_LIMIT_EXCEEDED, TEMPLATE_EVALUATION_FAILED...) et un flag `recoverability`. Côté API, des raisers d'exceptions centralisés (`raise_user_not_found`, `raise_permission_denied`...) remplacent partout les HTTPException brutes — garantissant des contrats d'erreur cohérents.

### 23.4. Système de Prompts

57 fichiers `.txt` versionnés dans `src/domains/agents/prompts/v1/`, chargés via `load_prompt()` avec cache LRU (32 entrées). Versions configurables par variables d'environnement.

### 23.5. Activation Centralisée des Composants (ADR-061)

Système en 3 couches résolvant un problème de duplication : avant l'ADR-061, le filtrage des composants activés/désactivés était dispersé dans 7+ endroits. Maintenant :

| Couche | Mécanisme |
|--------|-----------|
| Couche 1 | Gate-keeper de domaine : valide les domaines LLM contre `available_domains` |
| Couche 2 | `request_tool_manifests_ctx` : ContextVar construit une fois par requête |
| Couche 3 | Guard API 403 sur les endpoints proxy MCP |

### 23.6. Feature Flags

Chaque sous-système optionnel est contrôlé par un flag `{FEATURE}_ENABLED`, vérifié au démarrage (enregistrement scheduler), au câblage des routes et à l'entrée des nœuds (court-circuit instantané). Cela permet de déployer le codebase complet tout en activant les sous-systèmes progressivement.

---

## 24. Architecture des décisions (ADR)

59 ADRs au format MADR documentent les décisions architecturales majeures. Quelques exemples représentatifs :

| ADR | Décision | Problème résolu | Impact mesuré |
|-----|----------|----------------|---------------|
| 001 | LangGraph pour orchestration | Besoin de state persistence + interrupts HITL | Checkpoints P95 < 50 ms |
| 002 | BFF Pattern (JWT → Redis) | JWT vulnérable XSS, révocation impossible | Mémoire -90 %, OWASP A |
| 003 | Filtrage dynamique par domaine | 10x prompt size = 10x coût | 73-83 % réduction catalogue |
| 005 | Filtrage AVANT asyncio.gather | Plan + fallback exécutés en parallèle = 2x coût | -50 % coût plans fallback |
| 007 | Message Windowing par nœud | Conversations longues = 100k+ tokens | -50 % latence, -77 % coût |
| 048 | Semantic Tool Router | Routage LLM imprécis sur multi-domaine | +48 % précision |
| 049 | Local E5 Embeddings | Coût embeddings API + latence réseau | Zéro coût, 50 ms local |
| 057 | Personal Journals | Pas de continuité de réflexion entre sessions | Injection planner + response |
| 061 | Centralized Component Activation | 7+ sites de filtrage dupliqués | Source unique, 3 couches |

---

## 25. Potentiel d'évolution et extensibilité

### 25.1. Points d'extension

| Extension | Interface | Documentation |
|-----------|-----------|---------------|
| Nouveau connecteur | `OAuthProvider` Protocol + Client Protocol | `GUIDE_CONNECTOR_IMPLEMENTATION.md` + checklist |
| Nouvel agent | `register_agent()` + ToolManifest | `GUIDE_AGENT_CREATION.md` |
| Nouvel outil | `@tool` + ToolResponse/ToolErrorModel | `GUIDE_TOOL_CREATION.md` |
| Nouveau canal | `BaseChannelSender` + `BaseChannelWebhookHandler` | `NEW_CHANNEL_CHECKLIST.md` |
| Nouveau provider LLM | Adaptateur + model profiles | Factory extensible |
| Nouvelle tâche proactive | `ProactiveTask` Protocol | `NEW_PROACTIVE_TASK_CHECKLIST.md` |

### 25.2. Scalabilité

| Dimension | Stratégie actuelle | Évolution possible |
|-----------|-------------------|-------------------|
| Horizontal | 4 uvicorn workers + leader election Redis | Kubernetes + HPA |
| Données | PostgreSQL + pgvector | Sharding, read replicas |
| Cache | Redis single instance | Redis Cluster |
| Observabilité | Stack complète embarquée | Managed Grafana Cloud |

---

## Conclusion

LIA est un exercice d'ingénierie logicielle qui tente de résoudre un problème concret : construire un assistant IA multi-agent de qualité production, transparent, sécurisé et extensible, capable de tourner sur un Raspberry Pi.

Les 59 ADRs documentent non seulement les décisions prises mais aussi les alternatives rejetées et les compromis acceptés. Les 2 300+ tests, le CI/CD complet, et le MyPy strict ne sont pas des métriques de vanité — ce sont les mécanismes qui permettent de faire évoluer un système de cette complexité sans régression.

L'intrication des sous-systèmes — mémoire psychologique, apprentissage bayésien, routage sémantique, HITL systématique, proactivité LLM-driven, journaux introspectifs — crée un système où chaque composant renforce les autres. Le HITL alimente le pattern learning, qui réduit les coûts, qui permettent plus de fonctionnalités, qui génèrent plus de données pour la mémoire, qui améliore les réponses. C'est un cercle vertueux par conception, pas par accident.

---

*Document rédigé sur la base de l'analyse du code source (`apps/api/src/`, `apps/web/src/`), de la documentation technique (190+ documents), des 63 ADRs, et du changelog (v1.0 à v1.13.0). Toutes les métriques, versions et patterns cités sont vérifiables dans le codebase.*
