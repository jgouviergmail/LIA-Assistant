# MCP Integration — Technical Documentation

## Overview

MCP (Model Context Protocol) support enables LIA to connect external tool servers using the standard Anthropic MCP protocol. External tools are discovered at startup and registered in the existing catalogue, making them available to any agent through the normal orchestration pipeline.

**Key principle**: MCP is infrastructure-level, NOT a new agent. Tools register in the existing catalogue and are usable by any agent via the standard planning/execution pipeline.

**Version**: evolution F2 + F2.1 + F2.2 + F2.3 + F2.4 + F2.5 + F2.6 + F2.7 — v6.3
**Status**: Admin MCP (F2) + Per-user MCP (F2.1) + Per-server domains (F2.2) + HTML Card Display (F2.3) + Structured Items Parsing (F2.4) + OAuth Scopes + Admin MCP Per-Server Routing & User Toggle (F2.5) + MCP Apps (F2.6) + Iterative Mode / ReAct (F2.7) implemented.

---

## Architecture

### Flow

```
Startup: MCPSettings → MCPClientManager.initialize() → session.list_tools()
         → MCPToolAdapter(BaseTool) → ToolManifest → AgentRegistry + tool_registry
         → domain_taxonomy "mcp" → _build_domain_index()

Runtime (standard): QueryAnalyzerService detects per-server domain → SmartCatalogueService includes MCP tools
         → Planner selects MCP tool → parallel_executor → tool_registry.get_tool()
         → MCPToolAdapter._arun() → session.call_tool()

Runtime (iterative_mode, admin): QueryAnalyzerService detects domain → Planner selects mcp_{server}_task
         → parallel_executor → mcp_server_task_tool → ReactSubAgentRunner
         → ReAct agent loop: read_me → understand API → call tools → return result

Runtime (iterative_mode, user): setup_user_mcp_tools() detects iterative_mode + mcp_react_enabled
         → individual tools in ContextVar (for ReAct) + single mcp_user_{id}_task manifest for planner
         → parallel_executor → mcp_user_server_task_tool → ReactSubAgentRunner
         → ReAct agent loop: read_me → understand API → call tools → return result

Shutdown: MCPClientManager.shutdown() → closes sessions + exit_stacks
```

### Module Structure

```
apps/api/src/infrastructure/mcp/
├── __init__.py           # Package exports
├── schemas.py            # MCPServerConfig, MCPDiscoveredTool, MCPServerStatus
├── security.py           # Server validation, SSRF prevention, HITL resolution
├── tool_adapter.py       # MCPToolAdapter (admin MCP → LangChain BaseTool)
├── client_manager.py     # MCPClientManager (lifecycle, connections, health)
├── registration.py       # Bridge: AgentRegistry + tool_registry + manifest builder
├── auth.py               # MCPNoAuth, MCPStaticTokenAuth, MCPOAuth2Auth, build_auth_for_server()
├── oauth_flow.py         # MCPOAuthFlowHandler (RFC 9728/8414 discovery, PKCE, callback)
├── user_pool.py          # UserMCPClientPool (tool metadata cache, ephemeral connections)
├── user_tool_adapter.py  # UserMCPToolAdapter (per-user MCP → BaseTool + UnifiedToolOutput)
└── user_context.py       # setup/cleanup functions + user_mcp_session context manager
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `BaseTool` subclass (not `@connector_tool`) | MCP tools are dynamic (discovered at runtime). Decorators only work on static functions. |
| Per-server agent (F2.2) `"mcp_<slug>_agent"` | Each MCP server gets its own domain via `_extract_domain()` (e.g., `"mcp_huggingface_hub"`). Replaces single `"mcp_agent"` for user servers. |
| Dual registry (AgentRegistry + tool_registry) | AgentRegistry for catalogue filtering, tool_registry for parallel_executor invocation |
| SSRF constants copied (not imported from `url_validator.py`) | Avoids infrastructure → domain dependency violation |
| In-memory rate limiting with `asyncio.Lock` | Prevents TOCTOU race conditions under concurrent requests |
| `repr=False` on `env`/`headers` fields | Prevents secret leakage in logs |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_ENABLED` | `false` | Enable MCP support |
| `MCP_SERVERS_CONFIG` | `{}` | JSON string defining MCP servers |
| `MCP_SERVERS_CONFIG_PATH` | _(none)_ | Path to JSON config file (overrides inline) |
| `MCP_TOOL_TIMEOUT_SECONDS` | `30` | Timeout per tool call (5-120s) |
| `MCP_MAX_SERVERS` | `10` | Maximum servers (1-50) |
| `MCP_MAX_TOOLS_PER_SERVER` | `20` | Maximum tools per server (1-100) |
| `MCP_HITL_REQUIRED` | `true` | Global HITL requirement |
| `MCP_RATE_LIMIT_CALLS` | `60` | Max calls per server per window |
| `MCP_RATE_LIMIT_WINDOW` | `60` | Rate limit window (seconds) |
| `MCP_HEALTH_CHECK_INTERVAL_SECONDS` | `300` | Health check interval |
| `MCP_CONNECTION_RETRY_MAX` | `3` | Connection retry attempts |
| `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` | `25` | Max structured items parsed from a single MCP call (1-200). Prevents registry explosion for tools returning large arrays. |

### Server Configuration Format

#### Inline JSON (`MCP_SERVERS_CONFIG`)

```json
{
  "filesystem": {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data"],
    "timeout_seconds": 30,
    "enabled": true,
    "hitl_required": null,
    "description": "Read and write files in the local filesystem"
  },
  "github": {
    "transport": "stdio",
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-github"],
    "env": {
      "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_xxx"
    },
    "hitl_required": true,
    "description": "Manage GitHub repos, issues, pull requests"
  },
  "remote_api": {
    "transport": "streamable_http",
    "url": "https://mcp-api.example.com/mcp",
    "headers": {
      "Authorization": "Bearer api_key_here"
    },
    "timeout_seconds": 60,
    "description": "Custom remote API tools"
  },
  "google_flights": {
    "transport": "streamable_http",
    "url": "http://google-flights:8000/mcp",
    "internal": true,
    "description": "Search flights, find airports, compare prices and get best flight deals worldwide",
    "timeout_seconds": 30,
    "enabled": true,
    "hitl_required": false
  }
}
```

#### MCPServerConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `transport` | `"stdio"` \| `"streamable_http"` | _(required)_ | Transport protocol |
| `command` | `string` | `null` | Command for stdio transport |
| `args` | `list[string]` | `[]` | Arguments for stdio command |
| `url` | `string` | `null` | URL for streamable_http transport |
| `env` | `dict` | `{}` | Environment variables |
| `headers` | `dict` | `{}` | HTTP headers |
| `timeout_seconds` | `int` | `30` | Timeout per tool call (5-120s) |
| `enabled` | `bool` | `true` | Enable/disable this server |
| `hitl_required` | `bool \| null` | `null` | HITL override (`null` = use global) |
| `description` | `string \| null` | `null` | Domain description for query routing. Helps the LLM select this server when analyzing user queries. |
| `internal` | `bool` | `false` | Mark as Docker-internal service. Skips SSRF validation (allows HTTP and private IPs). Only for trusted admin-configured services. |
| `iterative_mode` | `bool` | `false` | Enable ReAct agent loop instead of static planner for this server. When `true`, a sub-agent interacts iteratively with the server (reads docs, then calls tools). Requires `MCP_REACT_ENABLED=true`. Best for servers with complex APIs (e.g., Excalidraw). |

#### JSON File (`MCP_SERVERS_CONFIG_PATH`)

```bash
MCP_SERVERS_CONFIG_PATH=/etc/lia/mcp_servers.json
```

The file uses the same format as inline JSON. File takes precedence over inline config.

### Transport Types

| Transport | Use Case | Required Fields |
|-----------|----------|-----------------|
| `stdio` | Local process (Node.js, Python) | `command`, `args` (optional) |
| `streamable_http` | Remote HTTP endpoint | `url`, `headers` (optional) |

---

## Administration Procedures

### Adding a New MCP Server

1. **Choose transport**: `stdio` for local processes, `streamable_http` for remote APIs
2. **Configure in `.env`** or JSON file:
   ```env
   MCP_SERVERS_CONFIG={"my_server": {"transport": "stdio", "command": "npx", "args": ["-y", "my-mcp-server"]}}
   ```
3. **Set `MCP_ENABLED=true`**
4. **Restart the API container**: `task restart`
5. **Verify in logs**: Look for `mcp_initialized` with tool count
6. **Check Prometheus**: `mcp_server_health{server_name="my_server"}` should be `1`

### Removing a Server

1. Remove the server entry from `MCP_SERVERS_CONFIG` or the JSON file
2. Restart the API container
3. Tools from that server are automatically unregistered

### Updating a Server Configuration

1. Modify the server entry in configuration
2. Restart the API container (hot reload not supported in V1)

### Disabling a Server Temporarily

