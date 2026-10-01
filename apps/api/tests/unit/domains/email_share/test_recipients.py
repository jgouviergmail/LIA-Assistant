"""The recipient suggestions service: what it reads, what it files, what it keeps.

The match itself is pinned by ``test_recipient_match``. Here: the contacts
connector is opened through the door (ADR-304) and only when the query can
match anything; a LIVE read of the book is one consultation on the
``email_share`` surface while a cached one files nothing (ADR-263); a book
that cannot be read offers nothing and never raises; and the projection —
~140 ms for 5 000 contacts — is kept per directory version.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.clients.contact_directory import (
    ContactDirectory,
    DirectoryStamp,
)
from src.domains.connectors.models import ConnectorType
from src.domains.email_share import recipients

pytestmark = pytest.mark.unit


def _book(*names: str, version: str | None = "v1", from_cache: bool = False) -> ContactDirectory:
    persons = [
        {
            "names": [{"displayName": name}],
            "emailAddresses": [{"value": f"{name.lower()}@example.org"}],
        }
        for name in names
    ]
    return ContactDirectory(
        persons=persons, truncated=False, from_cache=from_cache, version=version
    )


def _door_and_client(
    result: ContactDirectory | Exception | ClientUnavailable,
) -> tuple[Any, MagicMock]:
    """``open_active_client`` yielding a client whose directory read returns ``result``."""
    client = MagicMock()
    if isinstance(result, Exception):
        client.list_email_directory = AsyncMock(side_effect=result)
    else:
        client.list_email_directory = AsyncMock(return_value=result)

    @asynccontextmanager
    async def door(category: str, user_id: object) -> AsyncIterator[Any]:
        assert category == "contacts"
        if isinstance(result, ClientUnavailable):
            yield result
        else:
            yield ActiveClient(
                client=client, connector_type=ConnectorType.GOOGLE_CONTACTS, preferred_name=None
            )

    return door, client


def _door(result: ContactDirectory | Exception | ClientUnavailable) -> Any:
    """The door alone, for a test that never looks at the client."""
    return _door_and_client(result)[0]


@pytest.fixture(autouse=True)
def _fresh_memo() -> Iterator[None]:
    recipients._PROJECTIONS.clear()
    yield
    recipients._PROJECTIONS.clear()


@pytest.fixture(autouse=True)
def provider() -> Iterator[AsyncMock]:
    """A Google contacts connector, and no stamp yet (the cold path)."""
    active = AsyncMock(return_value=ConnectorType.GOOGLE_CONTACTS)
    with (
        patch.object(recipients, "_active_contacts_provider", active),
        patch.object(recipients, "directory_stamp", AsyncMock(return_value=None)),
    ):
        yield active


@pytest.fixture
def recorded() -> Iterator[list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    with patch.object(
        recipients, "record_surface_consultations", side_effect=lambda **kw: rows.append(kw)
    ):
        yield rows


async def test_without_a_contacts_connector_nothing_is_offered(
    recorded: list[Any], provider: AsyncMock
) -> None:
    provider.return_value = None
    door, client = _door_and_client(_book("Jean"))
    with patch.object(recipients, "open_active_client", door):
        found = await recipients.suggest_recipients(uuid4(), "jean")

    assert found.suggestions == []
    client.list_email_directory.assert_not_awaited()
    assert recorded == []


async def test_a_connector_gone_between_the_check_and_the_door_offers_nothing(
    recorded: list[Any],
) -> None:
    with patch.object(recipients, "open_active_client", _door(ClientUnavailable.NO_CONNECTOR)):
        found = await recipients.suggest_recipients(uuid4(), "jean")

    assert found.suggestions == []
    assert recorded == []


async def test_unreadable_connectors_offer_nothing_and_never_raise(
    recorded: list[Any], provider: AsyncMock
) -> None:
    provider.side_effect = ConnectionError("database down")

    found = await recipients.suggest_recipients(uuid4(), "jean")

    assert found.suggestions == []


class TestTheStampSparesTheBook:
    """Measured: a 5 000-contact book is 3.3 MB and 19 ms of JSON per keystroke."""

    async def test_a_version_this_worker_projected_opens_nothing(self, recorded: list[Any]) -> None:
        user_id = uuid4()
        door, client = _door_and_client(_book("Jean", version="v7", from_cache=True))
        with patch.object(recipients, "open_active_client", door):
            await recipients.suggest_recipients(user_id, "jea")
        client.list_email_directory.reset_mock()

        stamp = DirectoryStamp(version="v7", truncated=True)
        with (
            patch.object(recipients, "open_active_client", door),
            patch.object(recipients, "directory_stamp", AsyncMock(return_value=stamp)),
        ):
            found = await recipients.suggest_recipients(user_id, "jean")

        client.list_email_directory.assert_not_awaited()
        assert [s.email for s in found.suggestions] == ["jean@example.org"]
        assert found.truncated is True

    async def test_a_version_not_projected_here_reads_the_book(self, recorded: list[Any]) -> None:
        door, client = _door_and_client(_book("Jean", version="v8", from_cache=True))
        stamp = DirectoryStamp(version="v8", truncated=False)
        with (
            patch.object(recipients, "open_active_client", door),
            patch.object(recipients, "directory_stamp", AsyncMock(return_value=stamp)),
        ):
            found = await recipients.suggest_recipients(uuid4(), "jea")

        client.list_email_directory.assert_awaited_once()
        assert found.suggestions


async def test_a_live_read_is_one_consultation_of_the_contacts(recorded: list[Any]) -> None:
    user_id = uuid4()
    with patch.object(recipients, "open_active_client", _door(_book("Jean"))):
        found = await recipients.suggest_recipients(user_id, "jea")

    assert [s.email for s in found.suggestions] == ["jean@example.org"]
    assert len(recorded) == 1
    assert recorded[0]["surface"] == "email_share"
    assert recorded[0]["user_id"] == user_id
    assert list(recorded[0]["opened"]) == ["contacts"]
    assert list(recorded[0]["failed"]) == []


async def test_a_cached_book_files_nothing(recorded: list[Any]) -> None:
    """Redis answered; the address book was never opened (ADR-263)."""
    with patch.object(recipients, "open_active_client", _door(_book("Jean", from_cache=True))):
        found = await recipients.suggest_recipients(uuid4(), "jea")

    assert found.suggestions
    assert recorded == []


async def test_a_book_that_cannot_be_read_offers_nothing_and_says_it_failed(
    recorded: list[Any],
) -> None:
    with patch.object(recipients, "open_active_client", _door(RuntimeError("401"))):
        found = await recipients.suggest_recipients(uuid4(), "jea")

    assert found.suggestions == []
    assert len(recorded) == 1 and list(recorded[0]["failed"]) == ["contacts"]


async def test_a_read_past_the_deadline_offers_nothing(recorded: list[Any]) -> None:
    door, client = _door_and_client(_book("Jean"))

    async def forever(max_contacts: int) -> ContactDirectory:
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    client.list_email_directory = forever
    with (
        patch.object(recipients, "open_active_client", door),
        patch.object(recipients, "EMAIL_SHARE_DIRECTORY_READ_TIMEOUT_SECONDS", 0.05),
    ):
        found = await recipients.suggest_recipients(uuid4(), "jea")

    assert found.suggestions == []
    assert list(recorded[0]["failed"]) == ["contacts"]


@pytest.mark.parametrize("query", ["", "j", "06", " "])
async def test_a_query_too_short_reads_nothing(query: str, recorded: list[Any]) -> None:
    door, client = _door_and_client(_book("Jean"))
    with patch.object(recipients, "open_active_client", door):
        found = await recipients.suggest_recipients(uuid4(), query)

    assert found.suggestions == []
    client.list_email_directory.assert_not_awaited()


async def test_the_answer_carries_the_query_it_answers_and_the_cut(recorded: list[Any]) -> None:
    cut = ContactDirectory(persons=_book("Jean").persons, truncated=True, from_cache=True)
    with patch.object(recipients, "open_active_client", _door(cut)):
        found = await recipients.suggest_recipients(uuid4(), "jea")

    assert found.query == "jea"
    assert found.truncated is True


class TestTheProjectionIsKeptPerVersion:
    async def test_one_version_is_projected_once(self, recorded: list[Any]) -> None:
        user_id = uuid4()
        spy = MagicMock(side_effect=recipients.project_directory)
        with (
            patch.object(recipients, "open_active_client", _door(_book("Jean", from_cache=True))),
            patch.object(recipients, "project_directory", spy),
        ):
            await recipients.suggest_recipients(user_id, "jea")
            await recipients.suggest_recipients(user_id, "jean")

        assert spy.call_count == 1

    async def test_a_new_version_replaces_the_old_projection(self, recorded: list[Any]) -> None:
        user_id = uuid4()
        with patch.object(recipients, "open_active_client", _door(_book("Jean", version="v1"))):
            await recipients.suggest_recipients(user_id, "jea")
        with patch.object(recipients, "open_active_client", _door(_book("Paul", version="v2"))):
            found = await recipients.suggest_recipients(user_id, "pau")

        assert [s.email for s in found.suggestions] == ["paul@example.org"]
        assert [key[1] for key in recipients._PROJECTIONS] == ["v2"]

    async def test_an_uncached_copy_is_never_kept(self, recorded: list[Any]) -> None:
        with patch.object(recipients, "open_active_client", _door(_book("Jean", version=None))):
            await recipients.suggest_recipients(uuid4(), "jea")

        assert not recipients._PROJECTIONS

    def test_the_memo_stays_within_its_entry_budget(self) -> None:
        entries = recipients.project_directory(_book("Ana", "Bo", "Cy").persons)
        with patch.object(recipients, "EMAIL_SHARE_RECIPIENT_PROJECTION_MEMO_MAX_ENTRIES", 5):
            recipients._remember(("a", "v"), entries)
            recipients._remember(("b", "v"), entries)

        # Six entries past a budget of five: the least recently used book goes.
        assert list(recipients._PROJECTIONS) == [("b", "v")]
