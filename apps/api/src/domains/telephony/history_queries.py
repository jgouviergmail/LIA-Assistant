"""Shared call-history projection from recorded account runs, never a vendor invoice."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.chat.models import MessageTokenSummary
from src.domains.chat.repository import ChatRepository
from src.domains.conversations.service import ConversationService
from src.domains.telephony.history_schemas import PhoneHistoryProjection, PhoneHistoryRead
from src.domains.telephony.models import PhoneCall
from src.domains.telephony.schemas import (
    StructuredCallData,
    TelephonyCallSummary,
    TelephonyCallUsage,
)
from src.domains.telephony.spend import phone_call_run_id
from src.domains.voice_sessions.summary import session_run_ids_by_key


def assert_history_projection_coverage() -> None:
    if set(TelephonyCallSummary.model_fields) != {
        "id",
        "callee_display",
        "objective",
        "status",
        "call_mode",
        "outcome",
        "summary",
        "debrief",
        "structured_data",
        "call_seconds",
        "created_at",
        "completed_at",
        "call_kind",
        "usage",
        "relay_outcome",
    }:
        raise AssertionError("New call history fields require native projection review")
    if set(StructuredCallData.model_fields) != {
        "agreed",
        "proposed_datetime",
        "location",
        "notes",
        "additional_costs",
        "pending_user_decision",
    } or set(TelephonyCallUsage.model_fields) != {
        "tokens_in",
        "tokens_out",
        "tokens_cache",
        "cost_eur",
        "google_api_requests",
    }:
        raise AssertionError("New nested call history fields require native projection review")


assert_history_projection_coverage()


async def read_call_history(
    db: AsyncSession, actor_id: UUID, request: PhoneHistoryRead
) -> PhoneHistoryProjection:
    query = select(PhoneCall).where(PhoneCall.user_id == actor_id)
    if request.cursor is not None:
        anchor = await db.scalar(
            select(PhoneCall).where(PhoneCall.user_id == actor_id, PhoneCall.id == request.cursor)
        )
        if anchor is None:
            raise ValueError("Call history cursor unavailable")
        query = query.where(
            tuple_(PhoneCall.created_at, PhoneCall.id) < (anchor.created_at, anchor.id)
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(PhoneCall.created_at.desc(), PhoneCall.id.desc()).limit(
                    request.limit + 1
                )
            )
        ).all()
    )
    visible = rows[: request.limit]
    total = await db.scalar(
        select(func.count()).select_from(PhoneCall).where(PhoneCall.user_id == actor_id)
    )
    return PhoneHistoryProjection(
        calls=await project_call_history(db, actor_id, visible),
        total=total or 0,
        next_cursor=visible[-1].id if len(rows) > request.limit else None,
    )


def call_usage(rows: Sequence[MessageTokenSummary]) -> TelephonyCallUsage:
    """Use the source billed total, including all recorded platform cost columns."""
    return TelephonyCallUsage(
        tokens_in=sum(r.total_prompt_tokens for r in rows),
        tokens_out=sum(r.total_completion_tokens for r in rows),
        tokens_cache=sum(r.total_cached_tokens for r in rows),
        cost_eur=float(sum(r.billed_cost_eur for r in rows)),
        google_api_requests=sum(r.google_api_requests for r in rows),
    )


async def delegated_runs_of(
    db: AsyncSession, user_id: UUID, calls: list[PhoneCall]
) -> dict[str, list[str]]:
    """Read stamps in the account's sole active conversation, without creating one."""
    keys = [phone_call_run_id(call.id) for call in calls if call.call_mode == "delegated"]
    if not keys:
        return {}
    conversation = await ConversationService().get_active_conversation(user_id, db)
    if conversation is None:
        return {}
    return await session_run_ids_by_key(db, conversation_id=conversation.id, live_session_ids=keys)


async def project_call_history(
    db: AsyncSession, actor_id: UUID, calls: list[PhoneCall]
) -> list[TelephonyCallSummary]:
    """Project owned rows and observed recorded usage; purged associations cannot imply zero."""
    if any(call.user_id != actor_id for call in calls):
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    if not calls:
        return []
    delegated = await delegated_runs_of(db, actor_id, calls)
    run_ids = {phone_call_run_id(call.id) for call in calls}
    run_ids.update(run for runs in delegated.values() for run in runs)
    summaries = await ChatRepository(db).get_token_summaries_by_run_ids(
        sorted(run_ids), user_id=actor_id
    )
    listed: list[TelephonyCallSummary] = []
    for call in calls:
        summary = TelephonyCallSummary.model_validate(call)
        own = phone_call_run_id(call.id)
        # A duplicated stamp, including the own run, cannot charge the same row twice.
        keys = dict.fromkeys((own, *delegated.get(own, [])))
        rows = [row for run in keys if (row := summaries.get(run)) is not None]
        if rows:
            summary.usage = call_usage(rows)
        listed.append(summary)
    return listed
