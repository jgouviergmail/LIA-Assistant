"""Reset binds every owned source record and uses the same pure transition as the UI."""

from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.psyche_queries import require_psyche_access
from src.domains.agents.application.psyche_reset_schemas import (
    PsycheResetIntent,
    PsycheResetPatch,
    PsycheResetValues,
)
from src.domains.agents.application.psyche_reset_spec import PSYCHE_RESET_OPERATION
from src.domains.agents.application.psyche_settings import psyche_settings_fence
from src.domains.psyche.reset_commands import PsycheResetCompletionUnknown, reset_managed_psyche
from src.domains.psyche.reset_snapshot import psyche_reset_snapshot
from src.domains.users.preference_cas import PreferenceWriteReceipt


def psyche_reset_preview(
    values: PsycheResetValues,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    scope = values.expected
    before: dict[str, JsonValue] = {
        "psyche_reset": {
            "level": values.request.level,
            "states": scope.states,
            "history": scope.history,
            "values": scope.before,
        }
    }
    after: dict[str, JsonValue] = {
        "psyche_reset": {
            "level": values.request.level,
            "states": 0 if values.request.level == "purge" else scope.states,
            "history": 0 if values.request.level == "purge" else scope.history + scope.states,
            "values": scope.after,
        }
    }
    return before, after


async def prepare_psyche_reset(
    db: AsyncSession, actor_id: UUID, request: PsycheResetIntent, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = PsycheResetIntent.model_validate(request.model_dump())
    await require_psyche_access(db, actor_id)
    scope = await psyche_reset_snapshot(db, actor_id, selected)
    values = PsycheResetValues(request=selected, expected=scope)
    before, after = psyche_reset_preview(values)
    await require_psyche_access(db, actor_id)
    return build_action_content(
        actor_id,
        PSYCHE_RESET_OPERATION,
        PsycheResetPatch(psyche_reset=values),
        before,
        after,
        command_id=command_id,
    )


def canonical_psyche_reset(draft: ApplicationActionDraftContent) -> bool:
    values = PsycheResetPatch.model_validate(draft.intent).psyche_reset
    return (draft.before, draft.after) == psyche_reset_preview(values)


async def execute_psyche_reset(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "psyche.reset":
        raise CommandRejected("FORBIDDEN")
    if not canonical_psyche_reset(draft):
        raise ValueError("Reset requires the exact confirmed source effects")
    await psyche_settings_fence(db, actor_id, draft)
    values = PsycheResetPatch.model_validate(draft.intent).psyche_reset

    async def check() -> None:
        await psyche_settings_fence(db, actor_id, draft)

    try:
        await reset_managed_psyche(
            db, actor_id, values.request, expected=values.expected, receipt=receipt, check=check
        )
    except PsycheResetCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
