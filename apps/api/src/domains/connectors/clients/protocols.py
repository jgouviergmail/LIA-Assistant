"""
Protocol classes for connector clients.

Structural typing (PEP 544) — no inheritance required.
GoogleGmailClient, AppleEmailClient, and MicrosoftOutlookClient all satisfy
EmailClientProtocol implicitly because they implement the same methods.

Used for type safety with mypy strict mode.

Created: 2026-03-10
"""

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Protocol, runtime_checkable

from src.domains.connectors.clients.calendar_answers import EventAnswer
from src.domains.connectors.clients.calendar_options import EventOptions
from src.domains.connectors.clients.contact_details import ContactDetails
from src.domains.connectors.clients.contact_directory import ContactDirectory
from src.domains.connectors.clients.contact_photos import ContactPhoto
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.connectors.clients.event_bounds import BoundsChange, EventBounds
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.clients.mail_inline_images import InlineBudget
from src.domains.connectors.clients.mail_moves import MailPlace, UnreadCounts
from src.domains.connectors.clients.mail_unsubscribe import Unsubscribe
from src.domains.connectors.clients.normalizers.contact_values import TypedAddress, TypedValue
from src.domains.connectors.clients.office_files import OfficeRefusal
from src.domains.connectors.clients.task_details import TaskDetails
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
        *,
        # Read with the message what its mailbox says it did with it — « answered »
        # (ADR-379): on Graph the one expansion of the request, so the files are left
        # out; already in every IMAP read; nothing on Gmail, which keeps no such mark.
        mailbox_mark: bool = False,
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
        cc: str | None = None,
        attachments: Sequence[OutgoingAttachment] = (),
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
        attachments: Sequence[OutgoingAttachment] = (),
    ) -> dict: ...

    async def trash_email(self, message_id: str) -> dict: ...

    async def mark_read(self, message_ids: Sequence[str], read: bool) -> dict:
        """Mark messages read or unread (ADR-369, D2), each id once.

        Returns ``{"updated": [ids], "failed": [{"id", "status"}]}``, each status
        one of ``mail_read_state.READ_STATE_FAILURE_STATUSES``: a message gone
        since it was listed never costs the rest of the selection.
        """
        ...

    async def set_starred(self, message_ids: Sequence[str], starred: bool) -> dict:
        """Star messages or take their star off: ``mark_read``'s contract (ADR-369, lot 4)."""
        ...

    async def move_emails(
        self,
        message_ids: Sequence[str],
        place: MailPlace,
        origin: MailPlace | None = None,
    ) -> dict:
        """Send messages to a place (ADR-369, lot 4).

        Args:
            message_ids: The messages (each counted once).
            place: Where they go.
            origin: Where they are, when the caller knows (Gmail's leaving is part
                of the move).

        Returns:
            ``mail_moves.moved_result``: ``mark_read``'s answer, and what each id became.
        """
        ...

    async def place_named(self, name: str) -> MailPlace:
        """The place a person's name for a folder is (Gmail keeps labels by id)."""
        ...

    async def unread_counts(self, folders_max: int) -> UnreadCounts:
        """What the inbox, the spam and the person's folders leave unread (ADR-369, lot 4)."""
        ...

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

    async def get_conversation(self, message_id: str, max_messages: int) -> dict:
        """The conversation a message belongs to, headers alone (``mail_conversation``)."""
        ...

    async def conversations_of(
        self, messages: Sequence[Mapping[str, Any]], max_messages: int
    ) -> dict[str, Conversation]:
        """What the conversations of listed messages hold, drafts apart (ADR-379).

        Keyed by each message's ``threadId``. The owner's own messages carry the
        ``SENT`` label and a message carries what its mailbox says of it, whatever
        the provider (``mail_conversation.Conversation``). A conversation that could
        not be read is ABSENT, never empty: its messages then get no reply state.
        A read that fails as a whole raises what its transport raised: the caller
        decides what a page without reply states is worth.
        """
        ...

    async def get_message_html(self, message_id: str) -> str | None:
        """The message's HTML body, as its author laid it out (ADR-369, D3).

        Display only: the model reads the clean text, never markup (ADR-287),
        so no tool reads this. None when the message carries no HTML body — an
        attached file, even an ``.html`` one, or a message forwarded as an
        attachment, is never the body. Reading it marks nothing read.
        """
        ...

    async def read_inline_images(
        self, message_id: str, cids: set[str], budget: InlineBudget
    ) -> None:
        """Read into ``budget`` the images of a message its HTML names (ADR-369, lot 3).

        Display only, like the HTML. A part ``budget`` refuses by its listed size is
        never read. A message forwarded as an attachment keeps its images.
        """
        ...

    async def read_unsubscribe(self, message_id: str) -> Unsubscribe | None:
        """The ways out a message names (``mail_unsubscribe``); None when it names none."""
        ...

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
        attachments: Sequence[OutgoingAttachment] = (),
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
        to: str | None = None,
        cc: str | None = None,
        attachments: Sequence[OutgoingAttachment] = (),
    ) -> dict:
        """Save the reply to ``message_id`` as a draft, in its thread.

        ``to`` and ``cc`` replace those the provider would answer, as in
        ``reply_email``: None keeps them, an empty ``cc`` removes them. Returns the
        saved draft, as ``get_draft`` reads it.
        """
        ...

    async def create_forward_draft(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
        attachments: Sequence[OutgoingAttachment] = (),
    ) -> dict:
        """Save the forward of ``message_id`` as a draft, with its files.

        ``to`` is required: Graph refuses a forward draft without a recipient.
        ``attachments`` are the person's own, after those of the original.
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
        add_files: Sequence[OutgoingAttachment] = (),
        remove_files: Sequence[str] = (),
        is_html: bool = False,
    ) -> dict:
        """Change the fields given (None keeps one, "" clears it), keep the rest.

        A new ``body`` is the whole body, text unless ``is_html`` says so (text takes an
        HTML draft's formatting with it, never its files). ``add_files`` join it; ``remove_files`` name
        those that leave, one file for each. Returns the saved draft, as ``get_draft``
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


class MailTrashClientProtocol(Protocol):
    """Deleting for good, where the provider's scopes allow it (ADR-369, lot 4)."""

    async def delete_emails_forever(self, message_ids: Sequence[str]) -> dict:
        """Delete messages of the trash for good: ``mark_read``'s answer, any other refused."""
        ...

    async def empty_trash(self, limit: int) -> dict:
        """Delete what the trash holds within a bound: ``{"deleted", "remaining"}``."""
        ...


class MailFolderClientProtocol(Protocol):
    """The folders of the person's own, where a mailbox has folders (ADR-369, lot 4).

    Outlook and iCloud; Gmail's are labels, and answer through its own client.
    """

    async def create_folder(self, name: str) -> str:
        """Create a folder (« / » nests it); answers what the pane names it by."""
        ...

    async def rename_folder(self, folder: str, name: str) -> str:
        """Rename a folder in place; answers what the pane names it by from now on."""
        ...

    async def delete_folder(self, folder: str) -> None:
        """Delete a folder that holds nothing; one that holds anything is refused."""
        ...


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
        bounds: EventBounds,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
        add_conference: bool = False,
        idempotency_key: str | None = None,
        options: EventOptions | None = None,
    ) -> dict:
        """An event at the bounds it is given: wall times in their zone, or days (ADR-380).

        Never text: a client says the bounds in its provider's words, and reads
        no time on the way (``event_bounds``).
        """
        ...

    async def update_event(
        self,
        event_id: str,
        summary: str | None = None,
        bounds: BoundsChange | None = None,
        description: str | None = None,
        location: str | None = None,
        attendees: list[str] | None = None,
        calendar_id: str = "primary",
        send_updates: str | None = None,
        add_conference: bool = False,
        options: EventOptions | None = None,
    ) -> dict:
        """What changes of its ``bounds``: a whole pair gives the event its shape, sides
        alone keep the shape it has, None leaves its bounds as they are (ADR-380).

        ``send_updates`` says who is told (Google ``sendUpdates``; None, the
        provider's own default). Graph tells attendees on its own and CalDAV
        leaves it to the server: both accept it and ignore it.
        """
        ...

    async def list_events_window(
        self, calendar_id: str, time_min: str, time_max: str, *, bound: int
    ) -> dict:
        """Every event of a window, occurrences expanded, up to ``bound`` (ADR-369).

        Returns ``{"events": [...], "truncated": bool}``.
        """
        ...

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
        send_updates: str = "all",
    ) -> dict: ...


