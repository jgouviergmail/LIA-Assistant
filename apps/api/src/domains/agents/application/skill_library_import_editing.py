"""Library amendments retain source identity and rebuild observations at fresh consent."""

from src.domains.agents.application.command_repository import replace_pending_command
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.skill_library_import import (
    prepare_library_install,
    prepare_library_update,
)
from src.domains.agents.application.skill_library_import_schemas import (
    LibraryImportPatch,
    LibraryInstallInput,
    LibraryUpdateInput,
)
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.infrastructure.database.session import get_db_context


async def rebuild_library_import(
    old: ApplicationActionDraftContent, modified: dict[str, object]
) -> dict[str, object]:
    context = runtime_context_if_running()
    if context is None or context.user_id != old.actor_id:
        raise CommandRejected("FORBIDDEN")
    if modified.get("remove_fields"):
        raise CommandRejected("INVALID_INPUT")
    selected = LibraryImportPatch.model_validate(old.intent).skill_library_import
    async with get_db_context() as db:
        if isinstance(selected.request, LibraryInstallInput):
            install = LibraryInstallInput.model_validate(modified.get("intent"))
            if install.model_dump(exclude={"commit_sha"}) != selected.request.model_dump(
                exclude={"commit_sha"}
            ):
                raise CommandRejected("INVALID_INPUT")
            revised = await prepare_library_install(
                db, old.actor_id, install, command_id=old.command_id
            )
        else:
            update = LibraryUpdateInput.model_validate(modified.get("intent"))
            if update.skill_id != selected.request.skill_id:
                raise CommandRejected("INVALID_INPUT")
            revised = await prepare_library_update(
                db, old.actor_id, update, command_id=old.command_id
            )
        if not await replace_pending_command(db, old, revised, origin=context.application_origin):
            raise CommandRejected("STALE_STATE")
    return revised.model_dump(mode="json")
