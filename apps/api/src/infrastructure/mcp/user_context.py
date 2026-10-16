"""
User MCP Session Context Manager — Per-request setup of user MCP tools.

Sets up the ContextVar `user_mcp_tools_ctx` with UserMCPToolAdapter
instances and ToolManifests for all enabled+active user MCP servers.

Provides two APIs:
- user_mcp_session(): async context manager for simple use
- setup_user_mcp_tools() / cleanup_user_mcp_tools(): standalone pair
  for integration into existing blocks without adding indentation

Key properties:
- Short-circuits when mcp_user_enabled=false (no DB query)
- Resilient: one server failure doesn't block the chat
- ContextVar is cleaned up in finally/cleanup

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from contextvars import Token
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from langchain_core.tools import StructuredTool
from pydantic import JsonValue

from src.core.config import settings
from src.core.constants import (
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_REFERENCE_TOOL_NAME,
    MCP_USER_TOOL_NAME_PREFIX,
)
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.registry.domain_taxonomy import deduplicate_mcp_slugs
from src.infrastructure.mcp.auth import build_auth_for_server
from src.infrastructure.mcp.rate_limit import MCPServerPausedError
from src.infrastructure.mcp.registration import (
    get_admin_mcp_domains,
    record_tool_registration_failure,
)
from src.infrastructure.mcp.task_identity import bind_task_identity
from src.infrastructure.mcp.tool_aliases import allocate_user_prefixes, user_tool_aliases
from src.infrastructure.mcp.user_catalogue import describe_user_server, publish_user_server
from src.infrastructure.mcp.user_pool import PoolEntry, UserMCPClientPool, get_user_mcp_pool
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from src.infrastructure.mcp.utils import is_app_only

if TYPE_CHECKING:

    from src.domains.agents.registry.catalogue import ToolManifest
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)


# ============================================================================
# Standalone setup / cleanup (for flat integration without nesting)
# ============================================================================


async def _usable_tool_embeddings(
    server: UserMCPServer, tools: list[dict[str, Any]]
) -> dict[str, Any]:
    """The server's vectors in their compact form, parsed once per catalogue per worker.

    The per-worker :class:`~src.domains.agents.services.tool_vectors.ServerVectorCache`
    answers first, keyed by the server, the embedding model and the fingerprint
    of the tools just discovered. On a miss the persisted envelope is read
    ALONE (the listing that served the turn deferred it) and, when this model
    wrote it for this catalogue, converted to float32 arrays and cached; else it
    is recomputed and saved as before. Measured on production (ADR-283
    amendment 2026-10-12): every turn used to parse about a thousand vectors of
    1,536 Python floats, and each request context still alive held its own copy.

    Best-effort in both halves: a recompute that fails leaves the tools
    unranked for the turn (they still bind through their family's coverage)
    and never fails the request. The new envelope is written in a short
    transaction of its own, once the embeddings are computed (ADR-304).

    Args:
        server: The ``UserMCPServer`` row, read in a session already closed.
        tools: The tools the pool just discovered on the server.

    Returns:
        Vectors by raw MCP tool name — arrays, possibly empty.
    """
    from src.domains.agents.services.tool_embeddings_envelope import (
        embedding_model_key,
        read_server_cache,
        wrap_server_cache,
    )
    from src.domains.agents.services.tool_vectors import (
        compact_tool_vectors,
        get_server_vector_cache,
    )
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context
    from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint

    cache = get_server_vector_cache()
    key = (str(server.id), embedding_model_key(), canonical_fingerprint(tools))
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        async with get_db_context() as db:
            envelope = await UserMCPServerRepository(db).get_tool_embeddings_cache(server.id)
    except Exception as exc:
        # The envelope used to travel with the row; read alone, its failure must
        # cost the turn its ranking of this server's tools, never the tools.
        logger.warning(
            "user_mcp_tool_embeddings_read_failed",
            server_id=str(server.id),
            error_type=type(exc).__name__,
        )
        return {}
    vectors, stale = read_server_cache(envelope, tool_metadata=tools)
    if stale is None or not tools:
        compact = compact_tool_vectors(vectors)
        cache.put(key, compact)
        return compact
    try:
        from src.domains.agents.services.tool_selector import compute_tool_embeddings

        recomputed = await compute_tool_embeddings(tool_metadata=tools, server_name=server.name)
        if not recomputed:
            return {}
        async with get_db_context() as db:
            repo = UserMCPServerRepository(db)
            row = await repo.get_by_id(server.id)
            if row is not None:
                await repo.update(
                    row,
                    {"tool_embeddings_cache": wrap_server_cache(recomputed, tool_metadata=tools)},
                )
        logger.info(
            "user_mcp_tool_embeddings_refreshed",
            server_id=str(server.id),
            reason=stale,
            tool_count=len(recomputed),
        )
        compact = compact_tool_vectors(recomputed)
        cache.put(key, compact)
        return compact
    except Exception as exc:
        logger.warning(
            "user_mcp_tool_embeddings_refresh_failed",
            server_id=str(server.id),
            reason=stale,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {}


async def setup_user_mcp_tools(user_id: UUID) -> Token | None:
    """
    Setup user MCP tools for a chat request.

    Queries enabled+active servers, connects via the pool, builds tool
    adapters and manifests, sets the ContextVar. The servers are read in a
    session of their own, closed before any server is connected: it used to
    run on the turn's session, which then waited on every MCP handshake —
    and on the embedding refresh it wrote there (ADR-304).

    Returns:
        ContextVar token for cleanup (None if nothing was set).
        Caller MUST pass this to cleanup_user_mcp_tools() in a finally block.
    """
    # Short-circuit: feature disabled → no-op
    if not getattr(settings, "mcp_user_enabled", False):
        return None

    # Query enabled + active servers from DB
    from src.domains.user_mcp.repository import UserMCPServerRepository
    from src.infrastructure.database.session import get_db_context

    async with get_db_context() as db:
        servers = await UserMCPServerRepository(db).get_enabled_active_for_user(user_id)

    if not servers:
        logger.debug(
            "user_mcp_no_active_servers",
            user_id=str(user_id),
        )
        return None

    pool = get_user_mcp_pool()
    if pool is None:
        logger.warning(
            "user_mcp_session_pool_not_initialized",
            user_id=str(user_id),
        )
        return None

    # Build tools context (resilient: individual server failures are logged and skipped)
    ctx = UserMCPToolsContext()
    # F2.2: Per-server domain slugs for targeted domain routing
    domains = deduplicate_mcp_slugs([s.name for s in servers], reserved=get_admin_mcp_domains())
    from src.domains.agents.tools.tool_registry import list_tool_names

    prefixes = allocate_user_prefixes([s.id for s in servers], reserved=list_tool_names())
    for server in servers:
        await _register_user_server(
            server, user_id, pool, ctx, domains[server.name], prefixes[server.id]
        )

    # Set ContextVar only if we have at least one tool
    if not ctx.tool_instances:
        return None

    token = user_mcp_tools_ctx.set(ctx)

    logger.info(
        "user_mcp_session_ready",
        user_id=str(user_id),
        tool_count=len(ctx.tool_instances),
        server_count=len(
            {
                inst.server_id
                for inst in ctx.tool_instances.values()
                if isinstance(inst, UserMCPToolAdapter)
            }
        ),
    )

    return token


async def _register_user_server(
    server: UserMCPServer,
    user_id: UUID,
    pool: UserMCPClientPool,
    ctx: UserMCPToolsContext,
    domain: str,
    server_prefix: str | None = None,
) -> None:
    """Discover one server and publish it only after usable registration succeeds."""
    try:
        entry = await pool.get_or_connect(
            user_id=user_id,
            server_id=server.id,
            url=server.url,
            auth=build_auth_for_server(server),
            timeout_seconds=server.timeout_seconds,
            extra_headers=server.extra_headers,
        )
        hitl_required = (
            server.hitl_required
            if server.hitl_required is not None
            else getattr(settings, "mcp_hitl_required", True)
        )
        embeddings = await _usable_tool_embeddings(server, entry.tools)
        register = (
            _register_user_iterative_server
            if settings.mcp_react_enabled and server.iterative_mode
            else _register_user_standard_server
        )
        register(server, entry, user_id, ctx, hitl_required, embeddings, domain, server_prefix)
    except MCPServerPausedError as paused:
        # A known state, not a new failure (point 29): the server failed to
        # connect earlier and waits out its pause — no traceback every turn.
        logger.info(
            "user_mcp_server_paused",
            user_id=str(user_id),
            server_id=str(server.id),
            retry_in_seconds=paused.retry_in_seconds,
        )
    except Exception:
        logger.warning(
            "user_mcp_server_connect_failed",
            user_id=str(user_id),
            server_id=str(server.id),
            server_name=server.name,
            exc_info=True,
        )


def _register_user_standard_server(
    server: UserMCPServer,
    entry: PoolEntry,
    user_id: UUID,
    ctx: UserMCPToolsContext,
    hitl_required: bool,
    embeddings_cache: Mapping[str, dict[str, JsonValue]],
    domain: str,
    server_prefix: str | None = None,
) -> None:
    """Register usable individuals and describe exactly those current capabilities."""
    registered: list[Mapping[str, object]] = []
    from src.domains.agents.tools.tool_registry import list_tool_names

    aliases = user_tool_aliases(
        server.id,
        [str(tool.get("name", "")) for tool in entry.tools],
        server_prefix=server_prefix,
        reserved=list_tool_names(),
    )
    for tool_data in entry.tools:
        if is_app_only(tool_data.get("app_visibility")):
            continue
        if tool_data["name"] == MCP_REFERENCE_TOOL_NAME and entry.reference_content:
            continue
        try:
            adapter = UserMCPToolAdapter.from_discovered_tool(
                server_id=server.id,
                user_id=user_id,
                server_name=server.name,
                tool_name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("input_schema", {}),
                timeout_seconds=server.timeout_seconds,
                app_resource_uri=tool_data.get("app_resource_uri"),
                annotations=tool_data.get("annotations"),
                server_url=server.url,
                output_schema=tool_data.get("output_schema"),
                server_prefix=server_prefix,
                tool_alias=aliases[str(tool_data["name"])],
            )
            manifest = _build_user_tool_manifest(
                adapter_name=adapter.name,
                tool_name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("input_schema", {}),
                server_name=server.name,
                server_domain=domain,
                hitl_required=hitl_required,
                annotations=tool_data.get("annotations"),
                output_schema=tool_data.get("output_schema"),
                server_key=str(server.id),
            )
            ctx.tool_manifests.append(manifest)
            ctx.tool_instances[adapter.name] = adapter
            registered.append(tool_data)
            raw_name = tool_data["name"]
            if raw_name in embeddings_cache:
                ctx.tool_embeddings[adapter.name] = embeddings_cache[raw_name]
        except Exception as exc:
            record_tool_registration_failure(
                scope="user_standard",
                server=str(server.id),
                tool_name=str(tool_data.get("name", "unknown")),
                exc=exc,
                user_id=str(user_id),
            )
    if registered:
        publish_user_server(
            ctx,
            server.name,
            domain,
            describe_user_server(server.name, server.domain_description, registered),
            entry.reference_content,
        )


def cleanup_user_mcp_tools(token: Token | None) -> None:
    """
    Reset the user MCP tools ContextVar.

    Must be called in a finally block after setup_user_mcp_tools().
    """
    if token is not None:
        user_mcp_tools_ctx.reset(token)


# ============================================================================
# Context manager (convenience wrapper)
# ============================================================================


@asynccontextmanager
async def user_mcp_session(user_id: UUID) -> AsyncGenerator[None]:
    """
    Setup user MCP tools for a chat request (context manager variant).

    Wraps setup_user_mcp_tools / cleanup_user_mcp_tools for simple use cases.

    Args:
        user_id: Current authenticated user

    Yields:
        None — tools are accessible via user_mcp_tools_ctx ContextVar
    """
    token = await setup_user_mcp_tools(user_id)
    try:
        yield
    finally:
        cleanup_user_mcp_tools(token)


# ============================================================================
# Iterative mode registration (ADR-062)
# ============================================================================


def _count_user_tool_instances(ctx: UserMCPToolsContext, server_id: UUID) -> int:
    return sum(
        isinstance(instance, UserMCPToolAdapter) and instance.server_id == server_id
        for instance in ctx.tool_instances.values()
    )


def _register_user_iterative_server(
    server: UserMCPServer,
    entry: PoolEntry,
    user_id: UUID,
    ctx: UserMCPToolsContext,
    hitl_required: bool,
    embeddings_cache: Mapping[str, dict[str, JsonValue]],
    domain: str | None = None,
    server_prefix: str | None = None,
) -> None:
    """Register a user MCP server in iterative (ReAct) mode.

    Individual tools are stored in ctx.tool_instances (for the ReAct agent
    to use), but the planner sees only a single per-server task tool manifest.

    Args:
        server: User MCP server model instance.
        entry: Pool entry with discovered tools.
        user_id: Current user UUID.
        ctx: UserMCPToolsContext being built.
        hitl_required: Resolved HITL requirement.
        embeddings_cache: Pre-computed embeddings from DB.
    """
    from src.domains.agents.tools.mcp_react_tools import (
        account_scope_note,
        iterative_task_tool_description,
        mcp_user_server_task_tool,
    )
    from src.domains.user_mcp.models import UserMCPAuthType

    domain = domain or ctx.server_domains.get(server.name, "mcp_unnamed")
    server_id_prefix = server_prefix or str(server.id)[:8]

    # A user server's credential is the USER'S OWN (oauth2 grant, personal
    # bearer/API key): its calls are account-scoped, and the model must read
    # that where it reads the server's capabilities. Derived from auth_type —
    # never asserted in a prompt, which would be false for 'none' servers
    # (2026-09-02: "my repos" ended in a hallucinated username for lack of it).
    account_scoped = server.auth_type != UserMCPAuthType.NONE.value
    # 1. Register individual tools in ctx (ReAct agent needs them)
    registered: list[Mapping[str, object]] = []
    from src.domains.agents.tools.tool_registry import list_tool_names

    aliases = user_tool_aliases(
        server.id,
        [str(tool.get("name", "")) for tool in entry.tools],
        server_prefix=server_id_prefix,
        reserved=[
            *list_tool_names(),
            f"{MCP_USER_TOOL_NAME_PREFIX}_{server_id_prefix}{MCP_ITERATIVE_TASK_SUFFIX}",
        ],
    )
    for tool_data in entry.tools:
        if is_app_only(tool_data.get("app_visibility")):
            continue

        try:
            adapter = UserMCPToolAdapter.from_discovered_tool(
                server_id=server.id,
                user_id=user_id,
                server_name=server.name,
                tool_name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("input_schema", {}),
                timeout_seconds=server.timeout_seconds,
                app_resource_uri=tool_data.get("app_resource_uri"),
                annotations=tool_data.get("annotations"),
                server_url=server.url,
                output_schema=tool_data.get("output_schema"),
                server_prefix=server_id_prefix,
                tool_alias=aliases[str(tool_data["name"])],
                reserved_aliases=(
                    f"{MCP_USER_TOOL_NAME_PREFIX}_{server_id_prefix}{MCP_ITERATIVE_TASK_SUFFIX}",
                ),
            )
            manifest = _build_user_tool_manifest(
                adapter_name=adapter.name,
                tool_name=tool_data["name"],
                description=tool_data.get("description") or tool_data["name"],
                input_schema=tool_data.get("input_schema", {}),
                output_schema=tool_data.get("output_schema"),
                server_name=server.name,
                server_domain=domain,
                hitl_required=hitl_required,
                annotations=tool_data.get("annotations"),
                server_key=str(server.id),
            )
            ctx.tool_instances[adapter.name] = adapter
            ctx.reactive_tool_manifests[adapter.name] = manifest
            registered.append(tool_data)

            # Re-key embeddings for individual tools
            raw_tool_name = tool_data["name"]
            if raw_tool_name in embeddings_cache:
                ctx.tool_embeddings[adapter.name] = embeddings_cache[raw_tool_name]

        except Exception as exc:
            record_tool_registration_failure(
                scope="user_iterative",
                server=str(server.id),
                tool_name=str(tool_data.get("name", "unknown")),
                exc=exc,
                user_id=str(user_id),
            )

    if not registered:
        return
    catalogue = describe_user_server(server.name, server.domain_description, registered)

    # 2. Create per-server task tool instance (named copy of the generic tool).
    # The description must speak the SERVER'S domain: bind_tools serializes
    # the instance, not the manifest, so a name-only copy left the model
    # staring at "Execute a multi-step task on a user MCP server" for the
    # user's bank (2026-09-02 — ReAct refused what the pipeline could plan).
    task_tool_name = f"{MCP_USER_TOOL_NAME_PREFIX}_{server_id_prefix}{MCP_ITERATIVE_TASK_SUFFIX}"
    if not isinstance(mcp_user_server_task_tool, StructuredTool):
        raise TypeError("MCP task delegation requires a StructuredTool")
    named_task_tool = mcp_user_server_task_tool.model_copy(
        update={
            "name": task_tool_name,
            "metadata": {
                "mcp_origin": "user",
                "mcp_server_key": str(server.id),
                "mcp_server_name": server.name,
            },
            "description": iterative_task_tool_description(
                server.name,
                catalogue.description,
                server_id_prefix=server_id_prefix,
                account_scoped=account_scoped,
            ),
        },
    )
    named_task_tool = bind_task_identity(
        named_task_tool, {"server_name": server.name, "server_id_prefix": server_id_prefix}
    )
    # 3. Build task tool manifest (planner sees only this). The manifest is
    # the planner's whole knowledge of the server, so the account-scope fact
    # travels here too — a routing surface that says "public" while the
    # instance says "your account" is two authorities on one question.
    manifest_description = catalogue.description
    if account_scoped:
        manifest_description = f"{manifest_description} {account_scope_note(server.name)}"
    task_manifest = _build_user_iterative_task_manifest(
        task_tool_name=task_tool_name,
        server_id_prefix=server_id_prefix,
        server_name=server.name,
        server_domain=domain,
        description=manifest_description,
        hitl_required=hitl_required,
        server_key=str(server.id),
    )
    ctx.tool_manifests.append(task_manifest)
    ctx.tool_instances[task_tool_name] = named_task_tool
    publish_user_server(ctx, server.name, domain, catalogue, entry.reference_content)
    if account_scoped:
        ctx.account_scoped_prefixes.add(server_id_prefix)

    # Track iterative servers for reference_content skip in planner
    ctx.iterative_servers.add(server.name.lower())

    logger.info(
        "user_mcp_server_registered_iterative",
        server_id=str(server.id),
        server_name=server.name,
        task_tool=task_tool_name,
        individual_tools=_count_user_tool_instances(ctx, server.id),
    )


def _build_user_iterative_task_manifest(
    task_tool_name: str,
    server_id_prefix: str,
    server_name: str,
    server_domain: str,
    description: str,
    hitl_required: bool,
    server_key: str | None = None,
) -> ToolManifest:
    """Build a ToolManifest for the user MCP ReAct task tool.

    Delegates to the shared build_mcp_react_task_manifest() factory with
    user-specific parameter schema (server_id_prefix + server_name + task).

    Args:
        task_tool_name: Per-server tool name (e.g., "mcp_user_37e4468e_task").
        server_id_prefix: Allocated unique UUID prefix for this request's registered server.
        server_name: Human-readable server name.
        server_domain: Domain slug for agent routing.
        description: Server description for LLM context.
        hitl_required: Whether HITL approval is required.

    Returns:
        ToolManifest for the iterative task tool.
    """
    from src.domains.agents.registry.catalogue import (
        ParameterConstraint,
        ParameterSchema,
    )
    from src.infrastructure.mcp.registration import build_mcp_react_task_manifest

    return build_mcp_react_task_manifest(
        tool_name=task_tool_name,
        agent_name=f"{server_domain}_agent",
        server_name=server_name,
        description=description,
        parameters=[
            ParameterSchema(
                name="server_id_prefix",
                type="string",
                required=True,
                description=(f"User MCP server ID prefix. MUST be exactly '{server_id_prefix}'."),
                constraints=[
                    ParameterConstraint(kind="enum", value=[server_id_prefix]),
                ],
            ),
            ParameterSchema(
                name="server_name",
                type="string",
                required=True,
                description=(f"Human-readable server name. MUST be exactly '{server_name}'."),
                constraints=[
                    ParameterConstraint(kind="enum", value=[server_name]),
                ],
            ),
            ParameterSchema(
                name="task",
                type="string",
                required=True,
                description="Natural language description of the task to accomplish",
            ),
        ],
        semantic_keywords=[server_name, server_domain, "task", "iterative", "react"],
        hitl_required=hitl_required,
        mcp_origin="user",
        mcp_server_key=server_key,
    )


# ============================================================================
# Manifest builder
# ============================================================================


def _build_user_tool_manifest(
    adapter_name: str,
    tool_name: str,
    description: str,
    input_schema: dict,
    server_name: str,
    server_domain: str,
    hitl_required: bool,
    annotations: dict | None = None,
    output_schema: dict | None = None,
    server_key: str | None = None,
) -> ToolManifest:
    """Build a ToolManifest for a user MCP tool.

    Delegates to the shared build_mcp_tool_manifest() factory from registration.py,
    with user-specific naming and per-server domain routing (F2.2).

    Args:
        server_domain: Per-server domain slug (e.g., "mcp_huggingface_hub").
        annotations: Server-declared behaviour hints, believed only where
            they tighten a decision (see ``declared_tool_category``).
    """
    from src.infrastructure.mcp.registration import (
        build_mcp_tool_manifest,
        build_semantic_keywords_from_description,
    )

    semantic_keywords = [
        server_name,
        server_domain,
        tool_name,
        MCP_USER_TOOL_NAME_PREFIX,
        *build_semantic_keywords_from_description(description),
    ]

    return build_mcp_tool_manifest(
        adapter_name=adapter_name,
        agent_name=f"{server_domain}_agent",  # F2.2: Per-server agent for domain extraction
        tool_name=tool_name,
        description=description,
        input_schema=input_schema,
        semantic_keywords=semantic_keywords,
        hitl_required=hitl_required,
        annotations=annotations,
        output_schema=output_schema,
        mcp_origin="user",
        mcp_server_key=server_key,
    )
