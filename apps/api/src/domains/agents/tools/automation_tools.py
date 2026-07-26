"""Automation tools — pilot scheduled actions from chat (P11, ADR-140).

Closes the missing link identified by the 2026-07-21 product analysis:
"fais-moi ça tous les matins" could not succeed although the executor
already runs scheduled actions through the full agent pipeline.

Three tools:
- ``create_scheduled_action_tool`` — validates the schedule via the existing
  ``ScheduledActionCreate`` schema and returns a **SCHEDULED_ACTION draft**
  (requires_confirmation, D4 arbitration) — nothing is persisted until the
  user confirms in the HITL card.
- ``list_scheduled_actions_tool`` — read-only listing (exposes real ids so
  toggle can target them).
- ``toggle_scheduled_action_tool`` — direct reversible switch (no draft:
  toggling back is one message away; creation is the committing act).

Deletion stays UI-only in v1 (toggle-off covers the need reversibly) —
recorded in ADR-140.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.constants import AGENT_AUTOMATION
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.tools.decorators import read_tool, with_user_preferences, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.scheduled_actions.schedule_helpers import format_schedule_display
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


class ScheduledActionDraftInput(BaseModel):
    """Content of a SCHEDULED_ACTION draft (persisted until user confirmation)."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="User-facing title of the automation")
    action_prompt: str = Field(description="Instruction executed by the pipeline")
    days_of_week: list[int] = Field(description="ISO weekdays 1=Monday..7=Sunday")
    trigger_hour: int = Field(ge=0, le=23, description="Hour in user timezone")
    trigger_minute: int = Field(ge=0, le=59, description="Minute in user timezone")
    user_timezone: str = Field(description="IANA timezone of the schedule")
    schedule_human: str = Field(description="Localized human schedule for the card")