Set `"enabled": false` in the server config:
```json
{"my_server": {"transport": "stdio", "command": "npx", "enabled": false}}
```

---

## Security

### HITL (Human-in-the-Loop)

MCP tools require user approval by default (`MCP_HITL_REQUIRED=true`).

**Resolution hierarchy**: per-server `hitl_required` > global `MCP_HITL_REQUIRED`

```json
{
  "safe_server": {"transport": "stdio", "command": "npx", "hitl_required": false},
  "dangerous_server": {"transport": "stdio", "command": "npx", "hitl_required": true}
}
```

### SSRF Prevention (HTTP Transport)

For `streamable_http` servers:
- Only HTTPS URLs are accepted
- Blocked: private IPs (RFC 1918), CGNAT, loopback, link-local
- Blocked: cloud metadata endpoints (169.254.169.254)
- Blocked: hostnames ending in `.internal`, `.local`, `.localhost`
- IPv4-mapped IPv6 addresses are normalized before checking

### Rate Limiting

Per-server sliding window rate limiting prevents abuse:
- `MCP_RATE_LIMIT_CALLS`: Max calls per window (default: 60)
- `MCP_RATE_LIMIT_WINDOW`: Window size in seconds (default: 60)
- Protected by `asyncio.Lock` against concurrent access race conditions

---

## Monitoring

### Prometheus Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `mcp_tool_invocations_total` | Counter | server_name, tool_name, status | Total invocations |
| `mcp_tool_duration_seconds` | Histogram | server_name, tool_name | Execution duration |
| `mcp_server_health` | Gauge | server_name | Connection status (1/0) |
| `mcp_connection_errors_total` | Counter | server_name, error_type | Connection errors |

### Log Events

| Event | Level | Description |
|-------|-------|-------------|
| `mcp_initialized` | INFO | Startup complete with server/tool counts |
| `mcp_server_connected` | INFO | Server connected with tool list |
| `mcp_server_connection_failed` | ERROR | All retry attempts exhausted |
| `mcp_tool_discovery_failed` | ERROR | list_tools() failed |
| `mcp_connections_closed` | INFO | Shutdown complete |

---

## Troubleshooting

### Server Not Connecting

1. Check logs for `mcp_server_config_invalid` or `mcp_server_connection_attempt_failed`
2. Verify the command/URL is accessible from the API container
3. For stdio: ensure the command is installed (`npx`, `python`, etc.)
4. For HTTP: check HTTPS requirement and SSRF validation

### Tools Not Appearing in Catalogue

1. Verify `MCP_ENABLED=true` in environment
2. Check logs for `mcp_initialized` with tool count > 0
3. Verify `mcp_server_health` gauge is 1 in Prometheus
4. Ensure the query triggers domain "mcp" in QueryAnalyzerService

### Rate Limit Errors

Increase `MCP_RATE_LIMIT_CALLS` or `MCP_RATE_LIMIT_WINDOW` in configuration.

### Timeout Errors

Increase `MCP_TOOL_TIMEOUT_SECONDS` globally or set per-server `timeout_seconds`.

**Note:** The full MCP lifecycle (connect + handshake + list_tools / call_tool) is bounded by `timeout_seconds` per server. If a server is unresponsive during connection or handshake, the timeout fires and the server is skipped — other servers and the rest of the pipeline are not blocked.

### OAuth 403 Forbidden on Tool Calls

If `list_tools` succeeds but `call_tool` returns `403 Forbidden`:
1. The OAuth token lacks required scopes
2. Edit the server → add OAuth scopes (e.g., `repo project read:org` for GitHub)
3. Click "Disconnect OAuth" to purge the existing token
4. Click "Connect OAuth" to re-authorize with the new scopes
5. Check the provider's documentation for required scopes

---

## Popular MCP Servers

| Server | Transport | Package | Use Case |
|--------|-----------|---------|----------|
| Filesystem | stdio | `@modelcontextprotocol/server-filesystem` | File read/write |
| GitHub | stdio | `@modelcontextprotocol/server-github` | Repository operations |
| Slack | stdio | `@modelcontextprotocol/server-slack` | Message management |
| PostgreSQL | stdio | `@modelcontextprotocol/server-postgres` | Database queries |
| Brave Search | stdio | `@modelcontextprotocol/server-brave-search` | Web search |

---

## FAQ

**Q: Do I need to write any code to add MCP tools?**
A: No. Add a server to the configuration, restart, and tools are automatically discovered and registered.

**Q: Can users configure their own MCP servers?**
A: Yes! Feature 2.1 adds per-user MCP management. Users can add/edit/delete their own servers via Settings > Features > MCP Servers. See the "Per-User MCP (F2.1)" section below.

**Q: What happens if an MCP server goes down?**
A: The `mcp_server_health` gauge drops to 0. Tool calls to that server will fail with clear error messages. Other servers are unaffected.

**Q: Are MCP Resources and Prompts supported?**
A: Not in V1. Only Tools are supported. Resources and Prompts are YAGNI for now.

**Q: How are MCP tool results formatted?**
A: Text content is returned as-is. Image content shows `[Binary data]`. Multiple content parts are joined with newlines.

**Q: My OAuth MCP server returns 403 Forbidden on tool calls, but `list_tools` works. Why?**
A: The OAuth token was granted without sufficient scopes. `list_tools` is metadata-only (no scope required), but `call_tool` needs actual API permissions. Edit the server, add the required OAuth scopes (e.g., `repo project read:org` for GitHub), then re-authorize via "Connect OAuth". See the "OAuth 2.1 Scopes" section above.

**Q: How does domain description auto-generation work?**
A: When you test a connection (`POST /mcp/servers/{id}/test`) and the server has no manual `domain_description`, an LLM (configurable via `MCP_DESCRIPTION_LLM_*` env vars) analyzes the discovered tools and generates a description optimized for query routing. The prompt is in `domains/agents/prompts/v1/mcp_description_prompt.txt`. You can force-(re)generate a description at any time via `POST /mcp/servers/{id}/generate-description` or the "Generate description" button in the UI. If the LLM call fails, an algorithmic fallback produces a basic concatenation.

---

## Per-User MCP (Feature 2.1)

### Overview

Feature 2.1 extends MCP support to allow each user to declare, authenticate, and manage their own MCP servers. User MCP tools are isolated per-request via `ContextVar` and available only to the authenticated user's chat sessions.

**Key differences from admin MCP**:
- Transport: `streamable_http` only (no stdio for security)
- Auth: None, API Key, Bearer, OAuth 2.1 (PKCE + auto-refresh)
- Isolation: `ContextVar[UserMCPToolsContext]` per request (not global registry)
- Storage: `user_mcp_servers` table with Fernet-encrypted credentials
- Pool: `UserMCPClientPool` — tool metadata cache with **ephemeral connections** per tool call

### Architecture

```
Chat Request:
  1. setup_user_mcp_tools(user_id, db) → queries enabled+active servers
  2. For each server: pool.get_or_connect() → ephemeral connect → list_tools() → cache metadata
  3. Build UserMCPToolAdapter + ToolManifest per tool
  4. Set ContextVar user_mcp_tools_ctx

Pipeline:
  SmartCatalogueService → injects user MCP manifests from ContextVar
                        → bypasses semantic score for mcp_user_* tools
  ParallelExecutor → falls back to ContextVar for tool/manifest resolution
  UserMCPToolAdapter._arun() → pool.call_tool()
    → creates fresh ephemeral MCP connection (connect → initialize → call → close)

Cleanup:
  cleanup_user_mcp_tools(token) → resets ContextVar
```

> **Why ephemeral connections?** The MCP Python SDK's `streamablehttp_client` uses
> anyio task groups internally. When a session is stored in a long-lived pool, the
> background tasks die (cancel scope expires), causing `ClosedResourceError` /
> `CancelledError` on subsequent `call_tool()`. Ephemeral connections keep the full
> lifecycle (connect → initialize → call → close) within a single async scope,
> ensuring background tasks stay alive. The overhead (~1.5s handshake per call)
> is acceptable given typical MCP tool call latency (3-10s).

### Module Structure