class CalendarAnswerProtocol(Protocol):
    """Answering an invitation, on the three calendars (ADR-369, lot 5)."""

    async def respond_to_event(
        self, event_id: str, response: EventAnswer, calendar_id: str = "primary"
    ) -> dict:
        """The person's own answer, the organiser told; ``NotInvitedError`` when none is theirs."""
        ...


class TaskStepsProtocol(Protocol):
    """A task's steps (``WorkbenchFeature.TASK_STEPS``): To Do's alone."""

    async def add_task_step(self, task_list_id: str, task_id: str, title: str) -> dict: ...

    async def change_task_step(
        self,
        task_list_id: str,
        task_id: str,
        step_id: str,
        *,
        title: str | None = None,
        checked: bool | None = None,
    ) -> dict: ...

    async def remove_task_step(self, task_list_id: str, task_id: str, step_id: str) -> None: ...


class TaskOrderProtocol(Protocol):
    """The order of a list (``WorkbenchFeature.TASK_ORDER``): Google's alone."""

    async def place_task(self, task_list_id: str, task_id: str, previous_id: str | None) -> dict:
        """Put a task after a sibling; None puts it first."""
        ...


class FilesClientProtocol(Protocol):
    """A drive, in Drive's words: Google Drive and OneDrive (ADR-369, lot 6)."""

    async def recent_files(self, max_results: int) -> dict[str, Any]: ...

    async def folder_path(self, file: Mapping[str, Any], known: dict[str, Any]) -> str | None: ...

    async def search_files(
        self,
        query: str,
        max_results: int = 10,
        mime_type: str | None = None,
        folder_id: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
        search_mode: str = "name_only",
        page_token: str | None = None,
    ) -> dict:
        """``files`` and ``nextPageToken``; a page may be partial before the end."""
        ...

    async def list_files(
        self,
        folder_id: str = "root",
        max_results: int = 20,
        page_token: str | None = None,
        fields: list[str] | None = None,
        content_type: str | None = "files_only",
        order_by: str = "folder,name",
    ) -> dict:
        """``files`` and ``nextPageToken``; folders first on each page."""
        ...

    async def get_file_metadata(self, file_id: str, fields: list[str] | None = None) -> dict:
        """One item; ``root`` is the top of the drive."""
        ...

    async def get_file_content(
        self,
        file_id: str,
        max_size_bytes: int = 10 * 1024 * 1024,
        known_size: int | None = None,
    ) -> bytes | None:
        """A file's bytes; None past the ceiling."""
        ...

    async def delete_file(self, file_id: str) -> bool:
        """Moves a file to the trash."""
        ...

    async def restore_file(self, file_id: str) -> dict:
        """The item, out of the trash."""
        ...

    async def storage_quota(self) -> dict[str, int | None]:
        """What the account uses of what it has, in bytes."""
        ...

    async def read_sharing(self, file_id: str) -> dict:
        """Who reaches an item (``people``), and the ``link`` anyone can follow."""
        ...

    async def share_with(self, file_id: str, email: str, role: str) -> None:
        """Give a person access, told by the drive; ``role`` is ``reader`` or ``writer``."""
        ...

    async def open_link(self, file_id: str) -> dict:
        """Let anyone with the link read an item: its ``id`` and its ``url``."""
        ...

    async def remove_share(self, file_id: str, permission_id: str) -> None:
        """Take an access back."""
        ...

    async def create_folder(self, name: str, parent_id: str = "root") -> dict:
        """The new folder; ``FileNameTakenError`` where the provider keeps one of a name."""
        ...

    async def rename_file(self, file_id: str, name: str) -> dict:
        """The item under its new name."""
        ...

    async def upload_file(
        self, name: str, data: bytes, mime_type: str, parent_id: str = "root"
    ) -> dict:
        """Add a file to a folder; a drive that holds one name per folder refuses a second."""
        ...

    async def move_file(self, file_id: str, parent_id: str) -> dict:
        """The item in its new folder."""
        ...

    async def copy_file(
        self, file_id: str, parent_id: str | None = None, name: str | None = None
    ) -> dict | None:
        """The copy, or None where the provider finishes it after answering."""
        ...


