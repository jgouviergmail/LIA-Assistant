"""The one order a contacts listing follows (owner request 2026-10-31): family, then given.

A contact reads « Given Family » and the list is sorted by FAMILY then GIVEN name, ascending,
case and accents not deciding (``fold_name``, the one fold of a name). A name with no family
part — a company, a single name — sorts by what it shows; a contact with no name at all last.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.connectors.clients.normalizers.contact_order import contact_order_key

pytestmark = pytest.mark.unit


def _person(
    given: str | None = None, family: str | None = None, shown: str | None = None
) -> dict[str, Any]:
    names = {
        key: value
        for key, value in (("givenName", given), ("familyName", family), ("displayName", shown))
        if value is not None
    }
    return {"names": [names]} if names else {"emailAddresses": [{"value": "x@example.org"}]}


def _shown(people: list[dict[str, Any]]) -> list[str]:
    return [
        " ".join(
            part
            for part in (
                (person.get("names") or [{}])[0].get("givenName"),
                (person.get("names") or [{}])[0].get("familyName"),
            )
            if part
        )
        or (person.get("names") or [{}])[0].get("displayName", "—")
        for person in people
    ]


def test_by_family_name_then_given_name() -> None:
    people = [_person("Mathéo", "Garnet"), _person("Anne", "Martin"), _person("Hua", "Garnet")]

    assert _shown(sorted(people, key=contact_order_key)) == [
        "Hua Garnet",
        "Mathéo Garnet",
        "Anne Martin",
    ]


def test_case_and_accents_do_not_decide() -> None:
    people = [_person("Bob", "Emile"), _person("Zoé", "élie"), _person("Ana", "Dupont")]

    assert _shown(sorted(people, key=contact_order_key)) == ["Ana Dupont", "Zoé élie", "Bob Emile"]


def test_a_name_without_a_family_part_sorts_by_what_it_shows() -> None:
    people = [
        _person(given="Madonna", shown="Madonna"),
        _person("Anne", "Carré"),
        _person(shown="Boulangerie Martin"),
    ]

    assert _shown(sorted(people, key=contact_order_key)) == [
        "Boulangerie Martin",
        "Anne Carré",
        "Madonna",
    ]


def test_a_contact_with_no_name_at_all_comes_last() -> None:
    people = [_person(), _person("Anne", "Zola"), _person(shown="  ")]

    ordered = sorted(people, key=contact_order_key)

    assert _shown(ordered[:1]) == ["Anne Zola"]
    assert all(
        "names" not in person or not person["names"][0].get("givenName") for person in ordered[1:]
    )
