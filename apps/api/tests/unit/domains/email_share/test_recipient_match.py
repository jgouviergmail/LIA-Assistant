"""Which contacts « Send by e-mail » suggests for what is being typed.

The person types a first name, a last name or a phone number; the field needs
an ADDRESS. The match ignores accents and punctuation in names (one fold,
``fold_name``), reads numbers whatever their spacing or country prefix, and
never suggests someone it cannot address. Pure: the directory is handed in.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.config import get_settings
from src.domains.email_share.recipient_match import (
    RecipientSuggestion,
    match_recipients,
    project_directory,
)

pytestmark = pytest.mark.unit


def person(
    *,
    display: str = "",
    given: str = "",
    family: str = "",
    emails: tuple[str, ...] = (),
    phones: tuple[str, ...] = (),
) -> dict[str, Any]:
    name = {
        k: v
        for k, v in {"displayName": display, "givenName": given, "familyName": family}.items()
        if v
    }
    return {
        "names": [name] if name else [],
        "emailAddresses": [{"value": email} for email in emails],
        "phoneNumbers": [{"value": phone} for phone in phones],
    }


DIRECTORY = project_directory(
    [
        person(
            display="Jérôme Lefèvre",
            given="Jérôme",
            family="Lefèvre",
            emails=("jerome.lefevre@example.org",),
            phones=("06 12 34 56 78",),
        ),
        person(
            display="Jean-Pierre Dupont",
            given="Jean-Pierre",
            family="Dupont",
            emails=("jp.dupont@example.org", "jean-pierre@work.example"),
        ),
        person(
            display="Anne O'Brien", given="Anne", family="O'Brien", emails=("anne@example.org",)
        ),
        person(display="Zoé Martin", emails=("zoe@example.org",), phones=("+33 7 98 76 54 32",)),
        person(display="No Address", phones=("06 00 00 00 01",)),
    ]
)


def emails(query: str, *, limit: int = 10, min_chars: int = 2) -> list[str]:
    return [s.email for s in match_recipients(DIRECTORY, query, limit=limit, min_chars=min_chars)]


class TestNames:
    @pytest.mark.parametrize("query", ["jerome", "Jérôme", "JEROME", "jér", "lefevre", "Lefèvre"])
    def test_first_and_last_names_match_without_their_accents(self, query: str) -> None:
        assert emails(query) == ["jerome.lefevre@example.org"]

    @pytest.mark.parametrize("query", ["jean pierre", "jean-pierre", "jeanpierre", "pierre", "dup"])
    def test_punctuation_in_a_name_is_neither_required_nor_in_the_way(self, query: str) -> None:
        assert set(emails(query)) == {"jp.dupont@example.org", "jean-pierre@work.example"}

    @pytest.mark.parametrize("query", ["obrien", "o'brien", "o brien", "O’Brien"])
    def test_an_apostrophe_is_a_special_character_like_the_others(self, query: str) -> None:
        assert emails(query) == ["anne@example.org"]

    def test_first_and_last_name_in_either_order(self) -> None:
        assert (
            emails("lefevre jerome") == emails("jerome lefevre") == ["jerome.lefevre@example.org"]
        )

    def test_every_typed_word_must_start_a_word_of_the_name(self) -> None:
        assert emails("jerome dupont") == []

    def test_a_word_is_matched_at_its_start_not_inside(self) -> None:
        """« pont » inside « Dupont » is noise in an address field."""
        assert emails("pont") == []

    def test_a_name_only_in_the_display_name_still_matches(self) -> None:
        assert emails("zoe") == ["zoe@example.org"]


class TestAddresses:
    def test_an_address_prefix_matches(self) -> None:
        assert emails("jp.du") == ["jp.dupont@example.org"]

    def test_a_word_of_the_local_part_matches_but_not_the_domain(self) -> None:
        directory = project_directory([person(display="Zed", emails=("support.team@example.org",))])

        assert [s.email for s in match_recipients(directory, "team", limit=10, min_chars=2)] == [
            "support.team@example.org"
        ]
        assert match_recipients(directory, "example", limit=10, min_chars=2) == []

    def test_a_contact_saved_twice_is_one_line_and_no_error(self) -> None:
        twice = person(display="Twin", emails=("twin@example.org",))
        directory = project_directory([twice, twice])

        assert len(match_recipients(directory, "twin", limit=10, min_chars=2)) == 1


class TestPhones:
    """Numbers are compared on their digits, trunk and international zeros aside.

    The telephony rule decides the national/international equivalence
    (``telephony/phone_numbers``): with ``TELEPHONY_DEFAULT_COUNTRY_CODE`` set,
    a number stored nationally is also its E.164 form; without it, only a number
    stored internationally answers to both spellings — guessing a country from
    a half-typed prefix would merge lines of two countries.
    """

    @pytest.mark.parametrize("query", ["0612", "06 12 34", "06.12.34.56.78", "612345"])
    def test_a_national_number_is_found_however_it_is_spaced(self, query: str) -> None:
        assert emails(query) == ["jerome.lefevre@example.org"]

    @pytest.mark.parametrize("query", ["07 98 76", "0798765432", "+33798", "0033 7 98"])
    def test_an_international_number_answers_to_both_spellings(self, query: str) -> None:
        assert emails(query) == ["zoe@example.org"]

    def test_without_a_country_code_a_national_number_ignores_its_international_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "telephony_default_country_code", "")
        directory = project_directory(
            [person(display="Jérôme", emails=("jerome@example.org",), phones=("06 12 34 56 78",))]
        )

        assert match_recipients(directory, "+33 6 12 34", limit=10, min_chars=2) == []
        assert [s.email for s in match_recipients(directory, "0612", limit=10, min_chars=2)] == [
            "jerome@example.org"
        ]

    def test_with_a_country_code_a_national_number_is_also_its_international_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "telephony_default_country_code", "+33")
        directory = project_directory(
            [person(display="Jérôme", emails=("jerome@example.org",), phones=("06 12 34 56 78",))]
        )

        for query in ("+33 6 12 34", "0033612", "0612"):
            found = match_recipients(directory, query, limit=10, min_chars=2)
            assert [s.email for s in found] == ["jerome@example.org"], query

    def test_too_few_digits_suggest_nothing(self) -> None:
        assert emails("06") == []


class TestWhatIsSuggested:
    def test_a_contact_without_an_address_is_never_suggested(self) -> None:
        assert emails("no address") == []
        assert emails("06 00 00") == []

    def test_one_line_per_address_with_the_contact_name(self) -> None:
        suggestions = match_recipients(DIRECTORY, "dupont", limit=10, min_chars=2)

        assert suggestions == [
            RecipientSuggestion(name="Jean-Pierre Dupont", email="jean-pierre@work.example"),
            RecipientSuggestion(name="Jean-Pierre Dupont", email="jp.dupont@example.org"),
        ]

    def test_an_address_shared_by_two_contacts_is_suggested_once(self) -> None:
        directory = project_directory(
            [
                person(display="Alice Home", emails=("shared@example.org",)),
                person(display="Alice Work", emails=("SHARED@example.org",)),
            ]
        )

        assert len(match_recipients(directory, "alice", limit=10, min_chars=2)) == 1

    def test_the_limit_is_applied_after_the_ordering(self) -> None:
        directory = project_directory(
            [
                person(display=f"Paul {n:02d}", emails=(f"paul{n:02d}@example.org",))
                for n in range(12)
            ]
        )

        found = match_recipients(directory, "paul", limit=3, min_chars=2)

        assert [s.email for s in found] == [
            "paul00@example.org",
            "paul01@example.org",
            "paul02@example.org",
        ]

    def test_a_name_match_ranks_before_an_address_match(self) -> None:
        directory = project_directory(
            [
                person(display="Zed", emails=("martin.z@example.org",)),
                person(display="Martin Lebrun", emails=("lebrun@example.org",)),
            ]
        )

        assert [s.email for s in match_recipients(directory, "martin", limit=10, min_chars=2)] == [
            "lebrun@example.org",
            "martin.z@example.org",
        ]

    @pytest.mark.parametrize("query", ["", " ", "j", "-", "@"])
    def test_a_query_shorter_than_the_published_minimum_suggests_nothing(self, query: str) -> None:
        assert emails(query) == []

    def test_a_contact_without_any_name_is_shown_by_its_address(self) -> None:
        directory = project_directory([person(emails=("orphan@example.org",))])

        assert match_recipients(directory, "orph", limit=10, min_chars=2) == [
            RecipientSuggestion(name="orphan@example.org", email="orphan@example.org")
        ]

    def test_a_malformed_person_is_skipped_not_fatal(self) -> None:
        directory = project_directory(
            [
                {"names": "not-a-list", "emailAddresses": [{"value": None}, "x"]},
                {},
                person(display="Valid", emails=("valid@example.org",)),
            ]
        )

        assert [s.email for s in match_recipients(directory, "valid", limit=10, min_chars=2)] == [
            "valid@example.org"
        ]
