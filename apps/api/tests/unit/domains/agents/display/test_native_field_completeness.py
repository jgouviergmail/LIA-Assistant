"""Human facts supplied by native connectors reach the card without new fetches."""

from datetime import UTC, datetime
from html.parser import HTMLParser
from unittest.mock import patch

import pytest

from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.contact_card import ContactCard
from src.domains.agents.display.components.file_item import FileItem
from src.domains.connectors.clients.normalizers.contacts_normalizer import normalize_vcard
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    normalize_graph_contact,
)

pytestmark = pytest.mark.unit


class Text(HTMLParser):
    def __init__(self, markup: str) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.feed(markup)

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    @property
    def value(self) -> str:
        return " ".join(self.parts)


def test_contact_keeps_alternate_names_and_every_organization() -> None:
    markup = ContactCard().render(
        {
            "names": [{"displayName": "Alex"}, {"displayName": "Alex Rivera"}],
            "organizations": [
                {"name": "North", "title": "Engineer", "department": "Robotics"},
                {"name": "South <Lab>", "title": "Advisor", "department": "Accessibility"},
            ],
        },
        RenderContext(language="en"),
    )
    text = Text(markup).value
    for fact in (
        "Alex Rivera",
        "North",
        "Engineer",
        "Robotics",
        "South <Lab>",
        "Advisor",
        "Accessibility",
    ):
        assert fact in text
    assert "South <Lab>" not in markup


def test_contact_keeps_every_birthday_and_age_zero() -> None:
    with patch(
        "src.core.time_utils.now_in_timezone", return_value=datetime(2026, 10, 3, tzinfo=UTC)
    ):
        text = Text(
            ContactCard().render(
                {
                    "name": "Baby",
                    "birthdays": [
                        {"date": {"year": 2026, "month": 9, "day": 20}},
                        {"date": {"year": 0, "month": 10, "day": 1}},
                    ],
                },
                RenderContext(language="en"),
            )
        ).value
    assert "0 years old" in text
    assert "October 1" in text
    assert "2026" in text


def test_empty_secondary_birthday_does_not_create_empty_details() -> None:
    assert (
        ContactCard()._render_collapsible_details(
            {"birthdays": [{"date": {"month": 1, "day": 1}}, {}]}, RenderContext(language="en")
        )
        == ""
    )


def test_malformed_birthday_date_cannot_remove_the_contact() -> None:
    markup = ContactCard().render(
        {"name": "Alex", "birthdays": [{"date": "malformed"}]}, RenderContext(language="en")
    )
    assert "Alex" in Text(markup).value


def test_microsoft_department_only_contact_is_preserved_without_google_deep_link() -> None:
    source = normalize_graph_contact(
        {"id": "graph-id", "displayName": "Alex", "department": "Service Design"}
    )
    markup = ContactCard().render(source, RenderContext(language="en"))
    assert "Service Design" in Text(markup).value
    assert "contacts.google.com" not in markup


def test_apple_contact_does_not_invent_a_google_deep_link() -> None:
    source = normalize_vcard(
        "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Alex\r\nN:Rivera;Alex;;;\r\nEND:VCARD\r\n",
        "https://contacts.icloud.com/book/alex.vcf",
    )
    markup = ContactCard().render(source, RenderContext(language="en"))
    assert "Alex" in Text(markup).value
    assert "contacts.google.com" not in markup


def test_legacy_carddav_identifier_cannot_become_a_google_contact_url() -> None:
    markup = ContactCard().render(
        {"name": "Alex", "resourceName": "https://contacts.icloud.com/book/alex.vcf"},
        RenderContext(language="en"),
    )
    assert "contacts.google.com" not in markup


def test_structured_name_is_not_dumped_as_the_persons_display_name() -> None:
    markup = ContactCard().render(
        {"names": [{"displayName": {"private": "raw-tree"}}]}, RenderContext(language="en")
    )
    assert "raw-tree" not in markup


def test_file_keeps_all_owners_and_one_non_owner_permission() -> None:
    markup = FileItem().render(
        {
            "name": "Plan",
            "owners": [{"displayName": "Alex"}, {"displayName": "Robin"}],
            "permissions": [{"type": "anyone", "role": "reader"}],
            "version": "0",
        },
        RenderContext(language="en"),
    )
    text = Text(markup).value
    assert "Alex" in text and "Robin" in text
    assert "Anyone with the link" in text
    assert "Read only" in text
    assert "Version" in text and "0" in text


def test_file_zero_size_and_supplied_download_survive_without_unsafe_urls() -> None:
    data = {
        "name": "Empty file",
        "size": 0,
        "webContentLink": "https://drive.example.test/download",
        "trashed": True,
    }
    markup = FileItem().render(data, RenderContext(language="en"))
    assert "0 B" in Text(markup).value
    assert 'href="https://drive.example.test/download"' in markup
    assert "In trash" in Text(markup).value
    data["webContentLink"] = "javascript:alert(1)"
    assert "javascript:" not in FileItem().render(data, RenderContext(language="en"))


def test_file_sharing_identity_role_and_expiration_are_readable_and_escaped() -> None:
    markup = FileItem().render(
        {
            "name": "Plan",
            "permissions": [
                {
                    "type": "group",
                    "role": "writer",
                    "displayName": "Design <Team>",
                    "emailAddress": "team@example.org",
                    "expirationTime": "2027-01-10T12:00:00Z",
                }
            ],
            "sharingUser": {"displayName": "Taylor"},
        },
        RenderContext(language="en"),
    )
    text = Text(markup).value
    for fact in ("Design <Team>", "team@example.org", "Can edit", "2027", "Taylor"):
        assert fact in text
    assert "Design <Team>" not in markup


@pytest.mark.parametrize(
    "bad", [None, "malformed", 0, False, [{"role": {"secret": "not-readable"}}]]
)
def test_malformed_file_and_contact_lists_do_not_remove_the_card(bad: object) -> None:
    for component, data in (
        (ContactCard(), {"name": "Alex", "organizations": bad, "birthdays": bad, "addresses": bad}),
        (FileItem(), {"name": "Plan", "permissions": bad, "owners": bad}),
    ):
        markup = component.render(data, RenderContext(language="en"))
        assert "lia-card" in markup
        assert "not-readable" not in markup
