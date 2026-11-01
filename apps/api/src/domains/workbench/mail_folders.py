"""The mail screen's folders and Gmail's labels, by the person's own hand (ADR-369).

The folder pane draws the mailbox's SYSTEM places first — each provider's own,
named by role in the Gmail-style vocabulary the three clients translate (F12),
so the listing reads any of them as ``in:<role>`` — then the person's own
folders, from ``list_labels``, without the system ones a second time. Each
provider says which folders are its system ones in its own terms: Gmail by a
label's type; Graph by its well-known folders' ids, because their display
names are in the mailbox's language; iCloud by its role folders' names, which
the server keeps whatever the person's language.

Labels are Gmail's alone (the descriptor's ``LABELS``) and are managed as the
assistant's tools manage them: created, renamed, deleted — a system label
never — and applied to a selection in one act, the person's labels only. A
label has no revision, so Gmail's 409 on its write can only mean that its name
is taken, and is said as such.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Final
from uuid import UUID

from fastapi import status

from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.apple_imap import ROLE_FOLDER_NAMES
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import NAME_TAKEN, NOT_SUPPORTED_BY_PROVIDER, refuse
from src.domains.workbench.features import (
    PROVIDER_FEATURES,
    TOOL_PROVIDERS,
    WorkbenchFeature,
    WorkbenchTool,
)
from src.domains.workbench.mail_query import SYSTEM_PLACES
from src.domains.workbench.schemas.mail import (
    SYSTEM_FOLDER_PREFIX,
    LabelApplication,
    LabelChange,
    MailFolder,
    MailFolders,
    NewLabel,
)

_TOOL = WorkbenchTool.MAIL


async def read_folders(user_id: UUID) -> MailFolders:
    """The folder pane: the system places, then the person's own folders by name."""
    async with open_tool_client(_TOOL, user_id) as opened:
        async with provider_call(_TOOL, "folders", act=False):
            own = await _OWN_FOLDERS[opened.connector_type](opened)
        places = SYSTEM_PLACES[opened.connector_type]
    system = [
        MailFolder(id=f"{SYSTEM_FOLDER_PREFIX}{role}", kind="system", role=role, name=None)
        for role in places
    ]
    return MailFolders(folders=[*system, *sorted(own, key=lambda f: (f.name or "").casefold())])


async def create_label(user_id: UUID, request: NewLabel) -> MailFolder:
    """Create a Gmail label (« / » nests it); a system label's name is refused."""
    async with _labels_client(user_id) as client:
        _refuse_system(client, request.name)
        async with provider_call(_TOOL, "create_label", act=True):
            with _name_must_be_free():
                raw = await client.create_label(request.name)
    return _own_folder(raw)


async def rename_label(user_id: UUID, request: LabelChange) -> MailFolder:
    """Rename one of the person's labels (its sublabels keep their names, as the tools)."""
    async with _labels_client(user_id) as client:
        _refuse_system(client, request.label_id)
        _refuse_system(client, request.name)
        async with provider_call(_TOOL, "rename_label", act=True):
            with _name_must_be_free():
                raw = await client.update_label(request.label_id, request.name)
    return _own_folder(raw)


async def delete_label(user_id: UUID, label_id: str) -> None:
    """Delete one of the person's labels; its messages stay where they are."""
    async with _labels_client(user_id) as client:
        _refuse_system(client, label_id)
        async with provider_call(_TOOL, "delete_label", act=True):
            await client.delete_label(label_id)


async def apply_labels(user_id: UUID, request: LabelApplication) -> None:
    """Add and remove the person's labels on a selection, in one act."""
    async with _labels_client(user_id) as client:
        for label_id in (*request.add, *request.remove):
            _refuse_system(client, label_id)
        async with provider_call(_TOOL, "apply_labels", act=True):
            await client.batch_modify_labels(
                request.message_ids, add_label_ids=request.add, remove_label_ids=request.remove
            )


async def _gmail_labels(opened: ActiveClient) -> list[MailFolder]:
    client: GoogleGmailClient = opened.client
    # Fresh: a label made in Gmail itself shows at once, not after the cache's hour.
    labels = await client.list_labels_full(use_cache=False)
    return [_own_folder(label) for label in labels if label.get("type") == "user"]


async def _outlook_folders(opened: ActiveClient) -> list[MailFolder]:
    client: MicrosoftOutlookClient = opened.client
    names = await client.list_labels()
    system = await client.system_folder_ids()
    return [_named(name) for folder_id, name in names.items() if folder_id not in system]


async def _imap_folders(opened: ActiveClient) -> list[MailFolder]:
    client: EmailClientProtocol = opened.client
    names = await client.list_labels()
    return [_named(name) for name in names.values() if name not in ROLE_FOLDER_NAMES]


#: How each provider's own folders are read, the system ones left out.
_OWN_FOLDERS: Final[dict[ConnectorType, Callable[[ActiveClient], Awaitable[list[MailFolder]]]]] = {
    ConnectorType.GOOGLE_GMAIL: _gmail_labels,
    ConnectorType.MICROSOFT_OUTLOOK: _outlook_folders,
    ConnectorType.APPLE_EMAIL: _imap_folders,
}


@asynccontextmanager
async def _labels_client(user_id: UUID) -> AsyncIterator[GoogleGmailClient]:
    """The account's mail client, refused unsent when its provider has no labels."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if WorkbenchFeature.LABELS not in PROVIDER_FEATURES[opened.connector_type]:
            refuse(NOT_SUPPORTED_BY_PROVIDER)
        client: GoogleGmailClient = opened.client
        yield client


def _refuse_system(client: GoogleGmailClient, label: str) -> None:
    """A system label is never created, renamed, deleted or applied (as the tools)."""
    if client.is_system_label(label):
        refuse(NOT_SUPPORTED_BY_PROVIDER)


@contextmanager
def _name_must_be_free() -> Iterator[None]:
    """A label write Gmail refuses with 409: a label has no revision, its name is taken."""
    try:
        yield
    except ConnectorAPIError as refused:
        if refused.upstream_status_code == status.HTTP_409_CONFLICT:
            refuse(NAME_TAKEN)
        raise


def _own_folder(label: Mapping[str, Any]) -> MailFolder:
    return MailFolder(
        id=str(label.get("id") or ""), kind="user", role=None, name=str(label.get("name") or "")
    )


def _named(name: str) -> MailFolder:
    """A folder the listing finds by its name (Graph and IMAP resolve it that way)."""
    return MailFolder(id=name, kind="user", role=None, name=name)


def _assert_mail_panes_complete() -> None:
    """Refuse to boot when a mail provider has no folder pane (ADR-085).

    Raises:
        RuntimeError: Naming the providers missing a table entry.
    """
    served = TOOL_PROVIDERS[_TOOL]
    missing = sorted(
        kind.value for kind in served if kind not in SYSTEM_PLACES or kind not in _OWN_FOLDERS
    )
    if missing:
        raise RuntimeError(f"mail folder pane missing for {missing} (workbench/mail_folders.py)")


_assert_mail_panes_complete()
