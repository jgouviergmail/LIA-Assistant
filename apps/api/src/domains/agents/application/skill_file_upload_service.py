"""The shared original-browser package ledger settles one skill file upload."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.document_upload_execution import FormParser
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.package_upload_service import (
    PackageUploadDefinition,
    serve_package_upload_command,
)
from src.domains.agents.application.skill_file_upload_execution import accept_skill_file_upload
from src.domains.agents.application.skill_file_upload_spec import SKILL_FILE_UPLOAD_OPERATION
from src.domains.agents.application.skill_read import require_skill_access

_DEFINITION = PackageUploadDefinition(
    spec=SKILL_FILE_UPLOAD_OPERATION,
    field_name="skill_file_upload",
    access=require_skill_access,
    accept=accept_skill_file_upload,
)


async def serve_skill_file_upload_command(
    db: AsyncSession,
    actor_id: UUID,
    command_id: UUID,
    origin: ApplicationOrigin | None,
    *,
    file_confirmed: bool,
    parse_form: FormParser,
) -> ApplicationExecutionOutcome:
    return await serve_package_upload_command(
        db,
        actor_id,
        command_id,
        origin,
        _DEFINITION,
        file_confirmed=file_confirmed,
        parse_form=parse_form,
    )
