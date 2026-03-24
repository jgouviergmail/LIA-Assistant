# ADR-061: Centralized Component Activation/Deactivation Control

## Status

Accepted — 2026-03-23

## Context

When a user disables an admin MCP app (e.g., Excalidraw), the system continued
to route queries to that domain and execute its tools. The root cause was
twofold:

1. **No domain validation**: The Query Analyzer LLM received a filtered
   `available_domains` list but its output domains were never validated against
   that list. The LLM could hallucinate or return a domain absent from its
   prompt (e.g., a disabled MCP server it "remembers").

2. **Scattered tool manifest filtering**: `registry.list_tool_manifests()`
   returned all tools. Each consumer (router, catalogue strategies, expansion
   service) had to independently filter disabled tools — 7+ locations, easy to
   miss.

## Decision

### 1. Domain-level gate-keeper (root cause fix)

Validate LLM-output domains against `available_domains` at two points in
`query_analyzer_service.py`:

- **Post-LLM**: in `analyze_query()`, strip `primary_domain` and
  `secondary_domains` not in `available_domain_names`.
- **Post-expansion**: in `analyze_full()`, strip domains re-introduced by
  `_expand_domains_for_semantic_types()`.

A domain absent from `available_domains` can never enter the pipeline → zero
tools from that domain will be scored, planned, or executed.

### 2. Centralized tool manifest ContextVar

Follow the established `active_skills_ctx` pattern: a per-request ContextVar
(`request_tool_manifests_ctx`) containing the pre-filtered manifest list, built
once at request start, read everywhere.

- **Builder**: `build_request_tool_manifests(registry)` in `src/core/context.py`
  — combines registry manifests minus disabled admin MCP plus user MCP tools.
- **Accessor**: `get_request_tool_manifests()` — returns pre-built list,
  warns if called outside request lifecycle.
- **Setup**: in `AgentService._stream_with_new_services()`, after
  `admin_mcp_disabled_ctx` and `user_mcp_tools_ctx` are set.

### 3. API guard (out-of-pipeline defense)

Admin MCP app proxy endpoints (`/mcp/admin-servers/{key}/app/call-tool` and
`read-resource`) bypass the agent pipeline entirely (iframe → HTTP → MCP
client). These retain explicit `admin_mcp_disabled_servers` checks at both the
HTTP layer (403) and the `MCPClientManager` layer (defense in depth).

## Architecture

```
Layer 1 — Domain gate-keeper (query_analyzer_service.py)
  ↓  Disabled domain stripped → 0 tools considered
Layer 2 — Catalogue ContextVar (context.py → request_tool_manifests_ctx)
  ↓  Pre-filtered manifests, set once, read everywhere
Layer 3 — API guard (admin_router.py + client_manager.py)
       Blocks direct calls from iframe proxy (out-of-pipeline)
```

## Component Coverage

| Component         | Mechanism                                           |
|-------------------|-----------------------------------------------------|
| Admin MCP global  | Startup guard `mcp_enabled`                         |
| Admin MCP per-user| Domain validation + `request_tool_manifests_ctx`    |
| User MCP          | `user_mcp_tools_ctx` (set once)                     |
| Admin/User Skills | `active_skills_ctx` (set once)                      |
| Sub-agents        | Inherit `request_tool_manifests_ctx` via ContextVar  |
| RAG Spaces        | Repository filter (outside tool pipeline)           |
| Admin App Proxy   | 403 + client_manager defense in depth               |

## Consequences

- Adding a new toggleable component type requires only:
  1. Filtering it in `_build_available_domains()` (domain level) or
     `build_request_tool_manifests()` (manifest level).
  2. No changes needed in consumers (router, catalogue, planner, executor).
- `filter_admin_mcp_disabled_manifests()` is called in one place only
  (`build_request_tool_manifests()`), not scattered across consumers.
- Sub-agents automatically inherit restrictions via async ContextVar
  propagation.

## Files Changed

- `src/domains/agents/services/query_analyzer_service.py` — domain validation
- `src/core/context.py` — `request_tool_manifests_ctx` ContextVar
- `src/domains/agents/api/service.py` — setup/cleanup
- `src/domains/agents/services/catalogue/strategies/normal_filtering.py`
- `src/domains/agents/services/catalogue/strategies/panic_filtering.py`
- `src/domains/agents/nodes/router_node_v3.py`
- `src/domains/agents/semantic/expansion_service.py`
- `src/domains/agents/services/smart_planner_service.py`
