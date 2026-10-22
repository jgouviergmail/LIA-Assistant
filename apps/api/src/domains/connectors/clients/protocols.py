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

from src.domains.connectors.clients.contact_directory import ContactDirectory
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
        *,
        single_attempt: bool = True,
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

    # ------------------------------------------------------------------
    # Mailbox drafts (ADR-344): the person's own unsent messages, stored by
    # the provider. Every draft returned speaks the ``EmailMessage``
    # vocabulary plus ``mailbox_draft_id``, and its body keeps the quoted
    # history: a draft is the person's own text, and an edit must not lose it.
    # A draft that is not in the drafts folder — sent, deleted, in the trash,
    # or never there — raises ``MailboxDraftNotFoundError`` (``mailbox_drafts``).
    # ------------------------------------------------------------------

    async def list_drafts(
        self,
        query: str = "",
        max_results: int = 10,
        page_token: str | None = None,
        headers_only: bool = True,
    ) -> dict:
        """The newest drafts first, with the shape of ``search_emails``."""
        ...

    async def get_draft(self, draft_id: str) -> dict:
        """One draft, whole. Raises ``MailboxDraftNotFoundError`` when absent."""
        ...

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict:
        """Save a new draft; an empty ``to`` leaves the recipient unset.

        Returns the saved draft, as ``get_draft`` reads it. An address that
        cannot be read raises ``ValueError``.
        """
        ...

    async def create_reply_draft(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
    ) -> dict:
        """Save the reply to ``message_id`` as a draft, in its thread.

        Returns the saved draft, as ``get_draft`` reads it.
        """
        ...

    async def create_forward_draft(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
    ) -> dict:
        """Save the forward of ``message_id`` as a draft, with its files.

        ``to`` is required: Graph refuses a forward draft without a recipient.
        Returns the saved draft, as ``get_draft`` reads it.
        """
        ...

    async def update_draft(
        self,
        draft_id: str,
        *,
        to: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        expected_revision: str | None = None,
    ) -> dict:
        """Change the fields given (None keeps one, "" clears it), keep the rest.

        A new ``body`` is the whole plain-text body (an HTML draft loses its
        formatting, never its files). Returns the saved draft, as ``get_draft``
        reads it — under a NEW ``mailbox_draft_id`` on IMAP, which stores a new
        message.
        """
        ...

    async def trash_drafts(self, draft_ids: Sequence[str]) -> dict:
        """Move drafts to the mailbox trash, where they stay recoverable.

        Returns ``{"trashed": [ids], "failed": [{"mailbox_draft_id", "status"}]}``,
        each status one of ``mailbox_drafts.TRASH_FAILURE_STATUSES``.
        """
        ...

    async def send_draft(self, draft_id: str) -> dict:
        """Send a draft as it is stored — one attempt, never retried.

        The caller reads and verifies the stored revision before sending.
        This does not establish an atomic compare-and-send at the provider.
        Returns ``id`` (the sent message, when the provider names it),
        ``mailbox_draft_id`` and ``draft_kept`` — True only when the message
        left but the draft could not be taken out of the drafts folder (IMAP,
        where sending and filing are two acts).
        """
        ...

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

    async def list_email_directory(
        self, max_contacts: int, *, cache_scope: str | None = None
    ) -> ContactDirectory: ...


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
