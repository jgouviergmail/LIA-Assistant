"""The shared original-browser package ledger settles one plugin file upload."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.application_origin import ApplicationOrigin
from src.domains.agents.application.document_upload_execution import FormParser
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.package_upload_service import (
    PackageUploadDefinition,
    serve_package_upload_command,
)
from src.domains.agents.application.plugin_file_upload_execution import accept_plugin_file_upload
from src.domains.agents.application.plugin_file_upload_spec import PLUGIN_FILE_UPLOAD_OPERATION
from src.domains.agents.application.plugin_read import require_plugin_access

_DEFINITION = PackageUploadDefinition(
    spec=PLUGIN_FILE_UPLOAD_OPERATION,
    field_name="plugin_file_upload",
    access=require_plugin_access,
    accept=accept_plugin_file_upload,
)


async def serve_plugin_file_upload_command(
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