```
apps/api/src/domains/user_mcp/
├── __init__.py
├── models.py          # UserMCPServer, UserMCPAuthType, UserMCPServerStatus
├── schemas.py         # Pydantic CRUD schemas
├── repository.py      # SQLAlchemy repository
├── service.py         # Business logic (CRUD, encryption, pool coordination)
└── router.py          # FastAPI endpoints (10 routes)

apps/api/src/infrastructure/mcp/
├── auth.py            # MCPNoAuth, MCPStaticTokenAuth, MCPOAuth2Auth, build_auth_for_server()
├── oauth_flow.py      # MCPOAuthFlowHandler (RFC 9728/8414 discovery, PKCE, callback)
├── user_pool.py       # UserMCPClientPool (tool metadata cache, ephemeral connections, rate limiting)
├── user_tool_adapter.py # UserMCPToolAdapter (BaseTool wrapper for per-user tools)
└── user_context.py    # setup/cleanup functions + user_mcp_session context manager
```

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/mcp/servers` | List user MCP servers |
| `POST` | `/api/v1/mcp/servers` | Create server |
| `PATCH` | `/api/v1/mcp/servers/{id}` | Update server |
| `DELETE` | `/api/v1/mcp/servers/{id}` | Delete server |
| `PATCH` | `/api/v1/mcp/servers/{id}/toggle` | Toggle enable/disable |
| `POST` | `/api/v1/mcp/servers/{id}/test` | Test connection + discover tools + auto-generate description |
| `POST` | `/api/v1/mcp/servers/{id}/generate-description` | Force-(re)generate domain description from cached tools |
| `POST` | `/api/v1/mcp/servers/{id}/oauth/authorize` | Start OAuth 2.1 flow |
| `POST` | `/api/v1/mcp/servers/{id}/oauth/disconnect` | Purge OAuth tokens (force re-auth) |
| `GET` | `/api/v1/mcp/servers/oauth/callback` | OAuth callback (no auth) |

### Authentication Strategy

| Auth Type | Storage | Injection |
|-----------|---------|-----------|
| `none` | — | Pass-through (MCPNoAuth) |
| `api_key` | `{header_name, api_key}` encrypted | Custom header via MCPStaticTokenAuth |
| `bearer` | `{token}` encrypted | `Authorization: Bearer` via MCPStaticTokenAuth |
| `oauth2` | `{client_id, client_secret, access_token, refresh_token, ...}` encrypted | Bearer + auto-refresh on 401 via MCPOAuth2Auth |

### OAuth 2.1 Scopes

OAuth scopes define the permissions requested during the authorization flow. Many MCP servers require specific scopes to allow tool calls (e.g., GitHub returns `403 Forbidden` if the token lacks the required scope).

**Configuration**: Users specify scopes as a space-separated string in the "OAuth Scopes" field when creating/editing a server (e.g., `repo project read:org`).

**Storage**: Scopes are stored in `oauth_metadata.requested_scopes` (JSONB column) — no additional DB migration required.

**Priority chain** (in `oauth_flow.py:initiate_flow()`):
1. User-specified `requested_scopes` (from the form field) — **highest priority**
2. Auto-discovered `scopes_supported` from OAuth metadata (RFC 8414 / OpenID)
3. Empty string (minimal permissions) — **fallback**

**Common OAuth scopes by provider**:

| Provider | MCP URL | Required Scopes | Notes |
|----------|---------|-----------------|-------|
| GitHub Copilot | `https://api.githubcopilot.com/mcp/` | `repo project read:org` | Without scopes, `list_tools` works but `call_tool` returns 403 |
| Slack | Varies | `channels:read chat:write` | Depends on which tools you use |
| Google | Varies | Provider-specific | Typically auto-discovered via OpenID |

**Why user-specified scopes?** Many providers (GitHub notably) don't advertise supported scopes via OAuth metadata discovery. The heuristic fallback constructs endpoints but returns `scopes_supported: []`. Without explicit scopes, the authorization server grants a minimal token insufficient for actual API calls.

**Disconnect & re-authorize flow**: When scopes change, the existing token is invalidated. Click "Disconnect OAuth" on an active OAuth server to purge tokens (preserving client_id/client_secret), then "Connect OAuth" to re-authorize with the updated scopes. Endpoint: `POST /api/v1/mcp/servers/{id}/oauth/disconnect`.

### Frontend UI

Settings > Features > MCP Servers (`MCPServersSettings.tsx`):

- **Create dialog**: Add a new server (name, URL, auth type, credentials). No test button — server must exist first.
- **Edit dialog**: Update server configuration + **Test Connection** button. The test calls `POST /mcp/servers/{id}/test` and displays:
  - Success/error badge with tool count
  - Error details if connection fails
  - **Discovered tools list** (tool name + description) in a scrollable area
- **Server cards**: Toggle enable/disable, edit, delete. Status badges (active, error, auth_required).
- Test is **not** a prerequisite for saving — the Save button is always active.
- **Credential merge on update**: When updating OAuth credentials (client_id/client_secret), the service merges new values into the existing encrypted blob, preserving OAuth tokens (access_token, refresh_token). Same merge pattern for API key (header_name + api_key) and Bearer (token). The `has_oauth_credentials` flag in the API response tells the frontend that saved OAuth client credentials exist, so the edit form shows "Credentials saved" placeholders.

### Pipeline Integration (2-Level Architecture)

User MCP servers are **first-class citizens** in the pipeline, integrated at two levels:

#### Level 1 — Per-Server Domain Detection (F2.2, LLM, QueryAnalyzerService)

Each user MCP server gets its own domain (e.g., `mcp_huggingface_hub`, `mcp_github`) instead of sharing a single `"mcp"` domain. The LLM sees distinct entries with server-specific descriptions and selects only the relevant server(s).

- **Slugification**: `slugify_mcp_server_name()` in `domain_taxonomy.py` converts server names to domain slugs (`mcp_<slug>`, max 40 chars)
- **Deduplication**: `deduplicate_mcp_slugs()` appends `_2`, `_3` on collision
- **Source**: `query_analyzer_service.py` replaces the generic "mcp" domain with N per-server entries from `UserMCPToolsContext.server_domains`
- **Description**: Uses `domain_description` if provided, otherwise auto-generates from discovered tool descriptions.
  - **Auto-generation at test time**: `test_connection()` auto-generates and persists `domain_description` when the field is empty, using `auto_generate_server_description()`.
  - **Force-regeneration**: `POST /mcp/servers/{id}/generate-description` regenerates the description from cached tools (overwrites any existing description). No network call — uses `discovered_tools_cache` from DB.
- **Dynamic fallback**: `get_domain_config()` and `get_result_key()` synthesize configs for `mcp_*` domains not in static `DOMAIN_REGISTRY`
- **Web search**: No explicit suppression needed — when MCP domain detected, intent="action" routes to planner (not response_node), so Knowledge Enrichment (Brave Search) is naturally skipped

#### Level 2 — Tool Selection (OpenAI Embeddings, SemanticToolSelector)

At server registration (test_connection), OpenAI text-embedding-3-small embeddings are pre-computed for each discovered tool's description and keywords, then stored in `tool_embeddings_cache` (JSONB). At request time, these embeddings are loaded into `UserMCPToolsContext.tool_embeddings` and passed as `extra_embeddings` to `select_tools()`, enabling real semantic scoring alongside native tools.

- **Computation**: `compute_tool_embeddings()` in `tool_selector.py` (batch embed, same pattern as `initialize()`)
- **Storage**: JSONB column keyed by raw MCP tool name (e.g., `"hub_search"`)
- **Re-keying**: `user_context.py` re-keys from raw name to adapter name (e.g., `"mcp_user_37e4468e_hub_search"`) at request setup
- **Scoring**: `select_tools(extra_embeddings=...)` falls back to extra_embeddings when tool not in singleton cache

#### Integration Points

1. **Router Node** (`router_node_v3.py`): Includes user MCP tools in scoring when any `mcp_*` domain detected (`is_mcp_domain()`). Passes `extra_embeddings` from ContextVar.
2. **Catalogue — Normal Filtering** (`normal_filtering.py`): Injects user MCP manifests from ContextVar. Per-server domains are detected by the LLM (no force-include).
3. **Catalogue — Panic Filtering** (`panic_filtering.py`): Injects user MCP manifests. Force-includes ALL per-server MCP domains as a safety net.
4. **Executor — Manifest lookup** (`parallel_executor.py:_get_tool_manifest_for_step`): ContextVar fallback when manifest not in global registry.
5. **Executor — Type coercion** (`parallel_executor.py:_execute_tool_step`): ContextVar fallback for tool instance resolution.
6. **Executor — Tool execution** (`parallel_executor.py:_execute_tool`): ContextVar fallback for tool invocation.

### Configuration

```env
# .env
MCP_USER_ENABLED=false                    # Master toggle (default: off)
MCP_USER_MAX_SERVERS_PER_USER=5           # Per-user server limit
MCP_USER_POOL_TTL_SECONDS=900             # Idle connection TTL (15 min)
MCP_USER_POOL_MAX_TOTAL=50                # Global pool connection limit
MCP_USER_POOL_EVICTION_INTERVAL=60        # Eviction check interval (seconds)
# MCP_USER_OAUTH_CALLBACK_BASE_URL=https://app.example.com

# Domain description auto-generation (LLM-based)
MCP_DESCRIPTION_LLM_PROVIDER=openai               # LLM provider (openai, anthropic, deepseek, perplexity, ollama, gemini)
MCP_DESCRIPTION_LLM_PROVIDER_CONFIG={}             # Advanced provider-specific config (JSON)
MCP_DESCRIPTION_LLM_MODEL=gpt-4.1-mini            # Cheap/fast model for description generation
MCP_DESCRIPTION_LLM_TEMPERATURE=0.3                # Low temperature for consistent results
MCP_DESCRIPTION_LLM_TOP_P=1.0                      # Nucleus sampling (1.0 = disabled)
MCP_DESCRIPTION_LLM_FREQUENCY_PENALTY=0.0          # Frequency penalty
MCP_DESCRIPTION_LLM_PRESENCE_PENALTY=0.0           # Presence penalty
MCP_DESCRIPTION_LLM_MAX_TOKENS=300                 # Max output tokens
# MCP_DESCRIPTION_LLM_REASONING_EFFORT=             # OpenAI o-series/GPT-5 only
```