class FileViewsProtocol(Protocol):
    """Drive's views, stars and trash (ADR-369, lot 6): OneDrive has no call for them."""

    async def list_view(
        self, view: str, *, max_results: int, page_token: str | None, fields: list[str]
    ) -> dict:
        """One page of what the drive holds under a view."""
        ...

    async def set_starred(self, file_id: str, starred: bool) -> dict:
        """The item, its star set."""
        ...

    async def delete_file_forever(self, file_id: str) -> None:
        """Delete an item for good."""
        ...

    async def empty_trash(self) -> None:
        """Delete for good all that the trash holds."""
        ...


class CalendarManagementProtocol(Protocol):
    """Moving an event and managing calendars, on the three calendars (ADR-369, lot 5)."""

    async def move_event(self, event_id: str, calendar_id: str, destination_id: str) -> dict:
        """The event in its new calendar; a provider that copies refuses what it would reach."""
        ...

    async def create_calendar(self, name: str, timezone: str | None = None) -> dict:
        """A new calendar of the account's."""
        ...

    async def rename_calendar(self, calendar_id: str, name: str) -> dict:
        """The calendar under its new name."""
        ...

    async def delete_calendar(self, calendar_id: str) -> None:
        """Deletes the calendar and all it holds."""
        ...


@runtime_checkable
class SpreadsheetsProtocol(Protocol):
    """A drive's spreadsheets, in the words of Sheets: Google's and OneDrive's (ADR-369)."""

    async def get_spreadsheet(self, spreadsheet_id: str) -> dict[str, Any]: ...

    async def read_rows(
        self, spreadsheet_id: str, sheet: str, max_rows: int
    ) -> list[list[Any]]: ...

    async def write_refusal(
        self, a1_range: str, values: list[list[str]]
    ) -> OfficeRefusal | None: ...

    async def write_range(
        self, spreadsheet_id: str, sheet: str, a1_range: str, values: list[list[str]]
    ) -> int: ...

    async def append_rows(
        self, spreadsheet_id: str, sheet: str, values: list[list[str]]
    ) -> int: ...