@write_tool(name="create_scheduled_action", agent_name=AGENT_AUTOMATION)
@with_user_preferences
async def create_scheduled_action_tool(
    title: Annotated[str, "Short user-facing title, e.g. 'Revue de presse IA'"],
    action_prompt: Annotated[
        str,
        "The instruction LIA will execute on each run, in the user's own words "
        "(e.g. 'fais-moi une revue de presse IA'). Full agent capabilities apply.",
    ],
    days_of_week: Annotated[
        list[int],
        "ISO weekdays to run on: 1=Monday .. 7=Sunday (e.g. [1,2,3,4,5] for weekdays).",
    ],
    trigger_hour: Annotated[int, "Hour of execution 0-23, in the USER's timezone"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    trigger_minute: Annotated[int, "Minute of execution 0-59"] = 0,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Create a recurring automation (returns a confirmation draft).

    Validates the schedule against the scheduled-actions contract and returns
    a SCHEDULED_ACTION draft the user must confirm before anything persists.

    Args:
        title: Short automation title.
        action_prompt: Instruction executed by the agent pipeline on each run.
        days_of_week: ISO weekdays (1=Monday..7=Sunday).
        trigger_hour: Execution hour in the user's timezone.
        runtime: LangChain tool runtime.
        trigger_minute: Execution minute.
        user_timezone: User timezone (injected by @with_user_preferences).
        locale: User language (injected by @with_user_preferences).

    Returns:
        UnifiedToolOutput carrying the draft (requires_confirmation=True),
        or a validation failure the LLM can relay.
    """
    config = validate_runtime_config(runtime, "create_scheduled_action_tool")
    if isinstance(config, UnifiedToolOutput):
        return config

    try:
        data = ScheduledActionCreate(
            title=title,
            action_prompt=action_prompt,
            days_of_week=days_of_week,
            trigger_hour=trigger_hour,
            trigger_minute=trigger_minute,
        )
    except ValidationError as exc:
        errors = exc.errors()
        message = str(errors[0]["msg"]) if errors else "invalid schedule"
        return UnifiedToolOutput.failure(
            message=message,
            error_code="invalid_schedule",
        )

    draft_input = ScheduledActionDraftInput(
        title=data.title,
        action_prompt=data.action_prompt,
        days_of_week=sorted(data.days_of_week),
        trigger_hour=data.trigger_hour,
        trigger_minute=data.trigger_minute,
        user_timezone=user_timezone,
        schedule_human=format_schedule_display(
            sorted(data.days_of_week), data.trigger_hour, data.trigger_minute, locale
        ),
    )
    return DraftService().create_draft(
        draft_type=DraftType.SCHEDULED_ACTION,
        content=draft_input.model_dump(),
        related_registry_ids=[],
        source_tool="create_scheduled_action_tool",
        user_language=locale,
    )


@read_tool(name="list_scheduled_actions", agent_name=AGENT_AUTOMATION)
@with_user_preferences
async def list_scheduled_actions_tool(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """List the user's recurring automations (id, title, schedule, state).

    Args:
        runtime: LangChain tool runtime.
        user_timezone: User timezone (injected).
        locale: User language (injected).

    Returns:
        UnifiedToolOutput with the automations list (real ids for toggling).
    """
    config = validate_runtime_config(runtime, "list_scheduled_actions_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    from src.domains.scheduled_actions.service import ScheduledActionService

    async with get_db_context() as db:
        actions = await ScheduledActionService(db).list_for_user(user_id)
        items: list[dict[str, Any]] = [
            {
                "id": str(action.id),
                "title": action.title,
                "schedule": format_schedule_display(
                    action.days_of_week, action.trigger_hour, action.trigger_minute, locale
                ),
                "is_enabled": action.is_enabled,
                "status": action.status,
                "last_executed_at": (
                    action.last_executed_at.isoformat() if action.last_executed_at else None
                ),
                "next_trigger_at": (
                    action.next_trigger_at.isoformat() if action.next_trigger_at else None
                ),
            }
            for action in actions
        ]

    return UnifiedToolOutput.data_success(
        message=f"{len(items)} automation(s) found",
        structured_data={"automations": items, "count": len(items)},
    )


@write_tool(name="toggle_scheduled_action", agent_name=AGENT_AUTOMATION)
@with_user_preferences
async def toggle_scheduled_action_tool(
    action_id: Annotated[str, "Automation id from list_scheduled_actions"],
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Enable/disable an automation (direct — reversible, no draft).

    Args:
        action_id: Automation UUID (from the listing tool).
        runtime: LangChain tool runtime.
        user_timezone: User timezone (injected).
        locale: User language (injected).

    Returns:
        UnifiedToolOutput with the new state, or a not-found failure.
    """
    config = validate_runtime_config(runtime, "toggle_scheduled_action_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    user_id = parse_user_id(config.user_id)

    try:
        target = UUID(action_id)
    except ValueError:
        return UnifiedToolOutput.failure(message="invalid automation id", error_code="invalid_id")

    from src.core.exceptions import ResourceNotFoundError
    from src.domains.scheduled_actions.service import ScheduledActionService

    try:
        async with get_db_context() as db:
            action = await ScheduledActionService(db).toggle(target, user_id)
            payload = {
                "id": str(action.id),
                "title": action.title,
                "is_enabled": action.is_enabled,
            }
    except ResourceNotFoundError:
        return UnifiedToolOutput.failure(message="automation not found", error_code="not_found")

    state = "enabled" if payload["is_enabled"] else "disabled"
    return UnifiedToolOutput.action_success(
        message=f"automation '{payload['title']}' is now {state}",
        structured_data=payload,
    )


async def execute_scheduled_action_draft(
    draft_content: dict[str, Any],
    user_id: UUID,
    deps: Any,
) -> dict[str, Any]:
    """Execute a confirmed SCHEDULED_ACTION draft: persist the automation.

    Registered in ``draft_executor.ensure_executors_registered()``. Runs on
    its own DB session (same pattern as the telephony executor). The service
    computes ``next_trigger_at`` from the schedule + user timezone and
    enforces the per-user cap.

    Args:
        draft_content: SCHEDULED_ACTION draft content (validated shape).
        user_id: Owner user id.
        deps: ToolDependencies (unused — own session).

    Returns:
        Result dict {"success", "title", "action_id"} on creation.
    """
    from src.domains.scheduled_actions.service import ScheduledActionService

    data = ScheduledActionCreate(
        title=draft_content["title"],
        action_prompt=draft_content["action_prompt"],
        days_of_week=draft_content["days_of_week"],
        trigger_hour=draft_content["trigger_hour"],
        trigger_minute=draft_content.get("trigger_minute", 0),
    )
    user_timezone = draft_content.get("user_timezone") or DEFAULT_USER_DISPLAY_TIMEZONE

    async with get_db_context() as db:
        service = ScheduledActionService(db)
        action = await service.create(
            user_id=user_id,
            data=data,
            user_timezone=user_timezone,
        )
        await db.commit()

    logger.info(
        "scheduled_action_created_from_chat",
        action_id=str(action.id),
        user_id=str(user_id),
    )
    return {"success": True, "title": action.title, "action_id": str(action.id)}
