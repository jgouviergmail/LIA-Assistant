"""The mail screen's folders and Gmail's labels, by the person's own hand (ADR-369).

The folder pane draws the mailbox's SYSTEM places first — each provider's own,
named by role in the Gmail-style vocabulary the three clients translate (F12),
so the listing reads any of them as ``in:<role>`` — then the person's own
folders, without the system ones a second time. Each provider says which
folders are its system ones in its own terms: Gmail by a label's type; Graph by
its well-known folders' ids, because their display names are in the mailbox's
language; iCloud by its role folders' names, which the server keeps whatever
the person's language. A nested folder is named by its path (Gmail and iCloud
spell it so; Graph's is walked level by level, and a walk cut at its bound says
so): the page draws the tree, the listing finds the folder by that path.

Labels are Gmail's alone (the descriptor's ``LABELS``) and are managed as the
assistant's tools manage them: created, renamed, deleted — a system label
never — and applied to a selection in one act, the person's labels only. A
label has no revision, so Gmail's 409 on its write can only mean that its name
is taken, and is said as such. Outlook and iCloud have folders in their place
(``FOLDER_MANAGEMENT``), on the same routes: the pane names a folder by its path,
a rename gives it a new own name, never a new place, and neither client touches
a folder of the mailbox's own.

The pane's figures are read apart from its folders: they change all day, the
folders hardly ever. Each is keyed by the id the pane draws, and a folder the
reading left out draws nothing, its cut stated.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Final
from uuid import UUID

from fastapi import status

from src.core.constants import WORKBENCH_MAIL_COUNTS_FOLDERS_MAX
from src.core.exceptions import ConnectorAPIError
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.apple_imap import ROLE_FOLDER_NAMES
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.protocols import (
    EmailClientProtocol,
    MailFolderClientProtocol,
)
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.errors import (
    INVALID_REQUEST,
    NAME_TAKEN,
    NOT_SUPPORTED_BY_PROVIDER,
    refuse,
)
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
    MailCounts,
    MailFolder,
    MailFolders,
    NewLabel,
)

_TOOL = WorkbenchTool.MAIL


async def read_folders(user_id: UUID) -> MailFolders:
    """The folder pane: the system places, then the person's own folders by name."""
    async with open_tool_client(_TOOL, user_id) as opened:
        async with provider_call(_TOOL, "folders", act=False):
            own, complete = await _OWN_FOLDERS[opened.connector_type](opened)
        places = SYSTEM_PLACES[opened.connector_type]
    system = [
        MailFolder(id=f"{SYSTEM_FOLDER_PREFIX}{role}", kind="system", role=role, name=None)
        for role in places
    ]
    named = sorted(own, key=lambda f: (f.name or "").casefold())
    return MailFolders(folders=[*system, *named], truncated=not complete)


async def read_counts(user_id: UUID) -> MailCounts:
    """What the mailbox leaves unread, each figure keyed as the pane names its folder."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "counts", act=False):
            raw = await client.unread_counts(WORKBENCH_MAIL_COUNTS_FOLDERS_MAX)
    places = {f"{SYSTEM_FOLDER_PREFIX}{role}": count for role, count in raw.roles.items()}
    return MailCounts(counts={**places, **raw.folders}, truncated=not raw.complete)


async def create_label(user_id: UUID, request: NewLabel) -> MailFolder:
    """Create a Gmail label or a folder (« / » nests it); a system label's name is refused."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if _has_folders(opened):
            folders: MailFolderClientProtocol = opened.client
            async with provider_call(_TOOL, "create_folder", act=True):
                with _name_must_be_free():
                    return _named(await folders.create_folder(request.name))
        client = _labels_of(opened)
        _refuse_system(client, request.name)
        async with provider_call(_TOOL, "create_label", act=True):
            with _name_must_be_free():
                raw = await client.create_label(request.name)
    return _own_folder(raw)


async def rename_label(user_id: UUID, request: LabelChange) -> MailFolder:
    """Rename one of the person's labels (its sublabels keep their names, as the tools)
    or folders (a new own name, never a new place)."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if _has_folders(opened):
            if "/" in request.name:
                refuse(INVALID_REQUEST)
            folders: MailFolderClientProtocol = opened.client
            async with provider_call(_TOOL, "rename_folder", act=True):
                with _name_must_be_free():
                    return _named(await folders.rename_folder(request.label_id, request.name))
        client = _labels_of(opened)
        _refuse_system(client, request.label_id)
        _refuse_system(client, request.name)
        async with provider_call(_TOOL, "rename_label", act=True):
            with _name_must_be_free():
                raw = await client.update_label(request.label_id, request.name)
    return _own_folder(raw)


async def delete_label(user_id: UUID, label_id: str) -> None:
    """Delete one of the person's labels, whose messages stay where they are, or an empty
    folder of theirs: a folder holding anything is refused, never emptied in passing."""
    async with open_tool_client(_TOOL, user_id) as opened:
        if _has_folders(opened):
            folders: MailFolderClientProtocol = opened.client
            async with provider_call(_TOOL, "delete_folder", act=True):
                await folders.delete_folder(label_id)
            return
        client = _labels_of(opened)
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


async def _gmail_labels(opened: ActiveClient) -> tuple[list[MailFolder], bool]:
    client: GoogleGmailClient = opened.client
    # Fresh: a label made in Gmail itself shows at once, not after the cache's hour.
    labels = await client.list_labels_full(use_cache=False)
    return [_own_folder(label) for label in labels if label.get("type") == "user"], True


async def _outlook_folders(opened: ActiveClient) -> tuple[list[MailFolder], bool]:
    client: MicrosoftOutlookClient = opened.client
    folders, complete = await client.list_folders()
    system = await client.system_folder_ids()
    return [_named(item.path) for item in folders if item.folder_id not in system], complete


async def _imap_folders(opened: ActiveClient) -> tuple[list[MailFolder], bool]:
    client: EmailClientProtocol = opened.client
    names = await client.list_labels()
    return [_named(name) for name in names.values() if name not in ROLE_FOLDER_NAMES], True


#: How each provider's own folders are read, the system ones left out, and whether
#: all of them were.
_OWN_FOLDERS: Final[
    dict[ConnectorType, Callable[[ActiveClient], Awaitable[tuple[list[MailFolder], bool]]]]
] = {
    ConnectorType.GOOGLE_GMAIL: _gmail_labels,
    ConnectorType.MICROSOFT_OUTLOOK: _outlook_folders,
    ConnectorType.APPLE_EMAIL: _imap_folders,
}


@asynccontextmanager
async def _labels_client(user_id: UUID) -> AsyncIterator[GoogleGmailClient]:
    """The account's mail client, refused unsent when its provider has no labels."""
    async with open_tool_client(_TOOL, user_id) as opened:
        yield _labels_of(opened)


def _labels_of(opened: ActiveClient) -> GoogleGmailClient:
    """The opened client as a labels client, refused unsent when its provider has none."""
    if WorkbenchFeature.LABELS not in PROVIDER_FEATURES[opened.connector_type]:
        refuse(NOT_SUPPORTED_BY_PROVIDER)
    client: GoogleGmailClient = opened.client
    return client


def _has_folders(opened: ActiveClient) -> bool:
    """Whether this provider's folders of the person's own are managed here."""
    return WorkbenchFeature.FOLDER_MANAGEMENT in PROVIDER_FEATURES[opened.connector_type]


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