@runtime_checkable
class DocumentsProtocol(Protocol):
    """A drive's documents: Google Docs and OneDrive's Word files (ADR-369)."""

    async def read_text(self, document_id: str) -> dict[str, str]: ...

    async def read_title(self, document_id: str) -> str: ...

    async def append_text(self, document_id: str, text: str) -> Any: ...


@runtime_checkable
class MailboxSettingsProtocol(Protocol):
    """A mailbox's responder and filters, in the one vocabulary of both providers."""

    async def get_vacation(self) -> dict: ...

    async def update_vacation(
        self,
        enable: bool,
        subject: str | None = None,
        body: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> dict: ...

    async def list_filters(self) -> dict: ...

    async def label_names(self) -> dict[str, str]: ...

    async def create_filter(self, criteria: dict, action: dict) -> dict: ...

    async def delete_filter(self, filter_id: str) -> None: ...

    async def list_send_as(self) -> dict: ...


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
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict: ...

    # A list REPLACES that list and ``None`` keeps it; a single ``email`` /
    # ``phone`` / ``address`` replaces the PRIMARY value and keeps the others
    # (ADR-369, D4); a list the provider cannot hold raises ContactValuesRefused.
    async def update_contact(
        self,
        resource_name: str,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        organization: str | None = None,
        notes: str | None = None,
        address: str | None = None,
        *,
        emails: list[TypedValue] | None = None,
        phones: list[TypedValue] | None = None,
        addresses: list[TypedAddress] | None = None,
        details: ContactDetails | None = None,
    ) -> dict: ...

    async def delete_contact(self, resource_name: str) -> bool: ...

    async def get_contact_photo(self, resource_name: str) -> ContactPhoto | None: ...

    async def set_contact_photo(self, resource_name: str, photo: ContactPhoto) -> None: ...

    async def remove_contact_photo(self, resource_name: str) -> None: ...

    async def list_contact_groups(self) -> dict: ...

    async def group_people(
        self, group: str, max_members: int, fields: list[str] | None = None
    ) -> dict: ...

    async def groups_of_contact(self, resource_name: str) -> list[dict]: ...

    async def create_contact_group(self, name: str) -> dict: ...

    async def rename_contact_group(self, group: str, name: str) -> None: ...

    async def delete_contact_group(self, group: str) -> None: ...

    async def change_group_members(
        self, group: str, *, add: Sequence[str], remove: Sequence[str]
    ) -> None: ...

    async def list_email_directory(
        self, max_contacts: int, *, cache_scope: str | None = None
    ) -> ContactDirectory: ...


class TasksClientProtocol(Protocol):
    """Protocol for tasks clients (Google Tasks, Microsoft To Do)."""

    async def list_task_lists(
        self, max_results: int = 20, *, page_token: str | None = None
    ) -> dict:
        """One page of lists: ``items`` and ``next_page_token`` (None on the last page)."""
        ...

    async def get_task_list(self, task_list_id: str) -> dict: ...

    async def create_task_list(self, title: str) -> dict: ...

    async def rename_task_list(self, task_list_id: str, title: str) -> dict: ...

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
        page_token: str | None = None,
    ) -> dict:
        """One page of tasks: ``items`` and ``next_page_token`` (None on the last page)."""
        ...

    async def get_task(self, task_list_id: str, task_id: str) -> dict: ...

    async def create_task(
        self,
        task_list_id: str = "@default",
        title: str = "",
        notes: str | None = None,
        due: str | None = None,
        parent: str | None = None,
        *,
        details: TaskDetails | None = None,
        steps: Sequence[str] = (),
        due_zone: str | None = None,
    ) -> dict:
        """``details`` and ``steps`` are To Do's alone: Google refuses them (``task_details``).

        ``due_zone`` names the zone ``due`` is a wall time in: To Do keeps local midnight only when it
        is named (``core/task_due``); Google keeps a date and takes none.
        """
        ...

    async def update_task(
        self,
        task_list_id: str,
        task_id: str,
        title: str | None = None,
        notes: str | None = None,
        due: str | None = None,
        status: str | None = None,
        *,
        clear_due: bool = False,
        details: TaskDetails | None = None,
        due_zone: str | None = None,
    ) -> dict:
        """``None`` keeps a field; ``clear_due`` removes the due date (never with ``due``)."""
        ...

    async def move_task(self, task_list_id: str, task_id: str, destination_list_id: str) -> dict:
        """The task where it is now; To Do gives its copy another id (``task_details``)."""
        ...

    async def complete_task(self, task_list_id: str, task_id: str) -> dict: ...

    async def delete_task(self, task_list_id: str, task_id: str) -> bool: ...
