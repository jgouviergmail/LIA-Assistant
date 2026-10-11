"""One exact commit/receipt boundary for confirmed personal MCP setting changes."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import authorize_actor
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.personal_mcp_read import require_personal_mcp_access
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.mcp.personal_state_contract import PersonalMCPWriteCheck

PersonalMCPChange = Callable[[PersonalMCPWriteCheck], Awaitable[bool]]


async def check_personal_mcp_write(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    if draft.actor_id != actor_id:
        raise CommandRejected("FORBIDDEN")
    await require_personal_mcp_access(db, actor_id)
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def lock_personal_mcp_write(
    db: AsyncSession, actor_id: UUID, draft: ApplicationActionDraftContent
) -> None:
    await check_personal_mcp_write(db, actor_id, draft)
    authorize_actor(await UserRepository(db).get_by_id_for_preference_update(actor_id))


async def commit_personal_mcp_change(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
    apply: PersonalMCPChange,
    *,
    committed_values: dict[str, JsonValue] | None = None,
) -> None:
    if draft.actor_id != actor_id:
        raise CommandRejected("FORBIDDEN")

    async def check(session: AsyncSession) -> None:
        await check_personal_mcp_write(session, actor_id, draft)

    await lock_personal_mcp_write(db, actor_id, draft)
    changed = await apply(check)
    await check(db)
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as error:
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.no_op = not changed
    receipt.values = draft.after if committed_values is None else committed_values
