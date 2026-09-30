"""
Protocol classes for connector clients.

Structural typing (PEP 544) — no inheritance required.
GoogleGmailClient, AppleEmailClient, and MicrosoftOutlookClient all satisfy
EmailClientProtocol implicitly because they implement the same methods.

Used for type safety with mypy strict mode.

Created: 2026-03-10
"""

from collections.abc import Sequence
from typing import ClassVar, Protocol, runtime_checkable

from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.infrastructure.email.outgoing import OutgoingAttachment


@runtime_checkable
class OutgoingCeiling(Protocol):
    """What a mail provider's client publishes about the files it sends (ADR-321).

    Runtime-checkable so a caller holding only the CLASS (the options of the
    « Send by e-mail » dialog open no client) can read it without a cast.
    """

    #: The largest file one message may carry through this provider, derived
    #: from what the provider documents — published to the person.
    OUTGOING_FILE_MAX_BYTES: ClassVar[int]


class EmailClientProtocol(OutgoingCeiling, Protocol):
    """Protocol for email clients (Gmail, Apple Mail, Outlook)."""

    #: Whether each hit of ``search_emails`` (``headers_only=False``) is already
    #: the whole message — body and attachments — so a reader needs no
    #: ``get_message`` per hit. False where the provider's listing carries a
    #: preview only (Graph selects ``bodyPreview`` and never expands attachments).
    SEARCH_HITS_ARE_WHOLE: ClassVar[bool]

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
        fields: list[str] | None = None,
        use_cache: bool = True,
        page_token: str | None = None,
        headers_only: bool = False,
    ) -> dict: ...

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict: ...

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
        attachments: Sequence[OutgoingAttachment] = (),
    ) -> dict: ...

    async def reply_email(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
        to: str | None = None,
    ) -> dict:
        """Reply to an email. If to is provided, overrides the default recipient (original sender)."""
        ...

    async def forward_email(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
        include_attachments: bool = True,
    ) -> dict: ...

    async def trash_email(self, message_id: str) -> dict: ...

    async def get_own_address(self) -> str | None:
        """The connected mailbox's own address, as its provider states it (ADR-314).

        None when the provider vouches for no address — the caller refuses
        rather than guessing where « the person's own mailbox » is.
        """
        ...

    async def download_attachment(
        self,
        message_id: str,
        *,
        attachment_id: str | None = None,
        filename: str | None = None,
        max_bytes: int | None = None,
    ) -> EmailAttachmentContent: ...

    async def list_labels(self, use_cache: bool = True) -> dict[str, str]: ...

    async def resolve_label_names_in_query(self, query: str, use_cache: bool = True) -> str: ...


class CalendarClientProtocol(Protocol):
    """Protocol for calendar clients (Google Calendar, Apple Calendar)."""

    async def list_calendars(self, max_results: int = 100, show_hidden: bool = False) -> dict: ...

    async def list_events(
        self,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
        calendar_id: str = "primary",
        query: str | None = None,
        fields: list[str] | None = None,
    ) -> dict: ...

    async def get_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        fields: list[str] | None = None,
    ) -> dict: ...

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
        add_conference: bool = False,
    ) -> dict: ...

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
        timezone: str | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
    ) -> dict: ...

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict: ...


class ContactsClientProtocol(Protocol):
    """Protocol for contacts clients (Google Contacts, Apple Contacts, Microsoft Contacts)."""

    async def search_contacts(
        self,
        query: str,
        max_results: int = 10,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict: ...

    async def list_connections(
        self,
        page_size: int = 100,
        page_token: str | None = None,
        use_cache: bool = True,
        fields: list[str] | None = None,
    ) -> dict: ...

    async def get_person(
        self,
        resource_name: str,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict: ...

    async def create_contact(
        self,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
    ) -> dict: ...

    async def update_contact(
        self,
        resource_name: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        address: str | None = None,
    ) -> dict: ...

    async def delete_contact(self, resource_name: str) -> bool: ...


class TasksClientProtocol(Protocol):
    """Protocol for tasks clients (Google Tasks, Microsoft To Do)."""

    async def list_task_lists(self, max_results: int = 20) -> dict: ...

    async def get_task_list(self, task_list_id: str) -> dict: ...

    async def create_task_list(self, title: str) -> dict: ...

    async def delete_task_list(self, task_list_id: str) -> bool: ...

    async def list_tasks(
        self,
        task_list_id: str = "@default",
        max_results: int = 20,
        show_completed: bool = False,
        show_hidden: bool = False,
        due_min: str | None = None,
        due_max: str | None = None,
        completed_min: str | None = None,
    ) -> dict: ...

    async def get_task(self, task_list_id: str, task_id: str) -> dict: ...

    async def create_task(
        self,
        task_list_id: str = "@default",
        title: str = "",
        notes: str | None = None,
        due: str | None = None,
        parent: str | None = None,
    ) -> dict: ...

    async def update_task(
        self,
        task_list_id: str,
        task_id: str,
        title: str | None = None,
        notes: str | None = None,
        due: str | None = None,
        status: str | None = None,
    ) -> dict: ...

    async def complete_task(self, task_list_id: str, task_id: str) -> dict: ...

    async def delete_task(self, task_list_id: str, task_id: str) -> bool: ...
