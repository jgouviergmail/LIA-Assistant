"""Dialling a raw number must not invent a second relationship.

Until now ``_resolve_callee`` short-circuited on anything that looked like a
number: the callee's DISPLAY NAME became the number itself. The CRM keys
relationships on that display name, so calling "0612345678" and calling "Alice
Vernier" produced TWO relations for one person — exactly what the user
reported.

The lookup added here only ever changes the NAME. The dialled number stays the
one the user supplied, in every branch, including every failure branch: a
naming aid must never be able to place a call to someone else.

Verification is the point. The provider's search is fuzzy and its own idea of
"close"; a candidate is accepted ONLY when one of its numbers is the number
being dialled — ALL of them, not just the first, or a contact whose matching
number sits in second position would be rejected (the false negative the
dossier flagged).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

import src.domains.agents.tools.telephony_tools as tmod
from src.core.config import settings
from src.domains.agents.tools.telephony_tools import (
    _lookup_name_for_number,
    _number_search_variants,
    _person_all_phones,
    _resolve_callee,
    _same_line,
)

pytestmark = pytest.mark.unit

USER_ID = uuid4()


@pytest.fixture(autouse=True)
def _pin_country_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the deployment knob: these assertions describe the WITH-country-code
    behaviour and must not depend on the ambient .env value (same reason as
    ``test_place_phone_call_tool``)."""
    monkeypatch.setattr(settings, "telephony_default_country_code", "+33", raising=False)


def _person(name: str | None, *phones: str, canonical: bool = False) -> dict:
    key = "canonicalForm" if canonical else "value"
    return {
        "names": [{"displayName": name}] if name else [],
        "phoneNumbers": [{key: phone} for phone in phones],
    }


def _patch_raw_search(
    monkeypatch: pytest.MonkeyPatch, by_query: dict[str, list[dict]]
) -> list[str]:
    """Serve persons per query, recording the queries actually issued."""
    issued: list[str] = []

    async def _search(_user_id, query, max_results=5, fields=None):
        issued.append(query)
        return {"results": [{"person": p} for p in by_query.get(query, [])]}

    monkeypatch.setattr(tmod, "_search_contacts_raw", _search)
    return issued


class TestAllNumbersAreRead:
    def test_every_number_is_returned_not_just_the_first(self) -> None:
        assert _person_all_phones(_person("Alice", "0102030405", "0612345678")) == [
            "+33102030405",
            "+33612345678",
        ]

    def test_canonical_form_is_preferred(self) -> None:
        assert _person_all_phones(_person("Alice", "+33612345678", canonical=True)) == [
            "+33612345678"
        ]

    def test_a_person_without_numbers_yields_none(self) -> None:
        assert _person_all_phones(_person("Alice")) == []


class TestSameLine:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            ("0612345678", "+33612345678", True),
            ("+33612345678", "+33612345678", True),
            ("06 12 34 56 78", "0612345678", True),
            ("0612345678", "0613200871", False),
            ("", "+33612345678", False),
            ("0612345678", "", False),
        ],
    )
    def test_pairs(self, a: str, b: str, expected: bool) -> None:
        assert _same_line(a, b) is expected


class TestSearchVariants:
    def test_a_national_number_is_also_searched_international(self) -> None:
        """Providers index the string as STORED. A contact saved '06 12 34 56 78'
        is invisible to a '+33612345678' search — the reverse lookup would die
        silently on the most common case."""
        variants = _number_search_variants("+33612345678")

        assert "+33612345678" in variants
        assert "0612345678" in variants

    def test_variants_are_deduplicated_and_ordered(self) -> None:
        variants = _number_search_variants("0612345678")

        assert variants[0] == "+33612345678"  # the normalized form first
        assert len(variants) == len(set(variants))


class TestTheNameIsResolved:
    async def test_nominal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_raw_search(monkeypatch, {"+33612345678": [_person("Alice Vernier", "0612345678")]})

        assert await _lookup_name_for_number(USER_ID, "+33612345678") == "Alice Vernier"

    async def test_number_in_second_position_still_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The false negative the dossier flagged: `_person_first_phone` reads
        phones[0] only."""
        _patch_raw_search(
            monkeypatch,
            {"+33612345678": [_person("Alice Vernier", "0102030405", "0612345678")]},
        )

        assert await _lookup_name_for_number(USER_ID, "+33612345678") == "Alice Vernier"

    async def test_a_national_variant_is_tried_when_the_first_search_is_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        issued = _patch_raw_search(
            monkeypatch, {"0612345678": [_person("Alice Vernier", "0612345678")]}
        )

        assert await _lookup_name_for_number(USER_ID, "+33612345678") == "Alice Vernier"
        assert "0612345678" in issued


class TestNothingIsGuessed:
    async def test_no_candidate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_raw_search(monkeypatch, {})

        assert await _lookup_name_for_number(USER_ID, "+33612345678") is None

    async def test_candidate_that_does_not_carry_the_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The provider's idea of "close" is not proof."""
        _patch_raw_search(monkeypatch, {"+33612345678": [_person("Someone Else", "0999999999")]})

        assert await _lookup_name_for_number(USER_ID, "+33612345678") is None

    async def test_several_candidates_carry_the_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two people share a landline: naming one of them would be a guess."""
        _patch_raw_search(
            monkeypatch,
            {
                "+33612345678": [
                    _person("Alice Vernier", "0612345678"),
                    _person("Jean Vernier", "0612345678"),
                ]
            },
        )

        assert await _lookup_name_for_number(USER_ID, "+33612345678") is None

    async def test_candidate_without_a_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_raw_search(monkeypatch, {"+33612345678": [_person(None, "0612345678")]})

        assert await _lookup_name_for_number(USER_ID, "+33612345678") is None

    async def test_a_provider_failure_is_never_fatal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The call must go through even when the address book is unreachable."""

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("provider down")

        monkeypatch.setattr(tmod, "_search_contacts_raw", _boom)

        assert await _lookup_name_for_number(USER_ID, "+33612345678") is None


class TestTheDialledNumberIsNeverChanged:
    """The safety invariant: only the label may change."""

    @pytest.mark.parametrize(
        "persons",
        [
            [],  # nothing found
            [_person("Alice Vernier", "0612345678")],  # resolved
            [_person("Someone Else", "0999999999")],  # wrong candidate
            [_person(None, "0612345678")],  # nameless
        ],
    )
    async def test_phone_is_always_the_users_number(
        self, monkeypatch: pytest.MonkeyPatch, persons: list[dict]
    ) -> None:
        _patch_raw_search(monkeypatch, {"+33612345678": persons, "0612345678": persons})

        resolution = await _resolve_callee(USER_ID, "06 12 34 56 78")

        assert resolution.kind == "resolved"
        assert resolution.phone == "+33612345678"

    async def test_the_name_is_the_contact_when_verified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_raw_search(monkeypatch, {"+33612345678": [_person("Alice Vernier", "0612345678")]})

        resolution = await _resolve_callee(USER_ID, "06 12 34 56 78")

        assert resolution.name == "Alice Vernier"

    async def test_the_name_falls_back_to_the_number(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_raw_search(monkeypatch, {})

        resolution = await _resolve_callee(USER_ID, "06 12 34 56 78")

        assert resolution.name == "+33612345678"
