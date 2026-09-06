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

N-07 (ADR-175) boundary: this chat tool creates ``time`` routines only. The
schema fields it omits (``trigger_kind``, ``condition_config``,
``requires_approval``) are additive with time defaults, so a chat-created
routine and a studio-created one are the SAME object — the studio is simply
where condition triggers and propose-first mode are configured. Growing this
tool's signature to author conditions in chat is deferred (the natural-language
surface for "run X only when a task is overdue" is a whole design of its own).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE, RECURRENCE_ROUTINE_LIMITS
from src.core.recurrence import (
    RecurrenceError,
    RecurrenceSpec,
    describe,
    recurrence_from_parameters,
)
from src.core.time_utils import now_utc
from src.domains.agents.constants import AGENT_AUTOMATION
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.service import DraftService
from src.domains.agents.registry.recurrence_parameters import RECURRENCE_DOCS
from src.domains.agents.tools.decorators import read_tool, with_user_preferences, write_tool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import (
    parse_user_id,
    validate_runtime_config,
)
from src.domains.scheduled_actions.schemas import ScheduledActionCreate
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


class ScheduledActionDraftInput(BaseModel):
    """Content of a SCHEDULED_ACTION draft (persisted until user confirmation)."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(description="User-facing title of the automation")
    action_prompt: str = Field(description="Instruction executed by the pipeline")
    recurrence: dict = Field(description="Serialized RecurrenceSpec of the automation")
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
    repeat: Annotated[str, RECURRENCE_DOCS["repeat"]],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    times: Annotated[list[str] | None, RECURRENCE_DOCS["times"]] = None,
    repeat_every: Annotated[int, RECURRENCE_DOCS["repeat_every"]] = 1,
    weekdays: Annotated[list[int] | None, RECURRENCE_DOCS["weekdays"]] = None,
    month_days: Annotated[list[int] | None, RECURRENCE_DOCS["month_days"]] = None,
    months: Annotated[list[int] | None, RECURRENCE_DOCS["months"]] = None,
    nth_weekday: Annotated[str | None, RECURRENCE_DOCS["nth_weekday"]] = None,
    every_minutes: Annotated[int | None, RECURRENCE_DOCS["every_minutes"]] = None,
    window_start: Annotated[str | None, RECURRENCE_DOCS["window_start"]] = None,
    window_end: Annotated[str | None, RECURRENCE_DOCS["window_end"]] = None,
    until_date: Annotated[str | None, RECURRENCE_DOCS["until_date"]] = None,
    max_occurrences: Annotated[int | None, RECURRENCE_DOCS["max_occurrences"]] = None,
    starting_on: Annotated[str | None, RECURRENCE_DOCS["starting_on"]] = None,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    locale: str = "fr",
) -> UnifiedToolOutput:
    """Create a recurring automation (returns a confirmation draft).

    The schedule is spoken in the flat vocabulary `RECURRENCE_DOCS` declares and
    `recurrence_from_parameters` translates — the ONE place a spoken schedule
    becomes a `RecurrenceSpec`. The three cron parameters this replaced could
    say "weekdays at one time" and nothing else: no single occurrence, no
    interval, no second time in the same day.

    Args:
        title: Short automation title.
        action_prompt: Instruction executed by the agent pipeline on each run.
        repeat: How the schedule walks the calendar.
        runtime: LangChain tool runtime.
        times: Times of day, `HH:MM`.
        repeat_every: One period out of N.
        weekdays: ISO weekdays for a weekly schedule.
        month_days: Days of month, or -1 for the last.
        months: Months for a yearly schedule.
        nth_weekday: `<nth>:<weekday>` for "the 2nd Tuesday".
        every_minutes: A step inside a window, instead of explicit times.
        window_start: First clock of that window.
        window_end: Last clock of that window.
        until_date: The last day the schedule serves.
        max_occurrences: How many firings the schedule holds.
        starting_on: The day the series starts, and its phase.
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
        recurrence = recurrence_from_parameters(
            repeat=repeat,
            today=now_utc().astimezone(ZoneInfo(user_timezone)).date(),
            times=times,
            repeat_every=repeat_every,
            weekdays=weekdays,
            month_days=month_days,
            months=months,
            nth_weekday=nth_weekday,
            every_minutes=every_minutes,
            window_start=window_start,
            window_end=window_end,
            until_date=until_date,
            max_occurrences=max_occurrences,
            starting_on=starting_on,
        )
        # What a ROUTINE may ask, published in its own manifest and enforced
        # here: the ceiling travels with the caller, never with the engine.
        recurrence.validate_against(RECURRENCE_ROUTINE_LIMITS)
        data = ScheduledActionCreate(
            title=title, action_prompt=action_prompt, recurrence=recurrence
        )
    except RecurrenceError as exc:
        # Written for the model to relay: it names what could not be read, so
        # the reader is asked again rather than told "invalid schedule".
        return UnifiedToolOutput.failure(message=str(exc), error_code="invalid_schedule")
    except ValidationError as exc:
        errors = exc.errors()
        message = str(errors[0]["msg"]) if errors else "invalid schedule"
        return UnifiedToolOutput.failure(message=message, error_code="invalid_schedule")

    draft_input = ScheduledActionDraftInput(
        title=data.title,
        action_prompt=data.action_prompt,
        recurrence=data.recurrence.model_dump(mode="json"),
        user_timezone=user_timezone,
        schedule_human=describe(data.recurrence, locale),
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
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
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
                "schedule": describe(action.recurrence_spec, locale),
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
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
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
        recurrence=RecurrenceSpec.model_validate(draft_content["recurrence"]),
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
