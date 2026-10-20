"""Live SMS source for the existing briefing call, never an event-triggered model."""

import asyncio
from time import perf_counter
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.llm_config_helper import get_effective_context_window_for_slot
from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.briefing.schemas import CardSection, CardStatus, SmsData
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.sms.summary import SmsSignal, read_sms_signal, read_sms_summary, render_sms_signal


async def fetch_sms(*, user_id: UUID) -> SmsData:
    if not settings.sms_enabled:
        raise ConnectorNotConfiguredError("sms")
    try:
        return await read_sms_summary(user_id)
    except AuthorizationError as error:
        raise ConnectorNotConfiguredError("sms") from error


async def sms_for_prompt(
    owner: UUID, section: CardSection, *, verbose: bool
) -> tuple[str, SmsSignal | None]:
    """File the actual source attempt, including an abandoned publication."""
    if section.status is not CardStatus.OK or not isinstance(section.data, SmsData):
        return "", None
    started = perf_counter()
    opened = False
    answered = False

    def source_opened() -> None:
        nonlocal opened
        opened = True

    try:
        async with asyncio.timeout(settings.sms_identity_timeout_seconds):
            signal = await read_sms_signal(owner, include_bodies=verbose, on_read=source_opened)
        answered = True
        budget = min(
            settings.sms_context_token_budget,
            max(1, get_effective_context_window_for_slot("briefing") // 20),
        )
        return render_sms_signal(signal, verbose=verbose, budget=budget), signal
    except AuthorizationError, ResourceConflictError, SQLAlchemyError, OSError, TimeoutError:
        return "", None
    finally:
        if opened:
            record_surface_consultations(
                surface="briefing",
                user_id=owner,
                opened=["sms"],
                failed=() if answered else ["sms"],
                duration_ms=int((perf_counter() - started) * 1000),
            )
