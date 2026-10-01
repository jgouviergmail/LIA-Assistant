"""Which contacts « Send by e-mail » suggests for what is being typed.

The recipient field needs an ADDRESS, and a person types a first name, a last
name or a phone number. The providers' own searches cannot serve that the same
way on all three (``clients/contact_directory``), so the directory is matched
here, once:

- **Names** fold through ``fold_name`` — the one implementation of « two
  spellings of a person » — and any character that is neither a letter nor a
  digit separates words, so « Jérôme », « jerome », « Jean-Pierre »,
  « jean pierre », « jeanpierre » and « O'Brien » all find their contact. Each
  typed word must START a word of the name, in any order; a fragment inside a
  word (« pont » in « Dupont ») is noise in an address field.
- **Addresses** match by prefix, or by a word of their local part — folded as
  addresses are (``fold_email``: case only), since that is what is typed.
- **Numbers** compare on digits with trunk and international zeros aside, as
  a substring (the end of a number is often what is remembered), using the
  telephony rule for the national/international equivalence
  (``telephony/phone_numbers``) — from three digits on.

A contact without an address is never suggested: there is nothing to put in
the field. One line per address; an address two contacts share, once.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from src.domains.shared.text_normalization import fold_email, fold_name
from src.domains.telephony.phone_numbers import number_search_variants

#: Anything that is not a letter or a digit separates two words of a name.
_SEPARATORS = re.compile(r"[\W_]+")

#: A query read as a number: digits, an optional leading +, phone punctuation.
_PHONE_QUERY = re.compile(r"^\+?[\d\s().\-/]+$")

#: Digits a number query needs before it is compared (« 06 » is every mobile).
PHONE_QUERY_MIN_DIGITS = 3


@dataclass(frozen=True, slots=True)
class RecipientSuggestion:
    """One line of the list: who, and the address that goes in the field."""

    name: str
    email: str


@dataclass(frozen=True, slots=True)
class RecipientEntry:
    """One address of one contact, with everything a query is compared to."""

    name: str
    email: str
    sort_key: tuple[str, str]
    words: tuple[str, ...]
    compacts: tuple[str, ...]
    address: str
    address_words: tuple[str, ...]
    phones: tuple[str, ...]


def _words(text: str) -> tuple[str, ...]:
    """The folded words of a name, punctuation removed."""
    return tuple(word for word in _SEPARATORS.split(fold_name(text)) if word)


def _strings(items: Any, key: str) -> Iterator[str]:
    """The non-empty ``key`` strings of a People list field, tolerating junk."""
    if not isinstance(items, list):
        return
    for item in items:
        value = item.get(key) if isinstance(item, dict) else None
        if isinstance(value, str) and value.strip():
            yield value.strip()


def _significant_digits(number: str) -> str:
    """Digits only, without the trunk or international zeros in front."""
    return re.sub(r"\D", "", number).lstrip("0")


def _entries_of(person: dict[str, Any]) -> Iterator[RecipientEntry]:
    names = person.get("names")
    displays = list(_strings(names, "displayName"))
    givens = list(_strings(names, "givenName"))
    families = list(_strings(names, "familyName"))
    words: dict[str, None] = {}
    for text in (*displays, *givens, *families):
        words.update(dict.fromkeys(_words(text)))
    compacts = {
        "".join(_words(text))
        for text in (
            *displays,
            *(f"{g} {f}" for g in givens for f in families),
            *(f"{f} {g}" for g in givens for f in families),
        )
    } - {""}
    phones = {
        digits
        for number in _strings(person.get("phoneNumbers"), "value")
        for variant in number_search_variants(number)
        if (digits := _significant_digits(variant))
    }
    label = displays[0] if displays else " ".join((*givens[:1], *families[:1]))
    for email in _strings(person.get("emailAddresses"), "value"):
        local = email.split("@", 1)[0]
        name = label or email
        yield RecipientEntry(
            name=name,
            email=email,
            sort_key=(fold_name(name), fold_email(email)),
            words=tuple(words),
            compacts=tuple(sorted(compacts)),
            address=fold_email(email),
            address_words=_words(local),
            phones=tuple(sorted(phones)),
        )


def project_directory(persons: Iterable[Any]) -> list[RecipientEntry]:
    """Every address of the directory, with what a query is compared to.

    Args:
        persons: People-shape contacts (``clients/contact_directory``); a
            malformed one is skipped, never fatal.

    Returns:
        One entry per contact address.
    """
    return [
        entry for person in persons if isinstance(person, dict) for entry in _entries_of(person)
    ]


def _name_matches(entry: RecipientEntry, query_words: tuple[str, ...]) -> bool:
    if all(any(word.startswith(typed) for word in entry.words) for typed in query_words):
        return True
    compact = "".join(query_words)
    return any(candidate.startswith(compact) for candidate in entry.compacts)


def _address_matches(entry: RecipientEntry, query: str, query_words: tuple[str, ...]) -> bool:
    if entry.address.startswith(fold_email(query)):
        return True
    return len(query_words) == 1 and any(
        word.startswith(query_words[0]) for word in entry.address_words
    )


def _phone_digits(query: str) -> str | None:
    """The significant digits of a number query, or None when it is not one."""
    if not _PHONE_QUERY.match(query):
        return None
    digits = re.sub(r"\D", "", query)
    if len(digits) < PHONE_QUERY_MIN_DIGITS:
        return None
    return digits.lstrip("0") or None


def _query_parts(query: str, min_chars: int) -> tuple[str, tuple[str, ...], str | None]:
    """The trimmed query, its name words (when long enough), its number digits.

    A query made of digits and phone punctuation alone is a NUMBER: it is never
    compared to names, and it needs its three digits — « 06 » is not a name.
    """
    typed = query.strip()
    if _PHONE_QUERY.match(typed):
        return typed, (), _phone_digits(typed)
    words = _words(typed) if len(typed) >= min_chars else ()
    return typed, words, None


def is_searchable(query: str, min_chars: int) -> bool:
    """Whether a query is long enough to be compared at all.

    Checked before the directory is read: « j » or « 06 » would read the book
    to suggest everybody or nobody.

    Args:
        query: What is being typed.
        min_chars: The published minimum length of a name or address query.

    Returns:
        True when the query has name words or enough digits.
    """
    _typed, words, digits = _query_parts(query, min_chars)
    return bool(words) or digits is not None


def _tier(entry: RecipientEntry, query: str, words: tuple[str, ...], digits: str | None) -> int:
    """0 name, 1 address, 2 number, 3 no match — the order the list shows them in."""
    if words and _name_matches(entry, words):
        return 0
    if words and _address_matches(entry, query, words):
        return 1
    if digits and any(digits in phone for phone in entry.phones):
        return 2
    return 3


def match_recipients(
    entries: list[RecipientEntry], query: str, *, limit: int, min_chars: int
) -> list[RecipientSuggestion]:
    """The suggestions for one query: names first, then addresses, then numbers.

    Args:
        entries: The projected directory.
        query: What is being typed in the field (one recipient).
        limit: The published number of suggestions.
        min_chars: The published minimum length of a name or address query.

    Returns:
        At most ``limit`` suggestions, each address once, in a stable order.
    """
    typed, words, digits = _query_parts(query, min_chars)
    if not words and digits is None:
        return []
    # Sorted on an explicit key: two identical lines (a contact saved twice)
    # must never fall through to comparing the entries themselves.
    ranked = sorted(
        ((tier, entry) for entry in entries if (tier := _tier(entry, typed, words, digits)) < 3),
        key=lambda pair: (pair[0], pair[1].sort_key),
    )
    seen: set[str] = set()
    suggestions: list[RecipientSuggestion] = []
    for _tier_rank, entry in ranked:
        if entry.address in seen:
            continue
        seen.add(entry.address)
        suggestions.append(RecipientSuggestion(name=entry.name, email=entry.email))
        if len(suggestions) == limit:
            break
    return suggestions
