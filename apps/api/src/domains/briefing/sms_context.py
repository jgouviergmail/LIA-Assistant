"""Live SMS source for the existing briefing call, never an event-triggered model."""

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.llm_config_helper import get_effective_context_window_for_slot
from src.domains.briefing.constants import ERROR_CODE_INTERNAL
from src.domains.briefing.exceptions import ConnectorNotConfiguredError
from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus, SmsData
from src.domains.shared.consultation_surfaces import record_surface_consultations
from src.domains.sms.summary import (
    SmsSignal,
    read_sms_card,
    read_sms_signal,
    read_sms_summary,
    render_sms_signal,
    sms_card_current,
)


async def fetch_sms(*, user_id: UUID, include_messages: bool = False) -> SmsData:
    """Read the SMS briefing section: the summary, or the card with its messages.

    Args:
        user_id: The account.
        include_messages: Whether the card's messages are read too.

    Returns:
        The section's data.

    Raises:
        ConnectorNotConfiguredError: SMS are off, or the person cannot read them.
    """
    if not settings.sms_enabled:
        raise ConnectorNotConfiguredError("sms")
    try:
        if include_messages:
            return await read_sms_card(user_id)
        return SmsData(**(await read_sms_summary(user_id)).model_dump())
    except AuthorizationError as error:
        raise ConnectorNotConfiguredError("sms") from error


async def revalidate_sms_card(cards: CardsBundle) -> CardsBundle:
    """Turn a cached SMS card whose messages changed since into an error section.

    Args:
        cards: The cached bundle.

    Returns:
        The bundle, its SMS section replaced when its proof no longer holds.
    """
    data = cards.sms.data
    if not isinstance(data, SmsData) or not data.items or await sms_card_current(data):
        return cards
    now = datetime.now(UTC)
    return cards.model_copy(
        update={
            "sms": CardSection(
                status=CardStatus.ERROR,
                generated_at=now,
                last_attempt_at=now,
                error_code=ERROR_CODE_INTERNAL,
            )
        }
    )


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
