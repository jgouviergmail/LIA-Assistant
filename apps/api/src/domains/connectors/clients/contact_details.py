"""What a contact holds beyond a name, a company and notes (ADR-369, lot 9.2).

One write contract on the three providers: a field left out is kept, an empty text empties it,
and a birthday, which is no text, goes by a flag. Given and family names are written when the
person gave them; a client never splits a whole name over them where they did. A birthday with no
year stands in ``NO_YEAR``, as it does on Apple's and Microsoft's own: a leap year, so the 29th of
February exists, and read back as no year on all three.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

#: The year a birthday with none stands in.
NO_YEAR: Final = 1604


@dataclass(frozen=True, slots=True)
class ContactDetails:
    """What a write changes beyond a name, a company and notes; what is left out is kept."""

    given_name: str | None = None
    family_name: str | None = None
    job_title: str | None = None
    website: str | None = None
    birthday: date | None = None
    clear_birthday: bool = False


def birthday_text(entries: object) -> str | None:
    """A contact's first birthday as an ISO day, or ``--MM-DD`` when it holds no year.

    Args:
        entries: Its ``birthdays``, in the vocabulary the three providers share.

    Returns:
        The day; None when it holds none anyone can read.
    """
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], Mapping):
        return None
    day = entries[0].get("date")
    if not isinstance(day, Mapping) or not day.get("month") or not day.get("day"):
        return None
    tail = f"{day['month']:02d}-{day['day']:02d}"
    return f"{day['year']:04d}-{tail}" if day.get("year") else f"--{tail}"


__all__ = ["NO_YEAR", "ContactDetails", "birthday_text"]
