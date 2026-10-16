"""A folder a mail query names is read where the mailbox keeps it, or refused.

Three defects of one family (2026-10-13): Outlook read the INBOX for
``label:<a folder of the person's own>`` — its query knew the well-known
folders alone —; iCloud's ``in:trash`` asked for a folder named « Trash »
while iCloud keeps its trash in « Deleted Messages »; and a name iCloud did not
have failed as an internal error. A search read in the wrong folder answers
another question, and an empty one says « nothing » about a folder nobody
read: a system location is found by its ROLE, a folder of the person's own by
its name whatever its case (or its path), and a name nothing matches is
REFUSED with the folders that exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.mail_folders import (
    MailFolder,
    MailFolderAmbiguousError,
    MailFolderNotFoundError,
    find_mail_folder,
)
from src.domains.connectors.clients.mailbox_drafts import MailboxFolderUnavailableError
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.normalizers.graph_mail_query import graph_mail_query
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap, FolderInfo

pytestmark = pytest.mark.unit

_TREE = (
    MailFolder("id-inbox", "Inbox", "Inbox"),
    MailFolder("id-inbox-bills", "Inbox/Factures", "Factures"),
    MailFolder("id-trips", "Voyages", "Voyages"),
)


class TestFindingAFolder:
    def test_by_its_name_whatever_its_case(self) -> None:
        assert find_mail_folder(_TREE, "voyages").folder_id == "id-trips"

    def test_a_nested_folder_by_its_own_name(self) -> None:
        assert find_mail_folder(_TREE, "Factures").folder_id == "id-inbox-bills"

    def test_by_its_path(self) -> None:
        assert find_mail_folder(_TREE, "inbox/factures").folder_id == "id-inbox-bills"

    def test_two_folders_of_one_name_are_refused_with_their_paths(self) -> None:
        tree = (*_TREE, MailFolder("id-project-bills", "Projets/Factures", "Factures"))

        with pytest.raises(MailFolderAmbiguousError) as refused:
            find_mail_folder(tree, "Factures")

        assert refused.value.candidates == ("Inbox/Factures", "Projets/Factures")
        assert find_mail_folder(tree, "Projets/Factures").folder_id == "id-project-bills"

    def test_a_name_nothing_matches_is_refused_with_the_folders_that_exist(self) -> None:
        with pytest.raises(MailFolderNotFoundError) as refused:
            find_mail_folder(_TREE, "Impôts")

        assert refused.value.requested == "Impôts"
        assert refused.value.available == ("Inbox", "Inbox/Factures", "Voyages")
        assert refused.value.complete is True

    def test_a_listing_cut_short_says_so(self) -> None:
        with pytest.raises(MailFolderNotFoundError) as refused:
            find_mail_folder(_TREE, "Impôts", complete=False)

        assert refused.value.complete is False


class TestTheGraphQueryNamesTheFolder:
    @pytest.mark.parametrize("text", ["label:Factures", "in:Factures", 'label:"Factures"'])
    def test_a_folder_of_the_person_s_own_is_named_for_the_client(self, text: str) -> None:
        assert graph_mail_query(text).folder_name == "Factures"

    @pytest.mark.parametrize(
        ("text", "folder"), [("in:trash", "deleteditems"), ("label:SENT", "sentitems")]
    )
    def test_a_well_known_folder_is_routed_without_a_lookup(self, text: str, folder: str) -> None:
        query = graph_mail_query(text)

        assert query.folder == folder
        assert query.folder_name is None

    def test_the_star_is_a_condition_never_a_folder(self) -> None:
        assert graph_mail_query("label:starred").folder_name is None


def _graph_folder(folder_id: str, name: str, children: int = 0) -> dict[str, Any]:
    return {"id": folder_id, "displayName": name, "childFolderCount": children}


class _Graph:
    """Graph's folder listing and a mail listing, by endpoint."""

    def __init__(self, tree: dict[str, list[dict[str, Any]]]) -> None:
        self.tree = tree
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, method: str, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((endpoint, params))
        if endpoint.endswith("/messages"):
            return {"value": []}
        return {"value": self.tree.get(endpoint, [])}


@pytest.fixture
def outlook() -> MicrosoftOutlookClient:
    from datetime import UTC, datetime, timedelta

    return MicrosoftOutlookClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            token_type="Bearer",
        ),
        connector_service=MagicMock(),
    )


_MAILBOX = {
    "/me/mailFolders": [
        _graph_folder("inbox-id", "Inbox", children=1),
        _graph_folder("archive-id", "Archive"),
    ],
    "/me/mailFolders/inbox-id/childFolders": [_graph_folder("bills-id", "Factures")],
}