#### Domain Description Auto-Generation

When a user tests a connection (`POST /mcp/servers/{id}/test`) and no manual `domain_description` is set, an LLM analyzes the discovered tools and generates a description optimized for query routing. The prompt is in `domains/agents/prompts/v1/mcp_description_prompt.txt`. If the LLM call fails, an algorithmic fallback (`auto_generate_server_description()`) produces a basic concatenation.

Users can also force-(re)generate a description via `POST /mcp/servers/{id}/generate-description` using the tool cache from the last test.

### Security

| Measure | Detail |
|---------|--------|
| No stdio | Only `streamable_http` for user servers |
| SSRF prevention | `validate_http_endpoint()` on all URLs |
| Encrypted credentials | Fernet via `encrypt_data()`/`decrypt_data()` |
| Credentials never exposed | API response excludes `credentials_encrypted`. Only boolean flags (`has_credentials`, `has_oauth_credentials`) and non-sensitive metadata (`header_name`) are returned |
| Ownership isolation | All operations verify `user_id` match |
| Per-user limits | `MCP_USER_MAX_SERVERS_PER_USER` (default 5) |
| Global pool limit | `MCP_USER_POOL_MAX_TOTAL` (default 50) |
| HITL by default | Inherits `MCP_HITL_REQUIRED=true` |
| Rate limiting | Per-server sliding window |
| OAuth PKCE | S256 code_challenge_method |
| State single-use | Redis TTL 5min, deleted after consumption |
| OAuth metadata discovery | 3-strategy fallback (RFC 8414 → OpenID → heuristic) |

### OAuth 2.1 Metadata Discovery

The `MCPOAuthFlowHandler.discover_auth_server()` discovers the authorization server for a given MCP URL using 4 strategies in order:

1. **RFC 9728** — `.well-known/oauth-protected-resource` on the MCP server (returns `authorization_servers[]`)
2. **WWW-Authenticate** — Unauthenticated request to MCP URL, parse `resource_metadata` from 401 header
3. **RFC 8414** — `.well-known/oauth-authorization-server` on the auth server base URL
4. **OpenID Connect** — `.well-known/openid-configuration` fallback

