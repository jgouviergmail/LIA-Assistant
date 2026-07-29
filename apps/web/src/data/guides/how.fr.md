# LIA — Guide Technique Complet

> Architecture, patterns et décisions d'ingénierie d'un assistant IA multi-agent de nouvelle génération.
>
> Documentation de présentation technique destinée aux architectes, ingénieurs et experts techniques.

**Version** : 3.6
**Date** : 2026-07-29
**Application** : LIA v1.26.2
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
8. [Routage sémantique et embeddings IA](#8-routage-sémantique-et-embeddings-ia)
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
26. [Psyche Engine : intelligence émotionnelle dynamique](#26-psyche-engine--intelligence-émotionnelle-dynamique)

---

## 1. Contexte et choix fondateurs

### 1.1. Pourquoi ces choix ?

Chaque décision technique de LIA répond à une contrainte concrète. Le projet vise un assistant IA multi-agent **auto-hébergeable sur hardware modeste** (Raspberry Pi 5, ARM64), avec une transparence totale, une souveraineté des données, et un support multi-fournisseur LLM. Ces contraintes ont guidé l'intégralité de la stack.

| Contrainte | Conséquence architecturale |
|------------|--------------------------|
| Auto-hébergement ARM64 | Docker multi-arch, embeddings sémantiques (multilingues), Playwright chromium cross-platform |
| Souveraineté des données | PostgreSQL local (pas de SaaS DB), chiffrement Fernet au repos, sessions Redis locales |
| Multi-fournisseur LLM | Factory pattern avec 7 adaptateurs, configuration par nœud, pas de couplage fort à un provider |
| Transparence totale | 447 métriques Prometheus, debug panel embarqué, suivi token par token |
| Fiabilité en production | 170+ ADRs, ~16 535 tests collectés par pytest sur 873 fichiers, observabilité native, HITL à 6 niveaux |
| Coûts maîtrisés | Smart Services (89 % d'économie tokens), embeddings sémantiques, prompt caching, filtrage de catalogue |

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
| Tests | ~16 535 (collectés par pytest sur 873 fichiers de test) + 3 540 tests vitest côté frontend (seuils de couverture verrouillés, ADR-116) |
| Fixtures réutilisables | 170+ |
| Documents de documentation | 400+ |
| ADRs (Architecture Decision Records) | 160+ |
| Métriques Prometheus | 447 définitions |
| Dashboards Grafana | 26 |
| Langues supportées (i18n) | 6 (fr, en, de, es, it, zh) |

---

## 2. Stack technologique

### 2.1. Backend

| Technologie | Version | Rôle | Pourquoi ce choix |
|-------------|---------|------|-------------------|
| Python | 3.12+ | Runtime | Écosystème ML/IA le plus riche, async natif, typing complet |
| FastAPI | 0.136.3 | API REST + SSE | Validation auto Pydantic, docs OpenAPI, async-first, performances |
| LangGraph | 1.2.4 | Orchestration multi-agent | Seul framework offrant state persistence + cycles + interrupts (HITL) natifs |
| LangChain Core | 1.4.6 | Abstractions LLM/tools | Décorateur `@tool`, formats de messages, callbacks standardisés |
| SQLAlchemy | 2.0.50 | ORM async | `Mapped[Type]` + `mapped_column()`, async sessions, `selectinload()` |
| PostgreSQL | 16 + pgvector | Database + vector search | Checkpoints LangGraph natifs, recherche sémantique HNSW, maturité |
| Redis | 7.4 | Cache, sessions, rate limiting | O(1) ops, sliding window atomique (Lua), SETNX leader election |
| Pydantic | 2.13.4 | Validation + sérialisation | `ConfigDict`, `field_validator`, composition de settings via MRO |
| structlog | latest | Logging structuré | JSON output avec filtrage PII automatique, snake_case events |
| Gemini Embeddings | gemini-embedding-001 | Embeddings sémantiques | Embeddings multilingues Gemini (mémoire, routage, intérêts, journaux) — ADR-069 |
| Playwright | latest | Browser automation | Chromium headless, CDP accessibility tree, cross-platform |
| APScheduler | 3.x | Background jobs | Cron/interval triggers, compatible leader election Redis |

### 2.2. Frontend

| Technologie | Version | Rôle |
|-------------|---------|------|
| Next.js | 16.2.10 | App Router, SSR, ISR |
| React | 19.2.7 | UI avec Server Components |
| TypeScript | 6.0.2 | Typage strict |
| TailwindCSS | 4.3.2 | Utility-first CSS |
| TanStack Query | 5.101 | Server state management, cache, mutations |
| Radix UI | v2 | Primitives UI accessibles |
| react-i18next | 17.0 | i18n (6 langues), namespace-based |
| Zod | 4.x | Validation runtime des schémas debug |

### 2.3. LLM Providers supportés

| Provider | Modèles | Spécificités |
|----------|---------|-------------|
| OpenAI | GPT-5.4, GPT-5.4-mini, GPT-5.2, GPT-5.1, GPT-5 (+ mini/nano), GPT-4.1, GPT-4o, o3/o4-mini | Prompt caching natif, Responses API, reasoning_effort |
| Anthropic | Claude Opus 4.6/4.5, Claude Sonnet 4.6, Claude Haiku 4.5 | Extended thinking, prompt caching |
| Google | Gemini 3.1/3 Pro, Gemini 3.1/3 Flash, Gemini 2.5 Pro/Flash | Multimodal, embeddings duaux |
| DeepSeek | deepseek-v4-flash, deepseek-v4-pro (V4), deepseek-chat (V3), deepseek-reasoner (R1) | Coût réduit, reasoning natif |
| Perplexity | Sonar, Sonar Pro | Search-augmented generation |
| Qwen | qwen3.5-plus, qwen3.5-flash, qwen3-max | Thinking mode, tools + vision (Alibaba Cloud) |
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
│   │   ├── prompts/v1/           # 78 fichiers .txt de prompts versionnés
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
    └── observability/            # 23 fichiers de métriques Prometheus, tracing OTel
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

LIA expose deux modes d'exécution (basculables par utilisateur via un toggle dans l'en-tête du chat) : **Pipeline** (par défaut, déterministe et économe en tokens) et **ReAct** (autonome et itératif). Le Router classifie d'abord la requête (conversation directe ou actionable) puis dispatche vers le mode actif.

```mermaid
graph TD
    A[User Message] --> B[Router Node]
    B -->|conversation| C[Response Node]
    B -->|pipeline mode| D[Planner Node]
    B -->|react mode| R1[ReAct Setup]
    D --> E[Semantic Validator]
    E --> F{Approval Gate}
    F -->|approved| G[Task Orchestrator]
    F -->|rejected| C
    G --> H[Domain Agents + Tools]
    H --> G
    G --> C
    R1 --> R2[ReAct Call Model]
    R2 -->|tool_calls| R3[ReAct Execute Tools]
    R2 -->|done| R4[ReAct Finalize]
    R3 --> R2
    R4 --> C
    C --> J[SSE Stream]
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

### 5.3. Mode d'exécution ReAct (ADR-070)

LIA propose un second mode d'exécution : **ReAct** (Reasoning + Acting). Au lieu de planifier à l'avance, le LLM appelle itérativement les outils, observe les résultats et décide de la prochaine étape de manière autonome.

**Architecture** : 4 nodes custom dans le graph LangGraph parent (pas un sous-graphe) :

```
Router → react_setup → react_call_model ↔ react_execute_tools → react_finalize → Response
```

**Pipeline vs ReAct — compromis d'ingénierie** :

| Aspect | Pipeline (défaut) | ReAct (⚡) |
|--------|-------------------|-----------|
| **Coût en tokens** | **4–8× inférieur** — 1 appel planner + 1 appel response | 1 appel LLM par itération (2–15 itérations typiques) |
| **Planification** | ExecutionPlan anticipé avec validation sémantique | Aucune — le LLM décide étape par étape |
| **Exécution parallèle** | Oui — vagues `asyncio.gather()` | Non — appels séquentiels |
| **Adaptabilité** | Suit le plan rigidement | S'adapte à chaque résultat |
| **Contrôle** | Total — DSL planner, HITL, validateurs | Minimal — comportement guidé par le prompt |
| **Prévisibilité des coûts** | Élevée — borné par les steps du plan | Faible — dépend du raisonnement LLM |
| **Idéal pour** | Requêtes structurées multi-domaines | Recherche exploratoire, questions ambiguës |

Le mode Pipeline est un véritable travail d'ingénierie : le SmartPlanner, le Semantic Validator, le cache bayésien de patterns et l'exécuteur parallèle offrent ensemble la même puissance fonctionnelle que le ReAct tout en consommant une fraction des tokens. Le compromis est l'adaptabilité — quand la séquence optimale d'outils ne peut pas être prédite à l'avance, le raisonnement itératif du ReAct excelle.

Les deux modes partagent le même registre d'outils, le système HITL, le response node et l'infrastructure d'observabilité. L'utilisateur bascule entre les deux via un toggle dans l'en-tête du chat.

### 5.4. Exécutions détachées : la génération survit à la connexion (ADR-117)

Le streaming SSE classique a un défaut structurel : la génération vit *dans* le générateur de la réponse HTTP. Fermer l'onglet, naviguer ou perdre le réseau tue la connexion — et, avec elle, le tour de conversation entier. LIA découple les deux : un **producteur détaché** (tâche asyncio indépendante de la requête) exécute le graphe et publie chaque chunk dans un **Redis Stream par run** ; l'endpoint SSE n'est plus qu'un **abonné** qui relaie ce stream.

- **Déconnexion ≠ annulation** — fermer la page arrête l'abonnement, jamais la génération. Le message utilisateur est archivé *avant* l'exécution, la réponse se termine côté serveur et attend dans la conversation.
- **Reprise live** — au retour (montage de la page, retour d'onglet), le frontend détecte le run actif, rejoue l'intégralité des chunks déjà émis (sans pacing) puis bascule sur le flux live ; la frontière est un commentaire transport SSE (`: replay-end`), le contrat des chunks reste intact. Pendant le replay, les effets de bord (toasts, audio) sont neutralisés pendant que le reducer reconstruit la bulle en cours.
- **Silence détecté côté client** — la reprise suppose encore que le client sache qu'il doit reprendre. Un onglet gelé par le système d'exploitation ne reçoit ni fin ni erreur : la lecture reste suspendue, l'interface se croit toujours en train de recevoir, et le garde censé protéger un flux vivant bloque précisément la reprise. Un budget de silence calibré sur le rythme des battements de cœur du serveur tranche : au-delà, la connexion morte est abandonnée, l'état revient au repos et le rattachement ci-dessus prend le relais. Les minuteurs du navigateur gelant avec l'onglet, l'échéance tombe au réveil — exactement le moment où elle sert.
- **Un seul run par conversation** — un verrou Redis (`SET NX EX` + heartbeat producteur + libération conditionnelle Lua insensible aux zombies) fait répondre HTTP 409 à un envoi concurrent, que le frontend transforme en réattachement silencieux.
- **Annulation cross-worker** — le bouton d'envoi se mue en bouton stop ; le signal d'annulation transite par Redis et est sondé côté producteur (~1 s), y compris quand le producteur vit dans un autre worker que la requête HTTP. La réponse partielle est conservée et badgée « interrompue » ; les tokens déjà consommés restent comptabilisés — la facturation est honorée sur tous les chemins de sortie, kills compris.
- **Voix seulement si quelqu'un écoute** — la présence des abonnés (compteur Redis à TTL ré-armé périodiquement) conditionne la synthèse vocale : aucun TTS pour un run que personne n'écoute, et un auditeur qui arrive en cours de route obtient la voix pour la suite.
- **Arrêt propre** — au shutdown, le lifespan draine les producteurs en cours avant de rendre la main ; un run tué archive son partiel flaggé `interrupted`, et une réparation en début de tour nettoie les `tool_calls` orphelins qu'un checkpoint interrompu laisserait (les providers stricts les rejettent au tour suivant).

L'ensemble est gouverné par un feature flag et une dizaine de réglages env (TTL, heartbeat, drain, polling) validés au boot — une période de heartbeat incompatible avec le TTL du verrou refuse de démarrer.

---

**Ancrage sur les entités récentes.** Sur un tour qui n’appelle aucun outil, le registre du tour courant est vide par construction (garde anti-contamination) et l’historique conversationnel exclut délibérément les messages d’outil : le modèle de réponse n’a alors *aucune* donnée structurée faisant autorité, et ne peut que reformuler de la prose antérieure. Les entités les plus récentes du state sont donc réinjectées dans une section de prompt dédiée — sélectionnées par récence, bornées en âge, sans aucun aller-retour de stockage, et explicitement non prioritaires sur les données du tour courant. Une règle d’autorité complète le dispositif : interdiction d’inventer un attribut d’entité, et obligation d’annoncer comme manquante une donnée demandée mais jamais reçue.

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

L’identité d’un résultat corrélé inclut son parent. Les outils dérivent leur identifiant du contenu seul — la météo de `lieu + jour`, un trajet de `origine + destination` — si bien que deux itérations portant sur des parents partageant ces attributs produisaient le même identifiant, et l’accumulateur, un simple `dict.update()`, écrasait silencieusement le premier. L’identifiant est désormais dérivé par parent au moyen d’une empreinte déterministe, ce qui préserve aussi la stabilité de l’identité lors d’un rejeu ou d’une reprise après interruption.

### 6.3. Exécution parallèle en vagues

Le `parallel_executor.py` organise les étapes en vagues (DAG) :
1. Identifie les étapes sans dépendances non résolues → vague suivante
2. Filtre les étapes skipped (conditions non remplies, branches fallback) — **avant** `asyncio.gather()`, pas après (ADR-005 : corrige un bug qui causait 2x appels API et 2x coûts)
3. Exécute la vague avec isolation d'erreur par étape
4. Alimente le Data Registry avec les résultats
5. Répète jusqu'à complétion du plan

### 6.4. Validateur Sémantique

Avant l'approbation HITL, un LLM dédié (distinct du planner, pour éviter le biais d'auto-validation) inspecte le plan selon 14 types d'anomalies répartis en quatre catégories : **Critique** (capacité hallucinée, dépendance fantôme, cycle logique), **Sémantique** (incohérence de cardinalité, débordement/sous-couverture de périmètre, paramètres incorrects), **Sécurité** (ambiguïté dangereuse, hypothèse implicite) et **FOR_EACH** (cardinalité manquante, référence invalide). Court-circuit pour les plans triviaux (1 étape), timeout optimiste de 1 s.

En complément, un **registre anti-hallucination auto-enrichissant** (`hallucinated_tools.json`) détecte les outils inventés par le LLM (ex : `resolve_reference_tool`) via des patterns regex persistants. Chaque nouvelle hallucination est automatiquement ajoutée au registre pour une détection plus rapide lors des plans suivants. Les étapes hallucinées sont supprimées du plan et le planner est forcé à replanifier avec les outils réels du catalogue — éliminant une classe entière d'échecs d'exécution sans intervention humaine.

### 6.5. Validation des Références

Les références inter-étapes (`$steps.get_meetings.events[0].title`) sont validées au moment du plan avec des messages d'erreur structurés : champ invalide, alternatives disponibles et exemples corrigés — permettant au planner de s'auto-corriger lors d'un retry au lieu de produire des échecs silencieux.

### 6.6. Re-Planner Adaptatif (Panic Mode)

En cas d'échec d'exécution, un analyseur rule-based (sans LLM) classifie le pattern d'échec (résultats vides, échec partiel, timeout, erreur de référence) et sélectionne une stratégie de recovery : retry identique, replan avec périmètre élargi, escalade utilisateur ou abandon. Cette décision est **consultative à ce jour** : elle est journalisée et comptée à chaque échec, ce qui rend les modes de défaillance mesurables, mais l'orchestrateur ne l'applique pas encore automatiquement — les résultats partiels sont restitués plutôt qu'écartés. En **Panic Mode**, le SmartCatalogue s'élargit pour inclure tous les outils lors d'un unique retry — résolvant les cas où le filtrage par domaine était trop agressif.

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

## 8. Routage sémantique et embeddings IA

### 8.1. Pourquoi des embeddings sémantiques ? (ADR-049)

Le routage purement LLM avait deux problèmes : coût (chaque requête = un appel LLM) et précision (le LLM se trompait sur les domaines dans ~20 % des cas multi-domaines). Les embeddings sémantiques résolvent les deux :

| Propriété | Valeur |
|-----------|--------|
| Fournisseur | Google Gemini (`gemini-embedding-001`) |
| Langues | 100+ |
| Gain précision | +48 % sur Q/A matching vs routage LLM seul |

### 8.2. Semantic Tool Router (ADR-048)

Chaque `ToolManifest` possède des `semantic_keywords` multilingues. La requête est transformée en embedding, puis comparée par similarité cosinus avec **max-pooling** (score = MAX par outil, pas moyenne — évite la dilution sémantique). Double seuil : >= 0.70 = haute confiance, 0.60-0.70 = incertitude.

### 8.3. Semantic Expansion

Le `expansion_service.py` ajoute au catalogue du planner les domaines capables de fournir une donnée manquante. Le déclencheur est **piloté par l'évidence** : la détection d'une référence personnelle est l'union de trois sources — les mappings du résolveur mémoire (références personnelles par construction), les références relationnelles extraites même quand la résolution ne trouve aucun fait, et les références typées par le LLM d'analyse. Une entité référencée (personne → `Contact`, rendez-vous → `CalendarEvent`, lieu → `Place`, e-mail → `EmailMessage`) apporte les domaines dont les `properties` de son type ontologique fournissent un type requis par les outils sélectionnés — ancrage qui empêche toute expansion aveugle, avec plafond configurable et complétude du mapping vérifiée au démarrage (ADR-120).

La couche est alimentée par des manifests **profondément annotés** (`semantic_type` sur paramètres et outputs : participants d'un événement, expéditeur d'un e-mail, destination d'un trajet — ADR-121), qui nourrissent aussi les suggestions de liaison Jinja2 inter-domaines et un **garde d'exécution** : un nom de personne ne peut jamais atteindre un paramètre typé adresse/e-mail — l'appel échoue avant toute dépense API avec une erreur récupérable, dans les deux modes d'exécution. La validation post-expansion (ADR-061, Layer 1) filtre toujours les domaines désactivés par l'administrateur.

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

### 9.5. Boucles de révision replay-safe (ADR-092)

La sémantique de reprise de LangGraph ré-exécute le nœud interrompu **en entier** : les `interrupt()` passés rendent leurs valeurs mémorisées, mais tout le reste re-tourne en live. Une boucle écrite autour de `interrupt()` à l'intérieur d'un nœud rejoue donc ses effets de bord (appels LLM, API) à chaque décision utilisateur. Les deux boucles de révision — édition itérative de brouillon et confirmation d'opérations bulk (nœud dédié `for_each_confirm`) — suivent un pattern normatif : **un seul `interrupt()` par exécution de nœud**, l'état de boucle transite par le state checkpointé, et l'itération passe par un self-loop conditionnel. Garantie prouvée par harnais de replay compilés : chaque modification LLM ne s'exécute qu'une fois et le contenu confirmé est exactement le dernier contenu affiché.

### 9.6. Compaction Safety

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

**Résilience opérationnelle** : chaque appel LLM est encadré par un `asyncio.wait_for` par chunk (35 s par défaut) et un budget global de 120 s. Sur erreur transitoire, `tenacity.AsyncRetrying` rejoue jusqu'à 3 tentatives avec backoff exponentiel. Si le résumé n'aboutit toujours pas, un fallback explicite (`_truncation_fallback`) tronque proprement l'historique ancien avec un `SystemMessage` lisible préservant les identifiants — pas de stub silencieux. Les anciens résumés `compaction #N` sont consolidés dans le merge plutôt que d'être accumulés tour après tour.

**Signal SSE custom mode** : le nœud émet `compaction_start` / `compaction_done` via `langgraph.config.get_stream_writer()` à travers un `stream_mode="custom"` (LangGraph 1.x). Le streaming service les traduit en `ChatStreamChunk(type="execution_step")`. Côté frontend, un toast sonner morphé sur un id stable (`COMPACTION_TOAST_ID`) reste visible pendant toute la compaction, l'input est verrouillé via `status="compacting"`, et une pastille « ContextUsagePill » affiche en continu le ratio tokens/seuil. Le keepalive SSE concurrent (`iter_with_keepalive`) pulse `: heartbeat` toutes les 15 s pendant les awaits silencieux pour neutraliser les coupures Cloudflare. Cinq métriques Prometheus (`compaction_chunk_timeouts_total`, `compaction_global_timeouts_total`, `compaction_total_duration_seconds`, `compaction_writer_unavailable_total`, `compaction_executions_total{strategy}`) alimentent un dashboard Grafana dédié.

### 10.4. Checkpointing PostgreSQL

State complet checkpointé après chaque nœud. P95 save < 50 ms, P95 load < 100 ms, taille moyenne ~15 KB/conversation. Le checkpointer et le store s'appuient chacun sur un pool de connexions PostgreSQL dédié par worker (tailles réglables par environnement) : les conversations concurrentes ne se sérialisent plus sur une connexion unique, et une connexion tombée est détectée au checkout et remplacée automatiquement (ADR-111).

### 10.5. Les blocs système d'un tour ReAct sont de l'état (ADR-169/170)

`get_windowed_messages(include_system=True)` **hisse tous les `SystemMessage` en tête**, sans limite de fenêtre. Empiler les blocs système du tour dans l'historique revenait donc à renvoyer toutes les copies passées à chaque appel : `react_agent_prompt.txt` pèse **840 tokens**, soit 2 520 tokens dupliqués après trois tours — à chaque appel LLM de chaque itération. Le préfixe grossissant à chaque tour, aucun cache de préfixe fournisseur ne pouvait faire mouche, et Anthropic rejetait la séquence dès le deuxième tour : un `SystemMessage` ne peut pas apparaître au milieu d'un historique.

Les blocs vivent désormais dans une clé d'état dédiée et sont recomposés en tête à chaque appel — le préfixe redevient stable. Le schéma d'état passe en **1.4**, avec une migration additive et idempotente. Le fenêtrage écarte les `SystemMessage` hérités de l'historique **sauf le résumé de compaction** : une première version du correctif rétablissait la contiguïté en détruisant ce résumé, et c'est la revue de ce correctif-là qui a produit la bonne solution.

**Le délai de la boucle se mesure sur le calcul, pas sur l'horloge murale.** `interrupt()` lève : le nœud ne retourne jamais, aucune mise à jour d'état n'est persistée, aucun horodatage n'est rafraîchi, et la reprise ré-entre au nœud interrompu sans rejouer le routeur où vivait la remise à zéro — **2,01 s d'horloge pour 0,0102 s de calcul**, mesurées sur un graphe réel. Passé le budget, le tour repris était coupé au routage suivant et la réponse re-synthétisée par un second appel LLM, le travail multi-étapes perdu. Une garde d'absence de progrès complète l'ensemble : au quatrième appel d'outil identique le modèle est invité à changer d'approche, au cinquième le tour se conclut. L'empreinte est un HMAC calé sur la clé de l'application — elle survit à une reprise sur un autre worker — et seuls l'empreinte et un compteur atteignent le checkpoint, jamais le nom de l'outil ni ses arguments.

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
- Embedding `gemini-embedding-001` (1536d) via pgvector HNSW

**Pourquoi un poids émotionnel ?** Un assistant qui sait que votre mère est malade mais traite ce fait comme n'importe quelle donnée est au mieux maladroit, au pire blessant. Le poids émotionnel permet d'activer la `DANGER_DIRECTIVE` (interdiction de plaisanter, minimiser, comparer, banaliser) quand un sujet sensible est touché.

### 11.3. Extraction et injection

**Extraction** : après chaque conversation, un processus background analyse le dernier message utilisateur, adapté à la personnalité active. Coût suivi via `TrackingContext`.

**Injection** : le middleware `memory_injection.py` recherche les mémoires sémantiquement proches, construit le profil psychologique injectable, et active la `DANGER_DIRECTIVE` si nécessaire. Injection dans le prompt système du Response Node.

**Quels tours alimentent la mémoire.** Un message qui déclenche une action compte autant qu'une conversation : la reprise d'un brouillon n'injecte aucun message, si bien que la demande d'origine reste la dernière parole de l'utilisateur au moment de l'extraction. À l'inverse, les messages **fabriqués par le système** — l'échafaudage injecté lors d'un refus HITL — sont marqués dans leurs métadonnées et écartés à la fois comme cible et comme contexte : jamais reconnus à leur texte, puisqu'ils existent en six langues. Enfin, l'heuristique qui écarte les acquiescements ne s'applique qu'à ce que l'utilisateur a réellement tapé — appliquée à un nom de personne, elle faisait disparaître les souvenirs des contacts dont le patronyme ressemble à « bien » ou « cool ». Chaque décision est comptée par sous-système et par issue (`post_response_extraction_scheduled_total`), là où seuls des journaux de débogage existaient.

### 11.4. Recherche mémoire à deux vecteurs

Chaque souvenir porte **deux embeddings** : un sur son contenu, un sur les mots-clés qui le déclenchent. La requête est comparée aux deux et le meilleur des deux l'emporte (`LEAST(dist_content, dist_keyword)`, repli sur le contenu quand le vecteur de mots-clés est nul).

Un moteur **hybride BM25 + pgvector** a existé ici jusqu'en v1.14.0, quand la mémoire long terme a migré vers son propre modèle PostgreSQL. Le chemin de recherche a suivi, le chemin hybride non : au 2026-07-27 il n'avait plus **aucun appelant**, 21 % de couverture, 100 lignes sur 127 jamais atteintes — et le panneau de débogage annonçait pourtant l'option à l'utilisateur. Module, réglages, métriques et affichage ont été supprimés ensemble ([ADR-168](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/architecture/ADR-168-Removal-Of-Dead-Hybrid-Memory-Search.md)). La recherche hybride reste bien vivante, mais là où elle est réellement utilisée : les RAG Spaces (section 17).

### 11.5. Carnets de bord stratifiés (Journals)

L'assistant tient des réflexions introspectives organisées sur quatre thèmes (auto-réflexion, observations utilisateur, idées/analyses, apprentissages) ET quatre niveaux d'abstraction (`L0` observation brute, `L1` directive `WHEN→DO BECAUSE`, `L2` pattern transversal, `L3` facette de portrait — voir [ADR-079](https://github.com/jgouviergmail/LIA/blob/main/docs/architecture/ADR-079-Stratified-Journal-Consciousness.md)). Chaque entrée porte un statut épistémique (`confidence` ∈ {low, medium, high}) et deux compteurs (`evidence_count`, `contradiction_count`).

**Double déclencheur** : extraction post-conversation (fire-and-forget, fréquente, lightweight) + consolidation périodique (4-12 h par utilisateur, complexe).

**Embeddings dual-vector Gemini** (`gemini-embedding-001`, 1536d, ADR-069) : un vecteur sur `title + content`, un sur les `search_hints`. La recherche prend `LEAST(dist_content, dist_keyword)` par ligne pour ponter le vocabulaire introspectif et le vocabulaire utilisateur.

**Auto-évaluation différée T → T+1** : `MessagesState.injected_journal_ids` (symétrique de `injected_memories`) transporte les IDs entre tours. Le `response_node` lit les IDs du tour précédent au début, les passe à l'extracteur post-conversation, puis écrit les IDs du tour courant à la fin. L'extracteur voit les directives appliquées + la réaction utilisateur dans le même prompt et signale `evidence_outcome="evidence" | "contradiction"` sur des actions update — le service incrémente atomiquement les compteurs (anti-hallucination niveau 4 : le LLM ne fait que signaler, le service possède les entiers). Coût LLM additionnel **zéro** (même appel d'extraction, prompt enrichi).

**Diffusion ambiante du portrait utilisateur** : la consolidation produit dans le **même appel LLM** (zéro appel additionnel) un `portrait_full` (~200 tokens, conversation/planner) et un `portrait_brief` (~60 tokens, flux secondaires) persistés sur la table `users`. Le builder `build_journal_user_model_block(user_id, format, flow)` (`src/domains/journals/portrait_builder.py`, symétrique de `build_psyche_prompt_block`) retourne un bloc `<UserModelContext>...</UserModelContext>` avec dégradation gracieuse. Diffusé dans **8 flux** : 2 primaires en format full (`response_node`, `planner_node_v3`) et 6 secondaires en format brief (`react_setup_node`, `interests/proactive_task`, `scheduler/reminder_notification`, `voice/service`, `heartbeat/prompts`, `agents/services/fallback_response` sync + async).

**Trois leviers de correction utilisateur** sur le portrait (jamais directement éditable) : (1) édition CRUD des entrées L3 sources, (2) `POST /journals/portrait/feedback` (texte libre → entrée L0 `source=user_correction` + consolidation synchrone qui repondère les L3), (3) `POST /journals/consolidate` (consolidation manuelle, bypass cooldown).

**Discipline de dédoublonnage** : pas de garde-fou write-time (retiré v1.14.0). À la consolidation, `STEP 1` impose un scan pairwise explicite qui fusionne les doublons sémantiques, et `STEP 5` regroupe activement les L1 convergentes en patterns L2.

**Anti-hallucination en 4 couches** : `field_validator` Pydantic sur les UUIDs, table de référence d'IDs dans le prompt, filtrage des actions par IDs connus à l'extraction et à la consolidation, et incréments atomiques des compteurs (le LLM ne signale que `evidence_outcome`).

**Observabilité dédiée** : 11 métriques Prometheus dans `src/infrastructure/observability/metrics_journals.py` — `journal_entries_total{action,theme,source}`, `journal_evidence_total{outcome}`, `journal_consolidation_promotions_total{from_level,to_level}`, `journal_level_distribution{level}`, `journal_portrait_present_total{flow,format}`, `journal_portrait_age_hours`, `journal_portrait_feedback_total{outcome}`, etc.

### 11.6. Système d'intérêts

Détection par analyse des requêtes avec évolution bayésienne des poids (decay configurable). Les intérêts sont regroupés en **sujets** par clustering LLM batch (donnée dérivée, auto-réparante), et la sélection des notifications tire par **rareté à deux niveaux** (cooldown par sujet + priorité aux sujets et intérêts les moins servis) — une passion ne monopolise jamais les notifications. Contenu multi-source (Perplexity, Brave, Wikipedia, réflexion LLM) avec **liens sources cliquables** ajoutés de manière déterministe. Feedback utilisateur (thumbs up/down/block) ajuste les poids ; fusion nocturne des quasi-doublons.

---

## 12. Infrastructure LLM multi-provider

### 12.1. Factory Pattern

```python
llm = get_llm(provider="openai", model="gpt-5.4", temperature=0.7, streaming=True)
```

Le `get_llm()` résout la configuration effective via `get_llm_config_for_agent(settings, agent_type)` (code defaults → DB admin overrides), instancie le modèle, et applique les adaptateurs spécifiques.

### 12.2. 56 types de configuration LLM

Chaque nœud du pipeline est configurable indépendamment via l'Admin UI — sans redéploiement :

| Catégorie | Types configurables |
|-----------|-------------------|
| Pipeline | router, query_analyzer, planner, semantic_validator, context_resolver |
| Réponse | response, hitl_question_generator |
| Background | memory_extraction, interest_extraction, journal_extraction, journal_consolidation |
| Agents | contacts_agent, emails_agent, calendar_agent, browser_agent, etc. |

### 12.3. Token Tracking

Le `TrackingContext` suit chaque appel LLM avec `call_type` ("chat"/"embedding"), `sequence` (compteur monotone), `duration_ms`, tokens (input/output/cache), et coût calculé depuis les tarifs DB. Les trackers partagent un `run_id` pour l'agrégation. Le debug panel affiche toutes les invocations (pipeline + background tasks) dans une vue unifiée chronologique.

### 12.4. Catalogue admin DB-source-of-truth

La table `llm_models` porte le catalogue complet : provider, capacités fonctionnelles classiques (`supports_tools`, `supports_structured_output`, `supports_strict_mode`, `supports_streaming`, `supports_vision`), et — ajouts structurants — la **matrice sampling par modèle** (`supports_temperature`, `supports_top_p`, `supports_frequency_penalty`, `supports_presence_penalty`) ainsi que la **forme reasoning** (`reasoning_widget` ∈ {`none`, `enum`, `budget_int`, `toggle_budget`}, `reasoning_enum_values` JSONB list, `reasoning_budget_range` JSONB `{min, max, off_sentinel, dynamic_sentinel}`, `reasoning_doc_i18n_key`). Cette déclaration par-modèle remplace la regex côté frontend qui devinait jadis quels sliders cacher : la fenêtre Configuration LLM lit directement les flags DB et n'expose que les paramètres réellement acceptés par l'API du modèle.

L'admin Tarification LLM Texte expose un mécanisme de **templates dynamiques dérivés de la DB** : le service `LLMModelService.list_templates()` regroupe les lignes actives par leur empreinte reasoning à 4 champs et retourne un représentant déterministe par groupe (~15 formes uniques aujourd'hui). Ajouter un nouveau modèle reasoning revient à choisir « copier la forme depuis tel modèle existant » ; les 4 champs de forme sont snapshot-copiés à la création. Mode **Custom** disponible pour les disruptions ; tout modèle Custom à empreinte inédite devient automatiquement template pour les ajouts suivants. `kind` (chat / image / audio / …), les 4 caps sampling et la clé i18n du tooltip restent saisis indépendamment, hors du template. Voir `docs/technical/LLM_PRICING_TEMPLATES.md`.

### 12.5. Prompt caching provider-agnostique

Tous les providers facturent moins cher (et répondent plus vite) quand le début du prompt est identique octet pour octet d'une requête à l'autre — mais chacun avec son mécanisme : les blocs `cache_control` d'Anthropic, le routage `prompt_cache_key` d'OpenAI, les caches implicites de préfixe chez DeepSeek/Qwen/Gemini. LIA sépare les responsabilités : chaque prompt système versionné place son contenu statique (rôle, règles, exemples, format de sortie) en tête, puis un marqueur canonique `--- DYNAMIC CONTEXT ---`, puis tout le contenu par-requête (date, requête, contexte, catalogue d'outils). Les templates restent neutres vis-à-vis du modèle ; la couche infrastructure traduit le marqueur dans le dialecte de chaque provider — le split `cache_control` pour Anthropic, la clé de routage de cache pour OpenAI, rien du tout pour les caches implicites qui profitent du préfixe stable tel quel. Le prompt du planner — le plus coûteux du pipeline — expose ainsi un préfixe cacheable byte-stable d'environ 77 % entre deux requêtes quelconques. Des gardes CI shrink-only verrouillent la convention : tout prompt dynamique doit porter le marqueur, aucun placeholder ne peut le précéder sans exception justifiée, et la stabilité byte du préfixe du planner est vérifiée à chaque build.

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

### 13.4. Téléphonie agentique (ADR-127)

LIA peut passer un appel sortant à la place de l'utilisateur, mener une conversation orientée objectif, puis réinjecter un résumé écrit dans le chat. Contrairement aux connecteurs lecture/écriture ci-dessus, le connecteur de téléphonie pilote un **agent vocal tiers** (ElevenLabs Agents) sur le réseau téléphonique, configuré par utilisateur (identifiants personnels) — LIA n'effectue aucune facturation de son côté.

**Protection des données par capacité, pas par prompt.** L'agent d'appel ne dispose que d'un unique outil de disponibilité en lecture seule renvoyant les créneaux libre/occupé ; il ne peut jamais lire les titres, participants, lieux ou contenus des événements. La garantie est structurelle — l'outil n'expose tout simplement pas ces données — et non une instruction de prompt dont le modèle pourrait être détourné.

**Chemin de retour.** L'appel n'est jamais enregistré et la transcription n'est jamais conservée. À la fin de l'appel, un webhook signé HMAC propre à chaque utilisateur déclenche une synthèse LLM sans outils produisant un résumé court et éphémère, réinjecté de façon asynchrone dans la conversation (le même canal d'exécution détachée que l'ADR-117) avec un brouillon de suivi optionnel en un geste. Chaque appel est soumis à une confirmation HITL avant la composition, et l'ensemble du sous-système est protégé par un feature flag.

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

Factory **catalogue-driven** (ADR-081) : `factory.get_tts_client()` lit l'override actif `voice_tts` (provider + model + voice + tuning, stockés dans `llm_config_overrides.voice_tts.provider_config` JSONB) et instancie le client correspondant. Trois providers livrés : Edge (gratuit, défaut), OpenAI (`tts-1` / `tts-1-hd`) et ElevenLabs (`eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`). Si la clé d'un provider payant manque, repli automatique sur Edge (warning loggé). Streaming progressif phrase-par-phrase via `ProgressiveSentenceStreamer` (ADR-082) pour minimiser la latence — la première phrase est synthétisée pendant que le LLM en génère encore d'autres. Un délimiteur ne ferme une phrase qu'en fin d'entrée ou suivi d'une espace (ADR-154) : sur le chemin progressif le tampon grandit token par token, si bien que `"3."` est un état transitoire parfaitement normal — nombres décimaux, prix, numéros de version et URL restent d'un seul tenant, et les deux découpeurs (`_extract_sentences` et le streamer) sont épinglés par une table de cas commune assortie d'un test qui exige leur accord.

---

## 16. Proactivité : Heartbeat et actions planifiées

### 16.1. Heartbeat : architecture en 2 phases

**Phase 1 — Décision** (coût-effective, gpt-4.1-mini) :
1. `EligibilityChecker` : opt-in, fenêtre horaire, cooldown (1h global, 30 min par type), activité récente — les filtres optionnels `notification_filter`/`cross_type_filters` séparent le budget d'éligibilité de chaque flux du livre de comptes partagé
2. `ContextAggregator` : 12 sources en parallèle (`asyncio.gather`) : Calendar, Weather (détection de changements), Tasks, Emails, Interests, Activité, notifications heartbeat/intérêts récentes, autres surfaces proactives (rappels déclenchés, résultats d'automatisations, comptes rendus d'appels — la fenêtre anti-redondance étendue), Health, Anniversaires à venir et Boucles ouvertes (le registre d'engagements, ADR-139). Une **seconde passe** dérive ensuite une requête sémantique dynamique du contexte agrégé pour sélectionner Journaux et Mémoires (symétrie ADR-135) et calcule le conseil de départ tenant compte du trafic (ETA Routes, sous flag). Les intérêts arrivent sous forme d'**échantillon varié** (`pick_varied_sample` : un intérêt par sujet, sujets les moins récemment servis d'abord) — le modèle ne peut mentionner que ce qu'on lui montre, donc la rotation est mécanique
3. LLM structured output : `skip` | `notify` + `interest_topic` (copié verbatim de l'échantillon, garde runtime fail-open) et labels de sources contraints par un `Literal`. Anti-redondance à deux niveaux : source, et **contenu** — les 10 dernières notifications sur 7 jours sont injectées avec leurs extraits, ce qui interdit de reproposer un thème même issu d'une autre source

**Phase 1b — Enrichissement** (si `interest_topic`) : `InterestContentGenerator` (Perplexity → Brave → Wikipedia) sous timeout dur, dédupliqué contre les embeddings des notifications récentes. Fail-open intégral : flag éteint, échec ou vide → le message part sans faits.

**Phase 2 — Génération** (si notify) : LLM réécrit avec personnalité + langue utilisateur. Quand des faits ont été récupérés, un bloc VERIFIED FACTS impose de nommer 1-2 éléments concrets sans jamais inventer, et les liens sources sont ajoutés de façon déterministe. Dispatch multi-canal. Une mention d'intérêt est inscrite au livre de comptes partagé (`InterestNotification(source='heartbeat')`) : le sujet se met alors au repos pour les deux flux proactifs.

Chaque source est bornée par un budget de temps et faillit indépendamment. Ce budget encadre une part d’event-loop partagé entre les fetchers — ce n’est pas un délai de base de données : les signaux santé le franchissaient en régime nominal parce que leur lecture rapatriait des dizaines de milliers de lignes brutes pour produire quelques dizaines de nombres, figeant le worker le temps du décodage. La lecture s’appuie désormais sur une agrégation journalière calculée en base, et tout abandon de source est compté puis chronométré plutôt que silencieux — une source qui échoue en s’effaçant ne laisse aucune trace dans la notification.

### 16.2. Agent Initiative (ADR-062)

Node LangGraph post-exécution : après chaque tour actionnable, l'initiative analyse les résultats et vérifie proactivement les informations cross-domain (read-only). Exemples : météo pluie → vérifier calendrier pour activités outdoor, email mentionnant un rdv → vérifier disponibilité, tâche deadline → rappeler le contexte. 100% prompt-driven (pas de logique hardcodée), pré-filtre structurel (domaines adjacents), injection mémoire + centres d'intérêt, champ suggestion pour proposer des actions write. Configurable via `INITIATIVE_ENABLED`, `INITIATIVE_MAX_ITERATIONS`, `INITIATIVE_MAX_ACTIONS`.

Le même nœud émet aussi jusqu'à 3 **puces de suivi** — de courtes demandes que l'utilisateur enverra probablement ensuite, formulées dans sa langue et ancrées dans les résultats visibles. Une sanitisation côté serveur (clamp, dédoublonnage insensible à la casse, plafond dur) et un handoff pop-once par run les portent à la fois dans le chunk SSE `done` et dans les métadonnées du message archivé : les puces s'affichent en direct et survivent à un rechargement ; en taper une ne fait que préremplir la saisie.

### 16.3. Actions planifiées

APScheduler avec leader election Redis (SETNX, TTL 120s, recheck 5s). `FOR UPDATE SKIP LOCKED` pour isolation. Auto-approve des plans (`plan_approved=True` injecté dans le state). Auto-disable après 5 échecs consécutifs. Retry sur erreurs transitoires.

---

## 17. RAG Spaces et recherche hybride

### 17.1. Pipeline

Upload → Chunking → Embedding (gemini-embedding-001, 1536d) → pgvector HNSW → Recherche hybride (cosine + BM25 avec alpha fusion) → Injection contexte dans le **Response Node**.

Note : l'injection RAG se fait dans le nœud de réponse, pas dans le planificateur. Le planner reçoit en revanche l'injection des journaux personnels via `build_journal_context()`.

### 17.2. System RAG Spaces (ADR-058)

FAQ intégrée (200+ Q/A, 24 sections) indexée depuis `docs/knowledge/`. Détection `is_app_help_query` par QueryAnalyzer, Rule 0 override dans RoutingDecider, App Identity Prompt (~200 tokens, lazy loading). La péremption se juge sur un SHA-256 des fichiers source **et** sur le corpus stocké lui-même (un chunk par entrée parsée, exactement un document) : une empreinte concordante sur un nombre de lignes erroné est une réparation, pas un no-op. L'auto-indexation tourne dans chaque worker uvicorn, donc la ligne de l'espace est revendiquée par `FOR UPDATE SKIP LOCKED` — un seul écrivain, les autres passent sans attendre — et chaque vecteur est calculé **avant** la première instruction destructrice : un refus du fournisseur ne supprime rien et le corpus précédent continue de servir (ADR-162).

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

**Authentification forte (ADR-143/144).** Au-delà du mot de passe et d'OAuth Google, le compte peut être protégé par des **passkeys WebAuthn** (credentials discoverable, conditional UI sur le champ e-mail, défis Redis à usage unique, détection de clonage par compteur de signature, zéro énumération sur le chemin anonyme) et un **second facteur TOTP** (login en deux temps via un token éphémère, anti-rejeu par timestep explicite, 10 codes de secours hachés à usage unique). Les actions sensibles — gestion des credentials, export, révocation d'appareils, désactivation du mot de passe — passent par une **re-authentification step-up** : fenêtre de 5 minutes ouverte par toute connexion complète (sémantique sudo), contrat **403 typé** (`step_up_required`, jamais un 401 qui redirigerait vers /login). « **Mes appareils** » liste chaque session BFF sous un `display_id` opaque avec des métadonnées volontairement bornées (familles UA/OS, IP tronquée en /24), révoque un appareil ou tous les autres, et coupe le flux SSE d'une session révoquée en un tick de keepalive ; une notification push signale toute connexion depuis un appareil non attesté par un token FCM valide.

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
| XSS (rendu LLM) | Frontière `rehype-sanitize` sur le pipeline markdown du chat (`rehypeRaw → rehypeSanitize → rehypeMathInText → rehypeKatex`, schéma audité — `script`/`iframe`/`form`/handlers supprimés), HTTP-only cookies, CSP backend ; les MCP/Skill Apps ne passent jamais par le markdown (sentinelle → widget iframe sandboxé) |
| CSRF | SameSite=Lax |
| SQL Injection | SQLAlchemy ORM (requêtes paramétrées) |
| SSRF | DNS resolution + IP blocklist (Web Fetch, MCP, Browser) ; l'installation de skills par URL réutilise le même validateur avec des termes plus stricts : https uniquement, redirections refusées, plafond streamé, deadline totale de transfert, rate limit par utilisateur Le navigateur va plus loin : **chaque requête émise par une page** — redirection, sous-ressource, iframe, XHR — résout sa propre destination derrière un cache de verdicts borné, et un échec interrompt au lieu de laisser passer. |
| Prompt Injection | Provenance portée par la donnée : 24 types classés (défaut fermé, assert au démarrage), marquage sur les trois surfaces atteignant le LLM, 7 familles de motifs détectées en 6 langues sans jamais réécrire le contenu (ADR-167) ; marqueurs `<external_content>` conservés côté outils |
| Rate Limiting / spoofing IP | Redis sliding window distribué (Lua atomique) ; chaîne proxy de confiance — ports API bindés loopback (cloudflared = seule entrée), uvicorn `--proxy-headers`, `request.client.host` validé comme unique source d'IP (fini le bucket global partagé, XFF brut jamais lu) Un plafond global précède chaque route sous forme de véritable middleware ASGI adossé à ce même limiteur partagé, de sorte qu'un client seul ne peut consommer toute l'API ; les sondes en sont exemptées pour ne jamais brider la supervision. |
| Supply Chain | SHA-pinned GitHub Actions, Dependabot weekly |

### 19.4. Durabilité des données : sauvegardes automatisées (ADR-109)

**Une sauvegarde n'existe vraiment qu'une fois la restauration prouvée.** Un sidecar `postgres-backup` snapshotte la base complète selon une planification cron avec rotation à trois niveaux (quotidien / hebdomadaire / mensuel) ; chaque paramètre — planification, rétention, répertoire cible, options pg_dump — est piloté par `.env`. Les dumps portent `--clean --if-exists` : la restauration tient en une commande, vers la base vivante ou un conteneur jetable. Le drill lui-même est versionné : `task backup:verify` restaure le dernier dump dans un conteneur pgvector éphémère et compare la révision de schéma Alembic et des comptages de référence avec la source vivante. RPO : ≤ 24 h (paramétrable). Les limites assumées (copie off-site, volume des pièces jointes) sont tracées dans l'ADR-109 plutôt que laissées implicites.

### 19.5. Isoler ce qui s'exécute

Trois surfaces exécutent quelque chose pour le compte de l'utilisateur, et chacune est traitée comme hostile par construction.

**Les scripts de skills s'exécutent dans un conteneur jetable.** Pas de socket Docker, pas de réseau, un système de fichiers racine en lecture seule avec un petit tmpfs inscriptible, un uid non privilégié, toutes les capacités larguées, et des plafonds mémoire / processus / CPU / taille de fichier. Ce qui compte, c'est ce qu'un processus fils *hérite* : en production l'API appartient au groupe `docker`, et un groupe s'hérite — se contenter de changer d'uid laisserait la socket accessible. Le SOURCE du script est passé en argument plutôt que monté, parce que l'API est elle-même un conteneur et qu'un bind se résoudrait contre l'hôte ; ce choix laisse aussi stdin libre pour la charge JSON sur laquelle repose le contrat. Sans démon joignable, l'exécution est refusée plutôt que dégradée — un bac à sable qui se désactive tout seul ne protège de rien.

**Les tâches d'infrastructure se confirment, elles ne se présument pas.** Une tâche sur un serveur distant est préparée, pas lancée : la confirmation montre le serveur visé, le texte intégral de la tâche et les consignes que le modèle a lui-même écrites dans l'invite distante — le champ qu'une injection utiliserait est précisément celui qu'il ne faut pas masquer. Le privilège est re-vérifié à l'exécution, car des droits accordés au moment où une demande est formulée peuvent ne plus valoir au moment où elle est approuvée.

**Le corps d'une requête est borné avant d'être lu.** Le plafond s'applique en amont du handler, sur la longueur déclarée quand elle existe et sur les octets comptés sinon, de sorte que le pic mémoire est fixé par nous et non par l'appelant — sur les webhooks, cela se produit avant l'authentification. Sa cohérence avec les plafonds d'upload par endpoint est assertée au démarrage : une contradiction refuse de booter au lieu d'apparaître comme un refus distant qu'aucun journal n'explique.

### 19.6. La provenance du contenu est portée par la donnée (ADR-167)

**Un texte que LIA lit n'est pas un texte que LIA exécute.** Le corps d'un e-mail, la description d'une invitation écrite par son organisateur, une page web, le résumé éditorial d'un lieu, le résultat d'un serveur MCP : tous arrivent dans le prompt, et n'importe qui peut y déposer une consigne.

Le marquage outil par outil a été invalidé par la recherche exhaustive de ses appelants. **Il oublie** : `perplexity_tools`, `brave_tools`, `mcp_react_tools` et `emails_tools` n'étaient pas couverts — ce dernier annonçant pourtant dans sa docstring qu'il renvoie *« FULL email content (body, headers, attachments) »*. **Et il ne couvre pas la bonne surface** : le contenu atteint le modèle par deux chemins dont aucun n'est un outil, dont `generate_data_for_filtering`, qui construit le bloc `{data_for_filtering}` du prompt de réponse sur **tous** les tours produisant des données, dans les **deux** modes d'exécution.

La provenance est donc une propriété de la **donnée** : les 24 types du registre sont classés une fois, un type inconnu ou nul vaut *externe* (défaut fermé), et un assert de complétude au démarrage refuse de booter sur un type non classé — même doctrine qu'ADR-085. Quinze types sur vingt-quatre sont rédigés par des tiers.

**Détecter, jamais assainir.** Sept familles de motifs sont reconnues dans les six langues — rôle usurpé, détournement d'instruction, changement de persona, exfiltration, outil LIA nommé dans du texte tiers, Unicode invisible, directive cachée en commentaire HTML — et le contenu part au modèle **inchangé**, accompagné d'une note qui nomme la famille. Assainir reviendrait à réécrire un e-mail que l'utilisateur peut vouloir lire tel quel, pour une garantie que le contournement suivant démentirait. La détection est bornée aux 20 000 premiers caractères et **ne journalise jamais le texte** : il est par construction contrôlé par l'attaquant et contient couramment les données de l'utilisateur.

---

## 20. Observabilité et monitoring

### 20.1. Stack

| Technologie | Rôle |
|-------------|------|
| Prometheus | 447 métriques custom (RED pattern) |
| Grafana | 26 dashboards production-ready |
| Loki | Logs structurés JSON agrégés |
| Tempo | Traces distribuées cross-service (OTLP gRPC) |
| Langfuse | LLM-specific tracing (prompt versions, token usage) |
| Alertmanager | Noyau de 14 alertes vitales notifiées par e-mail (runbooks liés, seuils par environnement) |
| structlog | Logging structuré avec PII filtering |

### 20.2. Debug Panel embarqué

Le debug panel dans l'interface chat fournit une introspection temps réel par conversation : intent analysis, execution pipeline, LLM pipeline (réconciliation chronologique de tous les appels LLM + embedding), context/mémoire, intelligence (cache hits, pattern learning), journaux (injection + extraction background), lifecycle timing.

Les métriques debug persistent dans `sessionStorage` (50 entrées max).

**Pourquoi un debug panel dans l'UI ?** Dans un écosystème où les agents IA sont notoirement difficiles à debugger (comportement non déterministe, chaînes d'appels opaques), rendre les métriques accessibles directement dans l'interface élimine la friction de devoir ouvrir Grafana ou lire des logs. L'opérateur voit immédiatement pourquoi une requête a coûté cher ou pourquoi le routeur a choisi tel domaine.

### 20.3. DevOps Claude CLI (admin uniquement)

Les administrateurs peuvent interagir avec Claude Code CLI directement depuis la conversation LIA pour diagnostiquer les problèmes serveur en langage naturel : *"Regarde les logs pour voir si tout fonctionne"*, *"Vérifie l'espace disque"*, *"Quel container utilise le plus de RAM ?"*. Claude CLI est installé dans le container Docker API et exécuté localement via subprocess, avec accès au Docker socket pour inspecter tous les containers. Les permissions sont configurables par environnement (`--allowedTools`/`--disallowedTools`) et l'accès est restreint aux superusers via un check DB direct. Les sessions sont persistantes pour permettre des investigations multi-tours.

---

## 21. Performance : optimisations et métriques

### 21.1. Métriques clés (P95)

| Métrique | Valeur | SLO |
|----------|--------|-----|
| API Latency | 450 ms | < 500 ms |
| Premier événement SSE (accusé de réception) | 380 ms | < 500 ms |
| Router Latency | 800 ms | < 2 s |
| Planner Latency | 2.5 s | < 5 s |
| Embedding sémantique | ~100 ms | < 200 ms |
| Checkpoint save | < 50 ms | P95 |
| Redis session lookup | < 5 ms | P95 |

> Ces latences mesurent l'infrastructure. Le temps de réponse complet perçu dépend de la cascade d'appels LLM (de quelques secondes à plusieurs dizaines selon la complexité de la demande et le matériel) — c'est le principal chantier d'optimisation en cours, mesuré en production et suivi dans la roadmap.

### 21.2. Optimisations implémentées

| Optimisation | Gain mesuré | Compromis |
|-------------|-------------|-----------|
| Message Windowing | -50 % latence, -77 % coût | Perte de contexte ancien (compensé par Data Registry) |
| Smart Catalogue | 96 % réduction tokens | Panic mode nécessaire si filtrage trop agressif |
| Pattern Learning | 89 % économies LLM | Amorcage requis (golden patterns) |
| Prompt Caching | 90 % discount | Dépend du support provider |
| Embeddings sémantiques | Routage multilingue haute précision | Dépend de la disponibilité du fournisseur API |
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
Ruff + Black + MyPy               Unit tests + coverage (62 %)
                                  Integration tests (PostgreSQL + Redis)
Unit tests rapides                Code Hygiene (i18n, Alembic, lockfiles)
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
| Coverage | 62 % minimum (ratchet, jamais abaissé) | Imposé en CI |

### 22.3. Builds de dépendances reproductibles

Les dépendances backend sont verrouillées de bout en bout. Les fichiers
requirements sont des manifestes d'intention ; ce que chaque environnement
installe réellement — image de production, conteneur de dev, CI, venv local —
ce sont des lockfiles universels committés, compilés par `uv pip compile
--universal` : un seul fichier couvrant linux/amd64, linux/arm64 et Windows,
qui épingle les ~200 paquets réellement embarqués avec les hashes SHA256 de
chaque fichier publié. pip vanilla les installe avec `--require-hashes` : un
même commit produit donc toujours la même image, vérifiable octet par octet.
Un garde CI fait échouer toute édition de manifeste sans régénération du lock,
et `pip-audit` ainsi que le SBOM de release lisent le lockfile — l'arbre
transitif complet est audité et inventorié, pas seulement les paquets déclarés.

---

### 22.4. L'audit est public — et reproductible

Le niveau d'exigence décrit dans ce guide n'est pas auto-déclaré : un audit technique 360° complet — **8,3/10 sur 24 périmètres normalisés** de la grille ISO/IEC 25010, constats ouverts compris — est publié dans le dépôt ([rapport complet](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/README.md)), avec le [protocole d'audit](https://github.com/jgouviergmail/LIA-Assistant/blob/main/docs/audit/AUDIT_PROTOCOL.md) qui rend chaque cycle reproductible : commit épinglé, exigences de preuve par périmètre, notation ancrée, et un script versionné qui mesure la taille en SLOC logiques. Le rapport se termine par les commandes exactes pour reproduire les mesures vous-même.

### 22.5. Une garde ne vaut que ce qu'elle mesure

`html { overflow-x: hidden }` rogne un débordement horizontal au lieu de produire
un défilement. Toute garde bâtie sur `scrollWidth - clientWidth` est donc
**structurellement aveugle** à un contrôle poussé hors de l'écran : mesurée sur
108 échantillons, elle renvoyait zéro à chaque largeur pendant que le bouton de
déconnexion se trouvait 235 px au-delà du bord droit en allemand. La garde
compare désormais la boîte de chaque contrôle interactif à la fenêtre, largeur
par largeur **et langue par langue** — l'allemand et l'italien portent les
libellés les plus longs et cèdent les premiers.

Même logique pour la hauteur : `100vh` désigne la fenêtre *large*, celle qu'on
aurait si la barre d'adresse du navigateur était rétractée — donc pas l'état
dans lequel une page se charge sur un téléphone. Un test interdit toute
contrainte de hauteur exprimée en `vh` seul, avec une liste d'exemptions écrites
et un auto-test qui prouve que le détecteur détecte encore.

Enfin, ce que la mise en page mobile a le droit d'abandonner est écrit dans une
table plutôt que laissé au jugement : chaque surface conditionnée à la largeur
déclare si elle est bloquante, substituée ou réservée au bureau, avec sa raison.
Les tests tiennent cette table contre le code — l'emplacement doit exister,
porter la variante Tailwind du seuil annoncé, et une surface qui requête ou
minute doit être **montée conditionnellement**, pas simplement masquée :
`display:none` monte quand même le composant, qui continue de consommer réseau
et batterie pour un affichage que personne ne verra.

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

Tous les tools retournent `ToolResponse` (succès) ou `ToolErrorModel` (échec) avec un enum `ToolErrorCode` (18+ types : INVALID_INPUT, RATE_LIMIT_EXCEEDED, TEMPLATE_EVALUATION_FAILED...) et un flag `recoverability`. Côté API, des raisers d'exceptions centralisés (`raise_user_not_found`, `raise_permission_denied`...) remplacent partout les HTTPException brutes — zéro `raise HTTPException` dans le code, tenu par une garde CI et un filet de tests de contrat qui prouve les réponses byte-identiques — garantissant des contrats d'erreur cohérents, journalisés et mesurés (Prometheus) sur chaque chemin d'erreur.

### 23.4. Système de Prompts

78 fichiers `.txt` versionnés dans `src/domains/agents/prompts/v1/`, chargés via `load_prompt()` avec cache LRU (32 entrées). Versions configurables par variables d'environnement.

### 23.5. Activation Centralisée des Composants (ADR-061)

Système en 3 couches résolvant un problème de duplication : avant l'ADR-061, le filtrage des composants activés/désactivés était dispersé dans 7+ endroits. Maintenant :

| Couche | Mécanisme |
|--------|-----------|
| Couche 1 | Gate-keeper de domaine : valide les domaines LLM contre `available_domains` |
| Couche 2 | `request_tool_manifests_ctx` : ContextVar construit une fois par requête |
| Couche 3 | Guard API 403 sur les endpoints proxy MCP |

### 23.6. Feature Flags

Chaque sous-système optionnel est contrôlé par un flag `{FEATURE}_ENABLED`, vérifié au démarrage (enregistrement scheduler), au câblage des routes et à l'entrée des nœuds (court-circuit instantané). Cela permet de déployer le codebase complet tout en activant les sous-systèmes progressivement.

### 23.7. Skills enrichis : frames HTML et images

Les Skills (standard agentskills.io) peuvent retourner, en plus du texte, des **frames HTML interactives** et des **images** via un contrat JSON typé `SkillScriptOutput`. Le script Python écrit sur stdout :

```json
{ "text": "required", "frame": { "html" | "url", "title", "aspect_ratio" }, "image": { "url", "alt" } }
```

Les trois canaux sont indépendants et combinables (text seul, text+frame, text+image, tous les trois). La pipeline complète réutilise l'infrastructure Data Registry existante :

```
run_skill_script → parse_skill_stdout() → SkillScriptOutput
                 → build_skill_app_output() → RegistryItem(type=SKILL_APP)
                 → ReactToolWrapper._accumulated_registry
                 → response_node → SkillAppSentinel.render() → <div class="lia-skill-app">
                 → SSE registry_update + sentinel HTML
                 → MarkdownContent.tsx → SkillAppWidget (iframe sandbox + image card)
```

**Sécurité multi-couches** : iframe sandbox `allow-scripts allow-popups` (jamais `allow-same-origin`), CSP stricte auto-injectée pour `frame.html` des skills utilisateur (`connect-src 'none'`, `frame-src 'none'`), limite `SKILLS_FRAME_MAX_HTML_BYTES = 200 KB`, bridge `postMessage` minimaliste sans `tools/call` ni `resources/read`.

**Vignettes de galerie.** La fiche d'une compétence sert `assets/preview.png` et retombe sur une icône quand le fichier manque — un repli indiscernable d'une vignette simplement vide. Les aperçus des compétences système sont donc **générés** : un script versionné tient un dessin par compétence, en géométrie pure sans dépendance de police, ce qui rend la sortie identique d'une machine à l'autre. Une garde échoue si une compétence n'a pas de dessin, ou si l'image livrée ne correspond plus à ce que son générateur produit.

**Conventions runtime** : `_lang` et `_tz` auto-injectés dans `parameters` (les locales POSIX n'étant pas installées dans le container, les scripts utilisent des tables de traduction inline plutôt que `strftime`+`setlocale`). Thème et langue synchronisés en live via `postMessage` + `MutationObserver` sur `<html class>` et `<html lang>`. Auto-resize iframe via `getBoundingClientRect().bottom` (pattern iframe-resizer). Interactivité client-side via `addEventListener` uniquement (pas de `onclick` inline sous CSP) et `crypto.getRandomValues` pour le pseudo-aléatoire.

**Primacy effect** : `skills_context` est injecté comme 2ᵉ message système dédié avec préfixe `"SKILL INSTRUCTIONS CONTRACT (PRIORITY: HIGHEST)"`, ce qui garantit que les `references/*.md` d'un skill actif l'emportent sur les `<ResponseGuidelines>` génériques.

**Rendu conditionnel** : `INTERACTIVE_WIDGET_TYPES = {SKILL_APP, MCP_APP, DRAFT}` — ces widgets sont injectés en HTML indépendamment du `user_display_mode` (Rich HTML / Markdown / Cards), alors que les autres RegistryItems restent conditionnels au mode Cards.

Une bibliothèque de skills système démontre le contrat : `interactive-map`, `weather-dashboard`, `calendar-month`, `qr-code`, `pomodoro-timer`, `unit-converter`, `dice-roller` — chacun illustrant une combinaison différente des trois canaux.

**Cycle de vie des skills** : toute skill entre par un pipeline d'import unique et durci (`SkillImportService`) — validation stricte du nom agentskills.io avant toute écriture disque (garde anti path-traversal), plafonds d'expansion des zips, staging + swap avec restauration automatique de la version précédente en cas d'échec, et rejet des conflits de noms inter-scopes (DB + cache en double autorité). Le générateur de skills intégré emprunte le même pipeline via l'outil `import_user_skill` : une skill créée dans le chat est validée, installée et annoncée par son nom dans le même tour — sans upload manuel. Les skills dont le workflow s'étend sur plusieurs tours déclarent `dialogue: true` dans leur frontmatter, que le chat override du QueryAnalyzer respecte (leur détection survit aux réponses conversationnelles de suivi) tandis que le runner ReAct des skills reçoit l'historique de conversation fenêtré pour reprendre le dialogue au lieu de le recommencer.

La surface skills est une **galerie** : les cartes ouvrent une fiche détail avec la description localisée, les **canaux de sortie** déclarés (le loader lit enfin le champ frontmatter `outputs:` que le générateur validait depuis toujours — parité verrouillée en CI), une `assets/preview.png` embarquée servie par un endpoint dédié (garde traversal par pattern de nom, plafond de taille, 404 indifférencié pour les skills désactivées par l'admin), et un avertissement de provenance sur toute skill non-système. L'installation accepte une seconde source en plus de l'upload de fichier : une URL https, durcie comme décrit en §19.3, alimentant exactement le même pipeline d'import (`skill_url_imports_total{outcome}` compte chaque chemin).

**Modifier une skill.** Le moteur d'écriture existait déjà — ré-importer sa propre skill est un upsert atomique (ADR-118) — mais trois verrous le rendaient inatteignable : le manifeste était illisible (l'activation retire le frontmatter), un remplacement effaçait la vignette que le chat ne peut pas transporter, et le prompt du générateur ordonnait de renommer en cas de conflit. Une modification est désormais une **régénération intégrale** sous le même nom, précédée de la lecture du paquet courant. La confirmation vit **dans l'outil** et non dans le HITL : une skill embarquant un `scripts/` s'exécute dans un sous-agent ReAct à fil isolé, dont les brouillons ne remontent jamais au graphe principal. Elle repose sur un jeton dérivé du contenu — un simple drapeau serait une convention que le modèle peut ignorer, alors qu'un condensé ne peut qu'avoir été reçu, et lie l'accord au paquet exact qui sera écrit (ADR-165).

### 23.8. Historique de conversation, recherche et rendu riche du chat

Six capacités transverses partagent la même philosophie produit : **feedback immédiat, zéro surcoût serveur quand ce n'est pas nécessaire**.

- **Invariant de lecture & maturité de la saisie** — une réponse en streaming n'arrache jamais un lecteur remonté dans le fil : la décision de suivi mesure la géométrie en direct au moment de décider (compensée de la croissance), un tick d'envoi explicite remplace les heuristiques par diff de données (deux d'entre elles ont produit des faux positifs contre le vrai moteur), et un bouton flottant avec badge des réponses hors écran ramène le lecteur. La saisie porte un brouillon persistant par utilisateur (débouncé, purgé à la déconnexion), un parcours ↑/↓ des 10 derniers envois, des commandes slash `/` (combobox WAI-ARIA sur le textarea natif, filtrage localisé insensible aux accents) et une rangée d'actions in-flow sous chaque réponse (copier, feedback, trace d'exécution).
- **Recherche d'historique conversation** — query parameter `?search=` sur `GET /conversations/me/messages`. Le filtrage passe par PostgreSQL `ILIKE` (case-insensitive, accent-sensitive — contrat verrouillé par test). Côté frontend, un `useMemo` sur `messages` filtre instantanément les messages chargés ; l'endpoint backend reste disponible comme capacité latente pour un futur UI de recherche profonde.
- **Pagination scroll-up** — même endpoint, curseur keyset `?before=<created_at>` retournant `has_more` et `next_cursor`. L'UI chat branche un `IntersectionObserver` sur une sentinelle de 1 px au-dessus du premier message ; les pages plus anciennes sont préfixées avec dédoublonnage par id, et un `wasPrependRef` partagé fait sauter le `useEffect` d'auto-scroll-vers-le-bas pour ce cycle, de sorte que la fenêtre reste exactement là où le lecteur en était. L'index composite existant `(conversation_id, created_at DESC)` rend chaque page un seek index-only, quelle que soit la longueur de la conversation. Les bornes de pagination (défaut 50, plafond dur 200) sont ajustables via les variables d'environnement `CONVERSATION_HISTORY_DEFAULT_LIMIT` / `CONVERSATION_HISTORY_MAX_LIMIT`.
- **Rendu LaTeX** — Les formules mathématiques et scientifiques que LIA écrit (`$inline$` / `$$block$$`) sont rendues via KaTeX dans `MarkdownContent.tsx`. Comme l'assistant émet toute sa réponse en HTML, un plugin `rehypeMathInText` détecte les délimiteurs `$`/`$$` au niveau hast — après expansion du HTML par `rehypeRaw` — et les convertit en marqueurs que `rehype-katex` rend ; `remark-math`, limité au markdown, ne voit pas le math enfoui dans le HTML. Ordre : `rehypeRaw → rehypeSanitize → rehypeMathInText → rehypeKatex` ; les étapes math ne lisent que du texte déjà sanitisé et n'émettent que des spans à classe fixe, sans surface d'attaque nouvelle.
- **Coloration syntaxique** — `react-syntax-highlighter` (PrismAsyncLight) lazy-loaded. 25 langages enregistrés à la demande via `SyntaxHighlighter.registerLanguage(...)` pour garder le bundle initial léger (langages chargés au premier code block). Thème automatique `one-dark` / `one-light` piloté par `next-themes`.

- **Mode HTML enrichi : vocabulaire de composants** — quand l'utilisateur choisit l'affichage HTML enrichi, la directive de prompt expose sept composants stylés par le design system (callouts titrés, chips à icônes, sections dépliables `details` natives, listes clé-valeur, colonnes responsives, étapes numérotées, tuiles de chiffres) plus les accents inline `mark`/`kbd`/`abbr`, sous une règle de sobriété explicite — la prose mène, les composants appuient. L'enrichissement est purement déclaratif (prompt + CSS + allowlist de sanitisation : six tags inertes ajoutés, ordre des plugins inchangé) et un garde CI échoue si la directive annonce une classe que la feuille de style ne couvre pas. Copie, partage et export `.md` aplatissent le HTML en texte lisible (presse-papiers double saveur `text/html` + `text/plain`), miroir client des sémantiques `html_to_text` du backend ; les ligatures d'icônes sont exclues du surlignage de recherche.

### 23.9. Persistance du feedback proactif

Le feedback utilisateur sur les notifications proactives (👍/👎/🚫 sur intérêts, heartbeat) est persisté directement dans `conversation_messages.message_metadata` JSONB via `jsonb_set(jsonb_set(coalesce(metadata, '{}'::jsonb), '{feedback_submitted}', 'true'), '{feedback_value}', '"thumbs_up"')`. L'update est **scoped par `user_id`** via subquery sur `conversations.user_id` pour prévenir toute fuite cross-tenant.

Côté frontend, l'état initial lit `message.metadata?.feedback_submitted` (les boutons restent cachés au reload pour les messages déjà votés) et le feedback est appliqué **de manière optimiste** (boutons cachés + toast proactif avant la mutation réseau). Les clés de metadata sont centralisées dans `src/core/field_names.py` (`FIELD_TARGET_ID`, `FIELD_FEEDBACK_ENABLED`, `FIELD_FEEDBACK_SUBMITTED`, `FIELD_FEEDBACK_VALUE`).

### 23.10. Internationalisation des tools : pattern thread-safe

L'i18n des tools utilisateur repose sur un contrat clair entre l'invocation asynchrone (`execute_api_call`) et le formatage synchrone du résultat (`format_registry_response`). Comme les instances de tools sont des **singletons concurrents** partagés entre toutes les requêtes, l'état de langue ne peut pas vivre sur l'instance.

`ConnectorTool` expose donc deux helpers : `_fetch_language()` (async, lit la locale utilisateur depuis le contexte) et `_language_from_result(result)` (sync, lit la langue depuis le résultat lui-même), reliés par une constante `_LANGUAGE_RESULT_KEY = "_language"` qui sert de contrat interne. Aucune mutation d'instance, pas de ContextVar nécessaire pour ce flux, et chaque résultat embarque la langue qui a servi à son formatage. Les fichiers `.po`/`.mo` sont compilés à l'image Docker.

L'application complète à la météo (`gettext.gettext(text, language)` avec propagation explicite sur les 6 sites concernés) et aux 6 tools Hue (`list_lights`, `control_light`, `list_rooms`, `control_room`, `list_scenes`, `activate_scene`) garantit que les sorties sont rendues dans la langue de l'utilisateur, jamais dans la langue de service par défaut.

### 23.11. Architecture observabilité

L'observabilité repose sur trois piliers : **émission défensive** sur le chemin critique, **dashboards Grafana** pré-câblés (26 dashboards / 637 panels couvrant l'application, l'infra et chaque sous-système métier), et **gauges DB-backed** entretenues par un updater périodique.

Un 26e dashboard transforme cette télémétrie en cockpit produit (ADR-178) : les résultats sont validés E1 (confirmation explicite de l'utilisateur) ou E2 (action restée non corrigée pendant une fenêtre comportementale complète), le comptage exact et dédupliqué vit dans PostgreSQL — des états mutables ne se dérivent jamais de compteurs Prometheus — et Grafana le lit via un rôle en lecture seule restreint aux vues agrégées avec un statement timeout épinglé.

L'instrumentation Prometheus est systématiquement wrappée dans `try/except Exception: pass` avec imports lazy (`from ... import foo` à l'intérieur du try) pour qu'aucun problème de métrique ne propage sur la chaîne d'exécution. Trois index Postgres dédiés (`ix_conversations_updated_at` pour DAU/WAU, `ix_conversations_created_at` pour l'histogramme conversations, `ix_connectors_status` pour le taux d'activation) ramènent les queries du updater de ~500 ms à <50 ms sur base peuplée.

Côté validation, un handler FastAPI `RequestValidationError` comptabilise les 422 par `field` + `error_type` sur `validation_errors_total`, avec cap à 10 erreurs/requête et truncation 40 chars pour borner la cardinalité. Le contrat 422 (réponse FastAPI standard avec `detail`) est strictement préservé.

Pour mesurer la durée réelle d'activation des connecteurs sans intrusion dans les services métier, des **SQLAlchemy event listeners** `before_insert` / `after_insert` sur `Connector` capturent l'intervalle flush SQL → completion. Double métrique : `oauth_connector_activation_total` (counter) + `oauth_connector_activation_duration_seconds` (histogram).

Les **gauges DB-backed** alimentées toutes les 30 s : DAU (`user_active_daily_gauge`), WAU (`user_active_weekly_gauge`), pool Redis (`redis_connection_pool_size_current`, `redis_connection_pool_available_current`), `checkpoints_table_size_bytes`, `connector_activation_rate{connector_type}`.

Pour prévenir l'**explosion de cardinalité Prometheus** sur `connector_api_*{operation}`, les paths d'API sont sanitisés segment-par-segment avant émission : UUID/id/hex_id/token sont remplacés par des placeholders `{uuid}`, `{id}`, `{hex_id}`, `{token}`. Sans cette protection, chaque requête API Google/Apple/Microsoft portant un ID de ressource créerait une nouvelle série Prometheus.

### 23.12. Ingestion d'événements externes via tokens scopés

LIA accepte les ingestions d'événements externes (mesures iPhone Apple Health, payloads de tiers, futurs canaux IoT) via un pattern unifié : des endpoints REST authentifiés par **token Bearer scopé**, indépendants du système de session cookie. C'est le mécanisme retenu pour le domaine [`health_metrics`](../docs/architecture/ADR-076-Health-Metrics-Ingestion.md) (fréquence cardiaque + pas envoyés par une automatisation Raccourcis iOS), et il sert de gabarit pour tout futur connecteur entrant.

**Pourquoi un token et non l'ID utilisateur** : un identifiant d'utilisateur fuite naturellement (URLs, payload JWT, logs, screenshots, exports). Un token est un **secret rotatif et révocable** scopé à un endpoint. Le préfixe (`hm_` pour les health metrics) permet de typer le scope.

**Persistance** : la table de tokens stocke **uniquement le digest SHA-256** de la valeur brute. La valeur en clair (préfixe + ~32 chars `secrets.token_urlsafe`) est révélée une seule fois à la création. Un préfixe d'affichage de 8 caractères reste visible pour identification dans la liste. Plusieurs tokens actifs en parallèle, révocation individuelle.

**Batch upsert idempotent** : chaque requête porte un tableau de samples auto-horodatés (`date_start`/`date_end` ISO 8601 avec offset). Le serveur normalise en UTC, tronque à la seconde, puis applique un UPSERT PostgreSQL `ON CONFLICT (user_id, kind, date_start, date_end) DO UPDATE` avec `RETURNING (xmax = 0)` pour discriminer inserts vs updates en un aller-retour. Conséquence pratique : le client iOS peut repousser la journée entière à chaque déverrouillage sans risque de doublons — les lignes existantes sont simplement écrasées.

**Parser flexible** : les Raccourcis iOS émettent les payloads sous quatre formes selon l'auteur (tableau JSON canonique, NDJSON, enveloppe `{"data":[…]}`, ou wrapping « Dictionnaire » `{"<ndjson_blob>":{}}` où le NDJSON est encodé comme unique clé d'un dict externe à valeur vide). Un parser en amont du service aplanit les quatre formes vers un `list[dict]` standard avant validation — pas de contrainte sur la forme du Raccourci côté utilisateur.

**Dedupe intra-batch avec arbitrage per-kind** : PostgreSQL refuse qu'un `ON CONFLICT DO UPDATE` touche la même ligne cible deux fois (`CardinalityViolationError`). Or iOS émet légitimement des samples qui se chevauchent (Apple Watch + iPhone reportant le même intervalle). Un helper fusionne les doublons **avant** l'UPSERT avec une stratégie choisie par kind : **MAX** pour les pas (Watch et iPhone comptent des sous-ensembles complémentaires — MAX approche mieux la vérité terrain que SUM double-compte ou AVG sous-compte), **AVG** arrondi pour la fréquence cardiaque (fusion de deux capteurs visant le même signal). Les doublons collapsés sont comptabilisés comme `updated` dans la réponse et tracés via `health_samples_batch_duplicates_total{kind}`.

**Validation mixte par sample** : chaque échantillon est accepté ou rejeté individuellement avec son index 0-based et une raison bornée (`out_of_range | malformed | missing_field | invalid_date`). Les voisins valides du même lot sont persistés — une glitch ponctuelle de capteur ne fait pas perdre la journée. Les valeurs brutes ne sont jamais loggées (RGPD compatible), seulement des compteurs par raison.

**Sécurité** : rate limit Redis sliding window scopé par token (60 req/h par défaut, paramétrable), header `WWW-Authenticate: Bearer` (RFC 7235) sur les 401, `Retry-After` sur les 429, plafond de samples par requête avec `HTTP 413` au-delà. L'effacement de compte est assuré par le service de suppression de compte, qui purge explicitement chaque table de santé (le modèle de compte en soft-delete conserve la ligne `users`, donc la cascade FK ne se déclenche jamais) ; l'appareil d'un compte supprimé ne peut plus ingérer.

**Visualisation** : un aggregator polymorphe Python parcourt les samples ordonnés par `date_start` dans une fenêtre et émet un point par bucket (heure/jour/semaine/mois/année), `AVG/MIN/MAX` sur les samples `heart_rate` et `SUM` sur les samples `steps`. Les buckets sans donnée sont émis avec `has_data=False` pour que le frontend (`recharts`, `connectNulls={false}`) affiche des trous honnêtes plutôt qu'une interpolation. Le composant Settings réutilise le pattern `SettingsSection` + Accordion (5 sous-sections : API + tokens, Assistant, Graphiques, Statistiques, Gestion) et affiche la **fenêtre temporelle réellement agrégée** pour lever l'ambiguïté « les stats bougent pas quand je change de période » (HR invariant si toutes les données tiennent dans la plus petite fenêtre).

**Registre central + extensibilité** : un registre `HEALTH_KINDS: dict[str, HealthKindSpec]` (`src/domains/health_metrics/kinds.py`) porte pour chaque kind ses bornes physiologiques, sa stratégie de merge intra-batch (`MAX`/`AVG_ROUNDED`/…), sa méthode d'agrégation bucket (`SUM`/`AVG_MIN_MAX`/…), son type de baseline (`daily_sum`/`daily_avg`/`resting`), son agent associé, sa clé i18n d'affichage, et ses legacy fields backward-compat. Ingestion/repository/aggregator/baseline/heartbeat/memory/journal itèrent ce registre — ajouter un kind (sleep, SpO2, calories…) = une entrée dans `kinds.py` + un pack de tools, zéro modification des pipelines.

**Baseline adaptive + signaux factuels** : `baseline.compute_baseline()` choisit automatiquement entre `bootstrap` (médiane de toutes les données, exposée tant qu'on a moins de 7 jours) et `rolling` (médiane mobile 28 j) ; le mode est remonté au LLM pour qu'il qualifie ses affirmations. `signals.detect_recent_variations()` + `detect_notable_events()` produisent des **faits** (streaks directionnels ≥ 3 j au-dessus de 10 % delta quotidien, événements structurels comme les streaks d'inactivité) — jamais de diagnostic.

**Exposition aux boucles centrales** : un **toggle utilisateur unique** (opt-in) gouverne d'un seul coup quatre consommateurs — conversation (tools assistant), Heartbeat (source `health_signals`), extraction de mémoire (placeholder `{health_context}` + blob `context_biometric` JSONB en contexte d'émotion forte), et journal (extraction + consolidation). Tous reçoivent la même projection **factuelle et non-brute** : deltas vs baseline, tendances, événements structurels (streaks d'inactivité…) — jamais les valeurs brutes. La baseline mobile 28 j sélectionne automatiquement `bootstrap` (médiane simple tant qu'on a moins de 7 j d'historique, remonté au LLM pour qu'il qualifie ses affirmations) puis bascule en `rolling`. L'erasure RGPD n'a qu'une cible : la table `health_samples`.

### 23.13. Application installable (PWA)

Six manifests localisés (`/manifest-{lng}.json` — `lang`, `start_url`, trois raccourcis, entrées d'icônes `any`/`maskable` séparées ; la parité structurelle des 6 fichiers est verrouillée par test) sont liés par page via `generateMetadata`, avec de vraies icônes PNG et une `apple-touch-icon` (iOS ignore silencieusement les icônes SVG). Le **share target** de l'OS (`GET /{lng}/share`) compose titre/texte/url partagés en un brouillon de chat plafonné empruntant le rail `?draft=` existant — jamais auto-envoyé. Une suggestion d'installation discrète apparaît à partir de la troisième visite (jamais en display-mode standalone, refusable pour toujours) ; Chromium reçoit un vrai prompt d'installation via `beforeinstallprompt`, iOS l'instruction Partager → Sur l'écran d'accueil.

### 23.14. Index de navigation : une table, deux gardes en sens opposés

La page des réglages empile une trentaine de sections repliées sur plusieurs onglets. Les atteindre suppose une table qui associe un jeton d'URL à un onglet et à une valeur d'accordéon. Une table de ce genre ne se périme jamais bruyamment : elle se contente, un jour, de ne plus décrire la page.

Deux gardes la tiennent, et elles regardent dans des directions opposées. La première va de la table vers le code : chaque entrée doit désigner un fichier qui existe, y déclarer la valeur qu'elle revendique, et vivre dans l'onglet annoncé — l'onglet étant lu depuis la page plutôt que déclaré une seconde fois. La seconde va du code vers la table : **tout** composant rendu dans un panneau d'onglets doit être indexé, structurel, ou explicitement écarté avec une raison écrite. Il n'existe pas de quatrième issue, si bien qu'une section ajoutée demain impose une décision au moment où elle est ajoutée, au lieu de disparaître en silence.

L'index de recherche bâti par-dessus est exhaustif **par le type** : ses métadonnées forment un `Record` indexé par l'union des jetons, donc ajouter une destination sans dire comment on la nomme ne compile pas. Le rapprochement s'appuie sur le normaliseur que partagent toutes les surfaces de recherche du produit — casse, diacritiques, apostrophes typographiques et espaces insécables sont repliés vers la forme que produit un clavier. Ce repli obéit à une contrainte dure : un point de code pour un point de code, sans quoi les surligneurs qui reconstituent les positions d'origine se décalent d'autant.

Reste qu'une destination peut légitimement ne pas exister : plusieurs sections ne se rendent que si la fonctionnalité est active ou si la donnée existe, et le panneau d'onglet inactif n'est pas monté — rien ne peut donc l'observer à l'avance. Le parti retenu est de garder ces destinations dans l'index et d'énoncer l'observation à l'arrivée, plutôt que d'échanger un cul-de-sac visible contre un faux négatif invisible.

---

## 24. Architecture des décisions (ADR)

170+ ADRs au format MADR documentent les décisions architecturales majeures. Quelques exemples représentatifs :

| ADR | Décision | Problème résolu | Impact mesuré |
|-----|----------|----------------|---------------|
| 001 | LangGraph pour orchestration | Besoin de state persistence + interrupts HITL | Checkpoints P95 < 50 ms |
| 002 | BFF Pattern (JWT → Redis) | JWT vulnérable XSS, révocation impossible | Mémoire -90 %, OWASP A |
| 003 | Filtrage dynamique par domaine | 10x prompt size = 10x coût | 73-83 % réduction catalogue |
| 005 | Filtrage AVANT asyncio.gather | Plan + fallback exécutés en parallèle = 2x coût | -50 % coût plans fallback |
| 007 | Message Windowing par nœud | Conversations longues = 100k+ tokens | -50 % latence, -77 % coût |
| 048 | Semantic Tool Router | Routage LLM imprécis sur multi-domaine | +48 % précision |
| 049 | Embeddings sémantiques | Routage LLM seul imprécis | +48 % de précision via embeddings sémantiques |
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

## 26. Psyche Engine : intelligence émotionnelle dynamique

### 26.1. Architecture à 5 couches

Le Psyche Engine donne à l'assistant un état psychologique dynamique qui évolue à chaque interaction, inspiré du modèle ALMA (A Layered Model of Affect, Gebhard 2005) et de l'espace PAD de Mehrabian.

| Couche | Échelle de temps | Contenu |
|--------|-----------------|---------|
| 1 — Personnalité | Permanent | Big Five (O/C/E/A/N) hérités de la personnalité choisie. Modulent la réactivité émotionnelle, l'empathie, la vitesse de récupération. |
| 2 — Humeur | Heures | Position dans l'espace PAD (Plaisir/Activation/Dominance) → 14 humeurs distinctes. Décroît vers la baseline de personnalité. |
| 3 — Émotions | Minutes | 22 émotions discrètes (max 4 simultanées) avec intensité [0-100%]. Poussent l'humeur via leur vecteur PAD. Suppression croisée ±30%. |
| 4 — Relation | Semaines | 4 stades (Orientation → Exploratoire → Affective → Stable). Progression unidirectionnelle. Profondeur, chaleur, confiance. |
| 5 — Motivations | Par session | Curiosité (énergie de l'échange) et engagement (qualité). Auto-efficacité bayésienne par domaine. |

### 26.2. Principe fondamental : « Show, Don't Tell »

L'assistant ne dit jamais « je suis content » — à la place, son vocabulaire se réchauffe, ses phrases s'allongent, ses suggestions deviennent plus audacieuses. L'utilisateur perçoit une personnalité vivante sans déclarations émotionnelles explicites.

### 26.3. Injection de directives

Chaque message génère un bloc `<PsycheDirectives>` (~100-120 tokens) avec :
- **MOOD** : label + intensité + directive comportementale concrète (ex: « Respond with calm assurance. Use measured, flowing sentences. »)
- **EMOTIONS** : top 3 émotions avec directives (ex: « empathy (72%): Mirror the user's emotional tone. »)
- **RELATIONSHIP** : stade + directive relationnelle
- **DRIVES** : curiosité/engagement avec seuils d'activation
- **EVOLUTION** : shift de mood/émotion depuis le dernier message

Un guide d'incarnation de 540 mots (`psyche_usage_directive.txt`) explique au LLM comment traduire chaque état en comportement concret — humeur par humeur, intensités, transitions, distances sociales par stade relationnel.

### 26.4. Auto-évaluation à coût zéro

Après chaque réponse, le LLM s'auto-évalue via un tag XML caché `<psyche_eval/>` : valence utilisateur, émotion déclenchée, intensité, qualité de l'échange. Ce tag est strippé avant l'envoi à l'utilisateur. Aucun appel LLM supplémentaire — l'évaluation fait partie de la génération de réponse.

### 26.5. Injection globale

Le contexte psyché est injecté dans **tous** les points de génération utilisateur : réponse principale (format riche), notifications proactives, rappels, emails, voix, sous-agents, initiative, fallback (format compact avec directives spécifiques à l'humeur courante).

### 26.6. Frontend

- **Avatar émotionnel** : emoji d'humeur avec anneau coloré sur chaque message, persisté par message dans la metadata.
- **Dashboard 4 graphiques** : Humeur (PAD), Émotions (dynamique par émotion), Relation, Motivations — recharts avec sélecteur de période 24h à 90j.
- **Guide éducatif interactif** : 7 sections ordonnées couche 1→5 avec tableaux descriptifs des 14 humeurs et 22 émotions.
- **Réglages** : expressivité, stabilité, rafraîchissement d'humeur, réinitialisation complète avec descriptions explicites de ce qui est conservé/réinitialisé.

---

## Conclusion

LIA est un exercice d'ingénierie logicielle qui tente de résoudre un problème concret : construire un assistant IA multi-agent de qualité production, transparent, sécurisé et extensible, capable de tourner sur un Raspberry Pi.

Les 170+ ADRs documentent non seulement les décisions prises mais aussi les alternatives rejetées et les compromis acceptés. Les ~16 535 tests sur 873 fichiers, le CI/CD complet, et le MyPy strict ne sont pas des métriques de vanité — ce sont les mécanismes qui permettent de faire évoluer un système de cette complexité sans régression.

L'intrication des sous-systèmes — mémoire psychologique, apprentissage bayésien, routage sémantique, HITL systématique, proactivité LLM-driven, journaux introspectifs — crée un système où chaque composant renforce les autres. Le HITL alimente le pattern learning, qui réduit les coûts, qui permettent plus de fonctionnalités, qui génèrent plus de données pour la mémoire, qui améliore les réponses. C'est un cercle vertueux par conception, pas par accident.

---

*Document rédigé sur la base de l'analyse du code source (`apps/api/src/`, `apps/web/src/`), de la documentation technique (400+ documents), des 170+ ADRs, et du changelog (v1.0 à v1.26.2). Toutes les métriques, versions et patterns cités sont vérifiables dans le codebase.*
