"""Human-confirmed source metadata and activation changes, with private full-row CAS."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID

import structlog
from pydantic import JsonValue, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.space_update_schemas import (
    SpaceUpdateInput,
    SpaceUpdatePatch,
    SpaceUpdateSelection,
    SpaceUpdateTarget,
    canonical_space_update,
)
from src.domains.agents.application.space_update_spec import SPACE_UPDATE_OPERATION
from src.domains.agents.effects.digest import payload_digest
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.rag_spaces import space_mutation, ui_queries
from src.domains.rag_spaces.models import RAGSpace
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.users.preference_cas import PreferenceWriteReceipt

logger = structlog.get_logger(__name__)
_SOURCE_ROW = TypeAdapter(dict[str, JsonValue])


async def _access(db: AsyncSession, actor_id: UUID) -> None:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.RAG_SPACES)
    await load_actor(db, actor_id)


async def _source_row(db: AsyncSession, actor_id: UUID, space_id: UUID) -> dict[str, JsonValue]:
    raw = _SOURCE_ROW.validate_python(
        await db.scalar(
            select(func.to_jsonb(RAGSpace.__table__.table_valued())).where(
                RAGSpace.id == space_id, RAGSpace.user_id == actor_id
            )
        )
    )
    if len(json.dumps(raw, ensure_ascii=False).encode("utf-8")) > 64_000:
        raise ValueError("Source space too large for exact approval")
    return raw


def _result_digest(raw: dict[str, JsonValue]) -> str:
    # Only the source's automatic write timestamp may differ from exact consent.
    return payload_digest({key: value for key, value in raw.items() if key != "updated_at"})


async def _selection(
    db: AsyncSession, actor_id: UUID, request: SpaceUpdateInput
) -> SpaceUpdateSelection:
    space = await ui_queries.owned_space(db, actor_id, request.space_id)
    before = SpaceUpdateTarget.model_validate(space)
    changes = space_mutation.source_update_values(request.name, request.description)
    source_intent = {key: value if value is not None else "" for key, value in changes.items()}
    normalized = SpaceUpdateInput.model_validate(
        {**request.model_dump(exclude_unset=True), **source_intent}
    )
    # Empty description is the source's explicit clearing spelling. Keep that
    # input spelling while publishing the actual resulting NULL to the human.
    after_values: dict[str, object] = {**before.model_dump(), **changes}
    if request.is_active is not None:
        after_values["is_active"] = request.is_active
    after = SpaceUpdateTarget.model_validate(after_values)
    raw = await _source_row(db, actor_id, space.id)
    desired: dict[str, JsonValue] = {**raw, **changes}
    if request.is_active is not None:
        desired["is_active"] = request.is_active
    return SpaceUpdateSelection(
        request=normalized,
        expected=before,
        proposed=after,
        state_digest=payload_digest(raw),
        result_digest=_result_digest(desired),
    )


async def _verify_update(
    db: AsyncSession, actor_id: UUID, expected: SpaceUpdateSelection
) -> dict[str, JsonValue]:
    actual = await ui_queries.owned_space(db, actor_id, expected.expected.id)
    if (
        SpaceUpdateTarget.model_validate(actual) != expected.proposed
        or _result_digest(await _source_row(db, actor_id, actual.id)) != expected.result_digest
    ):
        raise ValueError("Source space does not match approved resulting fields")
    return {
        **expected.public_scope(after=True),
        "space": (await ui_queries.space_metadata(db, actual)).model_dump(mode="json"),
    }


async def prepare_space_update(
    db: AsyncSession, actor_id: UUID, request: SpaceUpdateInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    selected = SpaceUpdateInput.model_validate(request.model_dump(exclude_unset=True))
    await _access(db, actor_id)
    scope = await _selection(db, actor_id, selected)
    await _access(db, actor_id)
    return build_action_content(
        actor_id,
        SPACE_UPDATE_OPERATION,
        SpaceUpdatePatch(space_update=scope),
        {"space_update": scope.public_scope()},
        {"space_update": scope.public_scope(after=True)},
        command_id=command_id,
    )


async def execute_space_update(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != SPACE_UPDATE_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_space_update(draft):
        raise ValueError("Space update requires an exact canonical scope")
    expected = SpaceUpdatePatch.model_validate(draft.intent).space_update

    async def check() -> None:
        await _access(db, actor_id)
        if datetime.now(UTC) >= draft.expires_at:
            raise CommandRejected("EXPIRED")

    await check()
    service = RAGSpaceService(db)
    await service.get_space(expected.request.space_id, actor_id, for_update=True)
    await check()
    if await _selection(db, actor_id, expected.request) != expected:
        raise ResourceConflictError("space_update", detail={"error_code": "STALE_STATE"})
    if expected.expected == expected.proposed:
        receipt.committed = True
        receipt.no_op = True
        return
    await service.update_space(
        expected.expected.id,
        actor_id,
        expected.request.name,
        expected.request.description,
        commit=False,
    )
    if expected.request.is_active is not None:
        await service.set_space_activation(
            expected.expected.id, actor_id, expected.request.is_active, commit=False
        )
    await db.flush()
    public = await _verify_update(db, actor_id, expected)
    await check()
    try:
        await db.commit()
    except (Exception, asyncio.CancelledError) as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.values = {"space_update": public}
    if expected.expected.is_active != expected.proposed.is_active:
        try:
            space_mutation.publish_activation(expected.proposed.is_active)
        except Exception as exc:
            logger.warning("space_activation_telemetry_failed", error_type=type(exc).__name__)
