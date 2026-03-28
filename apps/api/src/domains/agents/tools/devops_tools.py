"""DevOps tools for remote server management via Claude CLI over SSH.

Provides the claude_server_task_tool that allows administrators to execute
tasks on remote servers using Claude Code CLI. Claude CLI independently
inspects, diagnoses, and reports on server state.
"""

from __future__ import annotations

import json
import time
from typing import Annotated, Any

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.core.constants import DEVOPS_AGENT_NAME
from src.domains.agents.services.devops_ssh_service import DevOpsService
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.agents.tools.tool_registry import registered_tool
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

__all__ = ["claude_server_task_tool"]


async def _check_user_is_admin(user_id: str) -> bool:
    """Check if the user has superuser privileges.

    Args:
        user_id: User UUID string.

    Returns:
        True if the user is a superuser, False otherwise.
    """
    try:
        from uuid import UUID

        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.auth.models import User

            result = await db.get(User, UUID(str(user_id)))
            if result is None:
                return False
            return bool(result.is_superuser)
    except Exception as e:
        logger.warning("devops_admin_check_failed", user_id=str(user_id), error=str(e))
        return False


def _resolve_server(server_name: str = "") -> tuple[dict[str, Any] | None, str]:
    """Resolve server name to configuration dict from settings.

    If server_name is empty, returns the first configured server (default).

    Args:
        server_name: Server identifier. Empty string for default.

    Returns:
        Tuple of (server config dict or None, resolved server name).
    """
    settings = get_settings()
    servers = json.loads(settings.devops_servers)
    if not servers:
        return None, server_name

    # Default to first server if none specified
    if not server_name:
        return servers[0], servers[0]["name"]

    for srv in servers:
        if srv["name"] == server_name:
            return srv, server_name
    return None, server_name


def _get_available_servers() -> list[str]:
    """Get list of configured server names.

    Returns:
        List of server name strings.
    """
    settings = get_settings()
    servers = json.loads(settings.devops_servers)
    return [s["name"] for s in servers]


@registered_tool
@track_tool_metrics(
    tool_name="claude_server_task",
    agent_name=DEVOPS_AGENT_NAME,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def claude_server_task_tool(
    task: Annotated[str, "Natural language description of the task to perform on the server"],
    server: Annotated[str, "Target server name. Empty for default server."] = "",
    context: Annotated[str, "Additional context or constraints for the task"] = "",
    resume_session: Annotated[str, "Previous Claude session ID to resume"] = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> UnifiedToolOutput:
    """Execute a task on a remote server using Claude Code CLI.

    Claude CLI will autonomously inspect, diagnose, and report on the remote server.
    Supports: log inspection, Docker container management, system health checks,
    deployment status, error diagnosis, and more.

    Args:
        task: What to do on the server (natural language).
        server: Target server name from configuration. Empty for default (first configured).
        context: Additional context to inject into Claude's system prompt.
        resume_session: Optional session ID to resume a previous investigation.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput with Claude CLI's response and session metadata.
    """
    settings = get_settings()
    start_time = time.monotonic()

    # 1. Validate runtime & extract user_id
    validated = validate_runtime_config(runtime, "claude_server_task_tool")
    if isinstance(validated, UnifiedToolOutput):
        return validated

    # 2. Admin-only access check
    is_admin = await _check_user_is_admin(validated.user_id)
    if not is_admin:
        return UnifiedToolOutput.failure(
            message="This feature is restricted to administrators.",
            error_code="FORBIDDEN",
        )

    # 3. Resolve server config (default to first configured server)
    server_config, server = _resolve_server(server)
    if not server_config:
        available = _get_available_servers()
        return UnifiedToolOutput.failure(
            message=(
                f"Unknown server '{server}'. Available servers: {', '.join(available)}"
                if available
                else "No DevOps servers configured. Set DEVOPS_SERVERS in .env."
            ),
            error_code="INVALID_INPUT",
            metadata={"available_servers": available},
        )

    # 4. Extract side channel for streaming progress to frontend
    configurable = (runtime.config.get("configurable") or {}) if runtime else {}
    side_channel_queue = configurable.get("__side_channel_queue")
    logger.debug(
        "devops_side_channel_extraction",
        has_runtime=runtime is not None,
        has_configurable=bool(configurable),
        has_queue=side_channel_queue is not None,
        queue_type=type(side_channel_queue).__name__ if side_channel_queue else "None",
    )

    # 5. Execute via local subprocess or SSH + Claude CLI
    devops_service = DevOpsService()
    result = await devops_service.execute_claude_task(
        server_config=server_config,
        task=task,
        context=context or None,
        resume_session=resume_session or None,
        timeout=settings.devops_command_timeout,
        max_output_chars=settings.devops_max_output_chars,
        side_channel_queue=side_channel_queue,
    )

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # 6. Log execution for audit trail
    logger.info(
        "devops_task_executed",
        user_id=validated.user_id,
        server=server,
        task=task[:200],
        success=result.success,
        duration_ms=duration_ms,
        session_id=result.session_id,
    )

    if not result.success:
        return UnifiedToolOutput.failure(
            message=f"Claude CLI execution failed on '{server}': {result.error}",
            error_code="EXTERNAL_API_ERROR",
            metadata={"server": server, "duration_ms": duration_ms},
        )

    # 7. Return result with session_id for potential follow-up
    return UnifiedToolOutput.action_success(
        message=result.output,
        structured_data={
            "server": server,
            "session_id": result.session_id,
        },
        metadata={
            "usage": result.usage,
            "duration_ms": duration_ms,
            "resumed": bool(resume_session),
        },
    )
