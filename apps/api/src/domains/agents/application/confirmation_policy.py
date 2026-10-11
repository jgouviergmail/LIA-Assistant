"""Fail-closed review of reversible personalization; mixed patches keep HITL.

Credentials, external delivery, microphone capture, deletion and autonomous
execution permissions are deliberately outside this exception.
"""

from collections.abc import Mapping

CONFIRMATION_FREE_FIELDS: dict[str, frozenset[str]] = {
    "habit_settings.update": frozenset({"habits_enabled"}),
    "psyche_settings.update": frozenset(
        {"psyche_display_avatar", "psyche_sensitivity", "psyche_stability"}
    ),
    "journal_settings.update": frozenset({"journals_enabled", "journal_consolidation_enabled"}),
    "interest_settings.update": frozenset(
        {
            "interests_enabled",
            "interests_notify_start_hour",
            "interests_notify_end_hour",
            "interests_notify_min_per_day",
            "interests_notify_max_per_day",
        }
    ),
    "heartbeat_preferences.update": frozenset(
        {
            "heartbeat_enabled",
            "heartbeat_notify_start_hour",
            "heartbeat_notify_end_hour",
            "heartbeat_disabled_sources",
            "moment_kinds_disabled",
        }
    ),
    "preferences.update": frozenset(
        {
            "timezone",
            "language",
            "personality_id",
            "theme",
            "color_theme",
            "font_family",
            "font_size",
            "image_generation_enabled",
            "image_generation_default_quality",
            "image_generation_default_size",
            "image_generation_output_format",
            "image_generation_prompt_enhancement",
            "exchange_rhythm",
        }
    ),
    "layout_preferences.update": frozenset(
        {"briefing_preferences", "chat_shortcuts", "settings_shortcuts"}
    ),
    "assistant_preferences.update": frozenset(
        {
            "memory_enabled",
            "execution_mode",
            "voice_enabled",
            "voice_mode_enabled",
            "tokens_display_enabled",
            "onboarding_completed",
            "debug_panel_enabled",
            "response_display_mode",
        }
    ),
}

# A saved hands-free preference can start the existing wake-word microphone
# owner when the interface applies it. Stopping it is still an immediate action.
SENSITIVE_ENABLE_FIELDS: dict[str, frozenset[str]] = {
    "assistant_preferences.update": frozenset({"voice_mode_enabled"}),
}


def requires_confirmation(operation_id: str, intent: Mapping[str, object]) -> bool:
    allowed = CONFIRMATION_FREE_FIELDS.get(operation_id, frozenset())
    if not intent or not set(intent) <= allowed:
        return True
    sensitive = SENSITIVE_ENABLE_FIELDS.get(operation_id, frozenset())
    return any(intent[field] is not False for field in set(intent) & sensitive)


def policy_for_call(
    tool_name: str, arguments: Mapping[str, object], policy: str | None
) -> str | None:
    """The outer ledger and the native executor use the same reviewed decision."""
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS

    operation = APPLICATION_OPERATIONS.get_by_tool_name(tool_name)
    if operation is None or operation.operation_id not in CONFIRMATION_FREE_FIELDS:
        return policy
    request = _call_intent(operation.operation_id, arguments)
    return (
        "reversible"
        if request is not None and not requires_confirmation(operation.operation_id, request)
        else policy
    )


def _call_intent(operation_id: str, arguments: Mapping[str, object]) -> dict[str, object] | None:
    from pydantic import BaseModel

    candidates = [value for key, value in arguments.items() if key != "runtime"]
    if len(candidates) != 1:
        return None
    request = candidates[0]
    if isinstance(request, BaseModel):
        request = request.model_dump(exclude_unset=True)
    if not isinstance(request, dict):
        return None
    if operation_id == "preferences.update":
        if request.get("mode") in {"increase_font", "decrease_font"}:
            return {
                "font_size": None
            }  # Only the field name is reviewed here; preparation resolves its value.
        request = request.get("patch")
        if isinstance(request, BaseModel):
            request = request.model_dump(exclude_unset=True)
    return request if isinstance(request, dict) else None


async def authorize_reversible_replay(tool_name: str) -> None:
    """A cached ledger result cannot bypass current account or platform permissions."""
    from src.domains.agents.application.authorization import load_actor
    from src.domains.agents.application.availability import require_application_tools
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.application.registry import APPLICATION_OPERATIONS
    from src.domains.agents.context.runtime_context import runtime_context_if_running
    from src.domains.feature_switches.guard import require_capability_fresh
    from src.infrastructure.database.session import get_db_context

    context = runtime_context_if_running()
    if context is None:
        raise CommandRejected("FORBIDDEN")
    spec = APPLICATION_OPERATIONS.get_by_tool_name(tool_name)
    if spec is None:
        raise CommandRejected("UNKNOWN_OPERATION")
    async with get_db_context() as db:
        await require_application_tools(db)
        await load_actor(db, context.user_id, administrative=spec.administrative)
        for capability in spec.required_capabilities:
            await require_capability_fresh(db, capability)


async def reversible_access_refusal(tool_name: str) -> object | None:
    from sqlalchemy.exc import SQLAlchemyError

    from src.core.exceptions import AuthorizationError
    from src.domains.agents.application.availability import application_access_error_code
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.agents.tools.output import UnifiedToolOutput

    try:
        await authorize_reversible_replay(tool_name)
    except AuthorizationError as exc:
        return UnifiedToolOutput.failure(
            message="Application setting access refused.",
            error_code=application_access_error_code(exc),
        )
    except CommandRejected as exc:
        return UnifiedToolOutput.failure(
            message="Application setting access refused.", error_code=exc.code
        )
    except SQLAlchemyError:
        return UnifiedToolOutput.failure(
            message="Application setting access unavailable.",
            error_code="DEPENDENCY_ERROR",
        )
    return None
