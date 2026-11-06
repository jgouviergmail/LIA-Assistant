"""What a contact tool call asks beyond a name, a company and notes (ADR-369, lot 9).

Read by the tools, the draft factories and the executors: a value object depending on nothing, so
none of them depends on another. A birthday stays the ISO day the model gave, read at execution:
a draft is plain data.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContactExtras:
    """What a tool call asks beyond a name, a company and notes."""

    given_name: str | None = None
    family_name: str | None = None
    job_title: str | None = None
    website: str | None = None
    birthday: str | None = None
    clear_birthday: bool = False

    @property
    def asked(self) -> bool:
        """Whether the call asks any of it; an empty text asks to empty a field."""
        texts = (self.given_name, self.family_name, self.job_title, self.website, self.birthday)
        return self.clear_birthday or any(value is not None for value in texts)

    def fields(self) -> dict[str, Any]:
        """The draft's fields."""
        return {
            "given_name": self.given_name,
            "family_name": self.family_name,
            "job_title": self.job_title,
            "website": self.website,
            "birthday": self.birthday,
            "clear_birthday": self.clear_birthday,
        }


def read_extras(kwargs: Mapping[str, Any]) -> ContactExtras:
    """What a tool call or a draft asks; what it leaves out is not asked."""
    return ContactExtras(
        given_name=kwargs.get("given_name"),
        family_name=kwargs.get("family_name"),
        job_title=kwargs.get("job_title"),
        website=kwargs.get("website"),
        birthday=kwargs.get("birthday"),
        clear_birthday=bool(kwargs.get("clear_birthday")),
    )


__all__ = ["ContactExtras", "read_extras"]
