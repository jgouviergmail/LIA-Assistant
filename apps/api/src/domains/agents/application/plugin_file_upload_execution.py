"""One bounded browser-confirmed file reaches the same package write port as URL imports."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_upload_execution import FormParser, _selected_file
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_file_upload import read_plugin_file_selection
from src.domains.agents.application.plugin_file_upload_schemas import (
    PluginFileUploadPatch,
    PluginFileUploadSelection,
    canonical_plugin_file_upload,
)
from src.domains.agents.application.plugin_package_import import install_plugin_package
from src.domains.agents.application.plugin_package_models import (
    PluginPackageCheck,
    PluginPackageWrite,
)
from src.domains.agents.application.plugin_state import observe_plugin_import_state
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.package_preview import PluginPackagePreview, preview_plugin_package
from src.domains.users.preference_cas import PreferenceWriteReceipt


def _require_matching_package(
    package: PluginPackagePreview, selected: PluginFileUploadSelection
) -> None:
    if selected.previous is not None and package.name != selected.previous.name:
        raise CommandRejected("INVALID_INPUT")


async def accept_plugin_file_upload(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
    check: PluginPackageCheck,
    *,
    file_confirmed: bool,
    parse_form: FormParser,
) -> dict[str, JsonValue]:
    if (
        file_confirmed is not True
        or draft.actor_id != actor_id
        or not canonical_plugin_file_upload(draft)
    ):
        raise CommandRejected("INVALID_INPUT")
    selected = PluginFileUploadPatch.model_validate(draft.intent).plugin_file_upload
    await check(db)
    if await read_plugin_file_selection(db, actor_id, selected.request) != selected:
        raise CommandRejected("STALE_STATE")
    await db.commit()
    async with parse_form() as form:
        file = _selected_file(form)
        if not (file.filename or "").lower().endswith(".zip"):
            raise CommandRejected("INVALID_INPUT")
        content = await file.read(selected.max_file_size_bytes + 1)
        if len(content) > selected.max_file_size_bytes:
            raise CommandRejected("CONSTRAINT_VIOLATION")
        await check(db)
        package = await preview_plugin_package(PluginImportService(db), content)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")
        _require_matching_package(package, selected)
        state = selected.state or await observe_plugin_import_state(
            db, actor_id, package.name, None
        )
        write = PluginPackageWrite(
            content=content,
            package=package,
            state=state,
            replace_plugin_id=selected.request.replace_plugin_id,
            value_field="plugin_file_upload",
        )
        await install_plugin_package(db, actor_id, draft, write, receipt, check)
        if not receipt.committed or receipt.values is None:
            raise CommandRejected("COMPLETION_UNKNOWN")
        receipt.values["upload_accepted"] = True
    return receipt.values