When strategies 3 & 4 fail (e.g., GitHub doesn't implement RFC 8414), a **convention-based heuristic** probes `{auth_server_url}/authorize`. If the endpoint exists (any status except 404/5xx), it constructs:

- `authorization_endpoint` = `{auth_server_url}/authorize`
- `token_endpoint` = `{auth_server_url}/access_token`
- `code_challenge_methods_supported` = `["S256"]` (assumed per MCP spec)

This heuristic handles providers like GitHub (`https://github.com/login/oauth`) that expose conventional sub-path endpoints without serving RFC 8414 metadata.

**Example: GitHub Copilot MCP**

```
MCP URL: https://api.githubcopilot.com/mcp/
 → Strategy 1: .well-known/oauth-protected-resource → authorization_servers: ["https://github.com/login/oauth"]
 → Strategy 3: .well-known/oauth-authorization-server on github.com → 404 (GitHub ≠ RFC 8414)
 → Strategy 4: .well-known/openid-configuration on github.com → 404
 → Heuristic: GET https://github.com/login/oauth/authorize → 200 ✓
 → Result: authorize=.../authorize, token=.../access_token, PKCE=S256
```

---

## Per-Server Domain Routing (Feature 2.2)

### Problem

All user MCP servers shared a single `"mcp"` domain. The LLM couldn't distinguish between servers (HuggingFace vs GitHub), so **all** MCP tools were injected whenever `"mcp"` was detected — defeating the purpose of SmartCatalogueService's targeted filtering.

### Solution

Each MCP server gets its own domain identifier (e.g., `mcp_huggingface_hub`). The LLM sees separate entries with specific descriptions and selects only the relevant server(s).

### Flow

```
BEFORE: LLM sees → "mcp: User MCP tools — HuggingFace: desc | GitHub: desc"
        LLM returns → primary_domain="mcp" → ALL MCP tools injected

AFTER:  LLM sees → "mcp_huggingface_hub: Search ML models on HuggingFace"
                  → "mcp_github: Repository management and code search"
        LLM returns → primary_domain="mcp_huggingface_hub" → ONLY HuggingFace tools
```

### Key Components

| Component | File | Role |
|-----------|------|------|
| `MCP_DOMAIN_PREFIX` | `agents/constants.py` | `"mcp_"` prefix constant |
| `slugify_mcp_server_name()` | `registry/domain_taxonomy.py` | Server name → domain slug |
| `deduplicate_mcp_slugs()` | `registry/domain_taxonomy.py` | Handle slug collisions |
| `is_mcp_domain()` | `registry/domain_taxonomy.py` | Check if domain is per-server MCP |
| `server_domains` | `core/context.py` | Per-request mapping (server_name → slug) |
| `_build_user_tool_manifest()` | `infrastructure/mcp/user_context.py` | Per-server `agent` field |

### Bugfix: `removesuffix` vs `replace`

Domain extraction throughout the pipeline used `agent_name.replace("_agent", "")`. This breaks when "agent" appears in the server name (e.g., "Agent Smith" → slug `mcp_agent_smith` → agent `mcp_agent_smith_agent`):

- **`replace("_agent", "")`** → `"mcp_smith"` (WRONG: removes ALL occurrences)
- **`removesuffix("_agent")`** → `"mcp_agent_smith"` (CORRECT: only removes suffix)

Fixed in 5 locations: `smart_catalogue_service.py`, `router_node_v3.py`, `semantic_validator.py`, `streaming/service.py`, `expansion_service.py`.

### Backward Compatibility

- Base `"mcp"` domain remains in `DOMAIN_REGISTRY` for admin MCP servers (no user context)
- `get_domain_config()` / `get_result_key()` synthesize configs for dynamic `mcp_*` domains
- `context_key` remains `CONTEXT_DOMAIN_MCP` ("mcps") — no change to `$steps` references

---

## HTML Card Display (Feature 2.3)

### Problem

MCP tools returned raw strings from `_arun()`, bypassing the Data Registry → HTML card rendering pipeline. While all other domains (contacts, emails, weather, etc.) produce `RegistryItem` → `UnifiedToolOutput` → HTML cards via `HtmlRenderer`, MCP results appeared as unformatted text.

Root cause: `parallel_executor` uses `tool.coroutine(**args)` for `StructuredTool` (preserves `UnifiedToolOutput`), but falls back to `tool.ainvoke()` for `BaseTool` subclasses — which stringifies the result via `ToolMessage(content=str(result))`.

### Solution: Coroutine Bridge

Added a `@property coroutine` on `UserMCPToolAdapter` (a `BaseTool` subclass) that returns `self._arun`. The `parallel_executor` (line ~2420) checks `hasattr(tool, "coroutine") and tool.coroutine is not None` — with the property, it takes the direct call path, preserving `UnifiedToolOutput`.

**Why a property?** `BaseTool` (LangChain) does NOT have a `coroutine` attribute — only `StructuredTool` does. Adding a `@property` on a Pydantic v2 `BaseTool` subclass is safe (properties are NOT model fields).

### Flow

```
UserMCPToolAdapter._arun(**kwargs)
  → pool.call_tool() → raw_result (str)
  → Build RegistryItem(type=MCP_RESULT, payload={tool_name, server_name, result})
  → Return UnifiedToolOutput.data_success(registry_updates={...})
  ↓
parallel_executor
  → hasattr(tool, "coroutine") → True (property bridge)
  → await tool.coroutine(**args) → UnifiedToolOutput preserved
  → Extract registry_updates → inject turn_id, step_id
  ↓
task_orchestrator_node → merge into state["registry"]
  ↓
response_node._extract_payloads_from_registry()
  → Group by meta.domain → "mcps" → [payload1, payload2, ...]
  ↓
HtmlRenderer.render("mcps", {...}, config)
  → McpResultCard.render_list(items, ctx)
  → HTML cards with server badge + tool name + content
```

### Card Component: McpResultCard

Located in `display/components/mcp_result_card.py`. Follows the `ReminderCard` pattern (uses `wrap_with_response`).

**Two rendering modes** (dispatched by `_mcp_structured` flag in payload):

1. **Structured mode** (`_mcp_structured=True`): For JSON array results parsed by F2.4.
   - **Title**: Auto-detected from `_TITLE_FIELDS` (name, title, subject, label, display_name, full_name)
   - **Description**: Auto-detected from `_DESCRIPTION_FIELDS` (description, summary, body, text)
   - **Details**: Up to 5 additional fields as key-value pairs, values truncated at 100 chars

2. **Raw mode** (fallback): For plain text or non-iterable JSON results.
   - **Badge**: Server name with puzzle piece icon (`Icons.EXTENSION`), format: "MCP · {server_name}"
   - **Title**: Humanized tool name (underscores → spaces, title case)
   - **Content**: Auto-detects JSON (starts with `{` or `[`) → `<pre>` block; otherwise plain text with `<br>` newlines, truncated to 2000 chars

**CSS classes** (BEM): `lia-card lia-mcp`, `lia-mcp__content`, `lia-mcp__content--json`

### RegistryItem Payload Structure

Two payload shapes depending on the result format:

**Structured items** (JSON array → one RegistryItem per item, F2.4):

```python
RegistryItem(
    id="mcp_result_<hash>",
    type=RegistryItemType.MCP_RESULT,
    payload={
        "tool_name": "search_models",
        "server_name": "HuggingFace Hub",
        "_mcp_structured": True,           # Triggers structured card rendering
        "name": "bert-base-uncased",       # Item fields spread into payload
        "downloads": 42000000,
        FIELD_REGISTRY_ID: "mcp_result_<hash>",  # For for_each expansion
    },
    meta=RegistryItemMeta(
        source="mcp_user_abc12345",
        domain="mcps",
        tool_name="mcp_user_abc12345_search_models",
    ),
)
```

**Raw result** (plain text or non-iterable JSON → single RegistryItem):

```python
RegistryItem(
    id="mcp_result_<hash>",
    type=RegistryItemType.MCP_RESULT,
    payload={
        "tool_name": "search_models",
        "server_name": "HuggingFace Hub",
        "result": "42 models found...",    # Raw result string
    },
    meta=RegistryItemMeta(
        source="mcp_user_abc12345",
        domain="mcps",
        tool_name="mcp_user_abc12345_search_models",
    ),
)
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `@property coroutine` bridge | Least-invasive way to preserve `UnifiedToolOutput` through `parallel_executor` without modifying the executor itself |
| `time.time_ns()` for unique key | Python randomizes hash seeds since 3.3 — `hash(str(kwargs))` is non-deterministic across processes |
| `server_display_name` field | Human-readable name (e.g., "HuggingFace Hub") vs `server_name_label` (e.g., "user_abc12345") for Prometheus |
| Single `"mcps"` domain for all servers | One card component for all MCP results; server differentiation via `payload.server_name` |
| No `TOOL_PATTERN_TO_DOMAIN_MAP` entry | `meta.domain = "mcps"` is the source of truth. Pattern matching would cause false matches (e.g., `mcp_user_abc_send_email` → "emails") |

---

## Structured Items Parsing (Feature 2.4)

### Problem

MCP tools returning JSON arrays (e.g., `list_commits`, `search_repositories`) produced a single `RegistryItem` with the entire array as a string. This prevented:
- Individual item cards in the response
- `for_each` expansion (e.g., "detail du 2ème")
- Structured rendering with title/description auto-detection

### Solution

`UserMCPToolAdapter._arun()` auto-detects JSON array results and creates **one RegistryItem per item**, capped at `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` (default 25).

### Flow

```
MCP call_tool() → raw_result (str)
  ↓
_parse_mcp_structured_items(raw_result)
  → JSON array of dicts? → (items_list, detected_key)
  → Dict wrapping an array? → find largest list-of-dicts value
  → Otherwise → None (fallback to raw rendering)
  ↓
_derive_collection_key(tool_name)
  → Strip verb prefix (search_, list_, get_, find_, fetch_, query_, create_, delete_, update_)
  → Pluralize remainder: "search_repositories" → "repositories", "get_user" → "users"
  → Default: "items"
  ↓
For each item (up to MCP_MAX_STRUCTURED_ITEMS_PER_CALL):
  → RegistryItem with _mcp_structured=True + item fields spread into payload
  → FIELD_REGISTRY_ID for for_each expansion support
  ↓
structured_data = {collection_key: [items_with_registry_id]}
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` | `25` | Maximum items parsed from a single tool call (1-200). Prevents registry explosion for paginated APIs. |

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `_mcp_structured` flag in payload | Lets McpResultCard dispatch between structured/raw rendering without checking item count or format |
| Collection key from tool name | Predictable naming (e.g., `"repositories"`) for `structured_data` and `for_each` references |
| Verb prefix stripping | MCP tool names follow `verb_noun` convention. Stripping the verb gives the entity type. |
| Cap at 25 items (configurable) | Prevents registry explosion while covering typical API page sizes (10-25 items) |

---

## OAuth 2.1 Advanced Patterns

### Token Response Compatibility

The `handle_callback()` token exchange supports both `application/json` and `application/x-www-form-urlencoded` responses. Some providers (notably GitHub) return form-urlencoded despite the `Accept: application/json` header. The `_parse_token_response()` method tries JSON first, then falls back to `parse_qs()` parsing.

### OAuth Refresh Distributed Lock

Token refresh uses a Redis distributed lock (`mcp_oauth_refresh_lock:{server_id}`, TTL `MCP_OAUTH_REFRESH_LOCK_TTL_SECONDS` = 15s) to prevent concurrent requests from simultaneously refreshing the same token. If the lock is already held, the request re-reads fresh credentials instead of refreshing. This follows the same pattern as the Google `OAuthLock` in `infrastructure/locks/`.

### Tool Name Fuzzy Resolution

`UserMCPToolsContext.resolve_tool_name()` handles LLM-hallucinated suffixes (`_tool`, `_action`) that the planner may append to MCP tool names. For example, `mcp_user_xxx_hub_search_tool` resolves to `mcp_user_xxx_hub_search`. This fuzzy matching is used by `parallel_executor` and `approval_gate_node` for tool/manifest resolution via `resolve_tool_manifest()`.

---

## Admin MCP Per-Server Routing & User Toggle (Feature 2.5)

### Overview

Admin MCP servers are now registered as **per-server agents** (one agent per MCP server) instead of a single generic `mcp_agent`. This enables targeted domain routing by the query analyzer — the LLM selects only the relevant MCP server(s) for each user query.

Users can also **toggle individual admin MCP servers** on/off from Settings > Features > "MCP Applicatifs".

### Per-Server Agent Registration

At startup, `register_mcp_tools()` creates one `AgentManifest` per server:

| Server Key | Domain Slug | Agent Name | Description |
|------------|-------------|------------|-------------|
| `google_flights` | `mcp_google_flights` | `mcp_google_flights_agent` | "Search flights, find airports, ..." |
| `filesystem` | `mcp_filesystem` | `mcp_filesystem_agent` | Auto-generated from tool descriptions |

- **Description source**: `MCPServerConfig.description` (from `.env`) or auto-generated via `auto_generate_server_description()`.
  - `auto_generate_server_description(tool_descriptions, server_name, tool_names=None)` extracts the first sentence of up to 5 tool descriptions, prefixes with `MCP {server_name}:`, and caps at 200 chars.
  - Optional `tool_names` param provides fallback context when descriptions are unavailable.
- **Module-level domain store**: `registration.py._admin_mcp_domains` (populated at startup, read by `collect_all_mcp_domains()`).

### Unified Domain Routing (DRY: admin + user MCP)

`domain_taxonomy.collect_all_mcp_domains()` merges admin and user MCP domains into a single list for the query analyzer prompt:

1. **Admin MCP** — from `get_admin_mcp_domains()` (startup registration), filtered by `admin_mcp_disabled_ctx` (user preference).
2. **User MCP** — from `user_mcp_tools_ctx` ContextVar (per-request).

This replaces the previous separate admin/user injection blocks in `query_analyzer_service.py`.

### Per-User Toggle

| Layer | Component | Description |
|-------|-----------|-------------|
| DB | `User.admin_mcp_disabled_servers` (JSONB) | List of server keys disabled by this user |
| API | `GET /api/v1/mcp/admin-servers` | List all admin servers with tools + toggle status |
| API | `PATCH /api/v1/mcp/admin-servers/{key}/toggle` | Toggle a server on/off for current user |
| ContextVar | `admin_mcp_disabled_ctx` | Propagated per-request in `AgentService._stream_with_new_services()` |
| Filter | `collect_all_mcp_domains()` | Filters out disabled servers before query analysis |

### Defense-in-Depth for Per-User Server Toggle (ADR-061)

When a user disables an admin MCP server, three independent layers enforce the restriction. See [ADR-061](../architecture/ADR-061-Centralized-Component-Activation.md) for the full rationale.

```
Layer 1 — Domain gate-keeper (query_analyzer_service.py)
  Validates LLM-output domains against available_domains.
  Disabled server's domain is stripped before it can enter the pipeline
  → 0 tools from that domain are scored, planned, or executed.

Layer 2 — Centralized tool manifest ContextVar (context.py)
  request_tool_manifests_ctx holds a pre-filtered manifest list built once
  per request (after admin_mcp_disabled_ctx is set). Every consumer
  (router, catalogue strategies, expansion service, planner) reads the
  same pre-filtered list — no per-consumer filtering needed.

Layer 3 — API guard (admin_router.py + client_manager.py)
  The MCP Apps proxy endpoints (POST admin-servers/{key}/app/call-tool and
  admin-servers/{key}/app/read-resource) bypass the agent pipeline entirely
  (iframe → HTTP → MCP client). These endpoints return HTTP 403 when the
  target server is in the user's disabled list. MCPClientManager performs
  an additional check as defense in depth.
```

| Layer | Component | Mechanism |
|-------|-----------|-----------|
| 1 — Domain gate-keeper | `query_analyzer_service.py` | Strips disabled domains from LLM output |
| 2 — Manifest ContextVar | `context.py` → `request_tool_manifests_ctx` | Pre-filtered manifests, set once, read everywhere |
| 3 — API guard | `admin_router.py` + `MCPClientManager` | HTTP 403 on proxy endpoints + client-level check |

#### `request_tool_manifests_ctx` — Centralized Tool Manifest ContextVar

`request_tool_manifests_ctx` is a per-request `ContextVar[list[ToolManifest]]` that serves as the **single source of truth** for tool availability during a request. It replaces the previous pattern of scattered `registry.list_tool_manifests()` calls that each had to independently apply their own disabled-server filtering.

| Item | Detail |
|------|--------|
| **Builder** | `build_request_tool_manifests(registry)` in `src/core/context.py` — combines registry manifests minus disabled admin MCP, plus user MCP tools from `user_mcp_tools_ctx` |
| **Accessor** | `get_request_tool_manifests()` — returns the pre-built list; logs a warning if called outside the request lifecycle |
| **Setup** | `AgentService._stream_with_new_services()`, after `admin_mcp_disabled_ctx` and `user_mcp_tools_ctx` are set |
| **Consumers** | Router node, catalogue strategies (normal + panic), expansion service, planner — all read from this ContextVar instead of calling the registry directly |
| **Sub-agents** | Automatically inherit the filtered list via async `ContextVar` propagation |

Adding a new toggleable component type requires only filtering it in `build_request_tool_manifests()` (manifest level) or `_build_available_domains()` (domain level) — no changes needed in any consumer.

### Docker-Internal Servers

Admin MCP servers running as Docker containers (e.g., `google-flights`) need the `internal: true` flag to bypass SSRF validation:

```json
{
  "google_flights": {
    "transport": "streamable_http",
    "url": "http://google-flights:8000/mcp",
    "internal": true,
    "description": "Search flights, find airports, compare prices",
    "hitl_required": false
  }
}
```

When `internal=true`, the server URL is not validated for HTTPS or private IP restrictions (trusted admin-configured only).

### Frontend

- **Component**: `AdminMCPServersSettings.tsx` (Settings > Features tab)
- **Hook**: `useAdminMCPServers.ts` (GET list + PATCH toggle)
- **i18n keys**: `settings.admin_mcp.*` (6 languages)
- **Behavior**: Auto-hides if no admin MCP servers configured. Shows server name, description, tool count, toggle switch, and expandable tool list.

---

## MCP Apps — Interactive HTML Widgets (Feature 2.6)

### Overview

MCP Apps (SEP-1865) enable interactive HTML widgets rendered via sandboxed iframes in the chat interface. When an MCP tool exposes UI metadata (`Tool.meta.ui.resourceUri` and `visibility`), the backend fetches the associated HTML resource after `call_tool()` and creates an `MCP_APP` RegistryItem. The frontend `McpAppWidget` renders the HTML in a sandboxed iframe with a JSON-RPC bridge for bidirectional communication.

This extends the existing MCP result display (F2.3 HTML cards) with a fully interactive experience: forms, dynamic content, and tool invocations initiated from within the iframe.

### Architecture

```
Tool Discovery:
  session.list_tools() → Tool.meta.ui.resourceUri + Tool.meta.ui.visibility
    → Store UI metadata on MCPToolAdapter / UserMCPToolAdapter

Runtime (tool with UI):
  call_tool() → raw result
    ↓
  read_resource(resourceUri) → HTML content
    ↓ (success)
  RegistryItem(type=MCP_APP, payload={html, tool_name, server_name, ...})
    ↓
  Frontend McpAppWidget → sandboxed iframe + JSON-RPC bridge
    ↓ (failure)
  Fallback → standard MCP_RESULT card (graceful degradation)
```

**Key components**:

| Component | Location | Role |
|-----------|----------|------|
| UI metadata extraction | `tool_adapter.py` / `user_tool_adapter.py` | Extracts `resourceUri` and `visibility` from `Tool.meta.ui` during discovery |
| HTML resource fetch | `tool_adapter.py` / `user_tool_adapter.py` | Calls `session.read_resource(resourceUri)` after `call_tool()` |
| `MCP_APP` RegistryItem | `orchestration/parallel_executor.py` | New `RegistryItemType` for app widgets |
| `McpAppWidget` | `apps/web/src/components/chat/` | React component rendering sandboxed iframe |
| JSON-RPC bridge | `McpAppWidget` | `postMessage` bridge between iframe and host |
| Proxy endpoints | `domains/user_mcp/router.py` / `infrastructure/mcp/admin_router.py` | HTTP proxy for iframe-initiated MCP calls |

### JSON-RPC Bridge Protocol

Communication between the sandboxed iframe (View) and the host application uses `window.postMessage` with JSON-RPC 2.0 format, following the [MCP Apps ext-apps specification (2026-01-26)](https://apps.extensions.modelcontextprotocol.io/api/).

**Initialization lifecycle**:

```
1. View → Host: ui/initialize (request with appCapabilities, protocolVersion)
2. Host → View: response (hostCapabilities, hostInfo, hostContext with toolInfo/theme/locale)
3. View → Host: ui/notifications/initialized (notification)
4. Host → View: ui/notifications/tool-input (notification with tool arguments)
5. Host → View: ui/notifications/tool-result (notification with tool result content)
```

**Supported methods**:

| Method | Direction | Type | Description |
|--------|-----------|------|-------------|
| `ui/initialize` | View → Host | Request | View initiates handshake; Host responds with capabilities and context |
| `ui/notifications/initialized` | View → Host | Notification | View confirms initialization; Host then delivers tool data |
| `ui/notifications/tool-input` | Host → View | Notification | Host sends complete tool call arguments |
| `ui/notifications/tool-result` | Host → View | Notification | Host sends tool execution result (content + structuredContent) |
| `tools/call` | View → Host | Request | View requests a tool invocation via the proxy endpoint |
| `resources/read` | View → Host | Request | View requests a resource read via the proxy endpoint |
| `ui/open-link` | View → Host | Request | View requests opening an external URL (https:// only) |
| `ui/message` | View → Host | Request | View sends a message to the chat (acknowledged, no-op) |
| `ui/resource-teardown` | Host → View | Request | Host signals cleanup before iframe removal |
| `ui/notifications/size-changed` | View → Host | Notification | View reports size change |

**Request format** (View → Host):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "tool_name",
    "arguments": { "key": "value" }
  }
}
```

**Response format** (Host → View):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": { "content": [...] }
}
```

**Payload fields**: The `McpAppRegistryPayload` includes `tool_arguments` (original tool call arguments) in addition to `tool_result` (raw result string), enabling the bridge to send both `ui/notifications/tool-input` and `ui/notifications/tool-result` per the spec.

### Proxy Endpoints

Iframe-initiated MCP calls are routed through dedicated proxy endpoints on the backend, since the sandboxed iframe cannot directly reach MCP servers.

| Endpoint | Scope | Description |
|----------|-------|-------------|
| `POST /api/v1/mcp/servers/{server_id}/app/tools/call` | User MCP | Proxy `call_tool()` for per-user MCP servers |
| `POST /api/v1/mcp/servers/{server_id}/app/resources/read` | User MCP | Proxy `read_resource()` for per-user MCP servers |
| `POST /api/v1/mcp/admin-servers/{server_key}/app/tools/call` | Admin MCP | Proxy `call_tool()` for admin MCP servers |
| `POST /api/v1/mcp/admin-servers/{server_key}/app/resources/read` | Admin MCP | Proxy `read_resource()` for admin MCP servers |

All proxy endpoints require authenticated session (BFF cookie) and enforce the same rate limiting as direct tool calls.

### Security

MCP Apps run in a heavily sandboxed environment to prevent XSS, data exfiltration, and privilege escalation.

| Control | Implementation |
|---------|---------------|
| Iframe sandbox | `sandbox="allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox"` — **without** `allow-same-origin` (prevents access to host cookies, localStorage, DOM); `allow-popups` required for `ui/open-link` to open URLs in new tabs |
| Origin validation | `McpAppWidget` validates `event.origin` on all incoming `postMessage` events |
| URL validation for `ui/open-link` | Only `https://` URLs are opened; others are silently rejected |
| No direct MCP access | Iframe cannot reach MCP servers directly; all calls go through authenticated proxy endpoints |
| CSP headers | Proxy responses include restrictive `Content-Security-Policy` headers |
| Rate limiting | Proxy endpoints share the same rate limits as standard MCP tool calls |

