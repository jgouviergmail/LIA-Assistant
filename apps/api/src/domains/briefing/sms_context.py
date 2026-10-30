"""Live SMS source for the existing briefing call, never an event-triggered model."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

import structlog
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
    section = await revalidate_sms_section(cards.sms)
    return cards if section is cards.sms else cards.model_copy(update={"sms": section})


async def revalidate_sms_section(section: CardSection) -> CardSection:
    """The SMS section, or an error section when its messages changed since it was read.

    Args:
        section: An SMS section.

    Returns:
        The same section when its proof holds, else an error section.
    """
    data = section.data
    if not isinstance(data, SmsData) or not data.items or await sms_card_current(data):
        return section
    now = datetime.now(UTC)
    return CardSection(
        status=CardStatus.ERROR,
        generated_at=now,
        last_attempt_at=now,
        error_code=ERROR_CODE_INTERNAL,
    )


logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class PromptSms:
    """ONE read of the person's SMS for the dashboard's text, rendered for both prompts.

    The greeting needs the counts and the synthesis the excerpts; reading the
    excerpts once serves both (spec 2026-10-21, E13: a page load read the SMS
    store three times). Each prompt still checks, before and after its model
    call, that ``signal`` is current (consent, D10).

    Attributes:
        signal: The snapshot read; None when nothing was read.
        brief: The greeting's rendering (counts only).
        detailed: The synthesis' rendering (bounded excerpts).
    """

    signal: SmsSignal | None
    brief: str
    detailed: str


#: Nothing read: no SMS card, consent missing, or a failed read.
NO_PROMPT_SMS = PromptSms(signal=None, brief="", detailed="")


async def read_prompt_sms(owner: UUID, section: CardSection) -> PromptSms:
    """Read the SMS once for both prompts; file the source attempt, abandoned or not.

    Args:
        owner: The account.
        section: The bundle's SMS card; nothing is read unless it is OK.

    Returns:
        The snapshot and its two renderings, or ``NO_PROMPT_SMS``.
    """
    if section.status is not CardStatus.OK or not isinstance(section.data, SmsData):
        return NO_PROMPT_SMS
    started = perf_counter()
    opened = False
    answered = False

    def source_opened() -> None:
        nonlocal opened
        opened = True

    try:
        async with asyncio.timeout(settings.sms_identity_timeout_seconds):
            signal = await read_sms_signal(owner, include_bodies=True, on_read=source_opened)
        answered = True
        budget = min(
            settings.sms_context_token_budget,
            max(1, get_effective_context_window_for_slot("briefing") // 20),
        )
        return PromptSms(
            signal=signal,
            brief=render_sms_signal(signal, verbose=False, budget=budget),
            detailed=render_sms_signal(signal, verbose=True, budget=budget),
        )
    except AuthorizationError, ResourceConflictError, SQLAlchemyError, OSError, TimeoutError:
        return NO_PROMPT_SMS
    except Exception as exc:  # noqa: BLE001 - the text is built without SMS, never failed
        logger.warning("briefing_sms_prompt_read_failed", error_type=type(exc).__name__)
        return NO_PROMPT_SMS
    finally:
        if opened:
            record_surface_consultations(
                surface="briefing",
                user_id=owner,
                opened=["sms"],
                failed=() if answered else ["sms"],
                duration_ms=int((perf_counter() - started) * 1000),
            )
