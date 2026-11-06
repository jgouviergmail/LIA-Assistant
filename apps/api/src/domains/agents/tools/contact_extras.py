"""What the assistant may write of a contact beyond its lists (ADR-369, lot 9, D2).

Out of ``google_contacts_tools.py``, frozen at its audited size. The three providers keep all of
it, so nothing is refused by provider: only a date the tool cannot read, under the one contract
of a date a tool is given (``core/date_contract``). What is accepted rides the draft, shows on the
card and is carried at execution.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import date
from typing import Any, Final

from src.core.date_contract import unreadable_date_message
from src.domains.agents.google_contacts.extras import ContactExtras, read_extras
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.mailbox_draft_base import refusal
from src.domains.connectors.clients.contact_details import ContactDetails

#: The one form of a day: ``date.fromisoformat`` alone also reads ``19900515`` and week dates.
_ISO_DAY: Final = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_a_day(raw: str) -> bool:
    if not _ISO_DAY.fullmatch(raw):
        return False
    try:
        date.fromisoformat(raw)
    except ValueError:
        return False
    return True


def extras_refusal(extras: ContactExtras, user_timezone: str) -> dict[str, Any] | None:
    """Why a call cannot be taken as it stands; None when it can.

    Args:
        extras: What the call asks.
        user_timezone: The person's IANA timezone, which defines « today ».

    Returns:
        The refusal to hand back to the model.
    """
    if extras.birthday is None:
        return None
    if extras.clear_birthday:
        return refusal(
            ToolErrorCode.INVALID_INPUT, "a birthday is set or removed, never both: pass one."
        )
    if not _is_a_day(extras.birthday):
        return refusal(
            ToolErrorCode.INVALID_INPUT,
            unreadable_date_message(extras.birthday, user_timezone),
        )
    return None


async def refusal_of(
    extras: ContactExtras, preferences: Callable[[], Awaitable[tuple[str, str]]]
) -> dict[str, Any] | None:
    """``extras_refusal`` for a tool, which reads the person's zone only when a birthday asks.

    Args:
        extras: What the call asks.
        preferences: The tool's reader of the person's timezone and locale.

    Returns:
        The refusal to hand back to the model.
    """
    if extras.birthday is None:
        return None
    user_timezone, _ = await preferences()
    return extras_refusal(extras, user_timezone)


def details_of(content: Mapping[str, Any]) -> ContactDetails | None:
    """The client's details a confirmed draft carries; None when it carries none."""
    extras = read_extras(content)
    if not extras.asked:
        return None
    return ContactDetails(
        given_name=extras.given_name,
        family_name=extras.family_name,
        job_title=extras.job_title,
        website=extras.website,
        birthday=date.fromisoformat(extras.birthday) if extras.birthday else None,
        clear_birthday=extras.clear_birthday,
    )


__all__ = ["ContactExtras", "details_of", "extras_refusal", "read_extras", "refusal_of"]
