"""Bounded SMS evidence for the heartbeat decision and its mention bookkeeping."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from src.core.config import Settings, settings
from src.core.exceptions import AuthorizationError
from src.core.llm_config_helper import get_effective_context_window_for_slot
from src.domains.sms.proactive import mark_sms_mentioned
from src.domains.sms.summary import SmsSignal, project_sms_signal, read_sms_signal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision, HeartbeatTarget
    from src.domains.users.models import User


def repair_sms_ids(value: object) -> list[UUID]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:3]:
        try:
            parsed = UUID(str(item))
        except ValueError, TypeError:
            continue
        if parsed not in result:
            result.append(parsed)
    return result


def _projection(signal: SmsSignal) -> tuple[str, tuple[UUID, ...]]:
    budget = min(
        settings.sms_context_token_budget,
        max(1, get_effective_context_window_for_slot("heartbeat_decision") // 20),
    )
    return project_sms_signal(signal, verbose=True, budget=budget)


async def fetch_sms_context(user_id: UUID, user: User, settings: Settings) -> SmsSignal | None:
    async with asyncio.timeout(settings.sms_identity_timeout_seconds):
        signal = await read_sms_signal(user_id, unmentioned_only=True)
    _, offered = _projection(signal)
    if not offered:
        return None
    return signal.model_copy(
        update={"messages": [item for item in signal.messages if item.id in offered]}
    )


def sms_prompt_sections(signal: SmsSignal | None) -> list[str]:
    if signal is None:
        return []
    text, ids = _projection(signal)
    return ["SMS (unmentioned source candidates, not unread messages):\n" + text] if ids else []


def sms_decision_allowed(context: HeartbeatContext, decision: HeartbeatDecision) -> bool:
    uses_sms = (
        "SMS" in decision.sources_used or bool(decision.sms_message_ids) or decision.sms_actionable
    )
    if not uses_sms:
        return True
    if context.sms is None or not decision.sms_actionable or not decision.sms_message_ids:
        return False
    _, offered = _projection(context.sms)
    return set(decision.sms_message_ids).issubset(offered)


def sms_owner_matches(signal: SmsSignal | None, user_id: UUID | str | None) -> bool:
    if signal is None:
        return True
    try:
        return UUID(str(user_id)) == signal.owner
    except ValueError, TypeError:
        return False


async def settle_sms_notification(
    db: AsyncSession, target: HeartbeatTarget, *, user_id: UUID
) -> None:
    if not sms_owner_matches(target.context.sms, user_id):
        raise AuthorizationError(detail={"error_code": "SMS_OWNER_MISMATCH"})
    if target.context.sms is not None:
        await mark_sms_mentioned(db, target.context.sms, target.decision.sms_message_ids)
