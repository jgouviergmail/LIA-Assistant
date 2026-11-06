"""A contact as a vCard file, on the way out and on the way in (ADR-369, lot 9).

One door in both directions: what a card holds is read into the vocabulary the three providers
share, and a contact leaves through the same reading. A birthday with no year keeps having none
on every provider, 1604 standing for it as it does on Apple's and Microsoft's own.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest
import vobject

from src.domains.connectors.clients.contact_details import (
    NO_YEAR,
    ContactDetails,
    birthday_text,
)
from src.domains.connectors.clients.normalizers import contact_cards
from src.domains.connectors.clients.normalizers.contact_cards import (
    read_cards,
    vcard_of_person,
    written_contact,
)
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    merge_vcard_fields,
    normalize_vcard,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    build_contact_update_body,
)

pytestmark = pytest.mark.unit

PERSON: dict[str, Any] = {
    "resourceName": "people/c1",
    "names": [{"displayName": "Ana Lima", "givenName": "Ana", "familyName": "Lima"}],
    "emailAddresses": [
        {"value": "ana@example.org", "type": "work"},
        {"value": "ana@home.example", "type": "home"},
    ],
    "phoneNumbers": [{"value": "+33 6 12 34 56 78", "type": "mobile"}],
    "addresses": [{"formattedValue": "1 rue de la Paix, Paris", "type": "home"}],
    "organizations": [{"name": "Atlas", "title": "Engineer"}],
    "urls": [{"value": "https://a.example.org"}, {"value": "https://b.example.org"}],
    "birthdays": [{"date": {"year": 1990, "month": 5, "day": 15}}],
    "biographies": [{"value": "Met at the fair."}],
}


class TestOnTheWayOut:
    def test_a_contact_leaves_whole(self) -> None:
        card = vobject.readOne(vcard_of_person(PERSON))

        assert card.fn.value == "Ana Lima"
        assert card.n.value.given == "Ana" and card.n.value.family == "Lima"
        assert [line.value for line in card.contents["email"]] == [
            "ana@example.org",
            "ana@home.example",
        ]
        assert card.tel.value == "+33 6 12 34 56 78"
        assert card.org.value == ["Atlas"]
        assert card.title.value == "Engineer"
        assert card.note.value == "Met at the fair."
        assert card.bday.value == "1990-05-15"

    def test_every_website_leaves_not_only_the_first(self) -> None:
        card = vobject.readOne(vcard_of_person(PERSON))

        assert [line.value for line in card.contents["url"]] == [
            "https://a.example.org",
            "https://b.example.org",
        ]

    @pytest.mark.parametrize("year", [0, None])
    def test_a_birthday_with_no_year_leaves_with_none(self, year: int | None) -> None:
        day: dict[str, Any] = {"month": 2, "day": 29}
        if year is not None:
            day["year"] = year

        back = normalize_vcard(vcard_of_person({**PERSON, "birthdays": [{"date": day}]}))

        assert back["birthdays"] == [{"date": {"month": 2, "day": 29}}]

    def test_a_birthday_nobody_can_read_is_left_out(self) -> None:
        odd = {**PERSON, "birthdays": [{"date": {"year": 1990, "month": 13, "day": 40}}]}

        assert "BDAY" not in vcard_of_person(odd)

    def test_a_name_holding_only_its_parts_still_names_the_card(self) -> None:
        card = vobject.readOne(
            vcard_of_person({"names": [{"givenName": "Ana", "familyName": "Lima"}]})
        )

        assert card.fn.value == "Ana Lima"


class TestOnTheWayIn:
    def test_a_file_reads_card_by_card(self) -> None:
        data = (build_vcard("Ana Lima") + build_vcard("Bea Rossi")).encode()

        assert [card["names"][0]["displayName"] for card in read_cards(data)] == [
            "Ana Lima",
            "Bea Rossi",
        ]

    def test_a_byte_order_mark_is_no_part_of_a_card(self) -> None:
        data = b"\xef\xbb\xbf" + build_vcard("Ana Lima").encode()

        assert len(read_cards(data)) == 1

    def test_an_old_export_in_latin_one_still_reads(self) -> None:
        data = build_vcard("Hélène Lima").encode("latin-1")

        assert read_cards(data)[0]["names"][0]["displayName"] == "Hélène Lima"

    @pytest.mark.parametrize(
        "data", [b"", b"hello", b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", b"\x00\x01\x02"]
    )
    def test_what_holds_no_card_reads_as_none(self, data: bytes) -> None:
        assert read_cards(data) == []

    def test_a_card_the_reader_chokes_on_is_counted_and_costs_only_itself(self) -> None:
        data = (build_vcard("Ana Lima") * 3).encode()
        real = vobject.readOne
        calls = 0

        def choking(text: str, *args: Any, **kwargs: Any) -> Any:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise vobject.base.ParseError("no", 1)
            return real(text, *args, **kwargs)

        with patch.object(contact_cards.vobject, "readOne", choking):
            people = read_cards(data)

        assert len(people) == 3, "a card nobody can read is said, never dropped"
        assert written_contact(people[0]) is None
        assert written_contact(people[1]) is not None

    def test_reading_stops_at_the_bound(self) -> None:
        assert len(read_cards((build_vcard("Ana") * 5).encode(), at_most=2)) == 2

    def test_a_card_left_open_is_no_card(self) -> None:
        assert read_cards(b"BEGIN:VCARD\r\nFN:Ana\r\n") == []


class TestWhatAContactWrites:
    def test_it_carries_all_a_create_takes(self) -> None:
        written = written_contact(PERSON)

        assert written is not None
        assert written.name == "Ana Lima"
        assert written.organization == "Atlas"
        assert written.notes == "Met at the fair."
        assert [item["value"] for item in written.emails] == [
            "ana@example.org",
            "ana@home.example",
        ]
        assert written.details == ContactDetails(
            given_name="Ana",
            family_name="Lima",
            job_title="Engineer",
            website="https://a.example.org",
            birthday=date(1990, 5, 15),
        )

    def test_a_card_with_no_name_goes_by_what_it_holds(self) -> None:
        company = written_contact({"organizations": [{"name": "Atlas"}]})
        address = written_contact({"emailAddresses": [{"value": "ana@example.org"}]})
        number = written_contact({"phoneNumbers": [{"value": "+33 1"}]})

        assert company is not None and company.name == "Atlas"
        assert address is not None and address.name == "ana@example.org"
        assert number is not None and number.name == "+33 1"

    def test_a_card_naming_nobody_writes_nothing(self) -> None:
        assert written_contact({"biographies": [{"value": "Who?"}]}) is None
        assert vcard_of_person({"biographies": [{"value": "Who?"}]}) == ""


class TestABirthdayAsText:
    @pytest.mark.parametrize(
        ("entries", "read"),
        [
            ([{"date": {"year": 1990, "month": 5, "day": 15}}], "1990-05-15"),
            ([{"date": {"year": 0, "month": 5, "day": 15}}], "--05-15"),
            ([{"date": {"month": 2, "day": 29}}], "--02-29"),
            ([{"text": "in May"}], None),
            ([{"date": {"month": 5}}], None),
            ([], None),
            ("x", None),
        ],
    )
    def test_one_door_reads_it(self, entries: Any, read: str | None) -> None:
        assert birthday_text(entries) == read


class TestABirthdayWithNoYear:
    day = date(NO_YEAR, 5, 15)

    def test_a_card_says_so_as_apple_does(self) -> None:
        text = build_vcard("Ana Lima", details=ContactDetails(birthday=self.day))

        assert normalize_vcard(text)["birthdays"] == [{"date": {"month": 5, "day": 15}}]
        assert vobject.readOne(text).bday.params["X-APPLE-OMIT-YEAR"] == [str(NO_YEAR)]

    def test_a_year_given_later_leaves_nothing_of_it(self) -> None:
        kept = build_vcard("Ana Lima", details=ContactDetails(birthday=self.day))

        card = vobject.readOne(
            merge_vcard_fields(kept, details=ContactDetails(birthday=date(1990, 5, 15)))
        )

        assert card.bday.value == "1990-05-15"
        assert "X-APPLE-OMIT-YEAR" not in card.bday.params

    def test_graph_holds_the_same_year(self) -> None:
        body = build_contact_update_body(details=ContactDetails(birthday=self.day))

        assert body["birthday"].startswith("1604-05-15")
