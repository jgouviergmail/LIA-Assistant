"""Proposals resolve original template facts and preserve every unrequested field."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_preferences import require_meeting_preferences
from src.domains.agents.application.meeting_template_schemas import (
    TemplateCreateInput,
    TemplateCreatePatch,
    TemplateCreation,
    TemplateDeleteInput,
    TemplateDeletePatch,
    TemplateRemoval,
    TemplateReplacement,
    TemplateUpdateInput,
    TemplateUpdatePatch,
    desired_template_update,
    template_creation_states,
    template_removal_states,
    template_replacement_states,
)
from src.domains.agents.application.meeting_template_spec import (
    TEMPLATE_CREATE_OPERATION,
    TEMPLATE_DELETE_OPERATION,
    TEMPLATE_UPDATE_OPERATION,
)
from src.infrastructure.meeting_templates import get_meeting_templates


async def prepare_template_creation(
    db: AsyncSession,
    actor_id: UUID,
    request: TemplateCreateInput,
    *,
    command_id: UUID | None = None,
    created_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    actor = await require_meeting_preferences(db, actor_id)
    facts = await get_meeting_templates().creation_facts(db, actor_id, request, actor.language)
    await require_meeting_preferences(db, actor_id)
    selected = TemplateCreation(request=request, expected=facts, created_id=created_id or uuid4())
    before, after = template_creation_states(selected)
    return build_action_content(
        actor_id,
        TEMPLATE_CREATE_OPERATION,
        TemplateCreatePatch(meeting_template_create=selected),
        before,
        after,
        command_id=command_id,
    )


async def prepare_template_replacement(
    db: AsyncSession,
    actor_id: UUID,
    request: TemplateUpdateInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    actor = await require_meeting_preferences(db, actor_id)
    before = await get_meeting_templates().get(db, actor_id, request.ref, actor.language)
    if before.builtin:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    request = request.model_copy(update={"ref": before.ref})
    desired = desired_template_update(request, before)
    await require_meeting_preferences(db, actor_id)
    selected = TemplateReplacement(request=request, expected=before, desired=desired)
    previous, after = template_replacement_states(selected)
    return build_action_content(
        actor_id,
        TEMPLATE_UPDATE_OPERATION,
        TemplateUpdatePatch(meeting_template_update=selected),
        previous,
        after,
        command_id=command_id,
    )


async def prepare_template_removal(
    db: AsyncSession,
    actor_id: UUID,
    request: TemplateDeleteInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    actor = await require_meeting_preferences(db, actor_id)
    before = await get_meeting_templates().get(db, actor_id, request.ref, actor.language)
    if before.builtin:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    request = request.model_copy(update={"ref": before.ref})
    default_ref = await get_meeting_templates().default_ref(db, actor_id)
    selected = TemplateRemoval(
        request=request,
        expected=before,
        default_template_ref=default_ref,
    )
    await require_meeting_preferences(db, actor_id)
    previous, after = template_removal_states(selected)
    return build_action_content(
        actor_id,
        TEMPLATE_DELETE_OPERATION,
        TemplateDeletePatch(meeting_template_delete=selected),
        previous,
        after,
        command_id=command_id,
    )
