"""A contact's e-mails, phones and addresses: one write contract for three providers (ADR-369, D4).

The clients READ a contact's values as typed lists (Google's shape, whatever the
provider) and used to WRITE each list as ONE value: changing a contact's e-mail
deleted its others. The write contract is now the read one:

- a list given REPLACES that list, ``None`` keeps it;
- the legacy single value (``email=``, ``phone=``, ``address=``) replaces the
  PRIMARY value — the first one read — keeps its kind, and keeps every other;
- an entry the person did not change is written back EXACTLY as the provider
  holds it, so what LIA does not model (a Google source, a vCard group or
  preference) survives; a changed one is built from the entry it replaces;
- a list the provider cannot hold is refused whole (:class:`ContactValuesRefused`),
  never truncated.

Each client keeps its own vocabulary (Google entries, Graph slots, vCard lines);
what they share — reading the request and keeping what did not change — is here,
once.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypedDict, TypeVar

_R = TypeVar("_R")
_D = TypeVar("_D")


class TypedValue(TypedDict):
    """An e-mail address or a phone number, and its kind (``home``, ``mobile``…; None unsaid)."""

    value: str
    type: str | None


class TypedAddress(TypedDict):
    """A postal address and its kind — one line, or the provider's own lines (Google)."""

    formatted: str
    type: str | None


class ContactValuesRefused(ValueError):
    """A list the provider cannot hold, refused whole — never truncated.

    Attributes:
        field: The list refused (``emails``, ``home_phones``, ``addresses``…).
        bound: How many the provider holds.
    """

    def __init__(self, field: str, bound: int) -> None:
        super().__init__(f"{field}: the provider holds at most {bound}")
        self.field = field
        self.bound = bound


def same_kind(left: object, right: object) -> bool:
    """Whether two kinds name the same thing (case aside; no kind is « other »)."""
    return str(left or "other").casefold() == str(right or "other").casefold()


def values_read(entries: object) -> list[TypedValue]:
    """The typed values of a normalised person's ``emailAddresses`` or ``phoneNumbers``."""
    if not isinstance(entries, list):
        return []
    return [
        {"value": str(entry["value"]), "type": entry.get("type") or None}
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("value")
    ]


def addresses_read(entries: object) -> list[TypedAddress]:
    """The typed addresses of a normalised person's ``addresses``, their text as written."""
    if not isinstance(entries, list):
        return []
    return [
        {"formatted": str(entry["formattedValue"]), "type": entry.get("type") or None}
        for entry in entries
        if isinstance(entry, Mapping) and entry.get("formattedValue")
    ]


def _refuse_both(single: str | None, given: object) -> None:
    if single is not None and given is not None:
        raise ValueError("give a single value or a list, not both")


def desired_values(
    single: str | None, given: list[TypedValue] | None, current: list[TypedValue]
) -> list[TypedValue] | None:
    """What an update asks of one list of values.

    Args:
        single: The legacy single value, which replaces the primary one.
        given: The whole new list, which replaces the stored one.
        current: The list as read (for ``single`` only).

    Returns:
        The list to write, or None to leave the stored list untouched.

    Raises:
        ValueError: Both ``single`` and ``given`` were given.
    """
    _refuse_both(single, given)
    if given is not None:
        return given
    if single is None:
        return None
    return [{"value": single, "type": current[0]["type"] if current else None}, *current[1:]]


def desired_addresses(
    single: str | None, given: list[TypedAddress] | None, current: list[TypedAddress]
) -> list[TypedAddress] | None:
    """What an update asks of the addresses (see :func:`desired_values`)."""
    _refuse_both(single, given)
    if given is not None:
        return given
    if single is None:
        return None
    return [{"formatted": single, "type": current[0]["type"] if current else None}, *current[1:]]


def kept_or_built(
    current: Sequence[_R],
    desired: Sequence[_D],
    *,
    same: Callable[[_R, _D], bool],
    build: Callable[[_D, _R | None], _R],
) -> list[_R]:
    """Each desired entry as the provider holds it.

    An entry the person did not change is the stored one, untouched. A new or
    changed entry is built — handed the stored entry at its place when no
    desired entry kept that one, so the primary's own attributes survive a new
    value; never a stored entry another desired entry kept.

    Args:
        current: The provider's entries, as read.
        desired: What the list must hold, in order.
        same: Whether a stored entry IS a desired one.
        build: The provider's entry for a desired one, from the entry it replaces.

    Returns:
        The provider's entries, in the desired order.
    """
    matches: dict[int, int] = {}
    for position, wanted in enumerate(desired):
        found = next(
            (
                index
                for index, entry in enumerate(current)
                if index not in matches.values() and same(entry, wanted)
            ),
            None,
        )
        if found is not None:
            matches[position] = found
    kept = set(matches.values())
    written: list[_R] = []
    for position, wanted in enumerate(desired):
        if position in matches:
            written.append(current[matches[position]])
            continue
        template = current[position] if position < len(current) and position not in kept else None
        written.append(build(wanted, template))
    return written


def bounded(entries: list[Any], field: str, bound: int) -> list[Any]:
    """``entries`` when the provider holds that many, else the whole list refused."""
    if len(entries) > bound:
        raise ContactValuesRefused(field, bound)
    return entries


__all__ = [
    "ContactValuesRefused",
    "TypedAddress",
    "TypedValue",
    "addresses_read",
    "bounded",
    "desired_addresses",
    "desired_values",
    "kept_or_built",
    "same_kind",
    "values_read",
]
