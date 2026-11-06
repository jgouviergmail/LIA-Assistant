"""What the assistant writes of a contact beyond a name, a company and notes (ADR-369, lot 9, D2).

The screen and the assistant keep one contract: what is left out is kept, an empty text empties a
field, a birthday goes by a flag. What the assistant asks is shown on the card before anyone
confirms and carried at execution; a date it cannot read is refused, never guessed.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.google_contacts.catalogue_manifests import (
    create_contact_catalogue_manifest,
    update_contact_catalogue_manifest,
)
from src.domains.agents.google_contacts.common_mappings import get_contacts_field_mappings
from src.domains.agents.google_contacts.value_descriptions import (
    CONTACT_BIRTHDAY_DESCRIPTION,
    CONTACT_CLEAR_BIRTHDAY_DESCRIPTION,
    CONTACT_WEBSITE_DESCRIPTION,
)
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.contact_extras import ContactExtras, details_of, extras_refusal
from src.domains.agents.tools.contacts_draft_executors import (
    execute_contact_draft,
    execute_contact_update_draft,
)
from src.domains.agents.tools.google_contacts_tools import (
    CreateContactDraftTool,
    UpdateContactDraftTool,
    create_contact_tool,
    update_contact_tool,
)
from src.domains.connectors.clients.contact_details import ContactDetails

pytestmark = pytest.mark.unit

USER = uuid4()
DETAILS = {
    "given_name": "Ana",
    "family_name": "Lima",
    "job_title": "Engineer",
    "website": "https://ana.example.org",
    "birthday": "1990-05-15",
}


def _card(kind: DraftType, content: dict[str, Any]) -> str:
    return Draft(type=kind, content=content).get_detailed_preview("en", "UTC")


def _resolving(client: MagicMock) -> Any:
    return patch(
        "src.domains.connectors.provider_resolver.resolve_client_for_category",
        AsyncMock(return_value=(client, MagicMock())),
    )


class TestWhatIsRefused:
    def test_nothing_asked_is_nothing_refused(self) -> None:
        assert extras_refusal(ContactExtras(), "UTC") is None

    @pytest.mark.parametrize("day", ["1990-05-15", "2000-02-29"])
    def test_a_real_day_goes_through(self, day: str) -> None:
        assert extras_refusal(ContactExtras(birthday=day), "UTC") is None

    @pytest.mark.parametrize(
        "day",
        [
            "next Friday",
            "15/05/1990",
            "1990-02-30",
            "1990-05",
            "--05-15",
            "1990-05-15T10:00",
            "19900515",
            "1990-W20-2",
        ],
    )
    def test_a_date_it_cannot_read_is_refused_with_the_format(self, day: str) -> None:
        refused = extras_refusal(ContactExtras(birthday=day), "UTC")

        assert refused is not None
        assert refused["error_code"] == ToolErrorCode.INVALID_INPUT.value
        assert "YYYY-MM-DD" in refused["message"]

    def test_a_birthday_is_not_written_and_taken_off_at_once(self) -> None:
        refused = extras_refusal(ContactExtras(birthday="1990-05-15", clear_birthday=True), "UTC")

        assert refused is not None
        assert refused["error_code"] == ToolErrorCode.INVALID_INPUT.value

    async def test_a_new_contact_with_an_unreadable_date_prepares_no_draft(self) -> None:
        answer = await CreateContactDraftTool().execute_api_call(
            MagicMock(), USER, name="Ana", birthday="next Friday"
        )

        assert answer["error_code"] == ToolErrorCode.INVALID_INPUT.value

    async def test_a_change_with_an_unreadable_date_reads_nothing(self) -> None:
        client = MagicMock(get_person=AsyncMock())

        answer = await UpdateContactDraftTool().execute_api_call(
            client, USER, resource_name="people/c1", birthday="next Friday"
        )

        assert answer["error_code"] == ToolErrorCode.INVALID_INPUT.value
        client.get_person.assert_not_awaited()


class TestTheDraft:
    async def test_a_new_contact_carries_them(self) -> None:
        answer = await CreateContactDraftTool().execute_api_call(
            MagicMock(), USER, name="Ana Lima", **DETAILS
        )

        assert {key: answer[key] for key in DETAILS} == DETAILS

    async def test_a_change_carries_only_what_it_names(self) -> None:
        client = MagicMock(get_person=AsyncMock(return_value={"resourceName": "people/c1"}))

        answer = await UpdateContactDraftTool().execute_api_call(
            client, USER, resource_name="people/c1", website=""
        )

        assert answer["website"] == ""
        assert answer["job_title"] is None and answer["birthday"] is None
        assert answer["clear_birthday"] is False


class TestTheCard:
    def test_a_new_contact_shows_what_it_will_hold(self) -> None:
        shown = _card(DraftType.CONTACT, {"name": "Ana Lima", **DETAILS})

        assert "Engineer" in shown
        assert "ana.example.org" in shown
        assert "15 May 1990" in shown
        assert "✏️" not in shown, "nothing is changed on a contact that does not exist yet"

    def test_a_contact_with_none_of_it_shows_none_of_it(self) -> None:
        shown = _card(DraftType.CONTACT, {"name": "Ana Lima"})

        assert "Job title" not in shown and "Website" not in shown and "Birthday" not in shown

    def test_a_change_marks_what_it_changes_and_shows_what_stays(self) -> None:
        shown = _card(
            DraftType.CONTACT_UPDATE,
            {
                "resource_name": "people/c1",
                "job_title": "CTO",
                "current_contact": {
                    "organizations": [{"name": "Acme", "title": "Engineer"}],
                    "urls": [{"value": "https://kept.example.org"}],
                    "birthdays": [{"date": {"year": 1990, "month": 5, "day": 15}}],
                },
            },
        )

        assert "CTO ✏️" in shown
        assert "kept.example.org" in shown
        assert "1990" in shown
        assert shown.count("✏️") == 1, "what stays is shown, not marked"

    def test_a_change_says_what_it_takes_off(self) -> None:
        shown = _card(
            DraftType.CONTACT_UPDATE,
            {
                "resource_name": "people/c1",
                "website": "",
                "clear_birthday": True,
                "current_contact": {
                    "urls": [{"value": "https://gone.example.org"}],
                    "birthdays": [{"date": {"year": 1990, "month": 5, "day": 15}}],
                },
            },
        )

        assert shown.count("removed") == 2
        assert "gone.example.org" not in shown

    def test_a_name_s_parts_are_shown_when_they_change(self) -> None:
        shown = _card(
            DraftType.CONTACT_UPDATE,
            {"resource_name": "people/c1", "given_name": "Ana", "family_name": "Silva"},
        )

        assert "Ana ✏️" in shown and "Silva ✏️" in shown


class TestExecution:
    async def test_a_confirmed_contact_carries_them(self) -> None:
        client = MagicMock(create_contact=AsyncMock(return_value={"resourceName": "people/c1"}))

        with _resolving(client):
            await execute_contact_draft({"name": "Ana Lima", **DETAILS}, USER, MagicMock())

        assert client.create_contact.await_args.kwargs["details"] == ContactDetails(
            given_name="Ana",
            family_name="Lima",
            job_title="Engineer",
            website="https://ana.example.org",
            birthday=date(1990, 5, 15),
        )

    async def test_a_contact_with_none_of_it_carries_none(self) -> None:
        client = MagicMock(create_contact=AsyncMock(return_value={"resourceName": "people/c1"}))

        with _resolving(client):
            await execute_contact_draft({"name": "Ana Lima"}, USER, MagicMock())

        assert client.create_contact.await_args.kwargs["details"] is None

    async def test_a_confirmed_change_carries_only_what_it_names(self) -> None:
        client = MagicMock(update_contact=AsyncMock(return_value={"names": []}))

        with _resolving(client):
            await execute_contact_update_draft(
                {"resource_name": "people/c1", "website": "", "clear_birthday": True},
                USER,
                MagicMock(),
            )

        assert client.update_contact.await_args.kwargs["details"] == ContactDetails(
            website="", clear_birthday=True
        )


class TestItsWords:
    @pytest.mark.parametrize(
        ("parameter", "wording"),
        [
            ("birthday", CONTACT_BIRTHDAY_DESCRIPTION),
            ("website", CONTACT_WEBSITE_DESCRIPTION),
            ("clear_birthday", CONTACT_CLEAR_BIRTHDAY_DESCRIPTION),
        ],
    )
    def test_a_change_s_manifest_and_schema_read_one_wording(
        self, parameter: str, wording: str
    ) -> None:
        declared = next(
            item for item in update_contact_catalogue_manifest.parameters if item.name == parameter
        )
        schema: dict[str, Any] = update_contact_tool.tool_call_schema.model_json_schema()

        assert declared.description == wording
        assert schema["properties"][parameter]["description"] == wording

    def test_a_new_contact_s_manifest_and_schema_offer_them_too(self) -> None:
        declared = {item.name for item in create_contact_catalogue_manifest.parameters}
        offered = create_contact_tool.tool_call_schema.model_json_schema()["properties"]

        assert set(DETAILS) <= declared
        assert set(DETAILS) <= set(offered)
        assert "clear_birthday" not in offered

    def test_a_website_can_be_asked_for_by_name(self) -> None:
        assert get_contacts_field_mappings()["website"] == "urls"


def test_details_of_a_draft_with_nothing_is_none() -> None:
    assert details_of({"name": "Ana"}) is None


def test_an_empty_text_alone_asks_to_empty_a_field() -> None:
    assert details_of({"website": ""}) == ContactDetails(website="")
