"""The one order a contacts listing follows: by family name, then given name (ADR-369).

Owner request 2026-10-31: the « Tools » contacts read « Given Family » and are sorted by
FAMILY then GIVEN name, ascending, case and accents not deciding (``fold_name``, the one
fold of a name). A name with no family part — a company, a single name — sorts by what it
shows; a contact with no name at all comes last.

Google and Graph sort their own pages (``LAST_NAME_ASCENDING``, ``$orderby=surname,
givenName``): a cursor-paged listing can only be ordered where it is paged. iCloud, read
whole anyway, sorts by this key before it pages; the workbench sorts what a provider
answers in one go — a search, a group — by it too.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.domains.shared.text_normalization import fold_name


def contact_order_key(person: Mapping[str, Any]) -> tuple[bool, str, str]:
    """Where a contact sorts, from its first name entry (the People shape every client reads).

    Args:
        person: A contact in the People shape (``names[0]``: ``givenName``,
            ``familyName``, ``displayName``).

    Returns:
        Whether it has no name at all (those last), then its family name — else what it
        shows — then its given name, each folded.
    """
    names = person.get("names")
    first = names[0] if isinstance(names, list) and names and isinstance(names[0], Mapping) else {}
    family = fold_name(str(first.get("familyName") or ""))
    given = fold_name(str(first.get("givenName") or ""))
    if family:
        return (False, family, given)
    shown = given or fold_name(str(first.get("displayName") or ""))
    return (not shown, shown, "")
