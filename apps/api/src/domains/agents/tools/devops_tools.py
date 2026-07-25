"""DevOps tools for remote server management via Claude CLI over SSH.

Provides the claude_server_task_tool that allows administrators to execute
tasks on remote servers using Claude Code CLI. Claude CLI independently
inspects, diagnoses, and reports on server state.
"""

from __future__ import annotations

import json
import time
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import get_settings
from src.core.constants import DEVOPS_AGENT_NAME
from src.core.i18n_drafts import get_draft_error_message
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.services.devops_ssh_service import DevOpsService
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    get_user_language_safe,
    validate_runtime_config,
)
from src.domains.agents.tools.tool_registry import registered_tool
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)

__all__ = ["claude_server_task_tool", "execute_devops_task_draft"]


class DevOpsExecutionError(Exception):
    """Raised by the draft executor to surface a localized, non-crashing failure.

    The draft-executor framework catches this and renders ``str(self)`` as the
    user-facing message, so the text MUST already be localized — no traceback
    and no raw CLI output reach the user.
    """


def settings_default_language() -> str:
    """Fallback language when a draft predates the ``user_language`` field."""
    return str(get_settings().default_language)


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
            from src.domains.users.models import User

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
@rate_limit(
    max_calls=lambda: get_settings().devops_rate_limit_calls,
    window_seconds=lambda: get_settings().devops_rate_limit_window,
    scope="user",
)
async def claude_server_task_tool(
    task: Annotated[str, "Natural language description of the task to perform on the server"],
    server: Annotated[str, "Target server name. Empty for default server."] = "",
    context: Annotated[str, "Additional context or constraints for the task"] = "",
    resume_session: Annotated[str, "Previous Claude session ID to resume"] = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> UnifiedToolOutput:
    """Prepare a task to run on a remote server via Claude Code CLI.

    Claude CLI autonomously inspects, diagnoses and acts on the remote server:
    log inspection, Docker container management, system health checks,
    deployment status, error diagnosis, and more.

    The task is NOT run here. It returns a draft the user must confirm (FN-1);
    execution happens in ``execute_devops_task_draft`` once approved.

    Args:
        task: What to do on the server (natural language).
        server: Target server name from configuration. Empty for default (first configured).
        context: Additional context to inject into Claude's system prompt.
        resume_session: Optional session ID to resume a previous investigation.
        runtime: LangChain tool runtime (injected).

    Returns:
        UnifiedToolOutput carrying a DEVOPS_TASK draft awaiting confirmation.
    """
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

    # 4. FN-1 — never execute here. Build a draft and let the user confirm.
    #    Claude CLI runs unattended on the server with the full toolbox: a task
    #    phrased as an inspection can restart a container, edit a file or push
    #    a deployment. The confirmation is therefore unconditional — it does not
    #    depend on an LLM judging the task "destructive", and it applies to the
    #    resume path too (a follow-up turn drives the same CLI).
    #    The draft is the ONLY mechanism that gates both execution modes: the
    #    pipeline ignores `hitl_required` (its approval gate is a pass-through),
    #    and in ReAct a draft-producing tool must keep `hitl_required=False` or
    #    the user is asked twice.
    # Imported here, not at module level: `drafts.service` imports
    # `agents.tools.output`, which runs `agents/tools/__init__.py`, which
    # conditionally imports THIS module — a module-level import closes that
    # cycle and silently drops the whole DevOps tool family at boot (observed:
    # `conditional_tool_import_failed`). `DraftType` stays at module level;
    # `drafts.models` imports nothing from `agents.tools`.
    from src.domains.agents.drafts.service import DraftService

    user_language = await get_user_language_safe(runtime)
    logger.info(
        "devops_task_draft_created",
        user_id=validated.user_id,
        server=server,
        task=task[:200],
        resumed=bool(resume_session),
        elapsed_ms=int((time.monotonic() - start_time) * 1000),
    )
    return DraftService().create_draft(
        draft_type=DraftType.DEVOPS_TASK,
        content={
            "server": server,
            "task": task,
            "context": context,
            "resume_session": resume_session,
            "user_language": user_language,
        },
        source_tool="claude_server_task_tool",
        user_language=user_language,
    )


async def execute_devops_task_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: object,
) -> dict[str, Any]:
    """Execute a confirmed DEVOPS_TASK draft: run the task on the server.

    Registered in ``draft_executor._ensure_executors_registered()``.

    The admin check is repeated here on purpose. It ran when the draft was
    BUILT, and an arbitrary delay separates that from the confirmation — a
    revoked superuser would otherwise still get their pending task executed,
    and the HITL resume path can replay a decision. The check is one indexed
    read against a privilege that must hold at the moment the server is
    touched, not at the moment the request was phrased.

    Progress is streamed exactly as before the confirmation step existed. The
    executor contract passes no config, so the SSE queue is read from the
    context set by the draft executor — without it, a 30 s+ task would run in
    complete silence, which is the kind of regression a security control is not
    allowed to cause.

    Args:
        draft_content: Draft content (server, task, context, resume_session).
        user_id: User UUID — audit trail AND privilege re-check.
        deps: ToolDependencies — unused, the service opens what it needs.

    Returns:
        Result dict with the CLI output, server and session id.

    Raises:
        DevOpsExecutionError: Privileges lost, unknown server, or Claude CLI
            failure — rendered as a message, never a traceback.
    """
    from src.domains.agents.services.draft_executor import get_current_side_channel_queue

    settings = get_settings()
    start_time = time.monotonic()
    server = str(draft_content.get("server", ""))

    language = str(draft_content.get("user_language") or settings_default_language())

    if not await _check_user_is_admin(str(user_id)):
        logger.warning(
            "devops_task_privileges_lost",
            user_id=str(user_id),
            server=server,
            msg="admin rights revoked between draft creation and confirmation",
        )
        raise DevOpsExecutionError(get_draft_error_message(language))

    server_config, server = _resolve_server(server)
    if not server_config:
        raise DevOpsExecutionError(get_draft_error_message(language))

    result = await DevOpsService().execute_claude_task(
        server_config=server_config,
        task=str(draft_content.get("task", "")),
        context=draft_content.get("context") or None,
        resume_session=draft_content.get("resume_session") or None,
        timeout=settings.devops_command_timeout,
        max_output_chars=settings.devops_max_output_chars,
        side_channel_queue=get_current_side_channel_queue(),
    )

    duration_ms = int((time.monotonic() - start_time) * 1000)
    logger.info(
        "devops_task_executed",
        user_id=str(user_id),
        server=server,
        success=result.success,
        duration_ms=duration_ms,
        session_id=result.session_id,
    )

    if not result.success:
        # The CLI's own error text is kept in the log, not in the user message:
        # it can quote paths, container names and server state.
        logger.warning("devops_task_failed", server=server, error=str(result.error)[:500])
        raise DevOpsExecutionError(get_draft_error_message(language))

    return {
        "success": True,
        "output": result.output,
        "server": server,
        "session_id": result.session_id,
        "duration_ms": duration_ms,
    }
