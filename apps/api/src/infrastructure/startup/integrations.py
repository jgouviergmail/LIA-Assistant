"""Startup steps: external integrations and optional channels.

MCP client manager (evolution F2), per-user MCP pool (F2.1), Telegram bot
(F3), currency rates startup sync and system RAG space indexing. Every step
is non-fatal; the optional ones are feature-flag gated.

Extracted verbatim from ``src.main.lifespan`` (ADR-123): same structlog
events, same exception handling, same feature-flag guards.
"""

from typing import TYPE_CHECKING

import structlog

from src.core.config import settings
from src.infrastructure.scheduler.currency_sync import sync_currency_rates

if TYPE_CHECKING:
    from telegram import Bot

    from src.domains.agents.registry import AgentRegistry
    from src.infrastructure.mcp.client_manager import MCPClientManager

logger = structlog.get_logger(__name__)


async def init_mcp(registry: "AgentRegistry | None") -> "MCPClientManager | None":
    """Initialize the MCP Client Manager (evolution F2 — MCP Support).

    Discovers tools from configured MCP servers, adapts them and registers
    them INTO the agent registry (which is why this must run after
    ``init_agent_registry`` and before ``init_semantic_services``).

    Args:
        registry: The agent registry to register MCP tools into; the step is
            skipped when None (or when ``mcp_enabled`` is off).

    Returns:
        The manager consumed by the shutdown gate. On a mid-initialization
        failure this returns the PARTIALLY initialized manager (not None) so
        shutdown still cleans it up — matching the historical lifespan
        behavior. None when disabled, skipped or failed before creation.
    """
    mcp_manager = None
    if getattr(settings, "mcp_enabled", False) and registry is not None:
        try:
            from src.infrastructure.mcp.client_manager import initialize_mcp_client_manager
            from src.infrastructure.mcp.registration import register_mcp_tools
            from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

            mcp_manager = await initialize_mcp_client_manager()
            if mcp_manager and mcp_manager.discovered_tools:
                # Create adapters for each discovered tool
                adapters: dict[str, MCPToolAdapter] = {}
                for server_name, tools in mcp_manager.discovered_tools.items():
                    for tool in tools:
                        adapter = MCPToolAdapter.from_mcp_tool(
                            server_name=server_name,
                            tool_name=tool.tool_name,
                            description=tool.description,
                            input_schema=tool.input_schema,
                            app_resource_uri=tool.app_resource_uri,
                        )
                        adapters[adapter.name] = adapter

                # Register in AgentRegistry + tool_registry
                tool_count = register_mcp_tools(
                    registry=registry,
                    discovered_tools=mcp_manager.discovered_tools,
                    adapters=adapters,
                    server_configs=mcp_manager.server_configs,
                    global_hitl_required=getattr(settings, "mcp_hitl_required", True),
                    reference_content=mcp_manager.reference_content,
                )

                # Rebuild domain index to include the "mcp" domain
                registry.rebuild_domain_index()

                logger.info(
                    "mcp_initialized",
                    servers=mcp_manager.connected_server_count,
                    tools=tool_count,
                )
        except Exception as exc:
            logger.error("mcp_initialization_failed", error=str(exc), exc_info=True)
    return mcp_manager


async def init_user_mcp_pool() -> None:
    """Initialize the User MCP Pool (evolution F2.1 — MCP Per-User)."""
    if getattr(settings, "mcp_user_enabled", False):
        try:
            from src.infrastructure.mcp.user_pool import initialize_user_mcp_pool

            await initialize_user_mcp_pool()
            logger.info("user_mcp_pool_initialized")
        except Exception as exc:
            logger.error("user_mcp_pool_initialization_failed", error=str(exc), exc_info=True)


async def init_telegram_bot() -> "Bot | None":
    """Initialize the Telegram Bot (evolution F3 — Multi-Channel).

    Returns:
        The bot consumed by the shutdown gate, or None when disabled or failed.
    """
    telegram_bot = None
    if getattr(settings, "channels_enabled", False):
        try:
            from src.infrastructure.channels.telegram.bot import initialize_telegram_bot

            telegram_bot = await initialize_telegram_bot()
            if telegram_bot:
                logger.info("telegram_bot_initialized")
        except Exception as exc:
            logger.error("telegram_bot_initialization_failed", error=str(exc), exc_info=True)

        # channel_active_bindings is refreshed from the DB by the lifetime-metrics
        # updater loop (runs in every worker -> identical values for the gauge's
        # 'mostrecent' multiprocess mode); no per-worker startup priming needed here.
    return telegram_bot


async def sync_currency_rates_at_startup() -> None:
    """Initialize currency rates on startup (critical for token cost tracking)."""
    try:
        logger.info("currency_rates_startup_sync_starting")
        await sync_currency_rates()
        logger.info("currency_rates_startup_sync_completed")
    except (RuntimeError, ConnectionError, TimeoutError, ValueError) as exc:
        # Don't fail startup, but log error prominently
        logger.error(
            "currency_rates_startup_sync_failed",
            error=str(exc),
            exc_info=True,
            remediation="Token cost tracking may fail until rates are synced",
        )


async def index_system_rag_spaces() -> None:
    """Auto-index system RAG spaces (FAQ knowledge base) if enabled.

    Idempotent: skips if content hash matches (no embedding cost on restart).
    """
    if getattr(settings, "rag_spaces_system_enabled", False):
        try:
            from src.domains.rag_spaces.system_indexer import SystemSpaceIndexer
            from src.infrastructure.database.session import get_db_context as _sys_db_ctx

            async with _sys_db_ctx() as sys_db:
                indexer = SystemSpaceIndexer(sys_db)
                result = await indexer.index_faq_space()
            if result["status"] == "success":
                logger.info(
                    "system_rag_startup_indexed",
                    chunks_created=result["chunks_created"],
                )
            elif result["status"] == "skipped":
                logger.info("system_rag_startup_skipped")
            else:
                logger.warning("system_rag_startup_error", error=result.get("error"))
        except Exception as exc:
            # Non-blocking: system FAQ is optional, don't prevent app startup
            logger.warning("system_rag_startup_failed", error=str(exc))