### Graceful Degradation

If `read_resource(resourceUri)` fails (network error, resource not found, server unavailable), the system falls back to the standard `MCP_RESULT` card rendering from F2.3. This ensures that MCP Apps are a progressive enhancement — tools continue to work even when the UI resource is unavailable.

```
read_resource(resourceUri)
  ↓ success → MCP_APP RegistryItem (interactive iframe)
  ↓ failure → MCP_RESULT RegistryItem (standard card, same as F2.3)
```

A warning is logged via structlog when the fallback is triggered, including the server name, tool name, and error details.

### Visibility Control

Tools can declare their `visibility` in `Tool.meta.ui`:

| Visibility | Behavior |
|------------|----------|
| `["app"]` | Iframe-only tool — skipped from the LLM tool catalogue (not available for autonomous agent selection). Only invocable via the iframe JSON-RPC bridge. |
| `["llm"]` | Standard tool — available in the LLM catalogue, no iframe rendering. |
| `["llm", "app"]` | Dual-mode — available to both the LLM catalogue and iframe rendering. |
| Not specified | Defaults to `["llm"]` (backward-compatible, standard tool behavior). |

The `SmartCatalogueService` filters out tools with `app_visibility == ["app"]` during catalogue building, ensuring these tools are invisible to the planner and agents but remain callable through the proxy endpoints.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `sandbox` without `allow-same-origin` | Strongest isolation — iframe cannot access host cookies, storage, or DOM even if the HTML content is malicious |
| JSON-RPC 2.0 over postMessage | Standard MCP Apps protocol (ext-apps spec 2026-01-26); View-initiated handshake with capability negotiation |
| Proxy endpoints instead of direct iframe-to-MCP | Iframe has no credentials or network access to MCP servers; proxy reuses existing auth + rate limiting infrastructure |
| Fallback to MCP_RESULT on resource fetch failure | Progressive enhancement — MCP Apps are optional UI; tool results are always available as structured cards |
| `["app"]` visibility filter in catalogue | Prevents LLM from selecting UI-only tools that would produce no meaningful text result |
| Auto-inject `read_me` content into planner prompt | Plan-then-execute architecture generates ALL parameters at planning time. Without format reference, the planner produces chaotic output (e.g., Excalidraw elements) |
| Exclude `read_me` from tool catalogue when auto-injected | Saves tokens and prevents the planner from generating a 2-step plan (read_me + create_view) when a 1-step plan suffices |

