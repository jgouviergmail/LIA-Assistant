"""Confirmed debrief builds delegate work and spend to the source guarded lifecycle."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.i18n import normalize_language
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.relation_debrief_build_schemas import (
    RelationDebriefBuildPatch,
    RelationDebriefBuildRequest,
    RelationDebriefBuildScope,
)
from src.domains.agents.application.relation_debrief_build_spec import (
    RELATION_DEBRIEF_BUILD_OPERATION,
)
from src.domains.agents.application.relation_debrief_read import require_bounded_debrief
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.relations.debrief.controls import (
    DebriefControlRefused,
    DebriefControls,
    installed_debrief_controls,
)
from src.domains.relations.debrief.repository import RelationDebriefRepository
from src.domains.relations.debrief.schemas import DebriefStatus, RelationDebriefRead
from src.domains.relations.debrief.service import RelationDebriefService, read_of
from src.domains.relations.grouping_commands import grouping_debriefs
from src.domains.relations.identity import IdentityResolver
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.relations.preference_commands import lock_relation_owner
from src.domains.relations.repository import RelationAliasRepository
from src.domains.shared.text_normalization import fold_name
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.database.session import get_db_context
from src.infrastructure.llm.usage_guard import enforce_usage_limit
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter


async def require_debrief_build_access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RELATION_DEBRIEF)
    actor = await load_actor(db, actor_id)
    if not actor.relation_debrief_enabled:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})


async def debrief_build_scope(
    db: AsyncSession, actor_id: UUID, request: RelationDebriefBuildRequest
) -> RelationDebriefBuildScope:
    await require_debrief_build_access(db, actor_id)
    actor = await load_actor(db, actor_id)
    aliases = await RelationAliasRepository(db).list_for_user(actor_id)
    resolver = IdentityResolver.from_pairs((row.alias_key, row.canonical_key) for row in aliases)
    canonical = resolver.key(request.name)
    if canonical in resolver.aliases:
        raise ValueError("Selected relationship grouping is not flat")
    scope = RelationOverviewScope.from_stored(actor.relation_overview_scope)
    # Validate the published finite source selection before exposing it to a prompt.
    from src.domains.agents.application.relation_settings_read import RelationSettingsProjection

    RelationSettingsProjection(
        overview_scope=scope,
        debrief_enabled=True,
        debrief_platform_enabled=True,
        observed_at=datetime.now(UTC),
    )
    language = normalize_language(actor.language)
    inputs = {
        "canonical": canonical,
        "scope": scope.model_dump(mode="json"),
        "language": language,
        "timezone": actor.timezone,
        "personality": str(actor.personality_id),
        "journals_enabled": actor.journals_enabled,
        "full_name": actor.full_name,
        "email": actor.email,
        "local_date": datetime.now(resolve_user_timezone(actor)).date().isoformat(),
        "aliases": [
            [str(row.id), row.alias_key, row.canonical_key, row.alias_display_name]
            for row in aliases
            if row.alias_key == resolver.key(request.name)
            or row.canonical_key == canonical
            or row.alias_key == fold_name(request.name)
        ],
    }
    row = await RelationDebriefRepository(db).get(actor_id, canonical)
    status = read_of(row).status.value if row else DebriefStatus.ABSENT.value
    stored = await grouping_debriefs(db, actor_id, [canonical])
    await require_debrief_build_access(db, actor_id)
    return RelationDebriefBuildScope(
        request=request,
        canonical_key=canonical,
        input_digest=payload_digest(inputs),
        debrief_digest=payload_digest(stored),
        status=status,
        language=language,
        scope=scope.model_dump(mode="json"),
    )


async def prepare_relation_debrief_build(
    db: AsyncSession,
    actor_id: UUID,
    request: RelationDebriefBuildRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    selected = RelationDebriefBuildRequest.model_validate(request.model_dump())
    scope = await debrief_build_scope(db, actor_id, selected)
    return build_action_content(
        actor_id,
        RELATION_DEBRIEF_BUILD_OPERATION,
        RelationDebriefBuildPatch(relation_debrief=scope),
        {"relation_debrief": scope.public_scope()},
        {"relation_debrief": {**scope.public_scope(), "requested": True}},
        command_id=command_id,
    )


def canonical_relation_debrief_build(draft: ApplicationActionDraftContent) -> bool:
    scope = RelationDebriefBuildPatch.model_validate(draft.intent).relation_debrief
    return draft.before == {"relation_debrief": scope.public_scope()} and draft.after == {
        "relation_debrief": {**scope.public_scope(), "requested": True}
    }


@dataclass(frozen=True)
class _ApprovedDebrief:
    actor_id: UUID
    draft: ApplicationActionDraftContent
    selected: RelationDebriefBuildScope
    receipt: PreferenceWriteReceipt

    async def authority(self, db: AsyncSession) -> RelationDebriefBuildScope:
        await require_debrief_build_access(db, self.actor_id)
        if datetime.now(UTC) >= self.draft.expires_at:
            raise CommandRejected("EXPIRED")
        current = await debrief_build_scope(db, self.actor_id, self.selected.request)
        if current.input_digest != self.selected.input_digest:
            raise ResourceConflictError("relation_debrief", detail={"error_code": "STALE_STATE"})
        return current

    async def claim(self, db: AsyncSession) -> None:
        # Background settlements fence their child row directly. Lock it before
        # comparing, under the source claim's owner lock, so it cannot change
        # between exact approval validation and the source conditional upsert.
        await grouping_debriefs(db, self.actor_id, [self.selected.canonical_key], lock=True)
        if await self.authority(db) != self.selected:
            raise ResourceConflictError("relation_debrief", detail={"error_code": "STALE_STATE"})

    async def work(self) -> None:
        async with get_db_context() as db:
            await self.authority(db)
        await enforce_usage_limit(self.actor_id, layer="relation_debrief")

    async def publish(self, db: AsyncSession) -> None:
        await lock_relation_owner(db, self.actor_id)
        await self.authority(db)

    def committed(self, status: str) -> None:
        self.receipt.committed = True
        self.receipt.values = {
            "relation_debrief": {"name": self.selected.request.name, "generation_status": status}
        }


async def execute_relation_debrief_build(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "relation_debrief.build":
        raise CommandRejected("FORBIDDEN")
    if not canonical_relation_debrief_build(draft):
        raise ValueError("Debrief generation requires exact approved scope")
    selected = RelationDebriefBuildPatch.model_validate(draft.intent).relation_debrief
    approved = _ApprovedDebrief(actor_id, draft, selected, receipt)
    await approved.claim(db)
    await enforce_usage_limit(actor_id, layer="relation_debrief")
    limiter = await get_rate_limiter()
    if not await limiter.acquire(
        key=f"auth:relations_debrief_build:user:{actor_id}",
        max_calls=settings.relation_debrief_daily_build_cap,
        window_seconds=86400,
    ):
        raise CommandRejected("RATE_LIMIT_EXCEEDED")
    await db.commit()  # Source claim and settlement own independent short transactions.
    controls = DebriefControls(
        actor_id, approved.claim, approved.work, approved.publish, approved.committed
    )
    try:
        with installed_debrief_controls(controls):
            result = await RelationDebriefService(actor_id).build(
                selected.request.name, force=selected.request.force
            )
    except DebriefControlRefused as exc:
        raise exc.cause from exc
    except SQLAlchemyError as exc:
        if receipt.committed:
            approved.committed("completion_unknown")
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    await approved.authority(db)
    if result.status not in {DebriefStatus.READY, DebriefStatus.EMPTY}:
        raise CommandRejected(
            "RESOURCE_BUSY" if result.status is DebriefStatus.BUILDING else "EXECUTION_FAILED"
        )
    await _release_debrief_result(db, actor_id, selected, result, receipt)


async def _release_debrief_result(
    db: AsyncSession,
    actor_id: UUID,
    selected: RelationDebriefBuildScope,
    result: RelationDebriefRead,
    receipt: PreferenceWriteReceipt,
) -> None:
    """Release only the verified stored result and its actual generation disposition."""
    receipt.no_op = not receipt.committed
    require_bounded_debrief(result)
    row = await RelationDebriefRepository(db).get(actor_id, selected.canonical_key)
    if row is None or read_of(row) != result:
        raise ResourceConflictError("relation_debrief", detail={"error_code": "STALE_STATE"})
    status = "reused"
    if receipt.values is not None:
        recorded = receipt.values.get("relation_debrief")
        if isinstance(recorded, dict):
            recorded_status = recorded.get("generation_status")
            if isinstance(recorded_status, str):
                status = recorded_status
    receipt.committed = True
    receipt.values = {
        "relation_debrief": {
            **result.model_dump(mode="json"),
            "generation_status": status,
            "new_synthesis": status == "ready",
        }
    }
