# Index de la Documentation LIA

> Carte complète de toute la documentation du projet LIA - Assistant IA multi-agent avec LangGraph

**Version**: 6.8
**Dernière mise à jour**: 2026-03-26
**Statut**: Complète (190+ documents)

---

## Vue d'Ensemble

Cette documentation couvre l'intégralité du projet **LIA** : un assistant IA conversationnel multi-agent basé sur **LangGraph 1.1.2**, **FastAPI 0.135.1**, et **Next.js 16**.

| Métrique | Valeur |
|----------|--------|
| Documents totaux | 190+ |
| Documents techniques | 50+ |
| Guides pratiques | 15+ |
| Runbooks | 34+ |
| ADRs | 62 |
| Skills Claude | 10 |

---

## Par Où Commencer ?

### Pour les Nouveaux Développeurs

| Étape | Document | Description |
|-------|----------|-------------|
| 1 | [GETTING_STARTED.md](./GETTING_STARTED.md) | Installation et premiers pas |
| 2 | [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture globale du projet |
| 3 | [STACK_TECHNIQUE.md](./technical/STACK_TECHNIQUE.md) | Référence versions technologies |
| 4 | [GUIDE_DEVELOPPEMENT.md](./guides/GUIDE_DEVELOPPEMENT.md) | Workflow de développement |
| 5 | [GUIDE_API.md](./guides/GUIDE_API.md) | Guide de l'API REST |

### Pour les Architectes

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture globale |
| [GRAPH_AND_AGENTS_ARCHITECTURE.md](./technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) | Système multi-agents LangGraph |
| [STATE_AND_CHECKPOINT.md](./technical/STATE_AND_CHECKPOINT.md) | State management et persistence |
| [ADR_INDEX.md](./architecture/ADR_INDEX.md) | Architecture Decision Records (59) |

### Pour les Product Managers

| Document | Description |
|----------|-------------|
| [HITL.md](./technical/HITL.md) | Human-in-the-Loop (approbations utilisateur) |
| [LLM_PRICING_MANAGEMENT.md](./technical/LLM_PRICING_MANAGEMENT.md) | Gestion des coûts LLM |
| [GOOGLE_API_TRACKING.md](./technical/GOOGLE_API_TRACKING.md) | Suivi consommation Google Maps Platform |
| [METRICS_REFERENCE.md](./technical/METRICS_REFERENCE.md) | Métriques business |

### Pour les DevOps / SRE

| Document | Description |
|----------|-------------|
| [GETTING_STARTED.md](./GETTING_STARTED.md) | Déploiement Docker |
| [CI_CD.md](./technical/CI_CD.md) | Pipeline CI, pre-commit, branch protection |
| [OBSERVABILITY_AGENTS.md](./technical/OBSERVABILITY_AGENTS.md) | Stack observabilité complète |
| [README_OBSERVABILITY.md](./readme/README_OBSERVABILITY.md) | Guide observabilité quickstart |
| [runbooks/](./runbooks/) | Runbooks opérationnels (34+ procédures) |

---

## Documentation Principale

| Document | Description | Statut |
|----------|-------------|--------|
| [GETTING_STARTED.md](./GETTING_STARTED.md) | Guide d'installation complet | ✅ |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Architecture globale, patterns, technologies | ✅ |
| [INDEX.md](./INDEX.md) | Ce document - carte de la documentation | ✅ |

---

## Documentation Technique

### Architecture & Système

| Document | Description | Statut |
|----------|-------------|--------|
| [GRAPH_AND_AGENTS_ARCHITECTURE.md](./technical/GRAPH_AND_AGENTS_ARCHITECTURE.md) | LangGraph, nodes, routing, orchestration | ✅ |
| [STATE_AND_CHECKPOINT.md](./technical/STATE_AND_CHECKPOINT.md) | MessagesState, reducers, PostgreSQL checkpointing | ✅ |
| [MESSAGE_WINDOWING_STRATEGY.md](./technical/MESSAGE_WINDOWING_STRATEGY.md) | Windowing par node, truncation, compaction intelligente (F4), performance | ✅ |
| [TOKEN_TRACKING_AND_COUNTING.md](./technical/TOKEN_TRACKING_AND_COUNTING.md) | Token tracking, alignment DB/Prometheus | ✅ |
| [DATABASE_SCHEMA.md](./technical/DATABASE_SCHEMA.md) | Schema PostgreSQL complet, migrations Alembic | ✅ |
| [STACK_TECHNIQUE.md](./technical/STACK_TECHNIQUE.md) | Référence complète versions technologies | ✅ |

### Agents & Outils

| Document | Description | Statut |
|----------|-------------|--------|
| [AGENTS.md](./technical/AGENTS.md) | Architecture multi-agent, AgentRegistry | ✅ |
| [TOOLS.md](./technical/TOOLS.md) | Architecture tools, @connector_tool | ✅ |
| [AGENT_MANIFEST.md](./technical/AGENT_MANIFEST.md) | ToolManifest, catalogue, domain taxonomy | ✅ |
| [GOOGLE_CONTACTS_INTEGRATION.md](./technical/GOOGLE_CONTACTS_INTEGRATION.md) | Intégration Google Contacts | ✅ |
| [EMAIL_FORMATTER.md](./technical/EMAIL_FORMATTER.md) | Formatage emails, templates | ✅ |
| [CONNECTORS_PATTERNS.md](./technical/CONNECTORS_PATTERNS.md) | Patterns connecteurs OAuth/API Key | ✅ |
| [CONNECTOR_PHILIPS_HUE.md](./connectors/CONNECTOR_PHILIPS_HUE.md) | Philips Hue smart lighting connector (local + remote) | ✅ |
| [MICROSOFT_365_INTEGRATION.md](./technical/MICROSOFT_365_INTEGRATION.md) | Intégration Microsoft 365 (Outlook, Calendar, Contacts, To Do) | ✅ |
| [VOICE.md](./technical/VOICE.md) | Voice/TTS Standard/HD, Factory Pattern | ✅ |
| [VOICE_MODE.md](./technical/VOICE_MODE.md) | STT, Wake Word, Push-to-Talk | ✅ |
| [ROUTES.md](./technical/ROUTES.md) | Google Routes API, directions | ✅ |
| [WEB_FETCH.md](./technical/WEB_FETCH.md) | Extraction contenu pages web (URL → Markdown), SSRF prevention | ✅ |
| [BROWSER_CONTROL.md](./technical/BROWSER_CONTROL.md) | Browser automation (Playwright) — navigation, interaction, extraction JS — evolution F7 | ✅ |
| [MCP_INTEGRATION.md](./technical/MCP_INTEGRATION.md) | MCP (Model Context Protocol) — Serveurs d'outils externes, MCP Apps, Excalidraw | ✅ |
| [CHANNELS_INTEGRATION.md](./technical/CHANNELS_INTEGRATION.md) | Canaux de messagerie externes (Telegram) — evolution F3 | ✅ |
| [ATTACHMENTS_INTEGRATION.md](./technical/ATTACHMENTS_INTEGRATION.md) | Pièces jointes (images, PDF) avec analyse vision LLM — evolution F4 | ✅ |
| [IMAGE_GENERATION.md](./technical/IMAGE_GENERATION.md) | AI Image Generation — multi-provider, cost tracking, attachment storage | ✅ |
| [HEARTBEAT_AUTONOME.md](./technical/HEARTBEAT_AUTONOME.md) | Notifications proactives LLM-driven (Heartbeat) — evolution F5 | ✅ |
| [LANDING_PAGE.md](./technical/LANDING_PAGE.md) | Architecture Landing Page — composants React, SEO, OpenGraph | ✅ |
| [LLM_CONFIG_ADMIN.md](./technical/LLM_CONFIG_ADMIN.md) | Administration dynamique des configurations LLM (34 types, 7 providers) | ✅ |
| [SKILLS_INTEGRATION.md](./technical/SKILLS_INTEGRATION.md) | Skills system (agentskills.io standard) — SKILL.md files, activation, scripts | ✅ |

### Cost Tracking & Billing

| Document | Description | Statut |
|----------|-------------|--------|
| [LLM_PRICING_MANAGEMENT.md](./technical/LLM_PRICING_MANAGEMENT.md) | Pricing LLM, token counting, exports | ✅ |
| [GOOGLE_API_TRACKING.md](./technical/GOOGLE_API_TRACKING.md) | Google Maps Platform tracking, pricing admin, consumption exports (admin + user v1.9.1) | ✅ |

### LLM & Intelligence

| Document | Description | Statut |
|----------|-------------|--------|
| [LLM_PROVIDERS.md](./technical/LLM_PROVIDERS.md) | Providers LLM, modèles, configuration (Admin UI + .env fallback), compatibilité | ✅ |
| [LLM_PROVIDER_CONSTRAINTS.md](./technical/LLM_PROVIDER_CONSTRAINTS.md) | Contraintes de paramétrage LLM par provider et par modèle (matrice complète) | ✅ |
| [PROMPTS.md](./technical/PROMPTS.md) | Système prompts, versioning | ✅ |
| [PLANNER.md](./technical/PLANNER.md) | Planner node, ExecutionPlan DSL, FOR_EACH | ✅ |
| [PLAN_PATTERN_LEARNER.md](./technical/PLAN_PATTERN_LEARNER.md) | Apprentissage patterns, Bayesian | ✅ |
| [PATTERN_LEARNER_TRAINING.md](./technical/PATTERN_LEARNER_TRAINING.md) | Training automatisé, Golden Patterns | ✅ |
| [RESPONSE.md](./technical/RESPONSE.md) | Response node, anti-hallucination | ✅ |
| [ROUTER.md](./technical/ROUTER.md) | Router node, binary routing | ✅ |
| [SMART_SERVICES.md](./technical/SMART_SERVICES.md) | QueryAnalyzer, SmartPlanner, SmartCatalogue | ✅ |
| [SEMANTIC_ROUTER.md](./technical/SEMANTIC_ROUTER.md) | Semantic Tool Router, max-pooling | ✅ |
| [SEMANTIC_INTENT_DETECTION.md](./technical/SEMANTIC_INTENT_DETECTION.md) | Semantic Intent Detection | ✅ |
| [LOCAL_EMBEDDINGS.md](./technical/LOCAL_EMBEDDINGS.md) | Local E5 embeddings, zero-cost | ✅ |
| [MULTI_DOMAIN_ARCHITECTURE.md](./technical/MULTI_DOMAIN_ARCHITECTURE.md) | Architecture multi-domaines | ✅ |
| [LANGFUSE.md](./technical/LANGFUSE.md) | Langfuse integration | ✅ |

### Mémoire & Contexte

| Document | Description | Statut |
|----------|-------------|--------|
| [LONG_TERM_MEMORY.md](./technical/LONG_TERM_MEMORY.md) | Mémoire long-terme, profil psychologique | ✅ |
| [MEMORY_RESOLUTION.md](./technical/MEMORY_RESOLUTION.md) | Résolution références, relations | ✅ |
| [INTERESTS.md](./technical/INTERESTS.md) | Système apprentissage centres d'intérêt | ✅ |
| [SCHEDULED_ACTIONS.md](./technical/SCHEDULED_ACTIONS.md) | Actions planifiées récurrentes | ✅ |
| [SUB_AGENTS.md](./technical/SUB_AGENTS.md) | Persistent specialized sub-agents (F6) | ✅ |
| [HYBRID_SEARCH.md](./technical/HYBRID_SEARCH.md) | Recherche hybride BM25 + sémantique | ✅ |
| [JOURNALS.md](./technical/JOURNALS.md) | Personal Journals — carnets de bord introspectifs, injection sémantique | ✅ |
| [USAGE_LIMITS.md](./technical/USAGE_LIMITS.md) | Per-user usage limits — tokens, messages, cost quotas with 5-layer enforcement | ✅ |

### Human-in-the-Loop (HITL)

| Document | Description | Statut |
|----------|-------------|--------|
| [HITL.md](./technical/HITL.md) | Architecture HITL, 6 couches, plan approval | ✅ |
| [PLAN_HITL_STREAMING_VALIDATION.md](./technical/PLAN_HITL_STREAMING_VALIDATION.md) | Validation plan streaming HITL | ✅ |

### Sécurité & Authentification

| Document | Description | Statut |
|----------|-------------|--------|
| [OAUTH.md](./technical/OAUTH.md) | OAuth 2.1, PKCE, Google provider | ✅ |
| [AUTHENTICATION.md](./technical/AUTHENTICATION.md) | BFF Pattern, sessions Redis | ✅ |
| [SECURITY.md](./technical/SECURITY.md) | Sécurité globale, encryption, compliance | ✅ |
| [PII_LOGGING_SECURITY.md](./technical/PII_LOGGING_SECURITY.md) | PII filtering, GDPR | ✅ |
| [RATE_LIMITING.md](./technical/RATE_LIMITING.md) | Rate limiting Redis distribué | ✅ |
| [OAUTH_HEALTH_CHECK.md](./technical/OAUTH_HEALTH_CHECK.md) | Surveillance connecteurs OAuth | ✅ |

### Observabilité & Monitoring

| Document | Description | Statut |
|----------|-------------|--------|
| [OBSERVABILITY_AGENTS.md](./technical/OBSERVABILITY_AGENTS.md) | Stack Prometheus/Grafana/Loki/Tempo | ✅ |
| [METRICS_REFERENCE.md](./technical/METRICS_REFERENCE.md) | 500+ métriques documentées | ✅ |
| [GRAFANA_DASHBOARDS.md](./technical/GRAFANA_DASHBOARDS.md) | 18 dashboards Grafana | ✅ |
| [README_OBSERVABILITY.md](./readme/README_OBSERVABILITY.md) | Guide observabilité quickstart | ✅ |
| [README_GRAFANA_LANGFUSE.md](./readme/README_GRAFANA_LANGFUSE.md) | Intégration Grafana + Langfuse | ✅ |
| [README_PROMETHEUS_ALERTMANAGER.md](./readme/README_PROMETHEUS_ALERTMANAGER.md) | Configuration AlertManager | ✅ |
| [README_PROMETHEUS_THRESHOLDS.md](./readme/README_PROMETHEUS_THRESHOLDS.md) | Seuils alertes par environnement | ✅ |

### CI/CD & Déploiement

| Document | Description | Statut |
|----------|-------------|--------|
| [CI_CD.md](./technical/CI_CD.md) | Pipeline CI, pre-commit hook, branch protection, Dependabot | ✅ |
| [DEPLOYMENT_INSTRUCTIONS.md](./technical/DEPLOYMENT_INSTRUCTIONS.md) | Instructions déploiement production | ✅ |

---

## Guides Pratiques

### Développement

| Guide | Description | Statut |
|-------|-------------|--------|
| [GUIDE_DEVELOPPEMENT.md](./guides/GUIDE_DEVELOPPEMENT.md) | Workflow dev, git, pre-commit, CI/CD | ✅ |
| [GUIDE_API.md](./guides/GUIDE_API.md) | Guide utilisation API REST | ✅ |
| [GUIDE_AGENT_CREATION.md](./guides/GUIDE_AGENT_CREATION.md) | Créer un nouvel agent de A à Z | ✅ |
| [GUIDE_TOOL_CREATION.md](./guides/GUIDE_TOOL_CREATION.md) | Créer un nouveau tool | ✅ |
| [GUIDE_PROMPTS.md](./guides/GUIDE_PROMPTS.md) | Optimiser les prompts, versioning | ✅ |
| [GUIDE_TESTING.md](./guides/GUIDE_TESTING.md) | Tests unitaires, integration, E2E | ✅ |
| [GUIDE_DEBUGGING.md](./guides/GUIDE_DEBUGGING.md) | Debug LangGraph, logs, breakpoints | ✅ |
| [GUIDE_CONNECTOR_IMPLEMENTATION.md](./guides/GUIDE_CONNECTOR_IMPLEMENTATION.md) | Implémenter un nouveau connecteur | ✅ |
| [GUIDE_CONFIG_ARCHITECTURE.md](./guides/GUIDE_CONFIG_ARCHITECTURE.md) | Architecture configuration modulaire | ✅ |
| [GUIDE_MIGRATION.md](./guides/GUIDE_MIGRATION.md) | Guide migrations Alembic | ✅ |
| [GUIDE_PERFORMANCE_TUNING.md](./guides/GUIDE_PERFORMANCE_TUNING.md) | Optimisation performance LLM | ✅ |
| [GUIDE_MCP_INTEGRATION.md](./guides/GUIDE_MCP_INTEGRATION.md) | Guide pratique MCP (admin + per-user + MCP Apps + Excalidraw) | ✅ |
| [GUIDE_TELEGRAM_INTEGRATION.md](./guides/GUIDE_TELEGRAM_INTEGRATION.md) | Guide pratique Telegram (bot, webhook, OTP, HITL) | ✅ |
| [GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md](./guides/GUIDE_HEARTBEAT_PROACTIVE_NOTIFICATIONS.md) | Guide pratique Heartbeat (ProactiveTask, ContextAggregator) | ✅ |
| [GUIDE_SCHEDULED_ACTIONS.md](./guides/GUIDE_SCHEDULED_ACTIONS.md) | Guide pratique Actions Planifiees (recurrentes, timezone, retry) | ✅ |
| [GUIDE_RAG_SPACES.md](./guides/GUIDE_RAG_SPACES.md) | Guide RAG Spaces (espaces de connaissances, upload, hybrid search) | ✅ |
| [docs/knowledge/](./knowledge/) | System Knowledge: FAQ Markdown files for system RAG indexation (17 files, 119+ Q/A) | ✅ |

### Operations

| Guide | Description | Statut |
|-------|-------------|--------|
| [GUIDE_DEPLOYMENT.md](./guides/GUIDE_DEPLOYMENT.md) | Déploiement production | ✅ |
| [GUIDE_BACKGROUND_JOBS_APSCHEDULER.md](./guides/GUIDE_BACKGROUND_JOBS_APSCHEDULER.md) | Background jobs APScheduler | ✅ |
| [GUIDE_FCM_PUSH_NOTIFICATIONS.md](./guides/GUIDE_FCM_PUSH_NOTIFICATIONS.md) | Push notifications Firebase | ✅ |

### Langfuse

| Guide | Description | Statut |
|-------|-------------|--------|
| [GUIDE_BEST_PRACTICES.md](./langfuse/GUIDE_BEST_PRACTICES.md) | Best practices Langfuse | ✅ |
| [GUIDE_PROMPT_VERSIONING.md](./langfuse/GUIDE_PROMPT_VERSIONING.md) | Versioning prompts Langfuse | ✅ |

---

## Architecture Decision Records (ADR)

### Index Principal

| ADR | Description | Statut |
|-----|-------------|--------|
| [ADR_INDEX.md](./architecture/ADR_INDEX.md) | Index complet des 59 ADRs | ✅ |

### ADRs Récents (2026)

| ADR | Titre | Date |
|-----|-------|------|
| ADR-063 | Cross-Worker Cache Invalidation via Redis Pub/Sub | 2026-03 |
| ADR-062 | Agent Initiative Phase + MCP Iterative Sub-Agent | 2026-03 |
| ADR-061 | Centralized Component Activation/Deactivation Control | 2026-03 |
| ADR-059 | Browser Control Architecture (Playwright) | 2026-03 |
| ADR-058 | System RAG Spaces for App Self-Knowledge | 2026-03 |
| ADR-057 | Personal Journals (Carnets de Bord) | 2026-03 |
| ADR-056 | RAG Spaces — Google Drive Folder Sync | 2026-03 |
| ADR-055 | RAG Spaces Architecture | 2026-03 |
| ADR-054 | Voice Input Architecture | 2026-01 |
| ADR-053 | Interest Learning System | 2026-01 |
| ADR-052 | Union Validation Strategy AgentResult | 2026-01 |
| ADR-051 | Reminder & Notification System | 2025-12 |
| ADR-050 | Voice Domain TTS Architecture | 2025-12 |
| ADR-049 | Local E5 Embeddings | 2025-12 |
| ADR-048 | Semantic Tool Router | 2025-12 |

### ADRs Fondamentaux

| ADR | Titre |
|-----|-------|
| [ADR-001](./architecture/ADR-001-LangGraph-Multi-Agent-System.md) | LangGraph Multi-Agent System |
| [ADR-003](./architecture/ADR-003-Human-in-the-Loop-Plan-Level.md) | Human-in-the-Loop Plan-Level |
| [ADR-006](./architecture/ADR-006-Message-Windowing-Strategy.md) | Message Windowing Strategy |
| [ADR-009](./architecture/ADR-009-Config-Module-Split.md) | Config Module Split |
| [ADR-037](./architecture/ADR-037-Semantic-Memory-Store.md) | Semantic Memory Store |

---

## Runbooks Opérationnels

### Alertes Générales

| Runbook | Description |
|---------|-------------|
| [TEMPLATE.md](./runbooks/alerts/TEMPLATE.md) | Template pour nouveaux runbooks |
| [PRIORITIZATION.md](./runbooks/alerts/PRIORITIZATION.md) | Guide priorisation alertes |
| [HighErrorRate.md](./runbooks/alerts/HighErrorRate.md) | Taux d'erreur élevé |
| [CriticalLatencyP99.md](./runbooks/alerts/CriticalLatencyP99.md) | Latence P99 critique |
| [ServiceDown.md](./runbooks/alerts/ServiceDown.md) | Service indisponible |
| [DatabaseDown.md](./runbooks/alerts/DatabaseDown.md) | Base de données indisponible |
| [ContainerDown.md](./runbooks/alerts/ContainerDown.md) | Container Docker down |
| [HighCPUUsage.md](./runbooks/alerts/HighCPUUsage.md) | Utilisation CPU élevée |
| [HighMemoryUsage.md](./runbooks/alerts/HighMemoryUsage.md) | Utilisation mémoire élevée |
| [DiskSpaceCritical.md](./runbooks/alerts/DiskSpaceCritical.md) | Espace disque critique |

### Alertes Base de Données

| Runbook | Description |
|---------|-------------|
| [CriticalDatabaseConnections.md](./runbooks/alerts/CriticalDatabaseConnections.md) | Connexions DB critiques |
| [HighDatabaseConnections.md](./runbooks/alerts/HighDatabaseConnections.md) | Connexions DB élevées |
| [CheckpointSaveSlowCritical.md](./runbooks/alerts/CheckpointSaveSlowCritical.md) | Checkpoint lent |

### Alertes LLM & Agents

| Runbook | Description |
|---------|-------------|
| [LLMAPIFailureRateHigh.md](./runbooks/alerts/LLMAPIFailureRateHigh.md) | Taux échec API LLM |
| [DailyCostBudgetExceeded.md](./runbooks/alerts/DailyCostBudgetExceeded.md) | Budget quotidien dépassé |
| [AgentsRouterLatencyHigh.md](./runbooks/alerts/AgentsRouterLatencyHigh.md) | Latence router élevée |
| [AgentsRouterLowConfidenceHigh.md](./runbooks/alerts/AgentsRouterLowConfidenceHigh.md) | Confiance router faible |
| [AgentsStreamingErrorRateHigh.md](./runbooks/alerts/AgentsStreamingErrorRateHigh.md) | Erreurs streaming |
| [AgentsTTFTViolation.md](./runbooks/alerts/AgentsTTFTViolation.md) | Violation TTFT |
| [HighConversationResetRate.md](./runbooks/alerts/HighConversationResetRate.md) | Taux reset conversations |

### Alertes Redis

| Runbook | Description |
|---------|-------------|
| [RedisConnectionPoolExhaustion.md](./runbooks/alerts/RedisConnectionPoolExhaustion.md) | Pool Redis épuisé |
| [RedisRateLimitHighHitRate.md](./runbooks/redis/RedisRateLimitHighHitRate.md) | Rate limit hits élevés |
| [RedisRateLimitCheckLatencyHigh.md](./runbooks/redis/RedisRateLimitCheckLatencyHigh.md) | Latence rate limit |

### Runbooks LangGraph

| Runbook | Description |
|---------|-------------|
| [README.md](./runbooks/langgraph/README.md) | Index runbooks LangGraph |
| [high-error-rate.md](./runbooks/langgraph/high-error-rate.md) | Taux d'erreur graphe |
| [high-latency.md](./runbooks/langgraph/high-latency.md) | Latence graphe élevée |
| [low-success-rate.md](./runbooks/langgraph/low-success-rate.md) | Taux succès faible |
| [recursion-error.md](./runbooks/langgraph/recursion-error.md) | Erreurs récursion |
| [state-size-critical.md](./runbooks/langgraph/state-size-critical.md) | Taille state critique |

---

## Templates & Checklists

| Template | Description |
|----------|-------------|
| [NEW_CONNECTOR_CHECKLIST.md](./templates/NEW_CONNECTOR_CHECKLIST.md) | Checklist creation d'un nouveau connecteur OAuth/API Key |
| [NEW_MCP_SERVER_CHECKLIST.md](./templates/NEW_MCP_SERVER_CHECKLIST.md) | Checklist integration d'un nouveau serveur MCP |
| [NEW_PROACTIVE_TASK_CHECKLIST.md](./templates/NEW_PROACTIVE_TASK_CHECKLIST.md) | Checklist creation d'une nouvelle notification proactive |
| [NEW_CHANNEL_CHECKLIST.md](./templates/NEW_CHANNEL_CHECKLIST.md) | Checklist ajout d'un nouveau canal de messagerie |

---

## README Specialises

| README | Description |
|--------|-------------|
| [README_ALERT_MANAGER2.md](./readme/README_ALERT_MANAGER2.md) | AlertManager avancé |
| [README_ALERTING_SMTP.md](./readme/README_ALERTING_SMTP.md) | Configuration SMTP alertes |
| [README_DOMAIN_AGENT_MIXINS.md](./readme/README_DOMAIN_AGENT_MIXINS.md) | Mixins agents domaine |
| [README_LOAD_TESTING.md](./readme/README_LOAD_TESTING.md) | Tests de charge |
| [README_OBSERVABILITY.md](./readme/README_OBSERVABILITY.md) | Stack observabilité |
| [README_GRAFANA_DASHBOARD.md](./readme/README_GRAFANA_DASHBOARD.md) | Configuration dashboards |
| [README_RUNBOOK.md](./readme/README_RUNBOOK.md) | Index runbooks |
| [README_SCRIPTS.md](./readme/README_SCRIPTS.md) | Documentation scripts |
| [README_TESTS.md](./readme/README_TESTS.md) | Guide tests global |
| [README_TESTS_AGENTS.md](./readme/README_TESTS_AGENTS.md) | Tests agents |
| [README_TESTS_AGENT_MIXINS.md](./readme/README_TESTS_AGENT_MIXINS.md) | Tests agent mixins |
| [README_WORKFLOW.md](./readme/README_WORKFLOW.md) | Workflow développement |
| [README_BENCHMARK.md](./readme/README_BENCHMARK.md) | Benchmarks performance |
| [README_REMINDERS.md](./readme/README_REMINDERS.md) | Système de rappels |

---

## Stack Technologique

### Backend (apps/api/)

| Technologie | Version | Usage |
|-------------|---------|-------|
| Python | ≥3.12 | Runtime |
| FastAPI | 0.135.1 | Framework API |
| LangGraph | 1.1.2 | Orchestration multi-agents |
| langchain-core | 1.2.19 | Core abstractions |
| SQLAlchemy | 2.0.48 | ORM async |
| PostgreSQL | 16 + pgvector | Database + vector search |
| Redis | 7.3.0 | Cache, sessions, rate limiting |
| Pydantic | 2.12.5 | Validation données |
| sentence-transformers | 5.0+ | Local E5 embeddings |
| Langfuse | 3.14.5 | LLM tracing |
| Edge TTS | 6.1+ | Synthèse vocale (gratuit) |

### Frontend (apps/web/)

| Technologie | Version | Usage |
|-------------|---------|-------|
| Next.js | 16.1.7 | Framework React |
| React | 19.2.4 | UI Library |
| TypeScript | 5.9.3 | Typage |
| Tailwind CSS | 4.2.1 | Styling |
| Radix UI | v2 | Composants UI |
| TanStack Query | 5.90 | State management |
| react-i18next | 16.5 | Internationalisation |

### Observabilité

| Technologie | Usage |
|-------------|-------|
| Prometheus | 500+ métriques |
| Grafana | 18 dashboards |
| Loki | Logs agrégés |
| Tempo | Traces distribuées |
| Langfuse | LLM observability |
| OpenTelemetry | Instrumentation |

### LLM Providers

| Provider | Models | Usage |
|----------|--------|-------|
| OpenAI | GPT-4.1, GPT-4.1-mini | Principal |
| Anthropic | Claude 3.5 | Alternatif |
| DeepSeek | V3, Reasoner | Économique |
| Perplexity | sonar-pro | Recherche web |
| Google | Gemini 2.0 | Multimodal |

---

## Structure du Projet

```
LIA/
├── apps/
│   ├── api/                    # Backend FastAPI + LangGraph
│   │   ├── src/
│   │   │   ├── core/           # Configuration, security, middleware
│   │   │   ├── domains/        # DDD: agents, auth, chat, connectors, google_api, etc.
│   │   │   └── infrastructure/ # Database, cache, LLM, observability
│   │   ├── tests/              # Tests pytest (2,300+)
│   │   └── alembic/            # Migrations DB
│   └── web/                    # Frontend Next.js
│       ├── src/
│       │   ├── app/            # App Router ([lng]/)
│       │   ├── components/     # Composants React
│       │   ├── hooks/          # Custom hooks
│       │   └── lib/            # API client, utils
│       └── locales/            # Traductions i18n (6 langues)
├── docs/                       # Documentation (ce répertoire)
│   ├── technical/              # Docs techniques détaillées (50+)
│   ├── guides/                 # Guides pratiques (15+)
│   ├── architecture/           # ADRs (59)
│   ├── runbooks/               # Procédures opérationnelles (34+)
│   └── readme/                 # README spécialisés (15+)
├── infrastructure/             # Docker, observabilité
│   └── observability/          # Prometheus, Grafana, Loki, Tempo
├── .claude/                    # Skills Claude (10)
│   └── skills/                 # analyzing-bugs, developing-code, etc.
└── PROD/                       # Configuration production
```

---

## Documentation Externe

### Technologies Principales

| Technologie | Documentation |
|-------------|---------------|
| LangGraph | https://langchain-ai.github.io/langgraph/ |
| LangChain | https://python.langchain.com/ |
| FastAPI | https://fastapi.tiangolo.com/ |
| Next.js | https://nextjs.org/docs |
| SQLAlchemy | https://docs.sqlalchemy.org/en/20/ |
| Pydantic | https://docs.pydantic.dev/ |

### Observabilité

| Technologie | Documentation |
|-------------|---------------|
| Prometheus | https://prometheus.io/docs/ |
| Grafana | https://grafana.com/docs/ |
| Langfuse | https://langfuse.com/docs |
| Loki | https://grafana.com/docs/loki/ |
| Tempo | https://grafana.com/docs/tempo/ |
| OpenTelemetry | https://opentelemetry.io/docs/ |

### LLM Providers

| Provider | Documentation |
|----------|---------------|
| OpenAI | https://platform.openai.com/docs/ |
| Anthropic | https://docs.anthropic.com/ |
| Google Gemini | https://ai.google.dev/docs |
| DeepSeek | https://platform.deepseek.com/docs/ |
| Perplexity | https://docs.perplexity.ai/ |

---

## Comment Contribuer à la Documentation

### Ajouter un Nouveau Document

1. **Créer le fichier** dans le bon répertoire :
   - `docs/technical/` - Documentation technique
   - `docs/guides/` - Guides pratiques
   - `docs/architecture/` - ADRs
   - `docs/runbooks/` - Procédures opérationnelles
   - `docs/readme/` - README spécialisés

2. **Suivre le template standard** :

```markdown
# Titre du Document

> Description courte

**Version**: 1.0
**Date**: YYYY-MM-DD
**Statut**: ✅ Complète

---

## Table des Matières
...
```

3. **Mettre à jour cet INDEX.md**

4. **Créer une PR** avec label `documentation`

### Standards de Qualité

| Standard | Règle |
|----------|-------|
| Format | CommonMark Markdown |
| Langue | Français (sauf code/termes techniques anglais) |
| Code Examples | Testés et fonctionnels |
| Diagrammes | Mermaid pour architecture |
| Liens | Toujours relatifs dans le projet |

---

## Contact

Questions ou suggestions ? Créer une issue GitHub avec le label `documentation`

---

<p align="center">
  <strong>LIA</strong> — Documentation complète pour l'assistant IA de nouvelle génération
</p>

<p align="center">
  <a href="#vue-densemble">⬆️ Retour en haut</a>
</p>
