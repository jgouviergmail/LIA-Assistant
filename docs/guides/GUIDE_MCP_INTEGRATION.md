# Guide Integration MCP - LIA

> Guide pratique pour les developpeurs travaillant avec le MCP (Model Context Protocol) dans LIA.

Version: 1.0
Date: 2026-03-08

---

## Table des Matieres

- [Introduction](#introduction)
- [Prerequis et Configuration](#prerequis-et-configuration)
- [Admin MCP](#admin-mcp)
- [Per-User MCP](#per-user-mcp)
- [Iterative Mode / ReAct (F2.7)](#iterative-mode--react-f27)
- [Convention read_me](#convention-read_me)
- [MCP Apps (F2.6)](#mcp-apps-f26)
- [Excalidraw Iterative Builder](#excalidraw-iterative-builder)
- [UserMCPToolAdapter Pattern](#usermcptooladapter-pattern)
- [Securite](#securite)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

---

## Introduction

### Qu'est-ce que MCP dans LIA ?

MCP (Model Context Protocol) permet a LIA de connecter des serveurs d'outils externes via le protocole standard Anthropic MCP. Les outils decouverts sont enregistres dans le catalogue existant et deviennent disponibles pour n'importe quel agent via le pipeline d'orchestration standard.

**Principe cle** : MCP est une couche d'infrastructure, PAS un nouvel agent. Les outils s'enregistrent dans le catalogue existant et sont utilisables via le pipeline planner/executor standard.

### Admin MCP vs Per-User MCP

| Aspect | Admin MCP (F2) | Per-User MCP (F2.1) |
|--------|---------------|---------------------|
| **Configuration** | `.env` / fichier JSON | Interface web (CRUD API) |
| **Transports** | `stdio` + `streamable_http` | `streamable_http` uniquement |
| **Connexion** | Persistante (singleton) | Ephemere (par appel) |
| **Cycle de vie** | Demarrage application | Lazy discovery au premier chat |
| **Authentification** | Variables d'env / headers | API key, Bearer, OAuth 2.1 |
| **Portee** | Globale (tous les utilisateurs) | Isolee par utilisateur |
| **Feature flag** | `MCP_ENABLED` | `MCP_ENABLED` + `MCP_USER_ENABLED` |

### Structure des modules

```
apps/api/src/infrastructure/mcp/
  __init__.py
  schemas.py              # MCPServerConfig, MCPDiscoveredTool, MCPServerStatus
  security.py             # Validation serveur, prevention SSRF, resolution HITL
  client_manager.py       # MCPClientManager (admin, connexions persistantes)
  tool_adapter.py         # MCPToolAdapter — BaseTool wrapper pour admin MCP
  user_pool.py            # UserMCPClientPool (per-user, connexions ephemeres)
  user_tool_adapter.py    # UserMCPToolAdapter — BaseTool wrapper pour per-user MCP
  user_context.py         # ContextVar pour isolation per-request des tools user
  registration.py         # Enregistrement dans le catalogue + domain_taxonomy
  oauth_flow.py           # Handler OAuth 2.1 pour per-user MCP
  utils.py                # Helpers partages (extract_app_meta, build_mcp_app_output, is_app_only)
  excalidraw/
    __init__.py
    overrides.py           # Constantes + SPATIAL_SUFFIX pour l'intent JSON
    iterative_builder.py   # Builder LLM-driven (1 appel : tous les éléments)

apps/api/src/domains/user_mcp/
  models.py               # UserMCPServer, UserMCPAuthType, UserMCPServerStatus
  schemas.py              # Schemas Pydantic v2 (CRUD + OAuth + MCP Apps proxy)
  repository.py           # Repository pattern async
  service.py              # UserMCPServerService (logique metier)
  router.py               # Endpoints per-user (/mcp/servers)
  admin_router.py         # Endpoints admin (/mcp/admin-servers)
```

---

## Prerequis et Configuration

### Feature Flags

Pour activer MCP, ajouter dans `.env` :

```bash
# Admin MCP — serveurs configures globalement
MCP_ENABLED=true

# Per-User MCP — chaque utilisateur peut declarer ses propres serveurs
# Necessite MCP_ENABLED=true en prerequis
MCP_USER_ENABLED=true
```

### Table des variables de configuration

Toutes les variables sont definies dans `MCPSettings` (`apps/api/src/core/config/mcp.py`) :

#### Feature Toggles

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_ENABLED` | `bool` | `false` | Active le support MCP admin |
| `MCP_USER_ENABLED` | `bool` | `false` | Active le MCP per-user (necessite `MCP_ENABLED`) |

#### Configuration Serveur

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_SERVERS_CONFIG` | `str` (JSON) | `"{}"` | Configuration JSON inline des serveurs admin |
| `MCP_SERVERS_CONFIG_PATH` | `str?` | `null` | Chemin vers fichier JSON (priorite sur inline) |

#### Limites d'execution

| Variable | Type | Default | Plage | Description |
|----------|------|---------|-------|-------------|
| `MCP_TOOL_TIMEOUT_SECONDS` | `int` | `30` | 5-120 | Timeout par appel d'outil |
| `MCP_MAX_SERVERS` | `int` | `10` | 1-50 | Nombre max de serveurs admin |
| `MCP_MAX_TOOLS_PER_SERVER` | `int` | `20` | 1-100 | Outils max par serveur |
| `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` | `int` | `50` | 1-200 | Items max par appel (anti-explosion registry) |

#### Securite

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_HITL_REQUIRED` | `bool` | `true` | HITL global pour tous les outils MCP |
| `MCP_RATE_LIMIT_CALLS` | `int` | `30` | Appels max par serveur par fenetre |
| `MCP_RATE_LIMIT_WINDOW` | `int` | `60` | Fenetre de rate limiting (secondes) |

#### MCP Apps

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_APP_MAX_HTML_SIZE` | `int` | `2MB` | Taille max HTML pour widgets iframes |
| `MCP_REFERENCE_CONTENT_MAX_CHARS` | `int` | `30000` | Chars max du contenu `read_me` injecte dans le planner |

#### Resilience

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_HEALTH_CHECK_INTERVAL_SECONDS` | `int` | `300` | Intervalle health checks |
| `MCP_CONNECTION_RETRY_MAX` | `int` | `3` | Tentatives de reconnexion au demarrage |

#### Per-User Pool

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_USER_MAX_SERVERS_PER_USER` | `int` | `5` | Serveurs max par utilisateur |
| `MCP_USER_POOL_TTL_SECONDS` | `int` | `3600` | TTL idle pour les entrees du pool |
| `MCP_USER_POOL_MAX_TOTAL` | `int` | `100` | Entrees max dans le pool global |
| `MCP_USER_POOL_EVICTION_INTERVAL` | `int` | `300` | Intervalle d'eviction des entrees idle |
| `MCP_USER_OAUTH_CALLBACK_BASE_URL` | `str?` | `null` | URL de base pour les callbacks OAuth 2.1 |

#### Excalidraw LLM

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_EXCALIDRAW_LLM_PROVIDER` | `str` | `anthropic` | Provider LLM pour les diagrammes |
| `MCP_EXCALIDRAW_LLM_MODEL` | `str` | `claude-opus-4-6` | Modele LLM |
| `MCP_EXCALIDRAW_LLM_TEMPERATURE` | `float` | `0.3` | Temperature (basse pour JSON fiable) |
| `MCP_EXCALIDRAW_LLM_MAX_TOKENS` | `int` | `16000` | Tokens max par appel |
| `MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS` | `int` | `60` | Timeout pour create_view (appel LLM unique) |

#### Description LLM (auto-generation)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `MCP_DESCRIPTION_LLM_PROVIDER` | `str` | `openai` | Provider LLM (modele bon marche) |
| `MCP_DESCRIPTION_LLM_MODEL` | `str` | `gpt-4.1-mini` | Modele LLM (rapide/bon marche) |
| `MCP_DESCRIPTION_LLM_TEMPERATURE` | `float` | `0.3` | Temperature |
| `MCP_DESCRIPTION_LLM_MAX_TOKENS` | `int` | `300` | Tokens max |

---

## Admin MCP

### Configurer un serveur MCP admin

Les serveurs admin sont declares dans `MCP_SERVERS_CONFIG` (JSON inline dans `.env`) ou via `MCP_SERVERS_CONFIG_PATH` (fichier JSON, prioritaire).

#### Transport stdio (processus local)

```json
{
  "excalidraw": {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@anthropic/mcp-excalidraw"],
    "env": {"NODE_ENV": "production"},
    "timeout_seconds": 30,
    "enabled": true,
    "hitl_required": false
  }
}
```

#### Transport streamable_http (serveur distant)

```json
{
  "huggingface_hub": {
    "transport": "streamable_http",
    "url": "https://hf-mcp.example.com/mcp",
    "headers": {"Authorization": "Bearer hf_xxxxx"},
    "timeout_seconds": 45,
    "enabled": true,
    "hitl_required": null,
    "description": "Search and access models, datasets, and spaces on Hugging Face"
  }
}
```

#### Service Docker interne (bypass SSRF)

```json
{
  "internal_service": {
    "transport": "streamable_http",
    "url": "http://mcp-service:8080/mcp",
    "internal": true,
    "enabled": true
  }
}
```

Le flag `internal: true` permet d'utiliser HTTP et des IP privees (services Docker de confiance). **Ne jamais utiliser pour des serveurs externes.**

### Schema MCPServerConfig

Le schema complet est defini dans `apps/api/src/infrastructure/mcp/schemas.py` :

```python
class MCPServerConfig(BaseModel):
    transport: MCPTransportType            # "stdio" | "streamable_http"
    command: str | None = None             # stdio: executable
    args: list[str] = []                   # stdio: arguments
    env: dict[str, str] | None = None      # stdio: variables d'env
    url: str | None = None                 # streamable_http: endpoint URL
    headers: dict[str, str] | None = None  # streamable_http: headers HTTP
    timeout_seconds: int = 30              # Timeout par appel (5-120s)
    enabled: bool = True                   # Serveur actif/inactif
    hitl_required: bool | None = None      # Override HITL (None = heriter du global)
    description: str | None = None         # Description pour le query routing
    internal: bool = False                 # Service Docker interne (skip SSRF)
```

### Cycle de vie au demarrage

```
Startup (main.py lifespan):
  1. MCPSettings charge MCP_SERVERS_CONFIG / MCP_SERVERS_CONFIG_PATH
  2. _parse_server_configs() cree dict[str, MCPServerConfig]
  3. MCPClientManager.initialize() pour chaque serveur enabled :
     a. validate_server_config() (securite, SSRF)
     b. _connect_server() avec retry (backoff exponentiel)
     c. discover_tools() → list_tools() + _fetch_reference_content()
  4. register_mcp_tools() dans le catalogue agent (domain_taxonomy "mcp_*")
  5. Auto-generation de description LLM si pas de description manuelle

Shutdown:
  MCPClientManager.shutdown() → ferme toutes les sessions + exit_stacks
```

### Auto-generation de description de domaine

Lorsqu'un serveur MCP admin n'a pas de `description` manuelle, une description est auto-generee via un LLM bon marche (`MCP_DESCRIPTION_LLM_*`). Cette description est optimisee pour le query routing (le `QueryAnalyzerService` l'utilise pour detecter le domaine pertinent).

Le prompt est defini dans `apps/api/src/domains/agents/prompts/v1/mcp_description_prompt.txt`.

### Toggle per-user des serveurs admin

Chaque utilisateur peut activer/desactiver individuellement les serveurs admin depuis les parametres. L'endpoint `PATCH /mcp/admin-servers/{server_key}/toggle` ajoute/retire le `server_key` de `user.admin_mcp_disabled_servers`.

### Systeme d'activation centralise

Quand un utilisateur desactive un serveur admin MCP, les effets sont appliques de facon centralisee a tous les niveaux de la pipeline :

1. **Query analysis** — Le domaine associe au serveur est filtre par le `QueryAnalyzerService` ; la requete n'est pas routee vers ce domaine.
2. **Catalogue** — Les manifests d'outils du serveur desactive sont exclus de `request_tool_manifests_ctx` ; le planner ne les voit jamais.
3. **Proxy endpoints** — Les appels aux endpoints proxy MCP du serveur desactive retournent `HTTP 403 Forbidden`.

---

## Per-User MCP

### Vue d'ensemble

Le MCP per-user permet a chaque utilisateur de declarer ses propres serveurs MCP via l'interface web. Les serveurs sont stockes en base de donnees (table `user_mcp_servers`).

**Contraintes** :
- **Transport** : `streamable_http` uniquement (pas de `stdio` pour des raisons de securite)
- **URL** : HTTPS obligatoire (valide par `UserMCPServerCreate.validate_url_scheme()`)
- **Credentials** : Chiffrees avec Fernet avant stockage en base

### Endpoints API

Tous les endpoints sont sous `/api/v1/mcp/servers` :

| Methode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/` | Liste les serveurs de l'utilisateur |
| `POST` | `/` | Cree un nouveau serveur |
| `PATCH` | `/{server_id}` | Met a jour un serveur |
| `DELETE` | `/{server_id}` | Supprime un serveur |
| `PATCH` | `/{server_id}/toggle` | Active/desactive un serveur |
| `POST` | `/{server_id}/test` | Teste la connexion + decouvre les outils |
| `POST` | `/{server_id}/generate-description` | Force la (re)generation de la description |
| `POST` | `/{server_id}/oauth/authorize` | Demarre le flow OAuth 2.1 |
| `POST` | `/{server_id}/oauth/disconnect` | Purge les tokens OAuth |
| `GET` | `/oauth/callback` | Callback OAuth (interne) |

### Types d'authentification

```python
class UserMCPAuthType(str, Enum):
    NONE = "none"           # Pas d'auth
    API_KEY = "api_key"     # Header custom (defaut: X-API-Key)
    BEARER = "bearer"       # Authorization: Bearer <token>
    OAUTH2 = "oauth2"       # OAuth 2.1 flow complet
```

### Creer un serveur per-user (exemple)

```json
POST /api/v1/mcp/servers
{
  "name": "My GitHub MCP",
  "url": "https://github-mcp.example.com/mcp",
  "auth_type": "bearer",
  "bearer_token": "ghp_xxxxxxxxxxxx",
  "domain_description": "Search repos, list commits, manage issues on GitHub",
  "timeout_seconds": 30,
  "hitl_required": true
}
```

### UserMCPClientPool : connexions ephemeres

Le `UserMCPClientPool` (`user_pool.py`) ne maintient **pas** de connexions persistantes. Il cache les metadonnees des outils (tool discovery) mais chaque `call_tool()` cree une connexion ephemere :

```
call_tool():
  connect → initialize → call_tool → close
  (tout dans un seul scope async)
```

**Pourquoi ephemere ?** Le SDK MCP Python utilise des anyio TaskGroups dont les cancel scopes meurent quand ils sont stockes dans un pool longue duree. Les connexions ephemeres gardent tout le lifecycle dans un seul scope async, evitant `ClosedResourceError` / `CancelledError`.

Le pool utilise :
- **Per-key asyncio.Lock** pour empecher les discoveries dupliquees
- **Reference counting** (`active_calls`) pour proteger les entries en cours d'utilisation de l'eviction
- **Rate limiting** par sliding window par serveur
- **TTL eviction** pour nettoyer les entries idle

### Flow OAuth 2.1

```
1. Frontend appelle POST /mcp/servers/{id}/oauth/authorize
2. Backend initie le flow OAuth via MCPOAuthFlowHandler
3. Backend retourne authorization_url au frontend
4. Frontend redirige vers l'authorization server
5. Utilisateur autorise l'application
6. Authorization server redirige vers GET /mcp/servers/oauth/callback
7. Backend echange le code contre des tokens
8. Tokens chiffres (Fernet) et stockes en base
9. Redirect vers le frontend avec ?oauth_success&server_id=xxx
```

**Securite du callback** : Pas de session auth requise (l'utilisateur est en mid-redirect). L'identite vient du parametre `state` signe stocke dans Redis (usage unique, supprime apres consommation).

---

## Iterative Mode / ReAct (F2.7)

When `iterative_mode=true` on an MCP server, the planner delegates to a **ReAct sub-agent** instead of calling individual tools directly.

### How It Works

```
Standard mode:  Planner → individual tools → parallel_executor → MCPToolAdapter
Iterative mode: Planner → mcp_{server}_task → ReactSubAgentRunner → ReAct agent loop
                                              └→ read_me → understand API → call tools → result
```

### Admin vs User MCP

| Aspect | Admin MCP | User MCP |
|--------|-----------|----------|
| **When** | At startup (`registration.py`) | Per-request (`user_context.py`) |
| **Tool name** | `mcp_{server_name}_task` | `mcp_user_{id_prefix}_task` |
| **Tool storage** | Global `tool_registry` | Per-request `ContextVar` |
| **Entry point** | `mcp_server_task_tool()` | `mcp_user_server_task_tool()` |
| **Shared logic** | `_run_mcp_react_task()` | `_run_mcp_react_task()` |
| **Manifest factory** | `build_mcp_react_task_manifest()` | `build_mcp_react_task_manifest()` |

### Key Files

- `src/domains/agents/tools/mcp_react_tools.py` — Task tools + `_MCPReActWrapper` + shared `_run_mcp_react_task()`
- `src/infrastructure/mcp/registration.py` — Admin registration + shared `build_mcp_react_task_manifest()`
- `src/infrastructure/mcp/user_context.py` — User registration: `_register_user_iterative_server()`
- `src/domains/agents/prompts/v1/mcp_react_agent_prompt.txt` — ReAct agent prompt (shared)

### LLM Type Auto-Selection

MCP App servers (with interactive widgets like Excalidraw) automatically use a dedicated, more capable LLM:

| Server type | LLM type | Default | Configurable in |
|-------------|----------|---------|-----------------|
| MCP App (`app_resource_uri` present) | `mcp_app_react_agent` | Opus | Admin LLM Config panel |
| Regular MCP | `mcp_react_agent` | Qwen | Admin LLM Config panel |

Detection is automatic via `_has_mcp_app_tools()` — no user action needed.

### Error Recovery

`_MCPReActWrapper` catches all MCP tool exceptions and returns them as strings to the ReAct agent. This enables retry with corrected parameters instead of crashing.

### Requirements

- `MCP_REACT_ENABLED=true` (global feature flag, default `false`)
- `iterative_mode=true` on the server config (admin) or user toggle (user)
- Reference content (`read_me`) is skipped in the planner prompt for iterative servers — the ReAct agent fetches it itself

---

## Convention read_me

### Principe

Les serveurs MCP exposant un outil nomme `read_me` (constante `MCP_REFERENCE_TOOL_NAME`) voient leur contenu auto-fetche a la decouverte et injecte dans le prompt du planner. L'outil `read_me` est ensuite masque du catalogue LLM.

### Fonctionnement

**Admin MCP** (`MCPClientManager._fetch_reference_content()`) :
```python
# A la decouverte (discover_tools):
read_me_tool = next((t for t in tools if t.tool_name == MCP_REFERENCE_TOOL_NAME), None)
if read_me_tool:
    result = await session.call_tool(MCP_REFERENCE_TOOL_NAME, {})
    self._reference_content[server_name] = result.content[0].text
```

**Per-User MCP** (`UserMCPClientPool._discover_tools()`) :
Le meme pattern, avec le contenu cache dans `PoolEntry.reference_content`.

### Injection dans le planner

Le `SmartPlannerService._build_mcp_reference()` merge les contenus `read_me` des sources admin et user, puis les injecte dans le prompt planner. Le contenu est tronque a `MCP_REFERENCE_CONTENT_MAX_CHARS` (defaut 30000 caracteres).

### Cas d'usage

Le `read_me` est particulierement utile pour les serveurs ayant des formats d'entree complexes (ex: Excalidraw avec son format JSON d'elements specifique). Le planner recoit la documentation de reference et genere des parametres de meilleure qualite.

---

## MCP Apps (F2.6)

### Concept

Les MCP Apps sont des widgets interactifs rendus dans des iframes sandbox. Un outil MCP peut declarer une UI associee via `Tool.meta.ui.resourceUri` et `Tool.meta.ui.visibility`.

### Architecture backend

**1. Detection des metadonnees UI** (`utils.py`) :

```python
def extract_app_meta(tool: Any) -> tuple[str | None, list[str] | None]:
    """Lit Tool.meta.ui.resourceUri et Tool.meta.ui.visibility."""
    meta = getattr(tool, "meta", None)
    ui = meta.get("ui") if isinstance(meta, dict) else None
    resource_uri = ui.get("resourceUri") if isinstance(ui, dict) else None
    visibility = ui.get("visibility") if isinstance(ui, dict) else None
    return resource_uri, visibility
```

**2. Filtrage app-only** (`utils.py`) :

Les outils avec `visibility: ["app"]` sont iframe-only et ne sont pas exposes au catalogue LLM :

```python
def is_app_only(visibility: list[str] | None) -> bool:
    return visibility is not None and set(visibility) == {"app"}
```

**3. Build du RegistryItem MCP_APP** (`utils.py`) :

`build_mcp_app_output()` construit un `UnifiedToolOutput` contenant un `RegistryItem` de type `MCP_APP` avec le HTML, le resultat de l'outil, et les metadonnees du serveur.

**4. Server-side sentinel** (`mcp_app_sentinel.py`) :

Le `McpAppSentinel` rend un placeholder HTML que le frontend detecte et remplace :

```html
<div class="lia-mcp-app" data-registry-id="mcp_app_xxx">
  <div class="lia-mcp-app__placeholder">
    <span class="lia-badge">MCP Apps · Excalidraw</span>
    <div class="lia-mcp-app__loading">Chargement...</div>
  </div>
</div>
```

### Architecture frontend

**1. McpAppWidget** (`apps/web/src/components/chat/McpAppWidget.tsx`) :

Le composant React qui remplace le sentinel. Il recoit le `registryId`, recupere le payload depuis le `RegistryContext`, et rend un iframe sandbox :

```tsx
<iframe
  srcDoc={payload.html_content}
  sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"
  title={`MCP App: ${payload.tool_name}`}
/>
```

**Securite sandbox** :
- `allow-scripts` : permet l'execution de JavaScript dans l'iframe
- `allow-forms` : permet les formulaires
- `allow-popups` : requis pour `ui/open-link`
- **PAS de `allow-same-origin`** : bloque l'acces aux cookies, localStorage, DOM du parent

**2. useMcpAppBridge** (`apps/web/src/hooks/useMcpAppBridge.ts`) :

Le hook implementant le protocole MCP Apps via PostMessage JSON-RPC 2.0 :

```
Handshake:
  1. iframe envoie ui/initialize → host repond avec capabilities
  2. iframe envoie ui/notifications/initialized → host envoie tool-input puis tool-result

Bidirectionnel:
  - tools/call → proxy via API backend
  - resources/read → proxy via API backend
  - ui/open-link → window.open (https:// uniquement)
  - ui/download-file → download via Blob URL
  - ui/notifications/size-changed → resize dynamique iframe
```

**Securite du bridge** :
- Valide `origin === "null"` (iframes srcdoc)
- Valide `event.source === iframeRef.current.contentWindow`
- Seuls les URLs `https://` sont autorises pour `ui/open-link`
- Guard `mounted` empeche les postMessage vers des iframes detruits

### Proxy API pour les iframes

Les iframes n'ont pas acces direct aux serveurs MCP. Les appels sont proxies via le backend :

| Endpoint | Description |
|----------|-------------|
| `POST /mcp/admin-servers/{key}/app/call-tool` | Proxy call_tool (admin) |
| `POST /mcp/admin-servers/{key}/app/read-resource` | Proxy read_resource (admin) |
| `POST /mcp/servers/{id}/app/call-tool` | Proxy call_tool (user) |
| `POST /mcp/servers/{id}/app/read-resource` | Proxy read_resource (user) |

### COEP credentialless

Le header `Cross-Origin-Embedder-Policy: credentialless` (pas `require-corp`) permet aux iframes MCP Apps de charger des ressources externes (esm.sh, fonts) sans headers CORP. Trade-off : `SharedArrayBuffer` indisponible sur Safari iOS uniquement.

---

## Excalidraw Iterative Builder

### Principe

Le Excalidraw Iterative Builder intercepte les appels a l'outil `create_view` du serveur MCP Excalidraw. Il fonctionne exclusivement en **intent-only mode** : le planner genere un intent JSON (jamais des raw elements), et `build_from_intent()` construit le diagramme complet en 1 seul appel LLM.

### Intent mode (mode prefere)

Le planner genere un **intent JSON** (pas des raw elements) grace au `EXCALIDRAW_SPATIAL_SUFFIX` ajoute a la description de l'outil dans le catalogue :

```json
{
  "intent": true,
  "description": "Architecture microservices",
  "components": [
    {"name": "API Gateway", "shape": "rectangle", "color": "#a5d8ff"},
    {"name": "Auth Service", "shape": "rectangle", "color": "#b2f2bb"},
    {"name": "Database", "shape": "ellipse", "color": "#ffec99"}
  ],
  "connections": [
    {"from": "API Gateway", "to": "Auth Service", "label": "auth check"},
    {"from": "Auth Service", "to": "Database"}
  ],
  "layout": "top-to-bottom"
}
```

### Flow de construction

```
_prepare_excalidraw() dans MCPToolAdapter._arun():
  1. Detecte server_name == "excalidraw" && tool_name == "create_view"
  2. is_intent() verifie si elements contient {"intent": true, "components": [...]}
  3. Fetch cheat_sheet (read_me du serveur Excalidraw)
  4. build_from_intent() fait 1 seul appel LLM:
     - _generate_diagram(): camera + background + composants + labels + fleches
  5. Les elements generes remplacent l'intent dans kwargs
```

> **Intent-only mode** : Excalidraw n'accepte plus de raw elements. Le planner doit toujours generer un intent JSON (detecte par `is_intent()`). Le `position_corrector` (fallback raw elements) a ete supprime.

### Configuration LLM dediee

Le builder utilise un LLM dedie (peut differer du planner) configure via `MCP_EXCALIDRAW_LLM_*` :

```bash
MCP_EXCALIDRAW_LLM_PROVIDER=anthropic
MCP_EXCALIDRAW_LLM_MODEL=claude-opus-4-6
MCP_EXCALIDRAW_LLM_TEMPERATURE=0.3
MCP_EXCALIDRAW_LLM_MAX_TOKENS=16000
MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS=60
```

**Attention Anthropic** : Les providers Claude 4.5+ rejettent `temperature` + `top_p` ensemble. Le provider filtre `top_p` automatiquement.

### Progressive rendering frontend

Le hook `useMcpAppBridge` detecte les appels `create_view` Excalidraw et envoie les elements un par un via `ui/notifications/tool-input-partial` (drip delay de 120ms), puis le `tool-input` final + `tool-result`. Le widget Excalidraw anime chaque nouvel element (fade in pour les shapes, draw on pour les lignes).

---

## UserMCPToolAdapter Pattern

### Difference avec MCPToolAdapter (admin)

| Aspect | MCPToolAdapter (admin) | UserMCPToolAdapter (per-user) |
|--------|----------------------|-------------------------------|
| **Nommage** | `mcp_{server_name}_{tool_name}` | `mcp_user_{server_id[:8]}_{tool_name}` |
| **Pool** | `MCPClientManager` (singleton) | `UserMCPClientPool` (per-user entries) |
| **Connexion** | Persistante (session cached) | Ephemere (connect-call-close) |
| **Structured parsing** | Non (result brut) | Oui (JSON arrays → N RegistryItems) |
| **Excalidraw** | Oui (intent-only mode) | Non |

### Parsing JSON structure (F2.4)

`UserMCPToolAdapter._arun()` parse intelligemment les resultats JSON :

```python
# _parse_mcp_structured_items(raw_result):
# 1. Si top-level JSON array de dicts → items directs
# 2. Si top-level dict → cherche la plus grande list-of-dicts value
# 3. Sinon → fallback single wrapper

# Resultat: 1 RegistryItem PAR item (pas un blob monolithique)
# Permet: for_each expansion, card rendering individuel
```

**Collection key** : Derivee du nom de l'outil via `_derive_collection_key()` :

```python
"search_repositories" → "repositories"
"list_commits"        → "commits"
"get_user"            → "users"
```

**Cap de securite** : `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` (defaut 50) empeche l'explosion du registry quand un outil retourne 100+ items.

### Property coroutine

Les deux adapters exposent `_arun` via la property `coroutine` pour que le `parallel_executor` puisse appeler directement la methode async sans passer par `ainvoke()` (qui stringifie le resultat et perd le `UnifiedToolOutput`).

---

## Securite

### Prevention SSRF

Le module `security.py` bloque les endpoints HTTP pointant vers des reseaux internes :

- **IP bloquees** : RFC 1918 (10/8, 172.16/12, 192.168/16), loopback (127/8), link-local (169.254/16), CGNAT (100.64/10), metadata (169.254.169.254), IPv6 ULA (fc00::/7), etc.
- **Hostnames bloques** : `localhost`, `metadata.google.internal`, suffixes `.internal`, `.local`, `.localhost`
- **Schema** : HTTPS obligatoire (sauf `internal: true` pour les services Docker admin)
- **Resolution DNS** : Verifie toutes les adresses resolues (pas seulement la premiere)
- **IPv4-mapped IPv6** : Normalise `::ffff:127.0.0.1` en `127.0.0.1` avant verification

### HTTPS obligatoire (per-user)

Les serveurs per-user doivent utiliser HTTPS :

```python
# UserMCPServerCreate.validate_url_scheme():
if not v.startswith("https://"):
    raise ValueError("MCP server URL must use HTTPS")
```

### Chiffrement des credentials

Les credentials utilisateur (API key, bearer token, OAuth tokens) sont chiffres avec **Fernet** avant stockage en base. Le `UserMCPServerService` gere le chiffrement/dechiffrement de maniere transparente.

### Rate limiting per-server

Les deux pools (admin et user) implementent un **sliding window** par serveur avec protection TOCTOU via `asyncio.Lock` :

```python
async with lock:
    # Purge expired timestamps
    while timestamps and timestamps[0] < now - window:
        timestamps.popleft()
    if len(timestamps) >= max_calls:
        raise RuntimeError("Rate limit exceeded")
    timestamps.append(now)
```

### Resolution HITL

Le HITL (Human-in-the-Loop) suit une hierarchie :

```
Per-server hitl_required (si non-None) > Global MCP_HITL_REQUIRED
```

La resolution est dans `security.py` :

```python
def resolve_hitl_requirement(server_config, global_hitl_required):
    if server_config.hitl_required is not None:
        return server_config.hitl_required
    return global_hitl_required
```

---

## Testing

### Tests unitaires admin MCP

Fichier : `apps/api/tests/unit/infrastructure/mcp/test_tool_adapter.py`

```python
# Tester la conversion JSON Schema → Pydantic
from src.infrastructure.mcp.tool_adapter import build_args_schema

def test_basic_types():
    schema = {
        "properties": {
            "name": {"type": "string", "description": "Name"},
            "count": {"type": "integer", "description": "Count"},
        },
        "required": ["name"],
    }
    model = build_args_schema(schema)
    assert model is not None
    assert "name" in model.model_fields

# Tester l'adapter MCP
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

def test_from_mcp_tool():
    adapter = MCPToolAdapter.from_mcp_tool(
        server_name="test_server",
        tool_name="search",
        description="Search something",
        input_schema={"properties": {"query": {"type": "string"}}},
    )
    assert adapter.name == "mcp_test_server_search"
    assert adapter.mcp_tool_name == "search"
```

### Tests unitaires per-user MCP

Fichier : `apps/api/tests/unit/domains/user_mcp/test_user_tool_adapter.py`

```python
from src.infrastructure.mcp.user_tool_adapter import (
    UserMCPToolAdapter,
    _derive_collection_key,
    _parse_mcp_structured_items,
)

# Tester le parsing structure
def test_parse_json_array():
    result = _parse_mcp_structured_items('[{"name": "a"}, {"name": "b"}]')
    assert result is not None
    items, key = result
    assert len(items) == 2
    assert key is None

# Tester la derivation de collection key
def test_derive_collection_key():
    assert _derive_collection_key("search_repositories") == "repositories"
    assert _derive_collection_key("list_commits") == "commits"
    assert _derive_collection_key("get_user") == "users"
```

### Tests Excalidraw

Fichiers :
- `apps/api/tests/unit/infrastructure/mcp/test_excalidraw_iterative_builder.py`

### Tests d'integration

Les tests d'integration MCP necessitent un serveur MCP running. Utiliser les markers pytest :

```bash
# Tests unitaires rapides (sans DB, sans serveur MCP)
task test:backend:unit:fast

# Tests d'integration (necessite l'infra Docker)
task test:backend:integration
```

### Mocker le MCPClientManager

```python
from unittest.mock import AsyncMock, patch

@patch("src.infrastructure.mcp.client_manager.get_mcp_client_manager")
async def test_mcp_tool_call(mock_get_manager):
    manager = AsyncMock()
    manager.call_tool.return_value = '{"result": "ok"}'
    mock_get_manager.return_value = manager

    # ... tester le code qui appelle call_tool
```

### Mocker le UserMCPClientPool

```python
@patch("src.infrastructure.mcp.user_pool.get_user_mcp_pool")
async def test_user_mcp_call(mock_get_pool):
    pool = AsyncMock()
    pool.call_tool.return_value = '{"items": [{"name": "test"}]}'
    mock_get_pool.return_value = pool

    # ... tester le code qui appelle le pool
```

---

## Troubleshooting

### Le serveur MCP ne se connecte pas au demarrage

**Symptome** : Logs `mcp_server_connection_failed` au demarrage.

**Verifications** :
1. `MCP_ENABLED=true` dans `.env`
2. Le JSON dans `MCP_SERVERS_CONFIG` est syntaxiquement valide (le validator fail-fast detecte les erreurs au chargement)
3. Pour stdio : la commande existe dans le PATH du container Docker
4. Pour streamable_http : l'URL est accessible depuis le container et utilise HTTPS
5. Verifier `MCP_CONNECTION_RETRY_MAX` (defaut 3, backoff exponentiel)

### Les outils MCP ne sont pas proposes par le planner

**Symptome** : L'utilisateur pose une question pertinente mais le planner ne selectionne pas les outils MCP.

**Verifications** :
1. Verifier que le serveur a une `description` claire et en anglais (le `QueryAnalyzerService` travaille en anglais post-SemanticPivot)
2. Verifier les logs `mcp_server_connected` avec `tool_count > 0`
3. L'utilisateur n'a-t-il pas desactive le serveur admin ? (endpoint `/mcp/admin-servers`)
4. Si auto-generation, verifier les logs `mcp_description_generated`

### Rate limit exceeded

**Symptome** : `RuntimeError: Rate limit exceeded for MCP server 'xxx'`

**Solution** : Augmenter `MCP_RATE_LIMIT_CALLS` et/ou `MCP_RATE_LIMIT_WINDOW` dans `.env`. Le defaut est 30 appels par 60 secondes par serveur.

### Pool per-user plein

**Symptome** : `RuntimeError: User MCP pool is full (N entries) and no idle entries available for eviction`

**Solutions** :
- Augmenter `MCP_USER_POOL_MAX_TOTAL` (defaut 100)
- Reduire `MCP_USER_POOL_TTL_SECONDS` (defaut 3600) pour eviction plus agressive
- Verifier qu'il n'y a pas de fuite de `active_calls` (reference counting)

### OAuth callback echoue

**Symptome** : Redirect vers le frontend avec `?oauth_error`

**Verifications** :
1. `MCP_USER_OAUTH_CALLBACK_BASE_URL` est correctement configure
2. Le state Redis n'a pas expire (TTL par defaut dans le handler)
3. Le serveur d'autorisation retourne bien un `code` et un `state`
4. Les logs `user_mcp_oauth_callback_failed` donnent le type d'erreur

### ExceptionGroup depuis le SDK MCP

**Symptome** : `ExceptionGroup` dans les logs au lieu de l'erreur reelle.

**Explication** : Le SDK MCP utilise des anyio TaskGroups en interne. Quand une sous-tache echoue, anyio wrappe l'erreur dans un `ExceptionGroup`. Le code dans `user_pool.py` (methodes `_execute_call_ephemeral` et `_execute_read_resource_ephemeral`) unwrap automatiquement les `ExceptionGroup` a un seul element pour exposer la cause racine.

### Les widgets MCP Apps ne s'affichent pas

**Symptome** : Le sentinel placeholder reste visible au lieu du widget interactif.

**Verifications** :
1. Le `RegistryContext` du frontend contient bien l'item `MCP_APP` avec le `registryId`
2. Le `MarkdownContent` detecte bien les `<div class="lia-mcp-app">` et les remplace par `McpAppWidget`
3. La taille du HTML ne depasse pas `MCP_APP_MAX_HTML_SIZE` (defaut 2MB)
4. Le header COEP est bien `credentialless` (pas `require-corp`)

### Excalidraw genere des diagrammes vides

**Symptome** : Le diagramme s'affiche mais sans elements.

**Verifications** :
1. Les logs `excalidraw_llm_call_failed` indiquent une erreur LLM
2. Le `cheat_sheet` (read_me) est bien fetche (logs `excalidraw_cheat_sheet_fetched`)
3. `MCP_EXCALIDRAW_LLM_MAX_TOKENS` est suffisant (defaut 16000)
4. `MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS` n'est pas trop bas (defaut 60s pour l'appel LLM unique)
5. Pour Anthropic : verifier que `top_p` est bien filtre (Claude 4.5+ rejette `temperature` + `top_p`)

---

## References

- **Documentation technique MCP** : `docs/technical/MCP_INTEGRATION.md`
- **Roadmap evolution** : `docs/technical/evolution_INTEGRATION_ROADMAP.md`
- **Guide creation d'outils** : `docs/guides/GUIDE_TOOL_CREATION.md`
- **Configuration** : `apps/api/src/core/config/mcp.py` (`MCPSettings`)
- **MCP Protocol** : [Anthropic MCP Specification](https://modelcontextprotocol.io)
