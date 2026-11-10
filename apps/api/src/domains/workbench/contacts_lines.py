"""What a contact and the person exchanged by phone (2026-11-07).

The calls LIA placed to the contact's numbers (``telephony.number_calls``) and the texts those
numbers sent (``sms.relation_reader.texts_from_lines``), read on LIA's own records: no provider is
asked, no model reads them, no register row is written (D5, the person reading their own records).
Each is read on a session of its own, so one failing leaves the other standing, and each says why
it has nothing: ``not_requested`` when the contact has no number, ``disabled`` when the capability
is switched off or LIA holds no record of that kind at all (a column with nothing to say for
anyone), ``unavailable`` when the read failed — never shown as nothing found. A line never carries
the number: a call says when, how it went and what for, a text when and how it begins.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import WORKBENCH_CONTACT_HISTORY_CALLS_SCAN, WORKBENCH_CONTACT_HISTORY_ITEMS
from src.core.exceptions import AuthorizationError, BaseAPIException
from src.domains.sms.constants import SMS_CARD_EXCERPT_CHARS
from src.domains.sms.relation_reader import LineText, texts_from_lines
from src.domains.telephony.number_calls import PlacedCall, calls_to_lines
from src.domains.workbench.schemas.contacts import HistoryCall, HistorySource, HistoryText
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

#: What ``require_capability_fresh`` raises for a switched-off capability: the SMS page's and the
#: calls list's own refusal, read here as « not offered », never as a failure.
_SWITCHED_OFF: Final = "CAPABILITY_DISABLED"


@dataclass(frozen=True, slots=True)
class PhoneHistory:
    """The calls and texts with a contact, each source saying why it has nothing."""

    telephony: HistorySource
    calls: list[HistoryCall]
    calls_window: int
    calls_cut: bool
    sms: HistorySource
    texts: list[HistoryText]
    texts_window: int
    texts_cut: bool


async def phone_history(user_id: UUID, phones: list[str]) -> PhoneHistory:
    """The latest calls to and texts from a contact's numbers.

    Args:
        user_id: The account.
        phones: The contact's numbers, as saved; none asks nothing.

    Returns:
        What each record holds for these numbers.
    """
    calls_source: HistorySource = "not_requested"
    texts_source: HistorySource = "not_requested"
    calls: list[HistoryCall] = []
    texts: list[HistoryText] = []
    calls_cut = texts_cut = False
    if phones:
        placed, calls_source = await _read(
            "telephony",
            lambda db: calls_to_lines(
                db,
                user_id,
                phones,
                limit=WORKBENCH_CONTACT_HISTORY_ITEMS,
                scan=WORKBENCH_CONTACT_HISTORY_CALLS_SCAN,
            ),
        )
        if placed is not None:
            calls, calls_cut = [_call_line(call) for call in placed.calls], placed.cut
        received, texts_source = await _read(
            "sms",
            lambda db: texts_from_lines(db, user_id, phones, limit=WORKBENCH_CONTACT_HISTORY_ITEMS),
        )
        if received is not None:
            texts, texts_cut = [_text_line(text) for text in received.texts], received.cut
    return PhoneHistory(
        telephony=calls_source,
        calls=calls,
        calls_window=WORKBENCH_CONTACT_HISTORY_CALLS_SCAN,
        calls_cut=calls_cut,
        sms=texts_source,
        texts=texts,
        texts_window=settings.sms_directory_max_contacts,
        texts_cut=texts_cut,
    )


async def _read[T](
    source: str, reading: Callable[[AsyncSession], Awaitable[T | None]]
) -> tuple[T | None, HistorySource]:
    """One record read on a session of its own: what it holds, or why it has nothing."""
    try:
        async with get_db_context() as db:
            found = await reading(db)
    except AuthorizationError as refusal:
        if _code_of(refusal) == _SWITCHED_OFF:
            return None, "disabled"
        _say_unavailable(source, refusal)
        return None, "unavailable"
    except (BaseAPIException, SQLAlchemyError) as failure:
        _say_unavailable(source, failure)
        return None, "unavailable"
    return found, ("disabled" if found is None else "used")


def _code_of(refusal: BaseAPIException) -> str | None:
    detail = refusal.detail
    code = detail.get("error_code") if isinstance(detail, dict) else None
    return code if isinstance(code, str) else None


def _say_unavailable(source: str, failure: Exception) -> None:
    error_code = _code_of(failure) if isinstance(failure, BaseAPIException) else None
    logger.warning(
        "contact_history_source_unavailable",
        source=source,
        error_type=type(failure).__name__,
        error_code=error_code,
    )


def _call_line(call: PlacedCall) -> HistoryCall:
    return HistoryCall(
        id=call.id,
        at=call.at,
        status=call.status,
        outcome=call.outcome,
        seconds=call.seconds,
        purpose=call.purpose,
    )


def _text_line(text: LineText) -> HistoryText:
    return HistoryText(
        id=text.id,
        at=text.at,
        excerpt=text.body[:SMS_CARD_EXCERPT_CHARS],
        truncated=len(text.body) > SMS_CARD_EXCERPT_CHARS,
    )


__all__ = ["PhoneHistory", "phone_history"]