### Reference Content Auto-Injection

MCP servers following the `read_me` convention expose a tool that returns format documentation (e.g., Excalidraw's 27KB element format reference). In a native MCP client (Claude Desktop), the LLM calls `read_me`, reads the result, then calls the target tool with properly formatted parameters. In LIA's plan-then-execute architecture, ALL step parameters are generated at planning time, so the planner never reads `read_me` output before generating parameters.

**Solution**: 5-step pipeline ensuring the planner LLM has both structural schema information AND format reference documentation. Supported by **both** admin MCP (`MCPClientManager`) and per-user MCP (`UserMCPClientPool`).

**Pipeline**:
```
1. Discovery:
   - Admin MCP: MCPClientManager.discover_tools() → _fetch_reference_content() → self._reference_content[server_name]
   - User MCP:  _discover_tools() → list_tools() + call_tool("read_me") → PoolEntry.reference_content

2. Schema injection: json_schema_to_parameters() → _compact_json_schema()
   Complex MCP params (array, object) get their full JSON Schema (up to 5 levels deep)
   stored in ParameterSchema.schema → serialized in catalogue as "schema" field

3. Context propagation:
   - Admin MCP: MCPClientManager.reference_content property (persistent, available at startup)
   - User MCP:  setup_user_mcp_tools() → ctx.server_reference_content[server_name] = content
   Both sources: read_me excluded from tool catalogue to avoid 2-step plans

4. Prompt injection: SmartPlannerService._build_mcp_reference()
   → Merges admin + user MCP reference content (admin first, user overrides on conflict)
   → Dedicated {mcp_reference} placeholder (after {catalogue}, not in {context})
   → MANDATORY directive with cross-reference to catalogue parameter names
   → Line-aware truncation (rfind("\n") to avoid breaking JSON examples)

5. Planner LLM generates parameters with:
   - Structural schema in catalogue (type, items, properties, enum, required)
   - Format reference documentation right after catalogue (authoritative position)
```

**Key design choices**:
- `{mcp_reference}` is a dedicated prompt placeholder, placed immediately after `{catalogue}` for proximity (not in `{context}` which is generic)
- Directive uses strong language ("MANDATORY", "you MUST follow") to override LLM tendency to hallucinate schemas
- Cross-reference instruction: "Match parameter names from the catalogue above" links catalogue ↔ reference
- `_compact_json_schema()` depth limit is 5 (sufficient for Excalidraw's deepest schemas; MCP App usage is occasional, token cost is acceptable)

**Constants**: `MCP_REFERENCE_TOOL_NAME` (convention name), `MCP_REFERENCE_CONTENT_MAX_CHARS_DEFAULT` (truncation limit, default 30000 chars to preserve full read_me content including examples, configurable via `MCP_REFERENCE_CONTENT_MAX_CHARS` env var; 0 disables injection).

**Degradation**: If `read_me` call fails (admin or user), the planner works normally without the reference (try/except with silent pass). `_build_mcp_reference()` merges both admin (`MCPClientManager.reference_content`) and user (`ctx.server_reference_content`) sources — if neither has content, returns empty string and the `{mcp_reference}` placeholder produces no output.

---

## Iterative Mode / ReAct Sub-Agent (Feature 2.7)

When `iterative_mode=true` on an MCP server (admin or user), the planner sees a single task delegation tool instead of individual server tools. This tool launches a **ReAct sub-agent** that interacts iteratively with the server.

### Admin MCP Iterative Mode

- **Registration**: At startup, `register_mcp_tools()` in `registration.py` detects `iterative_mode=true` + `MCP_REACT_ENABLED=true`.
- **Tool registry**: Individual tools go to central `tool_registry` (for ReAct agent). A single `mcp_{server_name}_task` tool is registered via `_register_iterative_task_tool()`.
- **Catalogue**: Only the task tool manifest is visible to the planner.
- **Execution**: `mcp_server_task_tool()` → `_run_mcp_react_task()` → `ReactSubAgentRunner`.

### User MCP Iterative Mode

- **Registration**: Per-request in `setup_user_mcp_tools()` (`user_context.py`). Detects `server.iterative_mode=True` + `settings.mcp_react_enabled`.
- **ContextVar**: Individual tools stored in `ctx.tool_instances` (for ReAct agent). A single `mcp_user_{id_prefix}_task` tool + manifest exposed to the planner.
- **Execution**: `mcp_user_server_task_tool()` → `_run_mcp_react_task()` → `ReactSubAgentRunner`.
- **Reference content**: Skipped in planner prompt for iterative servers (tracked via `ctx.iterative_servers`). The ReAct agent calls `read_me` itself.

### Shared Infrastructure

| Component | File | Purpose |
|-----------|------|---------|
| `build_mcp_react_task_manifest()` | `registration.py` | Shared ToolManifest factory for admin + user task tools |
| `_run_mcp_react_task()` | `mcp_react_tools.py` | Shared ReAct execution (runner + structured output) |
| `_MCPReActWrapper` | `mcp_react_tools.py` | Wraps MCPToolAdapter/UserMCPToolAdapter for ReAct string output. Catches all exceptions (including `ExceptionGroup`) and returns error strings for ReAct retry. |
| `_has_mcp_app_tools()` | `mcp_react_tools.py` | Detects MCP App servers (tools with `app_resource_uri`) for LLM type selection |
| `MCP_ITERATIVE_TASK_SUFFIX` | `constants.py` | `"_task"` suffix for per-server task tool names |
| `MCP_DISPLAY_EMOJI` | `constants.py` | `🔌` emoji shared by all MCP tool manifests |

### LLM Type Selection

The ReAct agent automatically selects the appropriate LLM based on server type:

| Server type | LLM type | Default model | Rationale |
|-------------|----------|---------------|-----------|
| MCP App (has `app_resource_uri`) | `mcp_app_react_agent` | Opus | Complex multi-step workflows with interactive widgets |
| Regular MCP | `mcp_react_agent` | Qwen | Simpler tool chains, cost-efficient |

Detection is automatic via `_has_mcp_app_tools()` — if any tool in the server has an `app_resource_uri`, the MCP App LLM is used. Configurable in the admin LLM Config panel.

### Error Recovery

`_MCPReActWrapper` catches all exceptions from MCP tool calls and returns them as `"ERROR: ..."` strings. This allows the ReAct agent to:
1. Read the error message (e.g., "Expected string, received null for projectId")
2. Reason about the cause
3. Retry with corrected parameters

Without this, `ExceptionGroup` from the MCP SDK's anyio task groups would crash the entire ReAct loop.

### Step Timeout

MCP iterative tools run a multi-iteration ReAct agent loop that needs significantly more time than single tool calls. The parallel executor enforces a minimum timeout of **120s** (configurable via `mcp_react_step_timeout_seconds`) for any tool ending with `_task` (the `MCP_ITERATIVE_TASK_SUFFIX`). This override uses `max(planner_timeout, 120)` to ensure the floor is respected even when the planner LLM specifies a lower value.

### Requirements

- `MCP_REACT_ENABLED=true` (global feature flag)
- `iterative_mode=true` on the server (admin config or user toggle)
- Prompt file: `prompts/v1/mcp_react_agent_prompt.txt`

---

## Constants Reference

### `core/constants.py` — MCP Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `MCP_TOOL_NAME_PREFIX` | `"mcp"` | Prefix for admin MCP tool names |
| `MCP_DEFAULT_TIMEOUT_SECONDS` | `30` | Default tool call timeout |
| `MCP_DEFAULT_RATE_LIMIT_CALLS` | `60` | Default rate limit per window |
| `MCP_DEFAULT_RATE_LIMIT_WINDOW` | `60` | Default rate limit window (seconds) |
| `MCP_MAX_SERVERS_DEFAULT` | `10` | Max admin MCP servers |
| `MCP_MAX_TOOLS_PER_SERVER_DEFAULT` | `20` | Max tools per server |
| `MCP_MAX_STRUCTURED_ITEMS_PER_CALL` | `25` | Max structured items per tool call |
| `MCP_APP_MAX_HTML_SIZE_DEFAULT` | `2MB` | Max HTML from read_resource (MCP Apps) |
| `MCP_REFERENCE_TOOL_NAME` | `"read_me"` | Convention name for MCP reference documentation tool |
| `MCP_REFERENCE_CONTENT_MAX_CHARS_DEFAULT` | `30000` | Max chars of read_me content injected in planner prompt |
| `MCP_USER_TOOL_NAME_PREFIX` | `"mcp_user"` | Prefix for per-user MCP tool adapter names |
| `MCP_USER_DEFAULT_API_KEY_HEADER` | `"X-API-Key"` | Default header for API key auth |
| `MCP_USER_MAX_SERVERS_PER_USER_DEFAULT` | `5` | Default per-user server limit |
| `MCP_USER_POOL_TTL_SECONDS_DEFAULT` | `900` | Idle connection TTL (15 min) |
| `MCP_USER_POOL_MAX_TOTAL_DEFAULT` | `50` | Global pool limit across all users |
| `MCP_DISPLAY_EMOJI` | `🔌` | Shared display emoji for MCP tool card metadata |
| `MCP_ITERATIVE_TASK_SUFFIX` | `"_task"` | Suffix for per-server iterative ReAct task tools |
| `MCP_USER_POOL_EVICTION_INTERVAL_DEFAULT` | `60` | Eviction sweep interval (seconds) |
| `MCP_USER_OAUTH_STATE_TTL_SECONDS` | `300` | OAuth state TTL in Redis (5 min) |
| `MCP_USER_OAUTH_STATE_REDIS_PREFIX` | `"mcp_oauth_state:"` | Redis key prefix for OAuth state |
| `MCP_USER_OAUTH_CALLBACK_PATH` | `"/api/v1/mcp/servers/oauth/callback"` | OAuth callback URL path |
| `MCP_OAUTH_HTTP_TIMEOUT_SECONDS` | `10` | OAuth HTTP call timeout (discovery, token exchange) |
| `MCP_OAUTH_REFRESH_LOCK_TTL_SECONDS` | `15` | Redis lock TTL for concurrent token refresh |
| `MCP_OAUTH_CLIENT_NAME` | `"LIA"` | Client name for Dynamic Client Registration (RFC 7591) |
| `MCP_USER_OAUTH_REDIRECT_PATH` | `"/dashboard/settings"` | Frontend redirect after OAuth callback |
| `SCHEDULER_JOB_USER_MCP_EVICTION` | `"user_mcp_pool_eviction"` | APScheduler job ID for pool eviction |

### `agents/constants.py` — MCP Domain Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `AGENT_MCP` | `"mcp_agent"` | Virtual agent name for admin MCP (not compiled) |
| `MCP_DOMAIN_PREFIX` | `"mcp_"` | Prefix for per-server MCP domain slugs |
| `CONTEXT_DOMAIN_MCP` | `"mcps"` | Domain context key for MCP results |

---

### Extension: Admin MCP Tools

Admin MCP tools (`MCPToolAdapter` in `tool_adapter.py`) do not yet produce HTML cards. To add support, apply the same pattern: add `coroutine` property + return `UnifiedToolOutput` from `_arun()`. The `McpResultCard` and `HtmlRenderer` registration are already generic.

### Admin MCP `read_me` Support

Admin MCP servers now support the `read_me` convention (same as user MCP). At discovery time, `MCPClientManager._fetch_reference_content()` auto-calls the `read_me` tool and stores the result in `self._reference_content[server_name]`. This content is:
- Passed to `register_mcp_tools()` via `reference_content` parameter — `read_me` tools are excluded from the agent manifest and tool registration
- Merged into the planner prompt by `SmartPlannerService._build_mcp_reference()` alongside user MCP references
- Available via the `MCPClientManager.reference_content` property (read-only snapshot)

This enables admin MCP servers (e.g., Excalidraw) to provide format documentation that guides the planner LLM when generating tool parameters.

## Excalidraw Iterative Builder

### Overview

The Excalidraw MCP server (`excalidraw/excalidraw-mcp`) provides diagram creation tools. Because Excalidraw element JSON is complex (coordinates, bindings, IDs), a dedicated **iterative builder** intercepts the planner's output and drives a specialized LLM to generate clean diagram elements.

### Architecture

Module: `infrastructure/mcp/excalidraw/`

| File | Role |
|------|------|
| `overrides.py` | Constants (`EXCALIDRAW_SERVER_NAME`, `EXCALIDRAW_CREATE_VIEW_TOOL`, `EXCALIDRAW_SPATIAL_SUFFIX`) |
| `iterative_builder.py` | LLM-driven builder: single call (all elements) |

### Flow

```
Planner generates intent JSON
        |
        v
MCPToolAdapter._prepare_excalidraw()
        |
        +-- Intent mode (only supported path):
        |     is_intent() detects {"intent": true, ...}
        |     build_from_intent() makes a single LLM call:
        |       All elements (camera + background + shapes + labels + arrows)
        |     Uses read_me cheat sheet from MCP server
        |
        +-- Non-intent elements:
        |     Passed through unchanged (no position correction)
        |
        v
call_tool("create_view", {elements: ...})
        |
        v
read_resource() -> build_mcp_app_output() -> MCP_APP RegistryItem
```

### Dedicated LLM Configuration

The iterative builder uses a dedicated LLM instance via `MCP_EXCALIDRAW_LLM_*` settings (in `core/config/mcp.py`), independent from the planner LLM:

| Setting | Default | Description |
|---------|---------|-------------|
| `MCP_EXCALIDRAW_LLM_PROVIDER` | `anthropic` | LLM provider |
| `MCP_EXCALIDRAW_LLM_MODEL` | `claude-opus-4-6` | Model ID |
| `MCP_EXCALIDRAW_LLM_TEMPERATURE` | `0.3` | Low temperature for deterministic output |
| `MCP_EXCALIDRAW_LLM_MAX_TOKENS` | `16000` | Enough for complex diagrams |
| `MCP_EXCALIDRAW_STEP_TIMEOUT_SECONDS` | `60` | Timeout per Excalidraw step |

### SPATIAL_SUFFIX

`EXCALIDRAW_SPATIAL_SUFFIX` is appended to the `create_view` tool description in the catalogue. It instructs the planner to generate a structured **intent JSON** instead of raw Excalidraw elements:

```json
{
  "intent": true,
  "description": "Brief description",
  "components": [
    {"name": "Component A", "shape": "rectangle", "color": "#a5d8ff"}
  ],
  "connections": [
    {"from": "Component A", "to": "Component B", "label": "sends data"}
  ],
  "layout": "top-to-bottom"
}
```

### Safety Limits

- Max 15 components per diagram (`_MAX_COMPONENTS`)
- Max 60 elements per LLM call (`_MAX_ELEMENTS_PER_CALL`)
- Graceful degradation: LLM failure returns empty array (no crash)
