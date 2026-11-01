"""Contacts written multi-valued on the three providers (ADR-369, D4).

Every client READ a contact's e-mails, phones and addresses as typed lists, and
every write REPLACED each list with ONE value: changing a contact's e-mail
through the assistant silently deleted its others. The write contract is now
the read one: a list given replaces that list, ``None`` keeps it, and the
legacy single value replaces the PRIMARY value only. What the person did not
change is written back exactly as the provider holds it; a list the provider
cannot hold is refused whole, never truncated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import vobject

from src.domains.connectors.clients.apple_contacts_client import AppleContactsClient
from src.domains.connectors.clients.google_people_client import GooglePeopleClient
from src.domains.connectors.clients.microsoft_contacts_client import MicrosoftContactsClient
from src.domains.connectors.clients.normalizers.contact_values import ContactValuesRefused
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    GRAPH_EMAILS_MAX,
)
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials

pytestmark = pytest.mark.unit

_TWO_EMAILS = [
    {
        "metadata": {"primary": True, "source": {"type": "CONTACT"}},
        "value": "a@x.org",
        "type": "home",
    },
    {"metadata": {"source": {"type": "CONTACT"}}, "value": "b@x.org", "type": "work"},
]


# ---------------------------------------------------------------------- Google
def _google(person: dict[str, Any]) -> tuple[GooglePeopleClient, AsyncMock]:
    client = GooglePeopleClient.__new__(GooglePeopleClient)
    client.user_id = uuid4()
    client.get_person = AsyncMock(return_value=person)  # type: ignore[method-assign]
    client._get_cache = AsyncMock(return_value=MagicMock(invalidate_user=AsyncMock()))  # type: ignore[method-assign]
    spy = AsyncMock(return_value={"resourceName": "people/c1"})
    client._make_request = spy  # type: ignore[method-assign]
    return client, spy


def _person(**lists: Any) -> dict[str, Any]:
    return {"resourceName": "people/c1", "etag": "%EtagOne", **lists}


class TestGoogle:
    async def test_a_list_replaces_that_list_and_names_it_alone(self) -> None:
        client, spy = _google(_person(emailAddresses=_TWO_EMAILS, phoneNumbers=[{"value": "1"}]))

        await client.update_contact(
            "people/c1",
            emails=[{"value": "b@x.org", "type": "work"}, {"value": "c@x.org", "type": None}],
        )

        params, body = spy.call_args.kwargs["params"], spy.call_args.kwargs["json_data"]
        assert params["updatePersonFields"] == "emailAddresses", "phones untouched: not named"
        assert body["etag"] == "%EtagOne"
        assert body["emailAddresses"] == [_TWO_EMAILS[1], {"value": "c@x.org"}]
        assert "phoneNumbers" not in body

    async def test_the_legacy_value_replaces_the_primary_and_keeps_the_others(self) -> None:
        client, spy = _google(_person(emailAddresses=_TWO_EMAILS))

        await client.update_contact("people/c1", email="new@x.org")

        written = spy.call_args.kwargs["json_data"]["emailAddresses"]
        assert [e["value"] for e in written] == ["new@x.org", "b@x.org"]
        assert written[0]["type"] == "home", "the primary keeps its kind"
        assert written[1] is _TWO_EMAILS[1] or written[1] == _TWO_EMAILS[1]

    async def test_a_legacy_address_keeps_the_others(self) -> None:
        home = {"formattedValue": "1 Main St", "type": "home", "city": "Paris"}
        work = {"formattedValue": "9 Work Rd", "type": "work", "city": "Lyon"}
        client, spy = _google(_person(addresses=[home, work]))

        await client.update_contact("people/c1", address="2 New St")

        written = spy.call_args.kwargs["json_data"]["addresses"]
        assert written[0] == {"formattedValue": "2 New St", "type": "home"}, "no stale city"
        assert written[1] == work

    async def test_a_single_value_and_a_list_together_are_refused(self) -> None:
        client, spy = _google(_person(emailAddresses=_TWO_EMAILS))

        with pytest.raises(ValueError, match="not both"):
            await client.update_contact("people/c1", email="x@x.org", emails=[])
        spy.assert_not_awaited()

    async def test_create_writes_every_value(self) -> None:
        client, spy = _google(_person())

        await client.create_contact(
            "Ada Lovelace",
            emails=[{"value": "ada@x.org", "type": "home"}, {"value": "a2@x.org", "type": None}],
            phones=[{"value": "+33 1", "type": "mobile"}],
            addresses=[{"formatted": "1 Main St", "type": "home"}],
        )

        body = spy.call_args.kwargs["json_data"]
        assert body["emailAddresses"] == [
            {"value": "ada@x.org", "type": "home"},
            {"value": "a2@x.org"},
        ]
        assert body["phoneNumbers"] == [{"value": "+33 1", "type": "mobile"}]
        assert body["addresses"] == [{"formattedValue": "1 Main St", "type": "home"}]


# ----------------------------------------------------------------------- Graph
def _graph(raw: dict[str, Any]) -> tuple[MicrosoftContactsClient, AsyncMock]:
    credentials = ConnectorCredentials(
        access_token="t", refresh_token="r", expires_at=datetime.now(UTC) + timedelta(hours=1)
    )
    client = MicrosoftContactsClient(uuid4(), credentials, MagicMock())

    async def answer(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        return dict(raw) if method == "GET" else {"id": "c1", **kwargs.get("json_data", {})}

    spy = AsyncMock(side_effect=answer)
    client._make_request = spy  # type: ignore[method-assign]
    return client, spy


def _patched(spy: AsyncMock) -> dict[str, Any]:
    return next(call.kwargs["json_data"] for call in spy.call_args_list if call.args[0] == "PATCH")


@pytest.fixture(autouse=True)
def _no_contacts_cache() -> Any:
    with patch(
        "src.domains.connectors.clients.microsoft_contacts_client.invalidate_contacts_cache",
        AsyncMock(),
    ):
        yield


class TestGraph:
    async def test_the_legacy_email_keeps_the_others_and_their_names(self) -> None:
        client, spy = _graph(
            {
                "id": "c1",
                "emailAddresses": [
                    {"address": "a@x.org", "name": "Ada"},
                    {"address": "b@x.org", "name": "Ada (work)"},
                ],
            }
        )

        await client.update_contact("people/c1", email="new@x.org")

        assert _patched(spy)["emailAddresses"] == [
            {"address": "new@x.org"},
            {"address": "b@x.org", "name": "Ada (work)"},
        ]

    async def test_a_fourth_email_is_refused_with_its_bound_and_never_written(self) -> None:
        client, spy = _graph({"id": "c1", "emailAddresses": []})
        emails = [{"value": f"{n}@x.org", "type": None} for n in range(GRAPH_EMAILS_MAX + 1)]

        with pytest.raises(ContactValuesRefused) as refused:
            await client.update_contact("people/c1", emails=emails)

        assert (refused.value.field, refused.value.bound) == ("emails", GRAPH_EMAILS_MAX)
        assert not [call for call in spy.call_args_list if call.args[0] == "PATCH"]

    async def test_phones_land_in_the_slot_their_kind_names(self) -> None:
        client, spy = _graph({"id": "c1", "homePhones": ["1"], "mobilePhone": "2"})

        await client.update_contact(
            "people/c1",
            phones=[{"value": "3", "type": "work"}, {"value": "4", "type": "mobile"}],
        )

        body = _patched(spy)
        assert (body["businessPhones"], body["mobilePhone"], body["homePhones"]) == (["3"], "4", [])

    async def test_a_legacy_phone_replaces_the_first_one_shown(self) -> None:
        client, spy = _graph({"id": "c1", "businessPhones": ["1"], "mobilePhone": "2"})

        await client.update_contact("people/c1", phone="9")

        body = _patched(spy)
        assert (body["businessPhones"], body["mobilePhone"]) == (["9"], "2")

    async def test_a_kept_address_is_written_back_whole(self) -> None:
        home = {"street": "1 Main St", "city": "Paris", "postalCode": "75001"}
        client, spy = _graph({"id": "c1", "homeAddress": home})

        await client.update_contact(
            "people/c1",
            addresses=[
                {"formatted": "1 Main St, Paris, 75001", "type": "home"},
                {"formatted": "9 Work Rd", "type": "work"},
            ],
        )

        body = _patched(spy)
        assert body["homeAddress"] == home
        assert body["businessAddress"]["street"] == "9 Work Rd"
        assert body["businessAddress"]["city"] == ""

    async def test_untouched_lists_are_not_written(self) -> None:
        client, spy = _graph({"id": "c1"})

        await client.update_contact("people/c1", name="Ada")

        body = _patched(spy)
        assert not {"emailAddresses", "mobilePhone", "homeAddress"} & set(body)
        assert [call.args[0] for call in spy.call_args_list] == ["PATCH"], "no read needed"


# --------------------------------------------------------------------- CardDAV
_CARD = """BEGIN:VCARD
VERSION:3.0
FN:Ada Lovelace
N:Lovelace;Ada;;;
item1.EMAIL;type=INTERNET;type=HOME;type=pref:a@x.org
item1.X-ABLabel:_$!<Home>!$_
EMAIL;type=INTERNET;type=WORK:b@x.org
TEL;type=CELL:+33 1
ADR;type=HOME:;;1 Main St;Paris;;75001;France
ADR;type=WORK:;;9 Work Rd;Lyon;;;
X-SOCIALPROFILE;type=twitter:https://example.org/ada
NOTE:Met in London
END:VCARD
"""


def _apple(card: str = _CARD) -> tuple[AppleContactsClient, AsyncMock]:
    client = AppleContactsClient(
        user_id=uuid4(),
        credentials=AppleCredentials(apple_id="ada@icloud.com", app_password="abcd-efgh-ijkl-mnop"),
        connector_service=MagicMock(),
    )
    http = AsyncMock()
    response = MagicMock(status_code=200, text=card)
    http.get = AsyncMock(return_value=response)
    http.put = AsyncMock(return_value=MagicMock(status_code=204, text=""))
    client._get_http_client = AsyncMock(return_value=http)  # type: ignore[method-assign]
    client._invalidate_contacts_cache = AsyncMock()  # type: ignore[method-assign]
    return client, http


def _written(http: AsyncMock) -> Any:
    return vobject.readOne(http.put.await_args.kwargs["content"])


class TestCardDav:
    async def test_the_legacy_email_keeps_the_second_and_its_line(self) -> None:
        client, http = _apple()

        await client._update_contact_impl("/c/ada.vcf", None, "new@x.org", None, None, None, None)

        card = _written(http)
        assert [e.value for e in card.contents["email"]] == ["new@x.org", "b@x.org"]
        assert "PREF" in {p.upper() for p in card.contents["email"][0].params["TYPE"]}

    async def test_unknown_lines_survive_a_rewrite(self) -> None:
        client, http = _apple()

        await client._update_contact_impl(
            "/c/ada.vcf",
            None,
            None,
            None,
            None,
            None,
            None,
            emails=[{"value": "c@x.org", "type": "home"}],
        )

        body = http.put.await_args.kwargs["content"]
        assert "X-SOCIALPROFILE" in body and "https://example.org/ada" in body
        assert "Met in London" in body
        card = _written(http)
        assert [e.value for e in card.contents["email"]] == ["c@x.org"]
        assert [t.value for t in card.contents["tel"]] == ["+33 1"], "phones=None keeps them"

    async def test_a_legacy_address_replaces_the_first_and_keeps_the_second(self) -> None:
        client, http = _apple()

        await client._update_contact_impl("/c/ada.vcf", None, None, None, None, None, "2 New St")

        streets = [a.value.street for a in _written(http).contents["adr"]]
        assert streets == ["2 New St", "9 Work Rd"]

    async def test_an_unreadable_card_is_refused_never_overwritten(self) -> None:
        client, http = _apple("GARBAGE")

        with pytest.raises(ValueError):
            await client._update_contact_impl("/c/ada.vcf", None, "x@x.org", None, None, None, None)
        http.put.assert_not_awaited()


class TestGraphIdsNeverShapeAPath:
    """Cold review of L2: a contact id from a browser or a model is quoted into the
    path — interpolated raw, ``x/../../messages/m`` would aim the person's token at
    another resource (the GET L2 added before a value write included)."""

    async def test_every_contact_request_quotes_its_id(self) -> None:
        client, spy = _graph({"id": "c1", "emailAddresses": []})

        await client.update_contact("people/x/../../messages/m", email="a@x.org")
        await client.delete_contact("people/x/../../messages/m")

        paths = [call.args[1] for call in spy.call_args_list]
        assert paths and all(path == "/me/contacts/x%2F..%2F..%2Fmessages%2Fm" for path in paths)

    @pytest.mark.parametrize("folded", ["..", ".", ""])
    async def test_an_id_the_http_client_would_fold_asks_nothing(self, folded: str) -> None:
        """L6 cold look at L2's fix: quoting leaves ``..`` as it is, and httpx removes
        dot segments — ``PATCH /me/contacts/..`` would leave as ``PATCH /me``."""
        from src.core.exceptions import ConnectorAPIError

        client, spy = _graph({"id": "c1", "emailAddresses": []})

        with pytest.raises(ConnectorAPIError) as refused:
            await client.update_contact(folded, email="a@x.org")
        with pytest.raises(ConnectorAPIError):
            await client.delete_contact(folded)

        assert refused.value.upstream_status_code == 404
        spy.assert_not_awaited()


class TestGoogleNamesNeverShapeAPath:
    """Cold review of L2, the Google side of the same rule: a resource name of
    another shape names no contact and sends nothing."""

    @pytest.mark.parametrize(
        "act",
        [
            lambda client: client.get_person("people/c1/../../contactGroups/x", use_cache=False),
            lambda client: client.update_contact("people/c1:batchDeleteContacts", name="x"),
            lambda client: client.delete_contact("contactGroups/myContacts"),
            lambda client: client.get_contact_group("people/c1"),
        ],
    )
    async def test_a_name_of_another_shape_is_refused_without_a_request(self, act: Any) -> None:
        from src.core.exceptions import ConnectorAPIError

        client = GooglePeopleClient.__new__(GooglePeopleClient)
        client.user_id = uuid4()
        cache = MagicMock(get_details=AsyncMock(return_value=(None, False, None, None)))
        client._get_cache = AsyncMock(return_value=cache)  # type: ignore[method-assign]
        spy = AsyncMock(return_value={})
        client._make_request = spy  # type: ignore[method-assign]

        with pytest.raises(ConnectorAPIError) as refused:
            await act(client)

        assert refused.value.upstream_status_code == 404
        spy.assert_not_awaited()
