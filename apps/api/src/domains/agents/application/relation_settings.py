"""Prepare and execute exact Relations preferences through their source transaction."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.relation_settings_schemas import (
    RelationSettingsPatch,
    ReviewedRelationScope,
)
from src.domains.agents.application.relation_settings_spec import RELATION_SETTINGS_UPDATE_OPERATION
from src.domains.relations.preference_commands import (
    RelationSettingsCompletionUnknown,
    update_relation_preferences,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def prepare_relation_settings(
    db: AsyncSession,
    actor_id: UUID,
    patch: RelationSettingsPatch,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = RelationSettingsPatch.model_validate(patch.model_dump(exclude_unset=True))
    if desired.relation_overview_scope is not None:
        expanded = desired.model_dump(mode="json", exclude_unset=True)
        expanded["relation_overview_scope"] = desired.relation_overview_scope.model_dump(
            mode="json"
        )
        desired = RelationSettingsPatch.model_validate(expanded)
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    before = {name: getattr(actor, name) for name in desired.model_fields_set}
    if "relation_overview_scope" in before and actor.relation_overview_scope is not None:
        ReviewedRelationScope.model_validate(actor.relation_overview_scope)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return build_action_content(
        actor_id,
        RELATION_SETTINGS_UPDATE_OPERATION,
        desired,
        before,
        desired.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def _fence(db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent) -> None:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def execute_relation_settings(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "relation_settings.update":
        raise CommandRejected("FORBIDDEN")
    desired = RelationSettingsPatch.model_validate(draft.intent)
    if draft.intent != draft.after or set(draft.before) != desired.model_fields_set:
        raise ValueError("Relations preferences require the exact confirmed before/after scope")
    await _fence(db, actor_id, draft)

    async def check() -> None:
        await _fence(db, actor_id, draft)

    try:
        await update_relation_preferences(
            db, actor_id, desired, expected=draft.before, receipt=receipt, check=check
        )
    except RelationSettingsCompletionUnknown as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
