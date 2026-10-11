"""Native plugin URL imports use original fetch/quotas/components and mandatory confirmation."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_import_guard import (
    require_plugin_package_access,
)
from src.domains.agents.application.plugin_package_import import install_plugin_package
from src.domains.agents.application.plugin_package_models import PluginPackageWrite
from src.domains.agents.application.plugin_read import require_plugin_access
from src.domains.agents.application.plugin_state import observe_plugin_import_state
from src.domains.agents.application.plugin_url_import_schemas import (
    PluginUrlImportInput,
    PluginUrlImportPatch,
    PluginUrlImportSnapshot,
    canonical_plugin_url_import,
)
from src.domains.agents.application.plugin_url_import_spec import PLUGIN_URL_IMPORT_OPERATION
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.package_preview import preview_plugin_package
from src.domains.skills.url_import import fetch_skill_from_url
from src.domains.skills.url_rate_limit import rate_limit_url_import
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def _fetch(db: AsyncSession, owner_id: UUID, url: str) -> tuple[bytes, str]:
    await require_plugin_access(db, owner_id)
    if not settings.skills_url_import_enabled:
        raise CommandRejected("CAPABILITY_DISABLED")
    actor = await load_actor(db, owner_id)
    await db.commit()
    await rate_limit_url_import(actor)
    content, filename = await fetch_skill_from_url(url)
    await require_plugin_access(db, owner_id)
    if not settings.skills_url_import_enabled:
        raise CommandRejected("CAPABILITY_DISABLED")
    return content, filename


async def prepare_plugin_url_import(
    db: AsyncSession,
    actor_id: UUID,
    request: PluginUrlImportInput,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    desired = PluginUrlImportInput.model_validate(request.model_dump())
    content, filename = await _fetch(db, actor_id, desired.url)
    package = await preview_plugin_package(PluginImportService(db), content)
    state = await observe_plugin_import_state(db, actor_id, package.name, desired.replace_plugin_id)
    snapshot = PluginUrlImportSnapshot(
        request=desired,
        filename=filename,
        size_bytes=len(content),
        package=package,
        state=state,
        package_digest=hashlib.sha256(content).hexdigest(),
    )
    if len(snapshot.model_dump_json().encode("utf-8")) > 64_000:
        raise CommandRejected("INVALID_INPUT")
    await require_plugin_package_access(db, actor_id, snapshot.package, snapshot.state)
    return build_action_content(
        actor_id,
        PLUGIN_URL_IMPORT_OPERATION,
        PluginUrlImportPatch(plugin_url_import=snapshot),
        {"plugin_url_import": state.previous.model_dump(mode="json") if state.previous else None},
        {"plugin_url_import": snapshot.public_scope()},
        command_id=command_id,
    )


async def execute_plugin_url_import(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != PLUGIN_URL_IMPORT_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_plugin_url_import(draft):
        raise CommandRejected("INVALID_INPUT")
    selected = PluginUrlImportPatch.model_validate(draft.intent).plugin_url_import
    await require_plugin_package_access(db, actor_id, selected.package, selected.state)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    content, filename = await _fetch(db, actor_id, selected.request.url)
    if (
        filename != selected.filename
        or len(content) != selected.size_bytes
        or hashlib.sha256(content).hexdigest() != selected.package_digest
    ):
        raise CommandRejected("STALE_STATE")

    async def check(session: AsyncSession) -> None:
        await require_plugin_access(session, actor_id)
        if not settings.skills_url_import_enabled:
            raise CommandRejected("CAPABILITY_DISABLED")

    write = PluginPackageWrite(
        content=content,
        package=selected.package,
        state=selected.state,
        replace_plugin_id=selected.request.replace_plugin_id,
        value_field="plugin_url_import",
    )
    await install_plugin_package(db, actor_id, draft, write, receipt, check)
