"""A described item is found by the WORDS that name it, folded (ADR-367).

Measured on the 2026-10-29 production list before this matcher existed: the
fuzzy resolver compared WHOLE strings with ``lower()``, so « jerome » scored
0.27–0.52 against « "Jérôme G" <…> » (threshold 0.7) and nothing was found —
« plaud » neither, against its own sender. Every word of the description must
be a word of the item; a word no item carries is never dropped, because
dropping it is how « Marc Dupont » would come to designate « Marc Dubois ».
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.context.descriptor_match import (
    descriptor_tokens,
    items_matching,
    strings_at,
)
from src.domains.agents.context.registry import ContextTypeDefinition

pytestmark = [pytest.mark.unit]


def _definition(fields: list[str], content: list[str] | None = None) -> ContextTypeDefinition:
    return ContextTypeDefinition(
        domain="things",
        agent_name="thing_agent",
        primary_id_field="id",
        display_name_field=fields[0],
        reference_fields=fields,
        content_reference_fields=content or [],
    )


EMAILS = _definition(["from", "subject", "to"], ["snippet"])
_INBOX: list[dict[str, Any]] = [
    {"id": "1", "from": '"Jérôme G" <jg@example.com>', "subject": "Photos", "snippet": "voici"},
    {
        "id": "2",
        "from": "PLAUD.AI <no-reply@plaud.example>",
        "subject": "Weekly",
        "snippet": "notes",
    },
    {"id": "3", "from": "Marc Dubois <marc.dubois@example.com>", "subject": "Facture garage"},
    {"id": "4", "from": "Marc Dubois <marc.dubois@example.com>", "subject": "Photos"},
    {
        "id": "5",
        "from": "Banque <info@banque.example>",
        "subject": "Relevé",
        "snippet": "facture jointe",
    },
]


def _ids(items: list[Any]) -> list[str]:
    return [item["id"] for item in items]


class TestTheWordsOfADescription:
    @pytest.mark.parametrize(
        ("descriptor", "tokens"),
        [
            ("Jérôme", ("jerome",)),
            ("le mail de Jérôme", ("mail", "jerome")),
            ("Marc's", ("marc",)),
            ("the garage of Marc", ("garage", "marc")),
            ("Mail von Marc", ("mail", "marc")),
            ("la factura del taller", ("factura", "taller")),
            ("la fattura della officina", ("fattura", "officina")),
            ("Budget 2026", ("budget", "2026")),
            ("删除 Acme那封", ("删除", "acme", "那封")),
            ("", ()),
            ("de la", ()),
        ],
    )
    def test_function_words_and_lone_letters_carry_no_identity(
        self, descriptor: str, tokens: tuple[str, ...]
    ) -> None:
        assert descriptor_tokens(descriptor) == tokens


class TestTheItemsADescriptionDesignates:
    def test_a_name_matches_whatever_its_accents_and_case(self) -> None:
        assert _ids(items_matching("jerome", _INBOX, EMAILS)) == ["1"]
        assert _ids(items_matching("JÉRÔME", _INBOX, EMAILS)) == ["1"]

    def test_a_sender_is_found_by_its_brand(self) -> None:
        assert _ids(items_matching("plaud", _INBOX, EMAILS)) == ["2"]

    def test_namesakes_are_all_returned_in_display_order(self) -> None:
        assert _ids(items_matching("Marc", _INBOX, EMAILS)) == ["3", "4"]

    def test_an_item_named_exactly_wins_over_those_containing_the_words(self) -> None:
        contacts = _definition(["name"])
        items = [{"id": "1", "name": "Jean Dupond"}, {"id": "2", "name": "Jean"}]
        assert _ids(items_matching("Jean", items, contacts)) == ["2"]
        assert _ids(items_matching("jean", items, contacts)) == ["2"]
        # Two items named exactly alike remain two: the description cannot choose.
        twins = [{"id": "1", "name": "Jean"}, {"id": "2", "name": "Jean"}]
        assert _ids(items_matching("Jean", twins, contacts)) == ["1", "2"]

    def test_every_word_must_be_carried(self) -> None:
        assert _ids(items_matching("Marc facture", _INBOX, EMAILS)) == ["3"]

    def test_a_word_no_item_carries_matches_nothing(self) -> None:
        # Never dropped: « Marc Dupont » must not designate « Marc Dubois ».
        assert items_matching("Marc Dupont", _INBOX, EMAILS) == []

    def test_an_address_local_part_is_a_word(self) -> None:
        assert _ids(items_matching("dubois", _INBOX, EMAILS)) == ["3", "4"]

    def test_content_is_read_only_when_no_identity_matches(self) -> None:
        # « facture » names item 3 by its subject; the bank's body is not read.
        assert _ids(items_matching("facture", _INBOX, EMAILS)) == ["3"]
        assert _ids(items_matching("jointe", _INBOX, EMAILS)) == ["5"]

    def test_a_long_word_matches_the_end_of_a_compound(self) -> None:
        mails = [{"id": "1", "from": "Werkstatt <w@example.de>", "subject": "Werkstattrechnung"}]
        assert _ids(items_matching("Rechnung", mails, EMAILS)) == ["1"]

    def test_a_short_word_or_a_prefix_never_matches_inside_another_name(self) -> None:
        people = [
            {"id": "1", "from": "Marcel Roux <m@example.com>", "subject": ""},
            {"id": "2", "from": "Ana Martinez <a@example.com>", "subject": ""},
        ]
        assert items_matching("Marc", people, EMAILS) == []
        assert items_matching("Martin", people, EMAILS) == []

    def test_chinese_is_matched_inside_its_run(self) -> None:
        events = _definition(["summary", "attendees"])
        items = [
            {"id": "1", "summary": "与王伟开会", "attendees": []},
            {"id": "2", "summary": "看牙医", "attendees": []},
        ]
        assert _ids(items_matching("王伟", items, events)) == ["1"]
        assert _ids(items_matching("牙医", items, events)) == ["2"]

    def test_nested_people_and_places_are_read(self) -> None:
        contacts = _definition(["name", "emailAddresses", "addresses"])
        items = [
            {
                "id": "1",
                "name": "Jean Martin",
                "addresses": [{"formattedValue": "Lyon", "city": "Lyon"}],
            },
            {
                "id": "2",
                "name": "Jean Petit",
                "emailAddresses": [{"value": "jean.petit@example.org"}],
            },
        ]
        assert _ids(items_matching("Jean Lyon", items, contacts)) == ["1"]
        assert _ids(items_matching("Jean", items, contacts)) == ["1", "2"]
        assert _ids(items_matching("petit", items, contacts)) == ["2"]

    def test_a_description_without_identity_designates_nothing(self) -> None:
        assert items_matching("de la", _INBOX, EMAILS) == []
        assert items_matching("", _INBOX, EMAILS) == []

    def test_unreadable_values_are_ignored(self) -> None:
        odd = [{"id": "1", "from": None, "subject": 42, "to": ["Marc <m@example.com>", None]}]
        assert _ids(items_matching("Marc", odd, EMAILS)) == ["1"]


class TestTheStringsAtAPath:
    def test_a_nested_field(self) -> None:
        event = {"start": {"dateTime": "2026-11-03T10:00:00+00:00", "formatted": "mardi 10:00"}}
        assert list(strings_at(event, "start.formatted")) == ["mardi 10:00"]

    def test_a_list_on_the_way_is_walked(self) -> None:
        contact = {"emailAddresses": [{"value": "a@x.example", "type": "home"}, {"value": "b@y"}]}
        assert list(strings_at(contact, "emailAddresses.value")) == ["a@x.example", "b@y"]

    def test_a_plain_field_reads_every_string_it_holds(self) -> None:
        assert list(strings_at({"from": "Marc <m@x.example>"}, "from")) == ["Marc <m@x.example>"]

    def test_a_missing_path_reads_nothing(self) -> None:
        assert list(strings_at({"start": None}, "start.formatted")) == []
        assert list(strings_at({}, "due_formatted")) == []
