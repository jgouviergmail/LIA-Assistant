# Roadmap d'Intégration evolution → LIA

> Document de travail persistant pour l'implémentation itérative des fonctionnalités inspirées de [evolution](https://github.com/HKUDS/evolution).
> Chaque conversation d'implémentation DOIT relire ce fichier en premier.

**Version**: 1.1
**Créé le**: 2026-02-28
**Dernière mise à jour**: 2026-03-07 (F2.7 Excalidraw Iterative Builder)
**Statut global**: EN COURS

---

## Table des Matières

1. [Contexte et Origine](#1-contexte-et-origine)
2. [Directives pour l'Implémentation Itérative](#2-directives-pour-limplémentation-itérative)
3. [Tableau de Bord des Features](#3-tableau-de-bord-des-features)
4. [Feature 1 — Web Fetch Tool](#4-feature-1--web-fetch-tool)
5. [Feature 2 — Support MCP](#5-feature-2--support-mcp)
6. [Feature 3 — Multi-Channel Telegram](#6-feature-3--multi-channel-telegram)
7. [Feature 4 — Background Task Spawning](#7-feature-4--background-task-spawning)
8. [Feature 5 — Heartbeat Autonome LLM](#8-feature-5--heartbeat-autonome-llm)
9. [Feature 6 — Code Sandbox Tool](#9-feature-6--code-sandbox-tool)
10. [Hypothèses Retirées](#10-hypothèses-retirées)
11. [Patterns de Référence](#11-patterns-de-référence)
12. [Journal des Décisions](#12-journal-des-décisions)

---

## 1. Contexte et Origine

### Analyse source

evolution est un assistant IA personnel ultra-léger (~4000 lignes) mono-utilisateur avec :
- **MessageBus** (async queues inbound/outbound)
- **ToolRegistry** avec 7 tools natifs (shell, filesystem, web, spawn, cron, message, mcp)
- **SubagentManager** (tâches de fond via `asyncio.create_task`)
- **CronService** (planification avec persistence JSON)
- **HeartbeatService** (proactivité LLM, 2 phases : decide → execute)
- **SkillsLoader** (plugins SKILL.md avec progressive disclosure)
- **10 channels** (Telegram, Discord, Slack, Matrix, IRC, CLI, etc.)
- **MCP support** (Stdio + HTTP transports via AsyncExitStack)
- **MemoryStore** (MEMORY.md + HISTORY.md avec consolidation LLM)

**Dépôt analysé** : https://github.com/HKUDS/evolution (cloné et étudié fichier par fichier)

### Différences architecturales fondamentales

| Aspect | evolution | LIA |
|--------|---------|------------|
| Modèle | Mono-utilisateur, local | Multi-utilisateur, web (SaaS) |
| Auth | Aucune | BFF session-based (HTTP-only cookies + Redis) |
| Isolation | Process unique | ContextVar + DB user_id + Redis keyed |
| Orchestration | Boucle LLM→tools (max 40 iter) | LangGraph 7-node state graph + ParallelExecutor |
| Planification | Aucune | SmartPlannerService (4 stratégies, 89% token reduction) |
| Tools | 7 natifs + MCP | 40+ tools avec SmartCatalogueService (96% token reduction) |
| Stockage | Fichiers JSON/JSONL | PostgreSQL + Redis + SQLAlchemy async |
| Observabilité | Logs basiques | Prometheus + Grafana + Langfuse + OpenTelemetry |
| Sécurité | Minimal (deny patterns shell) | OWASP, rate limiting Lua, Fernet encryption, RBAC |

### Hypothèses retirées après vérification (faux positifs)

Voir [Section 10](#10-hypothèses-retirées) pour le détail complet et les justifications.

---

## 2. Directives pour l'Implémentation Itérative

### Procédure pour chaque nouvelle conversation

```
1. LIRE ce fichier en entier (docs/technical/evolution_INTEGRATION_ROADMAP.md)
2. IDENTIFIER la prochaine feature à implémenter (statut "À FAIRE" dans le tableau de bord)
3. LIRE la section détaillée de la feature
4. VÉRIFIER les dépendances (certaines features en requièrent d'autres)
5. IMPLÉMENTER en suivant la checklist de la feature
6. TESTER (unit + vérification manuelle si applicable)
7. METTRE À JOUR ce fichier :
   - Cocher les items de la checklist
   - Passer le statut de la feature à "EN COURS" ou "TERMINÉ"
   - Ajouter les décisions prises dans le Journal (Section 12)
   - Mettre à jour "Dernière mise à jour" en haut du fichier
```

### Règles de qualité

Chaque implémentation DOIT respecter :

1. **Patterns existants** — Réutiliser les classes, helpers et patterns du projet (voir [Section 11](#11-patterns-de-référence))
2. **DRY/KISS/SRP** — Pas de code dupliqué, solutions simples, responsabilité unique
3. **i18n** — Toutes les chaînes UI dans les 6 langues (fr, en, es, de, it, zh)
4. **Tests** — Unit tests pour toute logique métier (schema validation, helpers, service)
5. **Constants** — Pas de magic strings, tout dans `constants.py` ou `.env`
6. **Sécurité** — User isolation, rate limiting, validation des entrées, SSRF prevention
7. **Documentation** — Mettre à jour `docs/INDEX.md` et ce roadmap
8. **Observabilité** — structlog, metrics Prometheus, track_tool_metrics
9. **Error handling** — `UnifiedToolOutput.failure()` avec `ToolErrorCode` approprié
10. **Type hints** — MyPy strict, Pydantic v2 pour les schemas

### Conventions de nommage

| Élément | Convention | Exemple |
|---------|-----------|---------|
| Agent name | `{domain}_agent` | `web_fetch_agent` |
| Tool function | `{action}_{domain}_tool` | `fetch_web_page_tool` |
| Constant agent | `AGENT_{DOMAIN}` | `AGENT_WEB_FETCH` |
| Constant context | `CONTEXT_DOMAIN_{DOMAIN}` | `CONTEXT_DOMAIN_WEB_FETCH` |
| Node name | `NODE_{DOMAIN}_AGENT` | `NODE_WEB_FETCH_AGENT` |
| Tool module | `{domain}_tools.py` | `web_fetch_tools.py` |
| Catalogue manifest | `{domain}/catalogue_manifests.py` | `web_fetch/catalogue_manifests.py` |
| Config class | `{Domain}Settings` | `WebFetchSettings` |
| Constants prefix | `WEB_FETCH_*` | `WEB_FETCH_MAX_CONTENT_LENGTH` |

---

## 3. Tableau de Bord des Features

| # | Feature | Priorité | Effort | Statut | Dépendances | Version cible |
|---|---------|----------|--------|--------|-------------|---------------|
| 1 | [Web Fetch Tool](#4-feature-1--web-fetch-tool) | P0 | Faible | TERMINÉ | Aucune | v6.2 |
| 2 | [Support MCP](#5-feature-2--support-mcp) | P1 | Moyen | TERMINÉ | Aucune | v6.3 |
| 3 | [Multi-Channel Telegram](#6-feature-3--multi-channel-telegram) | P2 | Élevé | TERMINÉ | Aucune | v6.2 |
| 4 | [Background Task Spawning](#7-feature-4--background-task-spawning) | P2 | Moyen | À FAIRE | Aucune | v7.0 |
| 5 | [Heartbeat Autonome LLM](#8-feature-5--heartbeat-autonome-llm) | P3 | Moyen | TERMINÉ | Notifications existantes | v6.4 |
| 6 | [Code Sandbox Tool](#9-feature-6--code-sandbox-tool) | P3 | Élevé | À FAIRE | Docker infra | v7.2+ |

**Légende statuts** : À FAIRE | EN COURS | TERMINÉ | ABANDONNÉ

---

## 4. Feature 1 — Web Fetch Tool

### Objectif

Permettre à LIA de récupérer et lire le contenu d'une URL spécifique pour répondre aux questions des utilisateurs nécessitant des informations web ciblées.

### Analyse du gap

LIA dispose déjà de :
- `unified_web_search_tool` : recherche via Perplexity + Brave + Wikipedia (retourne des résumés/snippets)
- `brave_search_tool` / `brave_news_tool` : recherche Brave (retourne des résultats avec URL + description)

**Ce qui manque** : aucun tool ne permet de **récupérer le contenu complet d'une page web** à partir d'une URL connue. L'utilisateur dit "lis cet article : https://..." → LIA ne peut pas.

### Inspiration evolution

**Fichier source** : `/tmp/evolution/evolution/agent/tools/web.py` — `WebFetchTool`
- Utilise `httpx` + `readability-lxml` pour extraire le contenu principal
- Conversion HTML → Markdown via `markdownify`
- Validation URL, suivi de redirections (max 5), troncature (50k chars)
- Timeout 30s, User-Agent personnalisé

### Use Cases utilisateur

1. **"Lis cet article"** — L'utilisateur partage un lien, LIA résume le contenu
2. **"Compare ces deux pages"** — L'utilisateur donne 2 URLs, LIA analyse les différences
3. **"Que dit ce site sur X ?"** — Extraction ciblée d'information
4. **Suite de recherche** — Après un `unified_web_search_tool`, LIA peut approfondir un résultat en lisant la page complète
5. **Veille technologique** — L'utilisateur demande de lire une documentation, un changelog, etc.

### Spécifications techniques

#### Architecture

```
fetch_web_page_tool (LangChain @tool)
    |
    ├── validate_url()           → SSRF prevention
    ├── httpx.AsyncClient.get()  → HTTP fetch
    ├── readability.Document()   → Content extraction
    ├── markdownify.convert()    → HTML → Markdown
    └── UnifiedToolOutput        → Structured response
```

#### Sécurité (CRITIQUE — multi-tenant)

| Risque | Mitigation |
|--------|-----------|
| SSRF (Server-Side Request Forgery) | Blacklist IPs privées (10.x, 172.16-31.x, 192.168.x, 127.x, ::1, 169.254.x), résolution DNS avant fetch |
| Exfiltration données internes | Blacklist hostnames (localhost, *.internal, metadata endpoints cloud) |
| DoS via fichiers énormes | `max_content_length` (500KB), timeout strict (15s), stream + early abort |
| Injection de contenu malveillant | Sanitization du markdown, pas d'exécution de JS |
| Abus (spam de requêtes) | Rate limiting par user (10 fetches/min) |
| HTTPS enforcement | Upgrade HTTP → HTTPS automatique, warning si HTTP non-upgradable |

#### Paramètres du tool

```python
async def fetch_web_page_tool(
    url: Annotated[str, "The URL of the web page to fetch and read"],
    extract_mode: Annotated[str, "Content extraction mode: 'article' (main content) or 'full' (entire page)"] = "article",
    max_length: Annotated[int, "Maximum content length in characters (default 30000)"] = 30000,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
```

#### Retour

```python
UnifiedToolOutput.data_success(
    message="Article 'Titre de la page' (3200 mots) — source: example.com",
    structured_data={
        "title": "Titre de la page",
        "content": "# Titre\n\nContenu markdown...",
        "url": "https://example.com/article",
        "word_count": 3200,
        "language": "fr",
        "extracted_at": "2026-02-28T10:30:00Z",
    },
    registry_updates={...}  # Pour RegistryItem si besoin de référence contextuelle
)
```

### Fichiers à créer

| Fichier | Description |
|---------|------------|
| `apps/api/src/domains/agents/tools/web_fetch_tools.py` | Tool principal (~430 lignes) |
| `apps/api/src/domains/agents/web_fetch/__init__.py` | Package agent |
| `apps/api/src/domains/agents/web_fetch/catalogue_manifests.py` | ToolManifest |
| `apps/api/src/domains/agents/web_fetch/url_validator.py` | Validation URL + SSRF prevention (~260 lignes) |
| `apps/api/src/domains/agents/graphs/web_fetch_agent_builder.py` | Agent builder (generic template) |
| `apps/api/src/domains/agents/prompts/v1/web_fetch_agent_prompt.txt` | Prompt système agent |
| `apps/api/tests/unit/domains/agents/tools/test_web_fetch_tools.py` | Tests unitaires tool |
| `apps/api/tests/unit/domains/agents/web_fetch/test_url_validator.py` | Tests validation URL |

### Fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| `apps/api/src/domains/agents/constants.py` | Ajouter `AGENT_WEB_FETCH`, `CONTEXT_DOMAIN_WEB_FETCH`, `NODE_WEB_FETCH_AGENT`, intentions |
| `apps/api/src/core/constants.py` | Ajouter constantes (`WEB_FETCH_*`) |
| `apps/api/src/core/config/llm.py` | Ajouter section LLM config `web_fetch_agent_llm_*` |
| `apps/api/src/domains/agents/tools/tool_registry.py` | Ajouter import `web_fetch_tools` dans `_import_tool_modules()` |
| `apps/api/src/domains/agents/registry/catalogue_loader.py` | Enregistrer manifests |
| `apps/api/src/domains/agents/graphs/__init__.py` | Exporter `build_web_fetch_agent` |
| `apps/api/src/main.py` | Import + `registry.register_agent("web_fetch_agent", ...)` |
| `apps/api/requirements.txt` | Ajouter `readability-lxml`, `markdownify` |
| `apps/web/locales/*/translation.json` | Clés i18n pour le tool (execution_step) |
| `docs/INDEX.md` | Référencer la doc |

### Dépendances Python à ajouter

```
readability-lxml>=0.8.1    # Extraction contenu principal HTML (algorithme Readability)
markdownify>=0.14.1        # Conversion HTML → Markdown
```

Note : `httpx` est déjà dans les dépendances (v0.27.2).

### Checklist d'implémentation

- [x] Créer `web_fetch/url_validator.py` avec tests
- [x] Créer `web_fetch_tools.py` avec pattern @tool + validate_runtime_config + UnifiedToolOutput
- [x] Créer `web_fetch/catalogue_manifests.py` (ToolManifest)
- [x] Ajouter constantes dans `agents/constants.py` et `core/constants.py`
- [x] Enregistrer dans `tool_registry.py` (`_import_tool_modules`)
- [x] Enregistrer manifests dans `catalogue_loader.py`
- [x] Ajouter ContextTypeRegistry pour Data Registry
- [x] Ajouter dépendances dans `requirements.txt`
- [x] Ajouter clés i18n (6 langues) pour `execution_step`
- [x] Tests unitaires (url_validator, tool logic avec mocks httpx)
- [x] `task lint:backend` + `task test:backend:unit:fast` passent
- [x] Mettre à jour ce roadmap (statut → TERMINÉ)
- [x] Mettre à jour `docs/INDEX.md`
- [x] Mettre à jour `docs/technical/AGENTS.md` (ajouter `web_fetch_agent` dans le tableau)
- [x] Mettre à jour `docs/technical/TOOLS.md` (ajouter domaine Web Fetch)
- [x] Mettre à jour FAQ site web (6 langues) — 2 questions ajoutées (q16 + q17) + q10 mise à jour

### Estimation

- **Backend** : ~500 lignes de code (tool + validator + manifests + constants)
- **Tests** : ~300 lignes
- **i18n** : ~6 lignes par langue (1 clé execution_step)
- **Effort total** : 1 session

### Retour d'expérience (REX) — Leçons pour les prochaines features

> Observations issues de l'implémentation réelle de F1, à consulter avant chaque nouvelle feature.

#### 1. Checklist complète pour un nouvel agent routable

Le plan initial avait omis **5 fichiers critiques** nécessaires au pipeline d'orchestration.
Tout agent avec `is_routable=True` dans `domain_taxonomy.py` doit avoir :

| Élément | Fichier | Obligatoire |
|---------|---------|-------------|
| Tool(s) | `tools/{domain}_tools.py` | Oui |
| Catalogue manifests | `{domain}/catalogue_manifests.py` | Oui |
| URL/Input validator | `{domain}/url_validator.py` (ou équivalent) | Si sécurité requise |
| **Agent builder** | **`graphs/{domain}_agent_builder.py`** | **Oui (manquait dans le plan)** |
| **Prompt système** | **`prompts/v1/{domain}_agent_prompt.txt`** | **Oui (manquait dans le plan)** |
| **Config LLM** | **`core/config/llm.py` (section agent)** | **Oui (manquait dans le plan)** |
| **Registration main.py** | **`main.py` (import + register_agent)** | **Oui (manquait dans le plan)** |
| **Export graphs/__init__.py** | **`graphs/__init__.py` (__all__)** | **Oui (manquait dans le plan)** |
| Constants | `agents/constants.py` + `core/constants.py` | Oui |
| RegistryItemType | `data_registry/models.py` + `tools/output.py` | Si data registry |
| Tool registry import | `tools/tool_registry.py` | Oui |
| Catalogue loader | `registry/catalogue_loader.py` | Oui |
| Domain taxonomy | `registry/domain_taxonomy.py` | Oui |
| i18n | `locales/*/translation.json` (6 langues) | Oui |
| Tests | `tests/unit/domains/agents/{domain}/` + `tests/unit/domains/agents/tools/` | Oui |

#### 2. Sécurité SSRF — Ranges IP à ne pas oublier

La première implémentation ne bloquait que les ranges RFC 1918 basiques. Les ranges suivants
sont aussi nécessaires pour une protection SSRF complète :

- `100.64.0.0/10` — CGNAT (RFC 6598) : IP partagées opérateur, accès réseau interne
- `198.18.0.0/15` — Benchmarking (RFC 2544)
- `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` — Test-Nets (RFC 5737)
- `240.0.0.0/4` — Réservé pour usage futur
- `224.0.0.0/4` — Multicast
- **IPv4-mapped IPv6** (`::ffff:127.0.0.1`) : contourne les blocklists IPv4 si non traité.
  Utiliser `ipaddress.IPv6Address.ipv4_mapped` pour extraire l'IPv4 sous-jacente.

#### 3. Tests — Patterns critiques pour les tools LangChain

- **InjectedToolArg (ToolRuntime)** : ne peut PAS recevoir un `MagicMock` via `ainvoke()`.
  Solution : patcher `validate_runtime_config` au niveau application avec un `autouse=True` fixture.
- **Assertions spécifiques** : toujours vérifier `result.error_code` (pas seulement `result.success`),
  et vérifier la structure complète de `structured_data` et `registry_updates`.
- **Content-Type HTTP** : la spec HTTP dit case-insensitive → toujours `.lower()` avant comparaison.
- **Sanitization markdown** : couvrir tous les protocoles dangereux (`javascript:`, `data:`,
  `vbscript:`, `file:`, `about:`), pas seulement les deux premiers.

#### 4. Effort réel vs estimé

- Estimé : 1 session, ~800 lignes
- Réel : ~2 sessions, ~1200 lignes (avec corrections post-revue)
- Principal facteur : le pipeline d'orchestration complet (builder + prompt + LLM config +
  registration) était sous-estimé car le plan se focalisait sur le pattern `reminder_tools.py`
  (outil intégré dans un agent existant) au lieu du pattern `brave_agent` (agent standalone routable)

---

## 5. Feature 2 — Support MCP

### Objectif

Permettre d'intégrer des serveurs MCP (Model Context Protocol) externes comme sources de tools additionnels, rendant LIA extensible sans modification du code source.

### Analyse du gap

LIA n'a aucun support MCP. Tous les tools sont codés en dur dans le monorepo. L'ajout d'un nouveau tool nécessite : code Python + manifest + registry + tests + deployment.

MCP est le standard émergent (Anthropic, 2024) pour l'extensibilité des tools LLM. Il permet de connecter des serveurs externes qui exposent des tools via un protocole standardisé (JSON-RPC over Stdio ou HTTP/SSE).

### Inspiration evolution

**Fichiers sources** :
- `/tmp/evolution/evolution/agent/tools/mcp.py` — `MCPToolWrapper` + `connect_mcp_servers()`
- `/tmp/evolution/evolution/config/schema.py` — `ToolsConfig` avec `mcp_servers: dict`

evolution utilise `mcp` SDK Python avec `StdioServerParameters` et `streamablehttp_client`. Chaque tool MCP est wrappé en tool natif via `MCPToolWrapper`.

### Use Cases

1. **Databases** — Connecter un serveur MCP PostgreSQL/Supabase pour requêtes SQL
2. **File systems** — Accès à des systèmes de fichiers distants (S3, GDrive via MCP)
3. **APIs tierces** — GitHub, Jira, Notion, Slack via serveurs MCP communautaires
4. **Tools custom** — L'admin crée un serveur MCP interne pour des besoins métier spécifiques
5. **Prototypage rapide** — Tester un nouveau tool sans coder dans LIA

### Considérations multi-tenant

| Aspect | Approche |
|--------|---------|
| **Serveurs globaux** (admin) | Configurés dans `.env` / config, partagés par tous les users |
| **Serveurs par user** (future) | Stockés en DB par user, sandboxés, limités en nombre |
| **Sécurité** | HITL obligatoire pour tout appel MCP (tools non audités) |
| **Isolation** | Chaque connexion MCP est par-session (pas de partage d'état) |
| **Rate limiting** | Compteur MCP séparé, plafond global configurable |
| **Timeout** | 30s par appel MCP, configurable par serveur |

### Architecture proposée

```
                    ┌─────────────────────────┐
                    │   SmartCatalogueService  │
                    │  (filtre tools natifs +  │
                    │   tools MCP dynamiques)  │
                    └───────────┬──────────────┘
                                │
                    ┌───────────▼──────────────┐
                    │     MCPToolAdapter        │
                    │  (wraps MCP tool →        │
                    │   LangChain BaseTool)     │
                    └───────────┬──────────────┘
                                │
                    ┌───────────▼──────────────┐
                    │    MCPClientManager       │
                    │  (lifecycle, pooling,     │
                    │   health checks)          │
                    └───────────┬──────────────┘
                                │
              ┌─────────────────┼──────────────────┐
              ▼                 ▼                   ▼
        MCP Server 1      MCP Server 2        MCP Server N
        (Stdio)           (HTTP/SSE)          (HTTP/SSE)
```

### Fichiers à créer

| Fichier | Description |
|---------|------------|
| `apps/api/src/infrastructure/mcp/__init__.py` | Package MCP |
| `apps/api/src/infrastructure/mcp/client_manager.py` | MCPClientManager (lifecycle, pooling) |
| `apps/api/src/infrastructure/mcp/tool_adapter.py` | MCPToolAdapter (MCP tool → LangChain BaseTool) |
| `apps/api/src/infrastructure/mcp/schemas.py` | MCPServerConfig, MCPToolSchema |
| `apps/api/src/infrastructure/mcp/security.py` | Validation, HITL enforcement |
| `apps/api/src/core/config/mcp.py` | MCPSettings (config module) |
| `apps/api/tests/unit/infrastructure/mcp/test_tool_adapter.py` | Tests |
| `apps/api/tests/unit/infrastructure/mcp/test_client_manager.py` | Tests |
| `docs/technical/MCP_INTEGRATION.md` | Documentation technique |

### Fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| `apps/api/src/core/config/__init__.py` | Ajouter `MCPSettings` dans la chaîne d'héritage `Settings` |
| `apps/api/src/main.py` | Initialiser `MCPClientManager` dans lifespan + cleanup |
| `apps/api/src/domains/agents/services/smart_catalogue_service.py` | Injecter tools MCP dans le catalogue dynamiquement |
| `apps/api/src/core/constants.py` | Constantes MCP |
| `apps/api/requirements.txt` | Ajouter `mcp>=1.0.0` |
| `apps/web/locales/*/translation.json` | Clés i18n MCP |
| `.env.example` | Variables MCP |

### Dépendances Python à ajouter

```
mcp>=1.0.0    # Model Context Protocol SDK (Anthropic)
```

### Checklist d'implémentation

- [x] Créer `core/config/mcp.py` avec `MCPSettings` + variables `.env`
- [x] Créer `infrastructure/mcp/schemas.py` (MCPServerConfig Pydantic)
- [x] Créer `infrastructure/mcp/client_manager.py` (connexion, pooling, health)
- [x] Créer `infrastructure/mcp/tool_adapter.py` (wrapping MCP → LangChain BaseTool)
- [x] Créer `infrastructure/mcp/security.py` (validation, HITL enforcement)
- [x] Créer `infrastructure/mcp/registration.py` (bridge AgentRegistry + tool_registry)
- [x] Domain taxonomy "mcp" + métriques Prometheus
- [x] Modifier `main.py` lifespan (init + cleanup)
- [x] Ajouter constantes et dépendances (`mcp>=1.9.0`)
- [x] Tests unitaires (5 fichiers : schemas, security, adapter, manager, registration)
- [x] i18n (6 langues)
- [x] Documentation technique (`docs/technical/MCP_INTEGRATION.md`)
- [x] `task lint:backend` + `task test:backend:unit:fast` passent
- [x] Mettre à jour ce roadmap (statut → TERMINÉ)

### Estimation

- **Backend** : ~800-1000 lignes de code
- **Tests** : ~400 lignes
- **Effort total** : 2-3 sessions

### REX (Retour d'Expérience)

1. **Dual registry obligatoire** : Les tools MCP doivent être enregistrés dans DEUX registries (AgentRegistry pour le catalogue, tool_registry pour parallel_executor). Un seul enregistrement = tools invisibles.
2. **Agent virtuel unique** : Utiliser un seul `"mcp_agent"` pour tous les tools MCP (pas un agent par serveur) car `_extract_domain_from_agent_name("mcp_filesystem_agent")` échoue.
3. **BaseTool subclass obligatoire** : Les décorateurs `@tool`, `@connector_tool`, `@rate_limit`, `@track_tool_metrics` ne fonctionnent que sur des fonctions statiques, pas sur des tools découverts dynamiquement au runtime.
4. **18 corrections en 5 itérations** : La revue systématique du plan a identifié des bugs critiques (TOCTOU rate limiting, CallToolResult.isError ignoré, JSON config non validée, secrets dans repr, SSRF cross-layer).
5. **Effort réel** : 1 session de planification (5 itérations de revue) + 1 session d'implémentation (~1000 lignes backend + ~500 lignes tests).

### Feature 2.1 — MCP Per-User ✅ TERMINÉ

> **Objectif** : Permettre aux utilisateurs de configurer leurs propres serveurs MCP.
>
> **Statut** : TERMINÉ (2026-02-28)
>
> **Implémentation** :
> - Table `user_mcp_servers` avec credentials Fernet-encrypted
> - Transport `streamable_http` uniquement (pas de stdio pour sécurité)
> - Auth à 3 niveaux : None, API Key/Bearer (static), OAuth 2.1 (PKCE + refresh)
> - `ContextVar[UserMCPToolsContext]` pour isolation per-request (pas de modification des singletons)
> - Lazy connection pool `UserMCPClientPool` avec TTL, eviction, rate limiting, reference counting
> - Pipeline intégration : catalogue injection (normal + panic filtering), semantic score bypass, executor ContextVar fallback (3 points)
> - API : 10 endpoints `/api/v1/mcp/servers` (CRUD + toggle + test + generate-description + OAuth flow)
> - Frontend : Settings > Features > MCP Servers (CRUD + test + OAuth)
> - i18n : 6 langues (fr, en, es, de, it, zh)
> - 105 tests unitaires, 0 régressions
>
> **Fichiers créés** : 13 | **Fichiers modifiés** : 17 | **Lignes** : ~3000
>
> **Prérequis** : Feature 2 (MCP infrastructure) terminée ✅

### Feature 2.2 — Per-Server Domain & Smart Catalogue ✅ TERMINÉ

> **Objectif** : Donner à chaque serveur MCP utilisateur son propre domaine sémantique dans le catalogue, au lieu du domaine générique "mcp", pour un routing plus précis par le planner et le QueryAnalyzer.
>
> **Statut** : TERMINÉ (2026-03-01)
>
> **Implémentation** :
> - Champ `domain_description` sur `UserMCPServer` (optionnel, saisi par l'utilisateur)
> - Calcul d'embeddings E5 sur la description pour matching sémantique via `compute_domain_embeddings()`
> - Slug de domaine per-server : `mcp_<slugified_server_name>` (ex: `mcp_huggingface_hub`)
> - `QueryAnalyzerService` détecte les domaines MCP via embeddings + seuil de similarité
> - `SmartCatalogueService` : injection des tools MCP user dans les stratégies normal + panic filtering
> - `domain_taxonomy.py` : entrées dynamiques per-server dans `TYPE_TO_DOMAIN_MAP`
> - Frontend : champ "Description du domaine" dans le formulaire de création/édition
> - i18n : labels pour le champ domain_description (6 langues)
>
> **Fichiers modifiés** : 8 | **Lignes** : ~400
>
> **Prérequis** : Feature 2.1 (Per-user MCP) terminée ✅

### Feature 2.3 — HTML Card Display ✅ TERMINÉ

> **Objectif** : Afficher les résultats des tools MCP dans des cards HTML dans le chat, alignées sur le pattern visuel existant (BEM, `BaseComponent`, `wrap_with_response`).
>
> **Statut** : TERMINÉ (2026-03-01)
>
> **Implémentation** :
> - `RegistryItemType.MCP_RESULT` enum + mapping dans `REGISTRY_TYPE_TO_KEY` et `TYPE_TO_DOMAIN_MAP`
> - `UserMCPToolAdapter._arun()` retourne `UnifiedToolOutput` (au lieu de `str` brut) avec `registry_updates`
> - Bridge executor : `@property coroutine` sur `UserMCPToolAdapter` → le `parallel_executor` utilise le chemin direct (préserve `UnifiedToolOutput` au lieu de stringifier via `ainvoke()`)
> - `McpResultCard(BaseComponent)` : composant card avec badge serveur, nom outil humanisé, contenu JSON/texte
> - `HtmlRenderer` : enregistrement composant `"mcps"` + data keys + icône `Icons.EXTENSION`
> - `i18n_v3.py` : labels domaine "mcps" (6 langues : "Résultats MCP", "MCP Results", etc.)
> - `Icons.EXTENSION` (puzzle piece) pour le badge MCP
> - Tests unitaires : card rendering (6 tests) + adapter output (7 tests)
>
> **Décisions architecturales** :
> - Bridge via `@property coroutine` (safe sur BaseTool Pydantic v2 — properties ne sont PAS des champs model)
> - `time.time_ns()` pour unicité des IDs (Python randomise les hash seeds depuis 3.3)
> - `meta.domain = "mcps"` → UN seul composant card pour tous les serveurs (nom serveur dans payload)
> - Pas d'ajout à `TOOL_PATTERN_TO_DOMAIN_MAP` (risque de collision : `mcp_user_abc_send_email` matcherait `"email"` avant `"mcp_user_"`)
>
> **Fichiers créés** : 1 (`mcp_result_card.py`) | **Fichiers modifiés** : 7 | **Lignes** : ~300
>
> **Prérequis** : Feature 2.1 (Per-user MCP) terminée ✅

### Revue qualité F2.1-F2.3 ✅ TERMINÉ (2026-03-01)

> Revue de code exhaustive des 85 fichiers staged (5 agents parallèles) avec corrections :
>
> **Critiques (7)** :
> - C1: DNS bloquant → async `loop.getaddrinfo()` dans `security.py`
> - C2: `expires_at` stockait `expires_in` (durée) au lieu de timestamp absolu
> - C3: `httpx.AsyncClient` non fermé → `__aenter__`/`__aexit__` sur `MCPOAuthFlowHandler`
> - C4: Clé i18n `common.optional` manquante → ajoutée dans 6 langues
> - C5: Mutations frontend sans try/catch → `toast.error()` sur 5 handlers
> - C6: Router try/except fragile (string matching) → supprimé (BaseAPIException auto-gérée par FastAPI)
> - C7: Documentation roadmap non mise à jour → cette section
>
> **Hautes (5)** :
> - H2: Magic string callback OAuth → constante `MCP_USER_OAUTH_CALLBACK_PATH`
> - H3: Locks `defaultdict(asyncio.Lock)` → cleanup dans `disconnect()`
> - H6: Imports inline dans router → top-level
> - H7: État test global → per-server (`testingServerId`)
> - H10: `get_creds_fn: Any` → `Callable[[], Coroutine[...]]`
>
> **Moyennes (5)** :
> - M1: `_HALLUCINATED_SUFFIXES` → `ClassVar` (évite champ dataclass)
> - M2: `NameError` potentiel sur import MCP → déplacé avant try
> - M3: `htmlFor`/`id` manquants sur formulaire → accessibilité
> - M6: `" ".join()` → `"\n".join()` (cohérence content parsing)
> - M12: Param erreur OAuth non URL-encodé → `quote()`

### Correctifs post-revue F2 (2026-03-02)

> Corrections fonctionnelles suite aux tests utilisateur :

**UI Settings (MCP Servers + Scheduled Actions)** :
- Refactoring layout : chaque info sur sa propre ligne (pas flex-wrap)
- Boutons d'action en hover-reveal (desktop) + Dialog mobile (pattern Mémoire/Intérêts)
- `e.stopPropagation()` sur tous les éléments interactifs dans les cartes
- `DialogDescription` sr-only pour accessibilité Radix

**OAuth credentials — bug save/reload** :
- `_encrypt_credentials_from_update()` pour OAUTH2 ignorait silencieusement les nouveaux `client_id`/`client_secret` (retournait `server.credentials_encrypted` inchangé)
- Fix : merge des nouveaux client credentials dans le blob existant, préservant les OAuth tokens (access_token, refresh_token)
- Ajout `has_oauth_credentials: bool` au schema `UserMCPServerResponse` + extraction depuis credentials décryptées
- Frontend : placeholders "Credentials saved" + hint sur les champs OAuth (aligné sur api_key/bearer)

**FAQ MCP** :
- Nouvelle section FAQ `mcp_servers` (6 questions) dans les 6 langues (fr, en, de, es, it, zh)
- Ajout section + icône `Plug` dans `FAQContent.tsx`

**OAuth metadata discovery — heuristic fallback** :
- `_fetch_auth_server_metadata()` échouait pour les providers non-RFC 8414 (GitHub, etc.) car elle ne tentait que `.well-known/oauth-authorization-server` et `.well-known/openid-configuration`
- Fix : ajout d'une 3ème stratégie "convention-based heuristic" qui probe `{auth_server_url}/authorize` et construit les endpoints (`/authorize`, `/access_token`, PKCE S256 assumé)
- Cas GitHub : `https://github.com/login/oauth` → `authorize` + `access_token` sous-chemins, sans metadata RFC 8414
- 12 tests unitaires ajoutés (`test_oauth_flow.py`)

**OAuth scopes configurables** :
- Problème : GitHub MCP renvoyait 403 Forbidden sur `call_tool` (mais `list_tools` OK) car le token OAuth était émis sans scopes (la metadata discovery heuristique retourne `scopes_supported: []`)
- Root cause : `oauth_flow.py` utilisait `" ".join(metadata.scopes_supported)` → chaîne vide → token avec permissions minimales → 403 sur les appels API réels
- Fix : champ `oauth_scopes` configurable par l'utilisateur (space-separated) stocké dans `oauth_metadata.requested_scopes` (JSONB, pas de migration DB)
- Priorité : `requested_scopes` utilisateur > `scopes_supported` auto-découverts > chaîne vide
- Backend : `schemas.py` (champ Create/Update/Response), `service.py` (stockage JSONB), `router.py` (extraction/passage), `oauth_flow.py` (paramètre `requested_scopes`)
- Frontend : `useUserMCPServers.ts` (types), `MCPServersSettings.tsx` (champ input dans section OAuth2, create + update handlers)
- i18n : 6 langues (fr, en, de, es, it, zh) — labels form + FAQ Q7 ajoutée

**Connexions éphémères MCP** :
- Problème : `CancelledError` wrappé dans `ExceptionGroup` lors des `call_tool()` après la première utilisation
- Root cause : le SDK MCP Python utilise des anyio TaskGroups internes. Quand la session est stockée dans un pool long-lived, les background tasks meurent (cancel scope expiré) → `ClosedResourceError`/`CancelledError`
- Fix : connexions éphémères — chaque `call_tool()` crée une connexion fraîche (connect → initialize → call → close) dans un seul scope async
- Overhead ~1.5s par appel, acceptable vs latence typique MCP (3-10s)

**ExceptionGroup unwrapping** :
- Problème : le logger ne montrait que "unhandled errors in a TaskGroup (1 sub-exception)" sans l'erreur réelle (car `str(ExceptionGroup)` cache les sub-exceptions)
- Fix : `exc_info=True` dans `user_tool_adapter.py` + unwrapping explicite dans `user_pool.py._execute_call_ephemeral()` (log sub-exceptions + re-raise first)

### Feature 2.4 — Structured Items Parsing ✅ TERMINÉ

> **Objectif** : Détecter automatiquement les résultats MCP contenant un JSON array et générer un `RegistryItem` par élément, au lieu d'un seul item brut pour tout le résultat.
>
> **Statut** : TERMINÉ (2026-03-02)
>
> **Implémentation** :
> - Détection automatique JSON array dans `UserMCPToolAdapter._arun()` : si le contenu est un `list[dict]`, chaque dict devient un `RegistryItem` individuel
> - Clé de collection dérivée du nom d'outil humanisé (ex: `list_repos` → `repos`)
> - Constante `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` (défaut: 50) pour limiter la volumétrie
> - `McpResultCard` supporte 2 modes de rendu : structured (titre + champs clés) et raw (JSON/texte brut)
> - `RegistryItem` payload en 2 formes : `{"item": dict, "server_name": str}` (structured) et `{"raw_content": str, "server_name": str}` (raw)
>
> **Fichiers modifiés** : 3 (`user_tool_adapter.py`, `mcp_result_card.py`, `core/constants.py`)
>
> **Prérequis** : Feature 2.3 (HTML Card Display) terminée ✅

### Revue qualité F2 — Rounds 4-5 ✅ TERMINÉ (2026-03-02)

> Revue exhaustive des 85 fichiers staged contre 15 critères qualité (complétude, patterns, nommage, Google Python Style Guide, constantes, i18n, DRY/YAGNI/KISS/SRP/SoC, best practices, réutilisation, pas de duplication, code générique, patterns framework, patterns codebase, gestion erreurs, documentation).
>
> **Round 4 (4 corrections)** :
> - Test HTTPS URL validation manquant sur `UserMCPServerUpdate`
> - Imports `from src.core.constants import` dupliqués dans `auth.py` et `oauth_flow.py`
> - Blank line manquante dans `schemas.py`
>
> **Round 5 (10 corrections)** :
> - H1: `registry = None` pré-initialisation → prévient `NameError` si AgentRegistry échoue
> - M1: `ValidationError` import inline → top-level dans `router.py`
> - M2: `oauth_scopes=None` ne clearait pas `requested_scopes` dans `service.py`
> - M3: `KeyError` nu sur `tokens["access_token"]` → guard explicite dans `oauth_flow.py`
> - M4: Import `user_mcp_router` eager → lazy dans `routes.py` (behind feature flag)
> - L1: Clé tool name incohérente dans `router.py` test_connection
> - L2: Constantes OAuth redirect centralisées dans `core/constants.py`
> - L4: Entrée `"mcp"` manquante dans `type_domain_mapping.py`
> - L5: Return type `-> object` → `-> ToolManifest` dans `user_context.py`
> - L6: `import json` inline → top-level dans `test_user_tool_adapter.py`
>
> **Résultat** : 333/333 tests passent, 0 régressions.
>
> **Documentation** : MCP_INTEGRATION.md exhaustivement mis à jour (F2.4, OAuth Advanced Patterns, Constants Reference), ARCHITECTURE.md mis à jour (domaines + infrastructure MCP).

### Feature 2.5 — Admin MCP Per-Server Routing & User Toggle ✅ TERMINÉ

> **Objectif** : Les serveurs MCP admin (configurés via `.env`) obtiennent chacun un agent dédié avec domain routing ciblé, remplaçant l'agent `mcp_agent` générique. Les utilisateurs peuvent activer/désactiver individuellement chaque serveur admin MCP.
>
> **Statut** : TERMINÉ (2026-03-04)
>
> **Implémentation** :
> - Per-server agents : chaque serveur admin MCP crée un agent `mcp_{slug}_agent` (ex: `mcp_google_flights_agent`)
> - Module-level store `_admin_mcp_domains` pour le domain routing au startup
> - `auto_generate_server_description()` : helper partagé admin + user MCP pour la description de domaine
> - `collect_all_mcp_domains()` : injection unifiée DRY des domains MCP (admin + user) dans le query analyzer
> - Colonne JSONB `admin_mcp_disabled_servers` sur User + ContextVar `admin_mcp_disabled_ctx`
> - API `GET /mcp/admin-servers` + `PATCH /mcp/admin-servers/{key}/toggle`
> - Champs `description` et `internal` sur `MCPServerConfig` (skip SSRF pour services Docker internes)
> - `strip_hallucinated_mcp_suffix()` : helper module-level partagé pour le suffix stripping dans 4 chemins d'exécution
> - Frontend : composant `AdminMCPServersSettings` avec toggle par serveur, hook `useAdminMCPServers`
> - i18n : 10 clés `settings.admin_mcp.*` dans 6 langues
> - Docker Compose : service `google-flights` (streamable-http) avec healthcheck socket
>
> **Fichiers modifiés** : 34 (backend 17 + frontend 9 + infra 2 + docs 3 + config 3)
>
> **Prérequis** : Feature 2.4 (Structured Items Parsing) terminée ✅

### Feature 2.6 — MCP Apps (Interactive HTML Widgets) ✅ TERMINÉ

> **Objectif** : Permettre aux outils MCP exposant des métadonnées UI (`Tool.meta.ui.resourceUri` + `visibility`) de rendre des widgets HTML interactifs dans des iframes sandboxées, avec un bridge JSON-RPC 2.0 bidirectionnel pour les appels d'outils et la lecture de ressources depuis l'iframe.
>
> **Statut** : TERMINÉ (2026-03-04)
>
> **Implémentation** :
> - Extraction des métadonnées UI (`resourceUri`, `visibility`) lors de la découverte des outils (`list_tools()`)
> - Après `call_tool()`, fetch HTML via `read_resource(resourceUri)` → `RegistryItemType.MCP_APP`
> - Graceful degradation : si `read_resource()` échoue → fallback vers card `MCP_RESULT` standard (F2.3)
> - Frontend `McpAppWidget` : iframe sandboxée (`sandbox="allow-scripts allow-forms"` sans `allow-same-origin`)
> - Bridge JSON-RPC 2.0 via `postMessage` : méthodes `tools/call`, `resources/read`, `ui/open`, `ui/initialize`
> - Proxy endpoints : User MCP (`/mcp/servers/{id}/app/...`) et Admin MCP (`/mcp/admin-servers/{key}/app/...`)
> - Sécurité : validation d'origine, whitelist URLs pour `ui/open`, pas d'accès direct iframe → MCP
> - Visibilité : `app_visibility == ["app"]` → outils iframe-only, exclus du catalogue LLM
> - i18n : labels MCP Apps dans 6 langues
>
> **Référence** : SEP-1865 (MCP Apps specification)
>
> **Documentation** : `docs/technical/MCP_INTEGRATION.md` section "MCP Apps — Interactive HTML Widgets (Feature 2.6)"
>
> **Prérequis** : Feature 2.5 (Admin MCP Per-Server Routing & User Toggle) terminée ✅

### Feature 2.7 — Excalidraw Iterative Builder ✅ TERMINÉ

> **Objectif** : Construction itérative de diagrammes Excalidraw via un appel LLM unique (tous les éléments) avec correction de position automatique.
>
> **Statut** : TERMINÉ (2026-03-07)
>
> **Implémentation** :
> - `infrastructure/mcp/excalidraw/iterative_builder.py` : `build_from_intent()` — intercepte l'intent JSON structuré du planner, effectue un appel LLM unique pour générer tous les éléments via les settings `MCP_EXCALIDRAW_LLM_*`
> - `infrastructure/mcp/excalidraw/position_corrector.py` : `correct_positions()` — corrige le centrage du texte et résout les overlaps sur les éléments bruts (fallback ou post-processing)
> - `infrastructure/mcp/excalidraw/overrides.py` : `EXCALIDRAW_SPATIAL_SUFFIX` — instructions intent JSON ajoutées à la description de l'outil `create_view` dans le catalogue
> - Interception dans `tool_adapter.py` : `_prepare_excalidraw()` détecte les appels `create_view` et route vers le mode intent (préféré) ou le fallback éléments bruts
> - Filtrage `top_p` pour Anthropic dans `adapter.py` (Claude 4.5+ rejette `temperature` + `top_p` ensemble)
>
> **Référence** : `docs/technical/MCP_INTEGRATION.md#excalidraw-iterative-builder`
>
> **Prérequis** : Feature 2 (MCP Admin) terminée ✅

---

## 6. Feature 3 — Multi-Channel Telegram

### Objectif

Permettre aux utilisateurs d'interagir avec LIA via Telegram, en plus de l'interface web, avec synchronisation bidirectionnelle des conversations et support des notifications push.

### Analyse du gap

LIA est exclusivement web. Les notifications passent par FCM (Firebase Cloud Messaging) pour le push web et par SSE pour le temps réel. Aucun canal alternatif n'existe.

### Inspiration evolution

**Fichiers sources** :
- `/tmp/evolution/evolution/channels/telegram.py` — TelegramChannel complet
- `/tmp/evolution/evolution/channels/base.py` — BaseChannel ABC
- `/tmp/evolution/evolution/channels/manager.py` — ChannelManager

evolution utilise `python-telegram-bot` avec long polling, typing indicators, media groups, voice transcription (Groq), message splitting (4000 chars), Markdown→HTML conversion.

### Use Cases

1. **Chat mobile** — L'utilisateur écrit à LIA sur Telegram, reçoit la réponse
2. **Notifications proactives** — Rappels, intérêts, alertes envoyés sur Telegram
3. **Voice sur Telegram** — L'utilisateur envoie un vocal, LIA transcrit et répond
4. **Partage de fichiers** — Envoi de documents/photos via Telegram pour analyse
5. **HITL mobile** — Approbation de plans via boutons inline Telegram

### Considérations multi-tenant (CRITIQUE)

| Défi | Solution |
|------|---------|
| Mapping user Telegram → user LIA | Table `user_channel_bindings` avec vérification par code OTP |
| Sécurité du bot | Webhook avec secret token, pas de long polling en prod |
| Rate limiting Telegram | 30 msg/sec global bot, queue par user |
| Conversations multiples | Chaque message Telegram crée/reprend une conversation LIA |
| Anti-spam | Un user LIA ne peut lier qu'un seul compte Telegram |
| Données sensibles | Pas de données confidentielles dans les messages Telegram (résumés uniquement) |

### Architecture proposée

```
Telegram Bot API
      │ (webhook)
      ▼
┌─────────────────────────┐
│  TelegramWebhookRouter  │  (FastAPI endpoint)
│  /api/v1/channels/      │
│  telegram/webhook        │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  ChannelDispatcher       │  (route message → bon user)
│  - lookup binding        │
│  - auth check            │
│  - rate limit            │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  AgentService            │  (pipeline existant)
│  .stream_chat_response() │
└───────────┬─────────────┘
            ▼
┌─────────────────────────┐
│  TelegramSender          │  (formatage + envoi)
│  - Markdown→HTML         │
│  - Message splitting     │
│  - Typing indicator      │
└─────────────────────────┘
```

### Fichiers à créer

| Fichier | Description |
|---------|------------|
| `apps/api/src/domains/channels/__init__.py` | Nouveau domaine |
| `apps/api/src/domains/channels/models.py` | UserChannelBinding (DB) |
| `apps/api/src/domains/channels/schemas.py` | Schemas Pydantic |
| `apps/api/src/domains/channels/repository.py` | CRUD bindings |
| `apps/api/src/domains/channels/service.py` | ChannelService |
| `apps/api/src/domains/channels/router.py` | Endpoints (link/unlink, webhook) |
| `apps/api/src/domains/channels/telegram/__init__.py` | Sous-package Telegram |
| `apps/api/src/domains/channels/telegram/handler.py` | Message handler |
| `apps/api/src/domains/channels/telegram/sender.py` | Response formatter + sender |
| `apps/api/src/domains/channels/telegram/formatter.py` | Markdown→HTML, message splitting |
| `apps/api/alembic/versions/YYYY_MM_DD-create_channel_bindings.py` | Migration |
| `apps/web/src/components/settings/TelegramSettings.tsx` | UI de liaison |
| `apps/web/src/hooks/useTelegramBinding.ts` | Hook API |
| `docs/technical/TELEGRAM_INTEGRATION.md` | Documentation |

### Fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| `apps/api/src/domains/auth/models.py` | Relation User → channel_bindings |
| `apps/api/src/api/v1/routes.py` | Enregistrer channel router |
| `apps/api/alembic/env.py` | Import model |
| `apps/api/src/domains/notifications/service.py` | Dispatch multi-canal |
| `apps/api/src/core/constants.py` | Constantes Telegram |
| `apps/api/src/core/config/` | TelegramSettings ou ChannelSettings |
| `apps/api/src/main.py` | Init bot Telegram dans lifespan |
| `apps/api/requirements.txt` | `python-telegram-bot>=21.0` |
| `apps/web/src/app/[lng]/dashboard/settings/page.tsx` | Section Telegram |
| `apps/web/locales/*/translation.json` | Clés i18n Telegram |
| `.env.example` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` |

### Dépendances Python à ajouter

```
python-telegram-bot>=21.0    # Telegram Bot API (async, webhooks)
```

### Checklist d'implémentation

- [x] Créer domaine `channels` (models, schemas, repository, service, router)
- [x] Migration Alembic pour `user_channel_bindings`
- [x] Créer sous-package `telegram` (handler, sender, formatter)
- [x] Webhook endpoint avec signature verification
- [x] Système OTP pour liaison compte
- [x] Intégration avec `AgentService.stream_chat_response()`
- [x] Dispatch notifications multi-canal dans `NotificationDispatcher`
- [x] Frontend : composant ChannelSettings + hook useChannelBindings
- [x] Config (.env, Settings — `ChannelsSettings`)
- [x] Tests unitaires (144 tests : handler, formatter, service, models, schemas, message_router, webhook, hitl_keyboard, voice, notifications)
- [x] i18n (6 langues — fr, en, es, de, it, zh)
- [x] Documentation technique (`docs/technical/CHANNELS_INTEGRATION.md`)
- [ ] `task pre-commit` passe
- [x] Mettre à jour ce roadmap (statut → TERMINÉ)

### Réalisation

- **Backend** : ~3500 lignes (domaine + infrastructure + bot lifecycle)
- **Frontend** : ~350 lignes (ChannelSettings.tsx + useChannelBindings.ts)
- **Tests** : ~2200 lignes (144 tests unitaires)
- **Sessions** : 5 sessions (fondations, infrastructure Telegram, pipeline messages, HITL+voice+notifs, frontend+docs)
- **Date** : 2026-03-03

---

## 7. Feature 4 — Background Task Spawning

### Objectif

Permettre à LIA de lancer des tâches de fond longues (recherches approfondies, analyses multi-sources) qui s'exécutent en parallèle de la conversation, avec notification du résultat au terme.

### Analyse du gap

Actuellement, toute interaction LIA est synchrone : l'utilisateur attend la réponse complète. Pour des tâches comme "fais une analyse complète de marché sur X", le streaming bloque la conversation pendant plusieurs minutes.

### Approche retenue (PAS le pattern evolution)

evolution utilise `SubagentManager` avec `asyncio.create_task` et un `ToolRegistry` réduit. Cette approche est mono-utilisateur et ne gère pas l'isolation.

**Notre approche** : réutiliser le pipeline existant (`AgentService.stream_chat_response()`) via une `asyncio.Task`, avec les résultats stockés en DB et envoyés par notification (SSE + FCM + Telegram si Feature 3 implémentée).

### Architecture proposée

```
User: "Lance une recherche approfondie sur X"
      │
      ▼
┌────────────────────────┐
│  launch_background_task │  (LangChain @tool)
│  - Validates prompt     │
│  - Checks user limits   │
│  - Creates DB record    │
│  - Spawns asyncio.Task  │
└──────────┬─────────────┘
           ▼
┌────────────────────────┐
│  BackgroundTaskRunner   │  (async, fire-and-forget)
│  - Uses AgentService    │
│  - Collects response    │
│  - Updates DB record    │
│  - Sends notification   │
└────────────────────────┘
```

### Fichiers à créer

| Fichier | Description |
|---------|------------|
| `apps/api/src/domains/background_tasks/__init__.py` | Nouveau domaine |
| `apps/api/src/domains/background_tasks/models.py` | BackgroundTask (DB) |
| `apps/api/src/domains/background_tasks/schemas.py` | Schemas |
| `apps/api/src/domains/background_tasks/repository.py` | CRUD |
| `apps/api/src/domains/background_tasks/service.py` | Business logic + runner |
| `apps/api/src/domains/background_tasks/router.py` | Endpoints (list, get, cancel) |
| `apps/api/src/domains/agents/tools/background_task_tools.py` | Tool `launch_background_task` |
| `apps/api/alembic/versions/YYYY_MM_DD-create_background_tasks.py` | Migration |
| `apps/api/tests/unit/domains/background_tasks/` | Tests |

### Fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| `apps/api/src/domains/auth/models.py` | Relation User → background_tasks |
| `apps/api/src/api/v1/routes.py` | Enregistrer router |
| `apps/api/alembic/env.py` | Import model |
| `apps/api/src/domains/agents/constants.py` | Constantes agent |
| `apps/api/src/core/constants.py` | Limites (max tasks par user, timeout) |
| `apps/api/src/domains/agents/tools/tool_registry.py` | Enregistrer tool |
| `apps/api/src/domains/agents/registry/catalogue_loader.py` | Manifest |
| `apps/api/src/main.py` | Cleanup des tasks orphelines au shutdown |
| `apps/web/locales/*/translation.json` | Clés i18n |

### Checklist d'implémentation

- [ ] Créer domaine `background_tasks` complet
- [ ] Migration Alembic
- [ ] Créer tool `launch_background_task` avec manifests
- [ ] BackgroundTaskRunner avec timeout et cleanup
- [ ] Notification du résultat (SSE + FCM)
- [ ] Endpoints REST (list, get result, cancel)
- [ ] Frontend : affichage des tâches en cours (optionnel dans un premier temps)
- [ ] Limites par user (max 3 simultanées)
- [ ] Tests unitaires
- [ ] i18n (6 langues)
- [ ] `task pre-commit` passe
- [ ] Mettre à jour ce roadmap

### Estimation

- **Backend** : ~1000-1200 lignes
- **Tests** : ~400 lignes
- **Effort total** : 2-3 sessions

---

## 8. Feature 5 — Heartbeat Autonome LLM

### Objectif

Permettre à LIA de prendre l'initiative de contacter l'utilisateur avec des informations pertinentes (événements proches, météo, actualités d'intérêt) sans attendre de requête.

### Analyse du gap

LIA a déjà :
- **Centres d'intérêt** (`domains/interests/`) : notifications proactives sur les sujets suivis, via Brave/Perplexity, déclenchées par APScheduler
- **Rappels** (`domains/reminders/`) : notifications programmées par l'utilisateur
- **ScheduledActions** (`domains/scheduled_actions/`) : prompts programmés avec exécution LIA

**Ce qui manque** : une proactivité **intelligente** où le LLM décide lui-même s'il y a quelque chose d'intéressant à dire, en agrégeant multiple sources de contexte.

### Inspiration evolution

**Fichier source** : `/tmp/evolution/evolution/heartbeat/service.py`

Approche 2 phases :
1. **Phase 1 (Décision)** : LLM reçoit le contexte (heure, jour, dernières interactions, mémoire) et décide via un virtual tool call : `skip` (rien à dire) ou `run` (message à envoyer)
2. **Phase 2 (Exécution)** : Si `run`, lance un agent complet avec le prompt généré par Phase 1

### Architecture proposée

```
APScheduler (interval configurable, ex: 30 min)
      │
      ▼ (pour chaque user opt-in)
┌────────────────────────────┐
│  HeartbeatService           │
│  Phase 1: Agrégation        │
│  - Calendrier (prochains    │
│    événements)              │
│  - Météo (si configuré)     │
│  - Intérêts (nouveautés)    │
│  - Dernière interaction     │
│  - Heure locale user        │
└──────────┬─────────────────┘
           ▼
┌────────────────────────────┐
│  Phase 2: Décision LLM      │
│  Structured output:          │
│  { action: "skip"|"notify",  │
│    reason: "...",             │
│    message: "...",            │
│    priority: "low"|"medium"  │
│    |"high" }                 │
└──────────┬─────────────────┘
           ▼ (si "notify")
┌────────────────────────────┐
│  Phase 3: Dispatch           │
│  - SSE push                  │
│  - FCM notification          │
│  - Telegram (si Feature 3)   │
└────────────────────────────┘
```

### Fichiers créés

| Fichier | Description |
|---------|------------|
| `apps/api/src/domains/heartbeat/__init__.py` | Package |
| `apps/api/src/domains/heartbeat/models.py` | `HeartbeatNotification` (audit trail) |
| `apps/api/src/domains/heartbeat/schemas.py` | Decision, Context, Target, Settings, History schemas |
| `apps/api/src/domains/heartbeat/repository.py` | Repository CRUD + queries |
| `apps/api/src/domains/heartbeat/router.py` | GET/PATCH settings, GET history, PATCH feedback |
| `apps/api/src/domains/heartbeat/context_aggregator.py` | Agrégation multi-source parallèle |
| `apps/api/src/domains/heartbeat/prompts.py` | Prompts LLM (decision + message) |
| `apps/api/src/domains/heartbeat/proactive_task.py` | `HeartbeatProactiveTask` (Protocol impl) |
| `apps/api/src/infrastructure/scheduler/heartbeat_notification.py` | Job APScheduler |
| `apps/api/src/domains/agents/prompts/v1/heartbeat_decision_prompt.txt` | Prompt décision LLM |
| `apps/api/src/domains/agents/prompts/v1/heartbeat_message_prompt.txt` | Prompt génération message |
| `apps/web/src/components/settings/HeartbeatSettings.tsx` | Composant settings UI |
| `apps/web/src/hooks/useHeartbeatSettings.ts` | Hook API |
| `apps/api/tests/unit/domains/heartbeat/` | Tests unitaires (schemas, aggregator, task, eligibility) |
| `docs/technical/HEARTBEAT_AUTONOME.md` | Documentation technique |

### Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `apps/api/src/domains/auth/models.py` | +3 champs : `heartbeat_enabled`, `heartbeat_max_per_day`, `heartbeat_push_enabled` |
| `apps/api/src/core/constants.py` | Constantes heartbeat + cross-type cooldown |
| `apps/api/src/core/config/agents.py` | Settings heartbeat (interval, cooldowns, LLM, weather thresholds) |
| `apps/api/src/infrastructure/proactive/base.py` | `ContentSource.HEARTBEAT` |
| `apps/api/src/infrastructure/proactive/eligibility.py` | Cross-type cooldown (`_check_cross_type_cooldown`) |
| `apps/api/src/infrastructure/proactive/notification.py` | Titre localisé + `push_enabled` param |
| `apps/api/src/infrastructure/proactive/runner.py` | Extraction settings heartbeat + `push_enabled` dispatch |
| `apps/api/src/infrastructure/scheduler/interest_notification.py` | Cross-type wiring (`HeartbeatNotification`) |
| `apps/api/src/main.py` | Job APScheduler heartbeat (conditionnel) |
| `apps/api/src/api/v1/routes.py` | Router registration (conditionnel) |
| `apps/web/locales/*/translation.json` | Clés i18n `heartbeat.*` (6 langues) |
| `apps/web/src/app/[lng]/dashboard/settings/page.tsx` | Intégration HeartbeatSettings |

### Checklist d'implémentation

- [x] Définir settings et constantes heartbeat
- [x] Créer `HeartbeatProactiveTask` (Protocol, 2 phases : decide → generate)
- [x] Créer `ContextAggregator` (calendrier, météo + changements, intérêts, mémoires, activité)
- [x] Prompts LLM avec structured output (`HeartbeatDecision`)
- [x] Migration pour champs user et table `heartbeat_notifications`
- [x] Job APScheduler dans `main.py` (conditionnel sur feature flag)
- [x] Dispatch multi-canal (SSE + FCM + Telegram, avec contrôle push utilisateur)
- [x] Frontend : settings avec toggle, max/jour, push control, indicateurs sources
- [x] Plages horaires dédiées (heartbeat_notify_start_hour / heartbeat_notify_end_hour)
- [x] Rate limiting : global cooldown + cross-type cooldown + daily quota
- [x] Tests unitaires (schemas, aggregator, task, eligibility)
- [x] i18n (6 langues, 17 clés)
- [x] Documentation technique (HEARTBEAT_AUTONOME.md)
- [x] `task pre-commit` passe
- [x] Roadmap mis à jour

### Estimation

- **Backend** : ~600-800 lignes
- **Frontend** : ~100 lignes (toggle)
- **Tests** : ~300 lignes
- **Effort total** : 2 sessions

---

## 9. Feature 6 — Code Sandbox Tool

### Objectif

Permettre à LIA de générer et exécuter du code Python dans un environnement sandboxé pour répondre à des besoins computationnels (calculs, transformations de données, graphiques, scripts utilitaires).

### Analyse du gap

LIA ne peut pas exécuter de code. Si l'utilisateur demande "calcule la moyenne de ces chiffres" ou "génère un graphique", LIA ne peut que décrire la marche à suivre.

### Prérequis infrastructure

**Docker DOIT être disponible** sur le serveur de déploiement. Actuellement :
- Dev : Docker Desktop (docker-compose)
- Prod : Docker sur Raspberry Pi 5

L'exécution de code utilisateur SANS conteneurisation est **inacceptable** en multi-tenant.

### Inspiration evolution (avec adaptations MAJEURES)

evolution utilise `ExecTool` avec :
- Deny patterns (rm -rf, shutdown, fork bombs)
- Allow patterns (whiteliste)
- Workspace restriction
- Timeout 60s

**Insuffisant pour nous** : deny patterns sont contournables, pas d'isolation process/filesystem/network.

### Sécurité (CRITIQUE)

| Couche | Mesure |
|--------|--------|
| **Container** | Docker éphémère, détruit après chaque exécution |
| **Réseau** | `--network=none` (aucun accès réseau) |
| **Mémoire** | `--memory=128m` (128 MB max) |
| **CPU** | `--cpus=0.5` (50% d'un core) |
| **Temps** | Timeout 10s (kill -9 après) |
| **Filesystem** | Read-only root, tmpfs pour /tmp (16MB) |
| **User** | `--user=nobody` (non-root) |
| **Capabilities** | `--cap-drop=ALL` |
| **Librairies** | Image Docker pré-construite avec whitelist (numpy, pandas, matplotlib, etc.) |
| **Taille sortie** | Troncature stdout/stderr à 10KB |
| **Rate limiting** | 5 exécutions/heure par user |

### Architecture proposée

```
execute_code_tool (LangChain @tool)
    │
    ├── Validate code (basic syntax check)
    ├── Check user rate limit
    │
    ▼
┌──────────────────────────┐
│  CodeSandboxService       │
│  - Build docker run cmd   │
│  - Execute with timeout   │
│  - Capture stdout/stderr  │
│  - Cleanup container      │
└──────────────────────────┘
    │
    ▼
UnifiedToolOutput
  - stdout (truncated)
  - stderr (if error)
  - execution_time_ms
  - exit_code
```

### Image Docker sandbox

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir numpy pandas matplotlib seaborn scipy sympy
# No network, no root, no capabilities
USER nobody
WORKDIR /sandbox
ENTRYPOINT ["python", "-c"]
```

### Fichiers à créer

| Fichier | Description |
|---------|------------|
| `apps/api/src/infrastructure/sandbox/__init__.py` | Package |
| `apps/api/src/infrastructure/sandbox/service.py` | CodeSandboxService |
| `apps/api/src/infrastructure/sandbox/docker_runner.py` | Docker container execution |
| `apps/api/src/infrastructure/sandbox/validators.py` | Code validation basique |
| `apps/api/src/domains/agents/tools/code_sandbox_tools.py` | Tool LangChain |
| `apps/api/src/domains/agents/code_sandbox/catalogue_manifests.py` | Manifests |
| `docker/sandbox/Dockerfile` | Image sandbox |
| `docker/sandbox/requirements.txt` | Librairies whitelistées |
| `apps/api/tests/unit/infrastructure/sandbox/test_service.py` | Tests (mocks Docker) |

### Fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| Mêmes patterns que les features précédentes (constants, registry, catalogue_loader, i18n, etc.) |

### Checklist d'implémentation

- [ ] Créer Dockerfile sandbox + build image
- [ ] Créer `CodeSandboxService` avec exécution Docker
- [ ] Créer `docker_runner.py` (subprocess avec timeout)
- [ ] Créer tool `execute_code_tool` avec manifests
- [ ] Validation basique du code (pas de import os/subprocess/socket)
- [ ] Rate limiting strict (5/heure/user)
- [ ] Gestion des fichiers output (graphiques matplotlib → base64)
- [ ] Enregistrement tool + manifests
- [ ] Tests unitaires (mocks Docker)
- [ ] i18n (6 langues)
- [ ] Documentation
- [ ] `task pre-commit` passe
- [ ] Test d'intégration avec Docker réel
- [ ] Mettre à jour ce roadmap

### Estimation

- **Backend** : ~800-1000 lignes
- **Docker** : ~50 lignes (Dockerfile + config)
- **Tests** : ~400 lignes
- **Effort total** : 3-4 sessions

---

## 10. Hypothèses Retirées

### 10.1 Conversation Summarization / Compaction — FAUX POSITIF

**Raison** : LIA dispose déjà d'un système à 5 couches :

1. **Message Windowing** (`agents/utils/message_windowing.py`) — Par noeud : Router 4 turns, Planner 4, Response 10, Orchestrator 4
2. **Agent History Filter** (`agents/middleware/message_history.py`) — 30 messages max, priorité ToolMessage
3. **SummarizationMiddleware** (`infrastructure/llm/middleware_config.py`) — LangChain, trigger à 70% contexte, utilise gpt-4.1-nano, garde 10 messages verbatim
4. **Text Compaction** (`agents/orchestration/text_compaction.py`) — Compaction post-Jinja2, 97% de réduction
5. **DB Message Limit** — 50 messages max par conversation en DB

### 10.2 Progress Streaming Amélioré — PARTIELLEMENT FAUX

**Raison** : Le système SSE existant est déjà très riche :
- 55+ types de chunks (`ChatStreamChunk`)
- `execution_step` events avec emoji + `i18n_key` par tool/node
- Side-channel Registry pour les données structurées
- Messages éphémères remplacés par le premier token

**Améliorations marginales possibles** : pourcentage de progression, ETA estimé. Mais le ROI est faible.

### 10.3 Shell/Exec Tool Brut — DANGEREUX

**Raison** : En multi-tenant, un shell non sandboxé donne accès à :
- Filesystem du serveur (toutes les données de tous les users)
- Réseau interne (autres services, DB, Redis)
- Process d'autres users

→ Remplacé par **Code Sandbox Tool** (Feature 6) avec isolation Docker.

### 10.4 FileSystem Tools (Read/Write/Edit/ListDir) — NON PERTINENT

**Raison** : LIA est une app web. Les utilisateurs n'ont pas de filesystem local accessible. Les fichiers sont sur Google Drive (déjà couvert par `drive_tools`).

### 10.5 Skills/Plugin System — SUPPLANTÉ PAR MCP

**Raison** : Le système de Skills de evolution (fichiers SKILL.md) est un mécanisme de plugins propriétaire. MCP (Feature 2) est le standard ouvert qui accomplit la même chose en mieux, avec un écosystème existant de serveurs.

### 10.6 Cron Tool — DÉJÀ COUVERT

**Raison** : `ScheduledActions` (domaine existant) est déjà supérieur au CronTool de evolution :
- UI dédiée (ScheduledActionsSettings.tsx)
- Persistence PostgreSQL (vs JSON file)
- Exécution via AgentService complet (vs simple prompt)
- HITL, rate limiting, observabilité

---

## 11. Patterns de Référence

### 11.1 Pattern Tool @tool (pour Features 1, 4, 6)

**Template de référence** : `apps/api/src/domains/agents/tools/reminder_tools.py`

```python
"""Module docstring."""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool

from src.core.constants import TOOL_CATEGORY_READ, WINDOW_SECONDS
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


@tool
@track_tool_metrics(
    tool_name="my_tool_name",
    agent_name="my_agent",
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
    log_execution=True,
    log_errors=True,
)
@rate_limit(max_calls=TOOL_CATEGORY_READ, window_seconds=WINDOW_SECONDS, scope="user")
async def my_tool(
    param1: Annotated[str, "Description for LLM"],
    param2: Annotated[int, "Description for LLM"] = 10,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Tool description for LLM (concise, action-oriented)."""
    config = validate_runtime_config(runtime, "my_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        user_id = parse_user_id(config.user_id)
        # ... business logic ...
        return UnifiedToolOutput.data_success(
            message="Summary for LLM",
            structured_data={"key": "value"},
        )
    except Exception as e:
        logger.error("my_tool_error", error=str(e), exc_info=True)
        return UnifiedToolOutput.failure(
            message=str(e),
            error_code="EXTERNAL_API_ERROR",
        )

# Export list
MY_TOOLS = [my_tool]
```

### 11.2 Pattern ToolManifest

**Template de référence** : `apps/api/src/domains/agents/brave/catalogue_manifests.py`

```python
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

my_tool_manifest = ToolManifest(
    name="my_tool",
    agent="my_agent",
    description="What this tool does (for catalogue filtering)",
    parameters=[
        ParameterSchema(name="param1", type="string", required=True, description="..."),
        ParameterSchema(name="param2", type="integer", required=False, description="..."),
    ],
    outputs=[
        OutputFieldSchema(path="result", type="string", description="..."),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=500, est_cost_usd=0.001, est_latency_ms=2000),
    permissions=PermissionProfile(required_scopes=[], data_classification="PUBLIC", hitl_required=False),
    semantic_keywords=[
        "keyword 1 in English",
        "keyword 2 in English",
    ],
    display=DisplayMetadata(
        emoji="🔗",
        i18n_key="my_tool",
        visible=True,
        category="tool",
    ),
    version="1.0.0",
    maintainer="Team AI",
)
```

### 11.3 Pattern Enregistrement Tool + Manifest

**1. Tool Registry** (`apps/api/src/domains/agents/tools/tool_registry.py`, line ~309) :
```python
# Ajouter dans tool_modules list :
("src.domains.agents.tools.web_fetch_tools", "web_fetch_tools"),
```

**2. Catalogue Loader** (`apps/api/src/domains/agents/registry/catalogue_loader.py`) :
```python
# AgentManifest défini directement dans catalogue_loader.py (comme les autres agents) :
WEB_FETCH_AGENT_MANIFEST = AgentManifest(
    name="web_fetch_agent",
    description="...",
    tools=["fetch_web_page_tool"],
    ...
)
registry.register_agent_manifest(WEB_FETCH_AGENT_MANIFEST)

# ToolManifest importé depuis le fichier dédié :
from src.domains.agents.web_fetch.catalogue_manifests import (
    fetch_web_page_catalogue_manifest,
)
registry.register_tool_manifest(fetch_web_page_catalogue_manifest)
```

**3. Constants** (`apps/api/src/domains/agents/constants.py`) :
```python
# Agent
AGENT_WEB_FETCH = "web_fetch_agent"
NODE_WEB_FETCH_AGENT = "web_fetch_agent"

# Context domain
CONTEXT_DOMAIN_WEB_FETCH = "web_fetchs"  # Convention: domain + "s"

# Ajouter à ALL_AGENTS list
ALL_AGENTS = [..., AGENT_WEB_FETCH]
```

### 11.4 Pattern Domaine CRUD (pour Features 3, 4)

**Template de référence** : `apps/api/src/domains/scheduled_actions/`

Voir les fichiers complets dans ce domaine pour les patterns de :
- `models.py` : BaseModel, ForeignKey user, __tablename__, __table_args__
- `schemas.py` : Create (required fields), Update (optional fields), Response (from_attributes=True)
- `repository.py` : BaseRepository[Model], get_all_for_user, count_for_user
- `service.py` : __init__(db), ownership check, limits check, partial update
- `router.py` : APIRouter(prefix, tags), Depends(get_current_active_session), commit in router

### 11.5 Pattern i18n Frontend

**6 fichiers** : `apps/web/locales/{en,fr,es,de,it,zh}/translation.json`

Ajouter les clés sous un namespace cohérent :
```json
{
  "web_fetch": {
    "execution_step": "Fetching web page",
    "tool_description": "Read a web page"
  }
}
```

### 11.6 Pattern APScheduler Job (pour Feature 5)

**Template** : `apps/api/src/main.py` (lignes 408-418)

```python
from src.core.constants import SCHEDULER_JOB_MY_FEATURE

scheduler.add_job(
    my_async_function,
    trigger="interval",
    seconds=MY_INTERVAL_SECONDS,
    id=SCHEDULER_JOB_MY_FEATURE,
    name="Description of my job",
    replace_existing=True,
    max_instances=1,
    misfire_grace_time=30,
)
```

Avec distributed lock :
```python
from src.infrastructure.locks.scheduler_lock import SchedulerLock

async def my_async_function():
    redis = await get_redis_cache()
    async with SchedulerLock(redis, SCHEDULER_JOB_MY_FEATURE) as lock:
        if not lock.acquired:
            return  # Another worker is executing, skip silently
        # ... job logic ...
        # NOTE: Lock is NOT released in __aexit__. It expires via TTL (default 5min).
        # This prevents other workers from re-executing the same job within the interval.
```

### 11.7 Pattern Config Settings

**Créer un nouveau module** : `apps/api/src/core/config/my_feature.py`

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class MyFeatureSettings(BaseSettings):
    my_feature_enabled: bool = Field(default=False, description="...")
    my_feature_timeout: int = Field(default=30, description="...")

    model_config = {"env_prefix": ""}  # Variables .env directes
```

**Ajouter à la chaîne** : `apps/api/src/core/config/__init__.py`
```python
class Settings(
    ...,
    MyFeatureSettings,  # Ajouter ici
    BaseSettings,       # Toujours en dernier
):
```

---

## 12. Journal des Décisions

> Chaque décision prise pendant l'implémentation doit être consignée ici.

| Date | Feature | Décision | Justification |
|------|---------|----------|---------------|
| 2026-02-28 | Global | Ordre de priorité P0→P3 | Web Fetch est le quick win, MCP l'extensibilité, Telegram la reach |
| 2026-02-28 | F1 | `readability-lxml` + `markdownify` | Même stack que evolution, prouvé et léger |
| 2026-02-28 | F2 | MCP via `mcp` SDK officiel | Standard Anthropic, SDK maintenu |
| 2026-02-28 | F3 | Webhook (pas long polling) en prod | Performance + scalabilité multi-worker |
| 2026-02-28 | F4 | asyncio.Task (pas celery/dramatiq) | Cohérent avec l'archi async existante, pas de broker supplémentaire |
| 2026-02-28 | F5 | Plages horaires dédiées heartbeat (initialement partagées avec intérêts, séparées pour UX) | Chaque feature a sa propre plage de notification indépendante |
| 2026-02-28 | F6 | Docker obligatoire (pas de process direct) | Sécurité multi-tenant non négociable |
| 2026-02-28 | Global | Retrait de 6 faux positifs | Vérification code existant vs hypothèses initiales |
| 2026-02-28 | F2 | BaseTool subclass (pas @connector_tool) | Tools MCP dynamiques découverts au runtime, décorateurs incompatibles |
| 2026-02-28 | F2 | Agent virtuel unique "mcp_agent" | Extraction de domaine correcte via _extract_domain_from_agent_name() |
| 2026-02-28 | F2 | Dual registry (AgentRegistry + tool_registry) | Catalogue filtrage + parallel_executor invocation |
| 2026-02-28 | F2 | SSRF constants copiées (pas importées) | Évite dépendance infrastructure → domain |
| 2026-02-28 | F2 | Rate limiting in-memory avec asyncio.Lock | Protection TOCTOU sous charge concurrente |
| 2026-02-28 | F2 | Feature 2.1 per-user MCP (v7.0+) | Autonomie utilisateurs pour configurer leurs propres serveurs MCP |
| 2026-03-01 | F2.2 | Per-server domain via embeddings E5 | Routing sémantique précis au lieu du domaine générique "mcp" |
| 2026-03-01 | F2.2 | Slug `mcp_<server_name>` comme domain | Cohérent avec `_extract_domain_from_agent_name()`, unique par serveur |
| 2026-03-01 | F2.3 | Bridge `@property coroutine` sur BaseTool | Évite `ainvoke()` qui stringifie le UnifiedToolOutput |
| 2026-03-01 | F2.3 | `meta.domain = "mcps"` (unique) | Un seul composant card pour tous les serveurs, nom serveur dans payload |
| 2026-03-01 | F2.3 | Pas d'ajout à TOOL_PATTERN_TO_DOMAIN_MAP | Collision potentielle : noms de tools MCP peuvent matcher d'autres domaines |
| 2026-03-01 | F2.x | Revue qualité 85 fichiers (5 agents) | 7 critiques + 5 hautes + 5 moyennes corrigées (DNS async, expires_at, httpx lifecycle, etc.) |
| 2026-03-02 | F2.1 | OAuth credential merge on update | `_encrypt_credentials_from_update` préserve access_token/refresh_token lors de la mise à jour client_id/client_secret |
| 2026-03-02 | F2.1 | `has_oauth_credentials` dans response schema | Frontend distingue "pas de credentials" vs "credentials OAuth sauvegardées" |
| 2026-03-02 | F2.x | FAQ MCP 6 langues (6 Q&A) | Section `mcp_servers` dans FAQContent + traductions fr/en/de/es/it/zh |
| 2026-03-02 | F2.1 | OAuth scopes configurables (champ utilisateur) | `requested_scopes` dans `oauth_metadata` JSONB — priorité sur auto-discovery |
| 2026-03-02 | F2.1 | Connexions éphémères MCP (pas de pool persistant) | Évite `CancelledError` des anyio TaskGroups long-lived du SDK MCP |
| 2026-03-02 | F2.1 | ExceptionGroup unwrapping dans `user_pool.py` | Log sub-exceptions + re-raise first pour diagnostic clair |
| 2026-03-02 | F2.x | FAQ MCP Q7 OAuth scopes (6 langues) | Guidance scopes par provider (GitHub, Slack) + troubleshooting 403 |
| 2026-03-02 | F2.1 | OAuth disconnect endpoint + UI button | `POST /oauth/disconnect` purge tokens, preserve client creds, force re-auth |
| 2026-03-04 | F2.5 | Per-server agents admin MCP (pas agent générique) | Domain routing ciblé `mcp_{slug}_agent` au lieu de `mcp_agent` unique |
| 2026-03-04 | F2.5 | `collect_all_mcp_domains()` unifié admin + user | DRY : un seul chemin d'injection pour le query analyzer |
| 2026-03-04 | F2.5 | `strip_hallucinated_mcp_suffix()` module-level | Source unique pour le suffix stripping — 4 points d'intégration |
| 2026-03-04 | F2.5 | Champ `internal` sur MCPServerConfig | Skip SSRF pour services Docker internes (HTTP + IPs privées) |
| 2026-03-04 | F2.5 | Per-user toggle via JSONB `admin_mcp_disabled_servers` | Pas de table de jointure — liste simple, N faible |
| 2026-03-04 | F2.6 | MCP Apps via `Tool.meta.ui.resourceUri` (SEP-1865) | Widgets HTML interactifs dans iframes sandboxées |
| 2026-03-04 | F2.6 | Bridge JSON-RPC 2.0 via `postMessage` | Protocole standard avec corrélation request/response via `id` |
| 2026-03-04 | F2.6 | `sandbox="allow-scripts allow-forms"` sans `allow-same-origin` | Isolation maximale — pas d'accès cookies/storage/DOM host |
| 2026-03-04 | F2.6 | Proxy endpoints pour appels iframe → MCP | Iframe n'a pas d'accès réseau direct aux serveurs MCP |
| 2026-03-04 | F2.6 | Graceful degradation `MCP_APP` → `MCP_RESULT` | Progressive enhancement — tools fonctionnent sans UI resource |
| 2026-03-04 | F2.6 | Visibility `["app"]` filtrée du catalogue LLM | Outils iframe-only invisibles pour le planner/agents |
| 2026-03-07 | F2.7 | Excalidraw Iterative Builder (`infrastructure/mcp/excalidraw/`) | Intent JSON → 1 LLM call (tous les éléments) pour diagrammes propres |
| 2026-03-07 | F2.7 | `MCP_EXCALIDRAW_LLM_*` settings dédiées | Provider/model/temperature indépendants du planner |
| 2026-03-07 | F2.7 | `EXCALIDRAW_SPATIAL_SUFFIX` dans le catalogue | Instruit le planner à générer un intent structuré |
| 2026-03-07 | F2.7 | `position_corrector.py` fallback | Re-centrage texte + résolution overlaps sur éléments bruts |
| 2026-03-07 | F2.7 | Filtrage `top_p` pour Anthropic dans `adapter.py` | Claude 4.5+ rejette `temperature` + `top_p` ensemble |

---

## Annexe A — Fichiers Clés de Référence

### Backend — Tools

| Fichier | Rôle | Lignes clés |
|---------|------|-------------|
| `agents/tools/base.py` | ConnectorTool (L84), APIKeyConnectorTool (L493) | Classes de base tools |
| `agents/tools/common.py` | ToolErrorCode (L57), ToolResponse (L97) | Types d'erreur |
| `agents/tools/output.py` | UnifiedToolOutput (L323) | Réponse unifiée |
| `agents/tools/runtime_helpers.py` | validate_runtime_config (L316), parse_user_id (L156) | Helpers runtime |
| `agents/tools/tool_registry.py` | @registered_tool (L89), _import_tool_modules (L296) | Registry |
| `agents/registry/catalogue.py` | ToolManifest (L402), AgentManifest (L532) | Manifests |
| `agents/registry/catalogue_loader.py` | Enregistrement manifests (L545-644) | Chargement |
| `agents/services/smart_catalogue_service.py` | SmartCatalogueService (L73) | Filtrage tools |

### Backend — Domain

| Fichier | Rôle |
|---------|------|
| `infrastructure/database/models.py` | BaseModel, TimestampMixin, UUIDMixin |
| `core/repository.py` | BaseRepository[ModelType] (L45) |
| `core/session_dependencies.py` | get_current_active_session (L135) |
| `core/exceptions.py` | ResourceNotFoundError (L193), ValidationError (L240) |
| `core/constants.py` | Toutes les constantes centralisées |
| `core/config/__init__.py` | Settings (composition par héritage) |
| `domains/agents/constants.py` | AGENT_*, CONTEXT_DOMAIN_*, NODE_*, INTENTION_* |

### Backend — Infrastructure

| Fichier | Rôle |
|---------|------|
| `infrastructure/cache/redis.py` | get_redis_cache(), get_redis_session() |
| `infrastructure/cache/redis_helpers.py` | cache_get_or_compute() |
| `infrastructure/locks/scheduler_lock.py` | SchedulerLock (distributed) |
| `infrastructure/observability/decorators.py` | @track_tool_metrics |
| `core/context.py` | ContextVars (panic_mode_used, etc.) |

### Frontend

| Fichier | Rôle |
|---------|------|
| `web/locales/*/translation.json` | i18n (6 langues) |
| `web/src/hooks/useScheduledActions.ts` | Hook API récent (template) |
| `web/src/components/settings/ScheduledActionsSettings.tsx` | Composant settings récent |
| `web/src/app/[lng]/dashboard/settings/page.tsx` | Page settings |

---

*Fin du document — Dernière mise à jour : 2026-03-04*