class TestOutlookReadsTheFolderNamed:
    async def test_a_nested_folder_of_the_person_s_own_is_read_where_it_is(
        self, outlook: MicrosoftOutlookClient
    ) -> None:
        graph = _Graph(_MAILBOX)
        outlook._make_request = graph  # type: ignore[method-assign]

        await outlook.search_emails("label:factures is:unread", max_results=10)

        endpoint, params = graph.calls[-1]
        assert endpoint == "/me/mailFolders/bills-id/messages"
        assert "isRead eq false" in params["$filter"]

    async def test_a_folder_nobody_has_is_refused_never_read_in_the_inbox(
        self, outlook: MicrosoftOutlookClient
    ) -> None:
        graph = _Graph(_MAILBOX)
        outlook._make_request = graph  # type: ignore[method-assign]

        with pytest.raises(MailFolderNotFoundError) as refused:
            await outlook.search_emails("label:Impôts", max_results=10)

        assert refused.value.available == ("Inbox", "Archive", "Inbox/Factures")
        assert not any(endpoint.endswith("/messages") for endpoint, _ in graph.calls)

    async def test_the_walk_reads_no_more_folders_than_a_request_may_and_says_so(
        self, outlook: MicrosoftOutlookClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "outlook_mail_folders_walk_max", 2)
        graph = _Graph(_MAILBOX)
        outlook._make_request = graph  # type: ignore[method-assign]

        with pytest.raises(MailFolderNotFoundError) as refused:
            await outlook.search_emails("label:Factures", max_results=10)

        assert refused.value.complete is False
        assert len(refused.value.available) <= 2

    async def test_a_well_known_folder_needs_no_listing(
        self, outlook: MicrosoftOutlookClient
    ) -> None:
        graph = _Graph(_MAILBOX)
        outlook._make_request = graph  # type: ignore[method-assign]

        await outlook.search_emails("in:trash", max_results=10)

        assert [endpoint for endpoint, _ in graph.calls] == [
            "/me/mailFolders/deleteditems/messages"
        ]


def _mail(subject: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Paul <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    message.set_content(f"{subject} body.")
    return message


@pytest.fixture
def imap() -> FakeImap:
    imap = FakeImap()
    imap.store["Factures"] = {}
    imap.put("INBOX", _mail("Inbox mail"))
    imap.put("Deleted Messages", _mail("Trashed mail"))
    imap.put("Factures", _mail("A bill"))
    return imap


@pytest.fixture
def icloud(imap: FakeImap) -> Iterator[AppleEmailClient]:
    instance = AppleEmailClient(
        user_id=uuid4(),
        credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
        connector_service=MagicMock(),
    )
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    redis = MagicMock(get=AsyncMock(return_value=None), set=AsyncMock())
    client_module = "src.domains.connectors.clients.apple_email_client"
    with (
        patch(f"{client_module}.MailBox", imap),
        patch(f"{client_module}.get_redis_session", AsyncMock(return_value=redis)),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
    ):
        yield instance


async def _subjects(client: AppleEmailClient, query: str) -> list[str]:
    listing = await client.search_emails(query, max_results=5, use_cache=False)
    return [str(message["subject"]) for message in listing["messages"]]


class TestICloudReadsTheFolderNamed:
    async def test_the_trash_is_found_by_its_role(self, icloud: AppleEmailClient) -> None:
        assert await _subjects(icloud, "in:trash") == ["Trashed mail"]

    async def test_a_server_that_flags_nothing_is_read_by_its_known_names(
        self, icloud: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.folder.list.side_effect = lambda: [FolderInfo(name, ()) for name in imap.store]

        assert await _subjects(icloud, "in:trash") == ["Trashed mail"]

    async def test_a_folder_of_the_person_s_own_is_found_whatever_its_case(
        self, icloud: AppleEmailClient
    ) -> None:
        assert await _subjects(icloud, "label:factures") == ["A bill"]

    async def test_a_name_nothing_matches_is_refused_with_the_folders_that_exist(
        self, icloud: AppleEmailClient
    ) -> None:
        with pytest.raises(MailFolderNotFoundError) as refused:
            await _subjects(icloud, "label:Impôts")

        assert "Factures" in refused.value.available

    async def test_a_system_folder_the_server_lacks_is_refused(
        self, icloud: AppleEmailClient
    ) -> None:
        with pytest.raises(MailboxFolderUnavailableError):
            await _subjects(icloud, "in:archive")

    async def test_the_star_is_a_flag_never_a_folder(
        self, icloud: AppleEmailClient, imap: FakeImap
    ) -> None:
        """Graph reads ``label:starred`` as the flag: IMAP selected a folder « starred »."""
        imap.put("INBOX", _mail("Starred mail"), flags=("\\Flagged",))

        assert await _subjects(icloud, "label:starred") == ["Starred mail"]


def test_an_exception_s_text_never_carries_the_person_s_folder_name() -> None:
    """A folder is the person's own label; an exception's text reaches the logs."""
    with pytest.raises(MailFolderNotFoundError) as refused:
        find_mail_folder(_TREE, "Dossier médical")

    assert "médical" not in str(refused.value)
    assert refused.value.requested == "Dossier médical"


class TestExcludingTheFolderReadIsRefused:
    """``-in:inbox`` means « everywhere but the inbox » to Gmail; a search that
    reads ONE folder cannot serve it, and reading that very folder answered the
    opposite of the question. It is refused before anything is read."""

    async def test_on_outlook(self, outlook: MicrosoftOutlookClient) -> None:
        graph = _Graph(_MAILBOX)
        outlook._make_request = graph  # type: ignore[method-assign]

        with pytest.raises(ValueError, match="excludes the folder it reads"):
            await outlook.search_emails("-in:inbox", max_results=10)

        assert graph.calls == []

    async def test_on_icloud(self, icloud: AppleEmailClient, imap: FakeImap) -> None:
        with pytest.raises(ValueError, match="excludes the folder it reads"):
            await _subjects(icloud, "in:trash -in:trash")

        assert imap.sessions == 0


async def test_outlook_lists_who_is_in_copy_so_a_negation_can_read_it(
    outlook: MicrosoftOutlookClient,
) -> None:
    graph = _Graph(_MAILBOX)
    outlook._make_request = graph  # type: ignore[method-assign]

    await outlook.search_emails("-cc:alice", max_results=10)

    _endpoint, params = graph.calls[-1]
    assert "ccRecipients" in params["$select"].split(",")
