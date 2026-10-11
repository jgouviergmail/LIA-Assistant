"""Account opt-outs for shared MCP servers; global server configuration is never written."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import (
    ResourceConflictError,
    raise_admin_mcp_server_not_found,
    raise_user_not_found,
)
from src.domains.user_mcp.schemas import AdminMCPServerResponse, AdminMCPToolInfo
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.mcp import client_manager
from src.infrastructure.mcp.catalogue_fingerprint import canonical_fingerprint
from src.infrastructure.mcp.preferences_contract import (
    SharedMCPPreferenceSnapshot as SharedMCPPreferenceSnapshot,
)
from src.infrastructure.mcp.preferences_contract import saved_shared_mcp_refusals


def assert_shared_preference_coverage() -> None:
    # Descriptions/tools remain the full-catalogue read slice; this owner reviews them
    # because they contribute to the exact displayed-identity digest.
    if set(AdminMCPServerResponse.model_fields) != {
        "server_key",
        "name",
        "description",
        "tools_count",
        "tools",
        "enabled_for_user",
    } or set(AdminMCPToolInfo.model_fields) != {"name", "description", "title"}:
        raise AssertionError("New shared MCP UI fields require explicit projection review")


assert_shared_preference_coverage()


async def read_shared_mcp_preferences(
    db: AsyncSession, actor_id: UUID, server_key: str | None = None
) -> list[SharedMCPPreferenceSnapshot]:
    actor: User | None = await db.scalar(
        select(User)
        .where(
            User.id == actor_id,
            User.is_active,
            User.deleted_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise_user_not_found(actor_id)
    if server_key is not None:
        return [shared_mcp_snapshot(actor, server_key)]
    return [_displayed_snapshot(server) for server in list_shared_server_settings(actor)]


def list_shared_server_settings(user: User) -> list[AdminMCPServerResponse]:
    from src.domains.agents.registry.domain_taxonomy import slugify_mcp_server_name
    from src.infrastructure.mcp.registration import (
        get_admin_mcp_domains,
        get_admin_mcp_server_domains,
    )

    manager = client_manager.get_mcp_client_manager()
    if manager is None:
        return []
    disabled = set(saved_shared_mcp_refusals(user.admin_mcp_disabled_servers))
    descriptions = get_admin_mcp_domains()
    domains = get_admin_mcp_server_domains()
    return [
        AdminMCPServerResponse(
            server_key=key,
            name=key.replace("_", " ").title(),
            description=descriptions.get(domains.get(key, slugify_mcp_server_name(key))),
            tools_count=len(tools),
            tools=[
                AdminMCPToolInfo(
                    name=tool.tool_name, description=tool.description, title=tool.title
                )
                for tool in tools
            ],
            enabled_for_user=key not in disabled,
        )
        for key, tools in manager.discovered_tools.items()
    ]


def shared_mcp_snapshot(user: User, server_key: str) -> SharedMCPPreferenceSnapshot:
    displayed = next(
        (server for server in list_shared_server_settings(user) if server.server_key == server_key),
        None,
    )
    if displayed is None:
        raise_admin_mcp_server_not_found(server_key)
    return _displayed_snapshot(displayed)


def _displayed_snapshot(displayed: AdminMCPServerResponse) -> SharedMCPPreferenceSnapshot:
    return SharedMCPPreferenceSnapshot(
        server_key=displayed.server_key,
        name=displayed.name,
        enabled_for_user=displayed.enabled_for_user,
        tools_count=displayed.tools_count,
        catalogue_digest=canonical_fingerprint(
            displayed.model_dump(mode="json", exclude={"enabled_for_user"})
        ),
    )


async def set_shared_mcp_enabled(
    db: AsyncSession,
    actor_id: UUID,
    server_key: str,
    enabled: bool,
    *,
    expected: SharedMCPPreferenceSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
) -> SharedMCPPreferenceSnapshot:
    actor = await _locked_actor(db, actor_id)
    before = shared_mcp_snapshot(actor, server_key)
    if expected is not None and before != expected:
        raise ResourceConflictError("shared_mcp_preference", detail={"error_code": "STALE_STATE"})
    return await _save_shared_state(db, actor, before, enabled, receipt)


async def toggle_shared_mcp_enabled(
    db: AsyncSession, actor_id: UUID, server_key: str
) -> SharedMCPPreferenceSnapshot:
    actor = await _locked_actor(db, actor_id)
    before = shared_mcp_snapshot(actor, server_key)
    return await _save_shared_state(db, actor, before, not before.enabled_for_user, None)


async def _locked_actor(db: AsyncSession, actor_id: UUID) -> User:
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise_user_not_found(actor_id)
    return actor


async def _save_shared_state(
    db: AsyncSession,
    actor: User,
    before: SharedMCPPreferenceSnapshot,
    enabled: bool,
    receipt: PreferenceWriteReceipt | None,
) -> SharedMCPPreferenceSnapshot:
    server_key = before.server_key
    if before.enabled_for_user == enabled:
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return before
    disabled = saved_shared_mcp_refusals(actor.admin_mcp_disabled_servers)
    actor.admin_mcp_disabled_servers = (
        [key for key in disabled if key != server_key] if enabled else [*disabled, server_key]
    )
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return before.model_copy(update={"enabled_for_user": enabled})
