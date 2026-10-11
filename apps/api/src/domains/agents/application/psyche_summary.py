"""Source summary generation keeps confirmation, initialization and paid boundaries distinct."""

import json
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import ResourceConflictError
from src.core.i18n import normalize_language
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.psyche_queries import psyche_settings, require_psyche_access
from src.domains.agents.application.psyche_settings import psyche_settings_fence
from src.domains.agents.application.psyche_summary_schemas import (
    PsycheSummaryPatch,
    PsycheSummaryRequest,
    PsycheSummaryScope,
)
from src.domains.agents.application.psyche_summary_spec import PSYCHE_SUMMARY_OPERATION
from src.domains.personalities.models import Personality
from src.domains.psyche.constants import PSYCHE_SCHEMA_VERSION
from src.domains.psyche.models import PsycheState
from src.domains.psyche.service import PsycheService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.llm.usage_guard import enforce_usage_limit


async def summary_scope(db: AsyncSession, actor_id: UUID) -> PsycheSummaryScope:
    actor = await require_psyche_access(db, actor_id)
    columns = tuple(PsycheState.__table__.columns)
    row = (
        (await db.execute(select(*columns).where(PsycheState.user_id == actor_id)))
        .mappings()
        .one_or_none()
    )
    personality = (
        (
            await db.execute(
                select(*Personality.__table__.columns).where(Personality.id == actor.personality_id)
            )
        )
        .mappings()
        .one_or_none()
    )
    preferences = psyche_settings(actor).model_dump(mode="json")
    language = normalize_language(actor.language)
    inputs = {
        "personality_id": str(actor.personality_id),
        "personality": dict(personality) if personality else None,
        "settings": preferences,
        "language": language,
        "baseline_damping": settings.psyche_baseline_damping,
        "dominance_center": settings.psyche_dominance_center,
        "schema_version": PSYCHE_SCHEMA_VERSION,
    }
    input_digest = sha256(
        json.dumps(inputs, sort_keys=True, default=str, allow_nan=False).encode()
    ).hexdigest()
    digest = sha256(
        json.dumps(
            {
                "columns": [column.name for column in columns],
                "state": dict(row) if row else None,
                "inputs": inputs,
            },
            sort_keys=True,
            default=str,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    await require_psyche_access(db, actor_id)
    return PsycheSummaryScope(
        digest=digest,
        input_digest=input_digest,
        state_present=row is not None,
        settings=preferences,
        language=language,
    )


async def prepare_psyche_summary(
    db: AsyncSession,
    actor_id: UUID,
    request: PsycheSummaryRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    PsycheSummaryRequest.model_validate(request.model_dump())
    scope = await summary_scope(db, actor_id)
    public = scope.public_scope()
    return build_action_content(
        actor_id,
        PSYCHE_SUMMARY_OPERATION,
        PsycheSummaryPatch(psyche_summary=scope),
        {"psyche_summary": public},
        {"psyche_summary": {**public, "requested": True}},
        command_id=command_id,
    )


def canonical_psyche_summary(draft: ApplicationActionDraftContent) -> bool:
    public = PsycheSummaryPatch.model_validate(draft.intent).psyche_summary.public_scope()
    return draft.before == {"psyche_summary": public} and draft.after == {
        "psyche_summary": {**public, "requested": True}
    }


async def execute_psyche_summary(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != "psyche.summary":
        raise CommandRejected("FORBIDDEN")
    if not canonical_psyche_summary(draft):
        raise ValueError("Summary requires exact confirmed source facts")
    selected = PsycheSummaryPatch.model_validate(draft.intent).psyche_summary
    await psyche_settings_fence(db, actor_id, draft)
    if await summary_scope(db, actor_id) != selected:
        raise ResourceConflictError("psyche_summary", detail={"error_code": "STALE_STATE"})
    await enforce_usage_limit(actor_id, layer="psyche_summary")
    if not selected.state_present:
        selected = await _initialize_summary_state(db, actor_id, draft, selected, receipt)

    async def check() -> None:
        await psyche_settings_fence(db, actor_id, draft)
        if await summary_scope(db, actor_id) != selected:
            raise ResourceConflictError("psyche_summary", detail={"error_code": "STALE_STATE"})
        await enforce_usage_limit(actor_id, layer="psyche_summary")
        await db.commit()
        receipt.values = {
            "psyche_summary": {
                "state_initialized": not PsycheSummaryPatch.model_validate(
                    draft.intent
                ).psyche_summary.state_present,
                "generation_status": "started",
            }
        }

    summary = await PsycheService(db).generate_summary(
        actor_id, selected.language, before_model=check
    )
    receipt.values = {
        "psyche_summary": {
            "state_initialized": not PsycheSummaryPatch.model_validate(
                draft.intent
            ).psyche_summary.state_present,
            "generation_status": "generated_not_released",
        }
    }
    # Billing is source-owned. A late withdrawal suppresses prose but retains paid settlement.
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    await psyche_settings_fence(db, actor_id, draft)
    if await summary_scope(db, actor_id) != selected:
        raise ResourceConflictError("psyche_summary", detail={"error_code": "STALE_STATE"})
    receipt.committed = True
    receipt.values = {
        "psyche_summary": {"summary": summary, "state_present": True, "language": selected.language}
    }


async def _initialize_summary_state(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    selected: PsycheSummaryScope,
    receipt: PreferenceWriteReceipt,
) -> PsycheSummaryScope:
    await UserRepository(db).get_by_id_for_preference_update(actor_id)
    await psyche_settings_fence(db, actor_id, draft)
    if await summary_scope(db, actor_id) != selected:
        raise ResourceConflictError("psyche_summary", detail={"error_code": "STALE_STATE"})
    await PsycheService(db).get_or_create_state(actor_id)
    await db.flush()
    await psyche_settings_fence(db, actor_id, draft)
    initialized = await summary_scope(db, actor_id)
    if not initialized.state_present or initialized.input_digest != selected.input_digest:
        raise ResourceConflictError("psyche_summary", detail={"error_code": "STALE_STATE"})
    try:
        await db.commit()
    except SQLAlchemyError as exc:
        raise CommandRejected("COMPLETION_UNKNOWN") from exc
    receipt.committed = True
    receipt.values = {
        "psyche_summary": {"state_initialized": True, "generation_status": "not_started"}
    }
    return initialized
