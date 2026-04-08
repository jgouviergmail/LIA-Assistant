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

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from contextvars import Token
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    MCP_ITERATIVE_TASK_SUFFIX,
    MCP_REFERENCE_TOOL_NAME,
    MCP_USER_TOOL_NAME_PREFIX,
)
from src.core.context import UserMCPToolsContext, user_mcp_tools_ctx
from src.domains.agents.registry.domain_taxonomy import deduplicate_mcp_slugs
from src.infrastructure.mcp.auth import build_auth_for_server
from src.infrastructure.mcp.user_pool import PoolEntry, get_user_mcp_pool
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from src.infrastructure.mcp.utils import is_app_only

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.agents.registry.catalogue import ToolManifest
    from src.domains.user_mcp.models import UserMCPServer

logger = structlog.get_logger(__name__)


# ============================================================================
# Standalone setup / cleanup (for flat integration without nesting)
# ============================================================================


async def setup_user_mcp_tools(
    user_id: UUID,
    db: AsyncSession,
) -> Token | None:
    """
    Setup user MCP tools for a chat request.

    Queries enabled+active servers, connects via the pool, builds tool
    adapters and manifests, sets the ContextVar.

    Returns:
        ContextVar token for cleanup (None if nothing was set).
        Caller MUST pass this to cleanup_user_mcp_tools() in a finally block.
    """
    # Short-circuit: feature disabled → no-op
    if not getattr(settings, "mcp_user_enabled", False):
        return None

    # Query enabled + active servers from DB
    from src.domains.user_mcp.repository import UserMCPServerRepository

    repo = UserMCPServerRepository(db)
    servers = await repo.get_enabled_active_for_user(user_id)

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
    ctx.server_domains = deduplicate_mcp_slugs([s.name for s in servers])
    global_hitl = getattr(settings, "mcp_hitl_required", True)

    # ADR-062: Check if ReAct iterative mode is globally enabled
    react_enabled = getattr(settings, "mcp_react_enabled", False)

    for server in servers:
        try:
            # Build auth handler from encrypted credentials
            auth = build_auth_for_server(server)

            # Get or create pooled connection
            entry = await pool.get_or_connect(
                user_id=user_id,
                server_id=server.id,
                url=server.url,
                auth=auth,
                timeout_seconds=server.timeout_seconds,
            )

            # Resolve HITL: per-server override > global setting
            hitl_required = (
                server.hitl_required if server.hitl_required is not None else global_hitl
            )

            # Load server-level data for pipeline integration
            if server.domain_description:
                ctx.server_descriptions[server.name] = server.domain_description

            # Cache auto-fetched read_me content for planner prompt injection
            if entry.reference_content:
                ctx.server_reference_content[server.name] = entry.reference_content

            # Pre-load embeddings cache for re-keying inside tool loop
            embeddings_cache = getattr(server, "tool_embeddings_cache", None) or {}

            # ADR-062: Iterative mode — delegate to ReAct sub-agent
            is_iterative = react_enabled and getattr(server, "iterative_mode", False)

            if is_iterative:
                _register_user_iterative_server(
                    server=server,
                    entry=entry,
                    user_id=user_id,
                    ctx=ctx,
                    hitl_required=hitl_required,
                    embeddings_cache=embeddings_cache,
                )
                continue

            # Standard mode: register individual tools in catalogue
            for tool_data in entry.tools:
                # MCP Apps: app-only tools are iframe-only → skip LLM catalogue.
                # Proxy endpoints call pool directly, no adapter needed.
                if is_app_only(tool_data.get("app_visibility")):
                    logger.debug(
                        "user_mcp_tool_app_only_skipped",
                        server_name=server.name,
                        tool_name=tool_data.get("name", "unknown"),
                    )
                    continue

                # Skip reference-only tools whose content was auto-injected
                # into the planner context (e.g., read_me for Excalidraw format).
                if tool_data["name"] == MCP_REFERENCE_TOOL_NAME and entry.reference_content:
                    logger.debug(
                        "user_mcp_tool_reference_skipped",
                        server_name=server.name,
                        tool_name=MCP_REFERENCE_TOOL_NAME,
                    )
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
                    )

                    manifest = _build_user_tool_manifest(
                        adapter_name=adapter.name,
                        tool_name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("input_schema", {}),
                        server_name=server.name,
                        server_domain=ctx.server_domains.get(server.name, "mcp_unnamed"),
                        hitl_required=hitl_required,
                    )

                    ctx.tool_manifests.append(manifest)
                    ctx.tool_instances[adapter.name] = adapter
                    # Store original input_schema for native function calling
                    ctx.tool_input_schemas[adapter.name] = tool_data.get("input_schema", {})

                    # Re-key pre-computed embeddings: raw MCP name → adapter name
                    # DB stores by raw name ("hub_search"), but select_tools() uses
                    # adapter name ("mcp_user_37e4468e_hub_search"). Re-key here
                    # where both names are available.
                    raw_tool_name = tool_data["name"]
                    if raw_tool_name in embeddings_cache:
                        ctx.tool_embeddings[adapter.name] = embeddings_cache[raw_tool_name]

                except Exception:
                    logger.warning(
                        "user_mcp_tool_build_failed",
                        user_id=str(user_id),
                        server_id=str(server.id),
                        tool_name=tool_data.get("name", "unknown"),
                        exc_info=True,
                    )

        except Exception:
            logger.warning(
                "user_mcp_server_connect_failed",
                user_id=str(user_id),
                server_id=str(server.id),
                server_name=server.name,
                exc_info=True,
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
async def user_mcp_session(
    user_id: UUID,
    db: AsyncSession,
) -> AsyncGenerator[None, None]:
    """
    Setup user MCP tools for a chat request (context manager variant).

    Wraps setup_user_mcp_tools / cleanup_user_mcp_tools for simple use cases.

    Args:
        user_id: Current authenticated user
        db: Request-scoped database session

    Yields:
        None — tools are accessible via user_mcp_tools_ctx ContextVar
    """
    token = await setup_user_mcp_tools(user_id, db)
    try:
        yield
    finally:
        cleanup_user_mcp_tools(token)


# ============================================================================
# Iterative mode registration (ADR-062)
# ============================================================================


def _register_user_iterative_server(
    server: UserMCPServer,
    entry: PoolEntry,
    user_id: UUID,
    ctx: UserMCPToolsContext,
    hitl_required: bool,
    embeddings_cache: dict[str, dict],
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
    from src.domains.agents.tools.mcp_react_tools import mcp_user_server_task_tool

    server_id_prefix = str(server.id)[:8]

    # 1. Register individual tools in ctx (ReAct agent needs them)
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
            )
            ctx.tool_instances[adapter.name] = adapter

            # Re-key embeddings for individual tools
            raw_tool_name = tool_data["name"]
            if raw_tool_name in embeddings_cache:
                ctx.tool_embeddings[adapter.name] = embeddings_cache[raw_tool_name]

        except Exception:
            logger.warning(
                "user_mcp_iterative_tool_build_failed",
                user_id=str(user_id),
                server_id=str(server.id),
                tool_name=tool_data.get("name", "unknown"),
                exc_info=True,
            )

    # 2. Create per-server task tool instance (named copy of the generic tool)
    task_tool_name = f"{MCP_USER_TOOL_NAME_PREFIX}_{server_id_prefix}{MCP_ITERATIVE_TASK_SUFFIX}"
    named_task_tool = mcp_user_server_task_tool.model_copy(
        update={"name": task_tool_name},
    )
    ctx.tool_instances[task_tool_name] = named_task_tool

    # 3. Build task tool manifest (planner sees only this)
    task_manifest = _build_user_iterative_task_manifest(
        task_tool_name=task_tool_name,
        server_id_prefix=server_id_prefix,
        server_name=server.name,
        server_domain=ctx.server_domains.get(server.name, "mcp_unnamed"),
        description=server.domain_description or server.name,
        hitl_required=hitl_required,
    )
    ctx.tool_manifests.append(task_manifest)

    # Track iterative servers for reference_content skip in planner
    ctx.iterative_servers.add(server.name.lower())

    logger.info(
        "user_mcp_server_registered_iterative",
        server_id=str(server.id),
        server_name=server.name,
        task_tool=task_tool_name,
        individual_tools=sum(
            1
            for k in ctx.tool_instances
            if k.startswith(f"mcp_user_{server_id_prefix}_") and k != task_tool_name
        ),
    )


def _build_user_iterative_task_manifest(
    task_tool_name: str,
    server_id_prefix: str,
    server_name: str,
    server_domain: str,
    description: str,
    hitl_required: bool,
) -> ToolManifest:
    """Build a ToolManifest for the user MCP ReAct task tool.

    Delegates to the shared build_mcp_react_task_manifest() factory with
    user-specific parameter schema (server_id_prefix + server_name + task).

    Args:
        task_tool_name: Per-server tool name (e.g., "mcp_user_37e4468e_task").
        server_id_prefix: First 8 chars of server UUID.
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
) -> ToolManifest:
    """Build a ToolManifest for a user MCP tool.

    Delegates to the shared build_mcp_tool_manifest() factory from registration.py,
    with user-specific naming and per-server domain routing (F2.2).

    Args:
        server_domain: Per-server domain slug (e.g., "mcp_huggingface_hub").
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
    )
