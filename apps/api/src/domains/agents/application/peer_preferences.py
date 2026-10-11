"""Approved selected consents use source setters under the existing account lock."""

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.peer_preference_schemas import (
    PEER_PREFERENCE_COLUMNS,
    PeerPreferencePatch,
)
from src.domains.agents.application.peer_preference_spec import PEER_PREFERENCE_OPERATION
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.peers.service import PeersService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository


def _consent_values(actor: User, fields: Iterable[str]) -> dict[str, JsonValue]:
    return {field: bool(getattr(actor, PEER_PREFERENCE_COLUMNS[field])) for field in fields}


async def prepare_peer_preferences(
    db: AsyncSession, actor_id: UUID, patch: PeerPreferencePatch, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = PeerPreferencePatch.model_validate(patch.model_dump(exclude_unset=True))
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.PEERS)
    actor = await load_actor(db, actor_id)
    before = _consent_values(actor, desired.model_fields_set)
    return build_action_content(
        actor_id,
        PEER_PREFERENCE_OPERATION,
        desired,
        before,
        desired.model_dump(mode="json", exclude_unset=True),
        command_id=command_id,
    )


async def execute_peer_preferences(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "peer_preferences.update":
        raise CommandRejected("FORBIDDEN")
    desired = PeerPreferencePatch.model_validate(draft.intent)
    if draft.intent != draft.after or set(draft.before) != desired.model_fields_set:
        raise ValueError("Consent changes require exact approved sparse fields")

    async def check() -> None:
        await require_application_tools(db)
        await require_capability_fresh(db, PlatformCapability.PEERS)
        await load_actor(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    actor = await UserRepository(db).get_by_id_for_preference_update(actor_id)
    await check()
    if actor is None:
        raise CommandRejected("FORBIDDEN")
    current = _consent_values(actor, desired.model_fields_set)
    if current != draft.before:
        raise ResourceConflictError("peer_preferences", detail={"error_code": "STALE_STATE"})
    if current == draft.after:
        receipt.committed = True
        receipt.no_op = True
        return
    service = PeersService(db)
    if desired.discovery_enabled is not None:
        await service.set_discovery(actor_id, desired.discovery_enabled)
    if desired.email_visible is not None:
        await service.set_email_visibility(actor_id, desired.email_visible)
    await check()
    if _consent_values(actor, desired.model_fields_set) != draft.after:
        raise ValueError("Source consent postcondition differs from approval")
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
