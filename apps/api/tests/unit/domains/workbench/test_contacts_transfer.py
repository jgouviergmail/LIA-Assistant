"""Contacts leave and arrive as vCard files, by the person's own hand (ADR-369, lot 9).

An export reads the address book a page at a time, up to a published bound, and its cut is said
in its name. An import is bounded by its size and its count, runs once per submission and one
card at a time (Google asks mutations for one person to be sequential), and answers card by card:
a card refused never costs the others.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.constants import WORKBENCH_CONTACTS_EXPORT_MAX, WORKBENCH_CONTACTS_IMPORT_MAX_CARDS
from src.core.exceptions import BaseAPIException, ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.normalizers.contact_values import ContactValuesRefused
from src.domains.connectors.clients.normalizers.contacts_normalizer import build_vcard
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import contacts_transfer
from src.domains.workbench.errors import (
    NOT_A_CONTACTS_FILE,
    TOO_MANY_CARDS,
    refusal_code_of,
)

pytestmark = pytest.mark.unit

USER = uuid4()
KEY = UUID("11111111-1111-4111-8111-111111111111")
GOOGLE = ConnectorType.GOOGLE_CONTACTS


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=GOOGLE, preferred_name=None)

    return patch.object(contacts_transfer, "open_tool_client", opened)


def _transfer() -> Any:
    @contextlib.asynccontextmanager
    async def held(user_id: Any) -> AsyncIterator[None]:
        yield

    return patch.object(contacts_transfer, "one_transfer", held)


def _person(number: int) -> dict[str, Any]:
    return {
        "resourceName": f"people/c{number}",
        "names": [{"displayName": f"Person {number}"}],
    }


async def _once(user_id: Any, key: Any, operation: Any, **kwargs: Any) -> Any:
    return await operation()


class TestAnExport:
    async def test_the_book_is_read_page_by_page_fresh_and_whole(self) -> None:
        client = MagicMock(
            list_connections=AsyncMock(
                side_effect=[
                    {"connections": [_person(1)], "nextPageToken": "p2"},
                    {"connections": [_person(2)], "next_page_token": None},
                ]
            )
        )

        with _door(client), _transfer():
            exported = await contacts_transfer.export_contacts(USER, None)

        assert exported.filename == "contacts.vcf"
        assert exported.data.count(b"BEGIN:VCARD") == 2
        first, second = client.list_connections.await_args_list
        assert first.kwargs["page_token"] is None and first.kwargs["use_cache"] is False
        assert second.kwargs["page_token"] == "p2"
        assert {"names", "urls", "birthdays"} <= set(first.kwargs["fields"])

    async def test_a_book_past_the_bound_says_its_cut_in_its_name(self) -> None:
        pages = [
            {"connections": [_person(number)], "nextPageToken": "more"}
            for number in range(WORKBENCH_CONTACTS_EXPORT_MAX + 5)
        ]
        client = MagicMock(list_connections=AsyncMock(side_effect=pages))

        with _door(client), _transfer():
            exported = await contacts_transfer.export_contacts(USER, None)

        assert exported.data.count(b"BEGIN:VCARD") == WORKBENCH_CONTACTS_EXPORT_MAX
        assert exported.filename == f"contacts-first-{WORKBENCH_CONTACTS_EXPORT_MAX}.vcf"
        assert client.list_connections.await_count == WORKBENCH_CONTACTS_EXPORT_MAX

    async def test_a_book_ending_on_the_bound_is_whole(self) -> None:
        page = [_person(number) for number in range(WORKBENCH_CONTACTS_EXPORT_MAX)]
        client = MagicMock(list_connections=AsyncMock(return_value={"connections": page}))

        with _door(client), _transfer():
            exported = await contacts_transfer.export_contacts(USER, None)

        assert exported.filename == "contacts.vcf"

    async def test_one_contact_goes_by_its_name(self) -> None:
        client = MagicMock(get_person=AsyncMock(return_value=_person(7)))

        with _door(client), _transfer():
            exported = await contacts_transfer.export_contacts(USER, "people/c7")

        client.get_person.assert_awaited_once_with("people/c7", use_cache=False)
        assert exported.filename == "Person 7.vcf"
        assert exported.data.count(b"BEGIN:VCARD") == 1

    async def test_an_other_contact_is_refused_before_anything_is_sent(self) -> None:
        client = MagicMock(get_person=AsyncMock())

        with _door(client), _transfer(), pytest.raises(BaseAPIException):
            await contacts_transfer.export_contacts(USER, "otherContacts/c9")

        client.get_person.assert_not_awaited()

    async def test_an_empty_book_is_an_empty_file(self) -> None:
        client = MagicMock(list_connections=AsyncMock(return_value={"connections": []}))

        with _door(client), _transfer():
            exported = await contacts_transfer.export_contacts(USER, None)

        assert exported.data == b""


class TestAnImport:
    def _cards(self, *names: str) -> bytes:
        return "".join(build_vcard(name) for name in names).encode()

    async def test_each_card_becomes_a_contact_in_turn(self) -> None:
        running = 0
        most = 0

        async def create(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal running, most
            running += 1
            most = max(most, running)
            await _yield()
            running -= 1
            return {"resourceName": "people/c1"}

        client = MagicMock(create_contact=AsyncMock(side_effect=create))

        with _door(client), patch.object(contacts_transfer, "run_once", _once):
            answer = await contacts_transfer.import_contacts(
                USER, self._cards("Ana Lima", "Bea Rossi", "Cid Melo"), KEY
            )

        assert answer.done == 3 and answer.failed == []
        assert most == 1, "Google asks mutations for one person to be sequential"
        assert client.create_contact.await_args_list[0].args[0] == "Ana Lima"

    async def test_a_file_runs_once_per_submission(self) -> None:
        client = MagicMock(create_contact=AsyncMock(return_value={}))
        keys: list[Any] = []

        async def once(user_id: Any, key: Any, operation: Any, **kwargs: Any) -> Any:
            keys.append(key)
            return await operation()

        with _door(client), patch.object(contacts_transfer, "run_once", once):
            await contacts_transfer.import_contacts(USER, self._cards("Ana Lima"), KEY)

        assert keys == [KEY]

    async def test_a_card_refused_costs_only_itself_and_is_named(self) -> None:
        refusal = ConnectorAPIError(
            connector_type="google_contacts", status_code=400, detail="refused"
        )
        client = MagicMock(
            create_contact=AsyncMock(
                side_effect=[{}, refusal, ContactValuesRefused("emails", 3), {}]
            )
        )

        with _door(client), patch.object(contacts_transfer, "run_once", _once):
            answer = await contacts_transfer.import_contacts(
                USER, self._cards("Ana", "Bea", "Cid", "Dea"), KEY
            )

        assert answer.done == 2
        assert [(item.position, item.name) for item in answer.failed] == [(2, "Bea"), (3, "Cid")]

    async def test_a_lone_card_a_provider_cannot_hold_is_reported_not_raised(self) -> None:
        client = MagicMock(create_contact=AsyncMock(side_effect=ContactValuesRefused("emails", 3)))

        with _door(client), patch.object(contacts_transfer, "run_once", _once):
            answer = await contacts_transfer.import_contacts(USER, self._cards("Ana"), KEY)

        assert answer.done == 0
        assert [item.name for item in answer.failed] == ["Ana"]

    async def test_a_card_naming_nobody_is_said_and_sends_nothing(self) -> None:
        nameless = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:\r\nNOTE:Who?\r\nEND:VCARD\r\n"
        client = MagicMock(create_contact=AsyncMock(return_value={}))

        with _door(client), patch.object(contacts_transfer, "run_once", _once):
            answer = await contacts_transfer.import_contacts(USER, nameless.encode(), KEY)

        assert answer.done == 0
        assert [(item.position, item.name) for item in answer.failed] == [(1, "")]
        client.create_contact.assert_not_awaited()

    async def test_a_provider_down_from_the_start_is_the_act_s_own_failure(self) -> None:
        down = ConnectionError("down")
        client = MagicMock(create_contact=AsyncMock(side_effect=down))

        with (
            _door(client),
            patch.object(contacts_transfer, "run_once", _once),
            pytest.raises(BaseAPIException),
        ):
            await contacts_transfer.import_contacts(USER, self._cards("Ana"), KEY)

    async def test_too_many_cards_are_refused_with_the_bound_and_nothing_sent(self) -> None:
        names = [f"Person {n}" for n in range(WORKBENCH_CONTACTS_IMPORT_MAX_CARDS + 1)]
        client = MagicMock(create_contact=AsyncMock())

        with _door(client), pytest.raises(BaseAPIException) as refused:
            await contacts_transfer.import_contacts(USER, self._cards(*names), KEY)

        assert refusal_code_of(refused.value) == TOO_MANY_CARDS
        client.create_contact.assert_not_awaited()

    async def test_a_file_holding_no_card_is_said_so(self) -> None:
        client = MagicMock(create_contact=AsyncMock())

        with _door(client), pytest.raises(BaseAPIException) as refused:
            await contacts_transfer.import_contacts(USER, b"hello", KEY)

        assert refusal_code_of(refused.value) == NOT_A_CONTACTS_FILE


async def _yield() -> None:
    import asyncio

    await asyncio.sleep(0)
