"""``update_contact_tool`` no longer drops a contact's other values (ADR-369, D2).

Asked to change a contact's e-mail, the assistant used to REPLACE the list with
that one address: a person with a home and a work e-mail lost the second in
silence. The single value now replaces the PRIMARY one and keeps the others —
a behaviour change the model is told about in the one wording its two readers
(the planner's manifest, the ReAct schema) both read.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.google_contacts.catalogue_manifests import (
    update_contact_catalogue_manifest,
)
from src.domains.agents.google_contacts.value_descriptions import (
    CONTACT_ADDRESS_DESCRIPTION,
    CONTACT_EMAIL_DESCRIPTION,
    CONTACT_PHONE_DESCRIPTION,
)
from src.domains.agents.tools.google_contacts_tools import (
    execute_contact_update_draft,
    update_contact_tool,
)
from src.domains.connectors.clients.google_people_client import GooglePeopleClient

pytestmark = pytest.mark.unit


def _two_email_contact() -> tuple[GooglePeopleClient, AsyncMock]:
    client = GooglePeopleClient.__new__(GooglePeopleClient)
    client.user_id = uuid4()
    client.get_person = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "resourceName": "people/c1",
            "etag": "%Etag",
            "emailAddresses": [
                {"value": "home@x.org", "type": "home"},
                {"value": "work@x.org", "type": "work"},
            ],
        }
    )
    client._get_cache = AsyncMock(  # type: ignore[method-assign]
        return_value=MagicMock(invalidate_user=AsyncMock())
    )
    spy = AsyncMock(return_value={"resourceName": "people/c1"})
    client._make_request = spy  # type: ignore[method-assign]
    return client, spy


async def test_a_new_email_keeps_the_contacts_other_one() -> None:
    client, spy = _two_email_contact()

    with patch(
        "src.domains.connectors.provider_resolver.resolve_client_for_category",
        AsyncMock(return_value=(client, MagicMock())),
    ):
        await execute_contact_update_draft(
            {"resource_name": "people/c1", "email": "new@x.org"}, uuid4(), MagicMock()
        )

    written = spy.call_args.kwargs["json_data"]["emailAddresses"]
    assert [entry["value"] for entry in written] == ["new@x.org", "work@x.org"]


@pytest.mark.parametrize(
    ("parameter", "wording"),
    [
        ("email", CONTACT_EMAIL_DESCRIPTION),
        ("phone", CONTACT_PHONE_DESCRIPTION),
        ("address", CONTACT_ADDRESS_DESCRIPTION),
    ],
)
def test_manifest_and_schema_read_one_description(parameter: str, wording: str) -> None:
    declared = next(p for p in update_contact_catalogue_manifest.parameters if p.name == parameter)
    assert declared.description == wording
    schema: dict[str, Any] = update_contact_tool.tool_call_schema.model_json_schema()
    assert schema["properties"][parameter]["description"] == wording
    assert "kept" in wording, "the model is told the other values survive"


def test_the_confirmation_card_shows_the_new_address() -> None:
    """The card used to show no address row: an address change was confirmed unseen."""
    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.drafts.card_spec import to_markdown_lines
    from src.domains.agents.drafts.dates import draft_datetime_formatter
    from src.domains.agents.drafts.preview_renderer import _render_contact_update

    labels = get_draft_preview_labels("en")
    lines = _render_contact_update(
        {
            "address": "2 New St, Paris",
            "current_contact": {"addresses": [{"formattedValue": "1 Main St, Paris"}]},
        },
        labels,
        draft_datetime_formatter("UTC", "en"),
    )
    card = "\n".join(to_markdown_lines(lines, labels["separator"]))
    assert f"{labels['address']}" in card
    assert "2 New St, Paris ✏️" in card
