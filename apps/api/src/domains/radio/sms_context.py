"""Explicit SMS source: bounded consented facts, with live publication authority."""

import asyncio
from datetime import datetime, tzinfo
from uuid import UUID

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.llm_config_helper import get_effective_context_window_for_slot
from src.domains.radio.facts import FactKind, FactPack, Sensitivity
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalDraft, PersonalSource
from src.domains.sms.summary import (
    SmsSignal,
    project_sms_signal,
    read_sms_signal,
    sms_signal_current,
)


async def read_sms(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """Read the recent source window, independently of dashboard previews/settings."""
    del now  # The source captures its actual read instant, not a future programme time.
    if not settings.sms_enabled:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    async with asyncio.timeout(settings.sms_identity_timeout_seconds):
        signal = await read_sms_signal(user_id)
    budget = min(
        settings.sms_context_token_budget,
        max(
            1,
            min(
                get_effective_context_window_for_slot(slot)
                for slot in ("radio_writer", "radio_verifier")
            )
            // 20,
        ),
    )
    _, offered = project_sms_signal(signal, verbose=True, budget=budget)
    proof = signal.model_copy(update={"messages": []})
    return [
        PersonalDraft(
            FactKind.SMS,
            f"Received SMS excerpt from {item.display_name}; source time "
            f"{item.received_at.astimezone(tz).isoformat()} ({item.date_kind}); "
            f"phone read status unknown; body may be incomplete: {item.body_excerpt}",
            f"sms:{item.id}",
            Sensitivity.SENSITIVE,
            sms_source=proof,
        )
        for item in signal.messages[: MAX_PER_SOURCE[PersonalSource.SMS]]
        if item.id in offered
    ]


async def sms_pack_current(pack: FactPack) -> bool:
    """A cached fact never grants future access; check once per source snapshot."""
    checked: set[tuple[UUID, int, str]] = set()
    for fact in pack.facts:
        proof = fact.sms_source
        if proof is None:
            if fact.kind is FactKind.SMS:
                return False
            continue
        key = (proof.owner, proof.revision, proof.stamp)
        if key in checked:
            continue
        if not await _source_current(proof):
            return False
        checked.add(key)
    return True


async def _source_current(proof: SmsSignal) -> bool:
    try:
        async with asyncio.timeout(settings.sms_identity_timeout_seconds):
            return await sms_signal_current(proof)
    except TimeoutError:
        return False
