"""Personal file imports freeze an exact optional replacement and original package limits."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import SKILLS_MAX_FILE_SIZE_KB
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.skill_file_upload_schemas import (
    SkillFileUploadInput,
    SkillFileUploadPatch,
    SkillFileUploadSelection,
)
from src.domains.agents.application.skill_file_upload_spec import SKILL_FILE_UPLOAD_OPERATION
from src.domains.agents.application.skill_import_state import observe_skill_import_state
from src.domains.agents.application.skill_read import require_skill_access
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.skills.models import SkillProvenance
from src.domains.skills.preference_service import captures_managed
from src.domains.skills.removal import observe_removal


async def read_skill_file_selection(
    db: AsyncSession, actor_id: UUID, request: SkillFileUploadInput
) -> SkillFileUploadSelection:
    previous: SkillReadItem | None = None
    digest = None
    if request.replace_skill_id is not None:
        observed = await observe_removal(db, actor_id, request.replace_skill_id)
        previous = SkillReadItem.model_validate(observed.metadata)
        if captures_managed(previous.provenance or "authored", SkillProvenance.AUTHORED):
            raise CommandRejected("INVALID_INPUT")
        state = await observe_skill_import_state(
            db, actor_id, previous.name, request.replace_skill_id
        )
        digest = state.digest
    return SkillFileUploadSelection(
        request=request,
        previous=previous,
        state_digest=digest,
        max_file_size_bytes=SKILLS_MAX_FILE_SIZE_KB * 1024,
        max_package_files=settings.skills_zip_max_files,
        max_decompressed_bytes=settings.skills_zip_max_decompressed_kb * 1024,
        max_personal_skills=settings.skills_max_per_user,
    )


async def prepare_skill_file_upload(
    db: AsyncSession,
    actor_id: UUID,
    request: SkillFileUploadInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_skill_access(db, actor_id)
    desired = SkillFileUploadInput.model_validate(request.model_dump())
    selected = await read_skill_file_selection(db, actor_id, desired)
    return build_action_content(
        actor_id,
        SKILL_FILE_UPLOAD_OPERATION,
        SkillFileUploadPatch(skill_file_upload=selected),
        {
            "skill_file_upload": (
                selected.previous.model_dump(mode="json") if selected.previous else None
            )
        },
        {"skill_file_upload": selected.public_scope()},
        command_id=command_id,
    )
