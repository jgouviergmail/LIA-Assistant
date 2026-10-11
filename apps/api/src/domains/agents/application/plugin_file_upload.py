"""An owned replacement and original package limits are sealed before selecting browser bytes."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export import authorize_management_export
from src.domains.agents.application.plugin_file_upload_schemas import (
    PluginFileUploadInput,
    PluginFileUploadPatch,
    PluginFileUploadSelection,
)
from src.domains.agents.application.plugin_file_upload_spec import PLUGIN_FILE_UPLOAD_OPERATION
from src.domains.agents.application.plugin_package_models import PluginImportState
from src.domains.agents.application.plugin_read import require_plugin_access
from src.domains.agents.application.plugin_read_schemas import PluginReadItem
from src.domains.agents.application.plugin_state import (
    observe_plugin_import_state,
    plugin_public_item,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.plugins.group_scope import load_plugin_group


async def read_plugin_file_selection(
    db: AsyncSession, actor_id: UUID, request: PluginFileUploadInput
) -> PluginFileUploadSelection:
    previous: PluginReadItem | None = None
    state: PluginImportState | None = None
    if request.replace_plugin_id is not None:
        group = await load_plugin_group(db, actor_id, request.replace_plugin_id)
        previous = plugin_public_item(group)
        state = await observe_plugin_import_state(
            db, actor_id, previous.name, request.replace_plugin_id
        )
    return PluginFileUploadSelection(
        request=request,
        previous=previous,
        state=state,
        max_file_size_bytes=settings.plugins_max_file_size_kb * 1024,
        max_package_files=settings.plugins_zip_max_files,
        max_decompressed_bytes=settings.plugins_zip_max_decompressed_kb * 1024,
        max_personal_plugins=settings.plugins_max_per_user,
    )


async def prepare_plugin_file_upload(
    db: AsyncSession,
    actor_id: UUID,
    request: PluginFileUploadInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await authorize_management_export(db, actor_id, context.application_origin)
    await require_plugin_access(db, actor_id)
    desired = PluginFileUploadInput.model_validate(request.model_dump())
    selected = await read_plugin_file_selection(db, actor_id, desired)
    return build_action_content(
        actor_id,
        PLUGIN_FILE_UPLOAD_OPERATION,
        PluginFileUploadPatch(plugin_file_upload=selected),
        {
            "plugin_file_upload": (
                selected.previous.model_dump(mode="json") if selected.previous else None
            )
        },
        {"plugin_file_upload": selected.public_scope()},
        command_id=command_id,
    )
