"""
Draft Models.

Defines the data structures for deferred commands (drafts) that require
user confirmation before execution. Part of the HITL draft critique pattern.

Architecture:
- DraftType: Enum of supported draft types (EMAIL, EVENT, CONTACT, etc.)
- DraftStatus: Lifecycle states for drafts
- DraftInput: Generic input data for creating drafts
- DraftAction: User actions on drafts (confirm, edit, cancel)
- Draft: Full draft object with lifecycle methods

Flow:
    User Request → create_draft() → DRAFT RegistryItem
                                    ↓
                                  HITL (draft_critique)
                                    ↓
    User confirms → execute_draft() → Final Action (send email, etc.)
    User edits → update_draft() → Updated DRAFT → HITL
    User cancels → cancel_draft() → DRAFT removed

Best Practices:
- Drafts are immutable (use lifecycle methods to create new copies)
- All state transitions are explicit via status enum
- Full audit trail via timestamps
- Type-specific inputs for validation

Created: 2025-11-27
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import resolve_language


class DraftType(str, Enum):
    """
    Types of drafts that can be created.

    Each type corresponds to a specific action that can be deferred.
    Extensible for future integrations.
    """

    EMAIL = "email"  # Email draft (send_email)
    EMAIL_REPLY = "email_reply"  # Email reply draft (reply_email)
    EMAIL_FORWARD = "email_forward"  # Email forward draft (forward_email)
    EMAIL_DELETE = "email_delete"  # Email delete draft (delete_email)
    EVENT = "event"  # Calendar event draft (create_event)
    EVENT_UPDATE = "event_update"  # Calendar event update draft (update_event)
    EVENT_DELETE = "event_delete"  # Calendar event delete draft (delete_event)
    EVENT_ANSWER = "event_answer"  # An invitation's answer, told to its organiser (ADR-369)
    CONTACT = "contact"  # Contact creation draft (create_contact)
    CONTACT_UPDATE = "contact_update"  # Contact update draft (update_contact)
    CONTACT_DELETE = "contact_delete"  # Contact delete draft (delete_contact)
    TASK = "task"  # Task creation draft (create_task)
    TASK_UPDATE = "task_update"  # Task update draft (update_task)
    TASK_DELETE = "task_delete"  # Task delete draft (delete_task)
    FILE_SHARE = "file_share"  # A file's sharing, told to the person by the drive
    FILE_DELETE = "file_delete"  # Drive file delete draft (delete_file)
    LABEL_DELETE = "label_delete"  # Gmail label delete draft (delete_label)
    REMINDER_DELETE = "reminder_delete"  # Reminder delete draft (cancel_reminder)
    PHONE_CALL = "phone_call"  # Outbound agentic phone-call draft (place_phone_call)
    SCHEDULED_ACTION = "scheduled_action"  # Recurring automation draft (ADR-140)
    DEVOPS_TASK = "devops_task"  # Remote server task via Claude CLI (FN-1)
    PEER_MESSAGE = "peer_message"  # Relayed message to a connected user (peers, A3)
    VACATION_RESPONDER = "vacation_responder"  # Gmail auto-reply settings (lot I)
    EMAIL_FILTER = "email_filter"  # Gmail filter creation (lot I)
    EMAIL_FILTER_DELETE = "email_filter_delete"  # Gmail filter deletion (ADR-369)
    TOOL_CALL = "tool_call"  # A tool whose policy demands confirmation (ADR-263)
    SANDBOX_EGRESS = "sandbox_egress"  # A script asks to reach hosts (ADR-298)
    SPREADSHEET_WRITE = "spreadsheet_write"  # Sheets range update / row append (lot F)
    DOCUMENT_APPEND = "document_append"  # Docs text append (lot F)
    DOCUMENT_REPLACE = "document_replace"  # A plain text file rewritten whole (ADR-369)
    TICKET_DELETE = "ticket_delete"  # Workboard ticket delete draft (ADR-276)
    APPLICATION_ACTION = "application_action"  # Confirmed application command
    MAILBOX_DRAFT_SEND = "mailbox_draft_send"  # A draft of the person's mailbox, sent (ADR-344)


class DraftStatus(str, Enum):
    """
    Lifecycle states for drafts.

    State machine:
        PENDING → CONFIRMED → EXECUTED
        PENDING → CANCELLED
        PENDING → MODIFIED → PENDING (loop for edits)
        CONFIRMED → FAILED (execution error)
    """

    PENDING = "pending"  # Awaiting user confirmation
    MODIFIED = "modified"  # User edited, awaiting re-confirmation
    CONFIRMED = "confirmed"  # User confirmed, ready for execution
    EXECUTED = "executed"  # Action completed successfully
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # User cancelled


class DraftAction(str, Enum):
    """
    Actions a user can take on a draft.

    Used in HITL draft_critique interaction.
    """

    CONFIRM = "confirm"  # Execute the draft as-is
    CONFIRM_BATCH = "confirm_batch"  # Execute multiple drafts from FOR_EACH batch
    EDIT = "edit"  # Modify the draft (triggers re-presentation)
    CANCEL = "cancel"  # Discard the draft


class BaseDraftInput(BaseModel):
    """
    Base class for all draft inputs.

    Contains common fields shared across draft types.
    """

    # Optional reference to existing registry items
    # e.g., contact_id for "send email to this contact"
    related_registry_ids: list[str] = Field(
        default_factory=list,
        description="Registry IDs this draft relates to",
    )

    # User language for HITL questions
    user_language: str = Field(
        default_factory=resolve_language,
        description="Language for HITL questions (the declared one when not given)",
    )

    # User timezone for datetime formatting in HITL previews
    user_timezone: str = Field(
        default=DEFAULT_USER_DISPLAY_TIMEZONE,
        description="User's IANA timezone for datetime display",
    )


class _EmailWithFiles(BaseDraftInput):
    """What an e-mail carries beyond its words, as the card names it (``tools/email_files``)."""

    files: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The person's files it carries (id, filename, mime_type, size, origin)",
    )


class EmailDraftInput(_EmailWithFiles):
    """
    Input for creating an email draft.

    Maps to SendEmailInput but deferred for user confirmation.
    """

    to: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content")
    cc: str | None = Field(default=None, description="CC recipients")
    bcc: str | None = Field(default=None, description="BCC recipients")
    is_html: bool = Field(default=False, description="Whether body is HTML")


class EmailReplyDraftInput(_EmailWithFiles):
    """
    Input for creating an email reply draft.

    Maps to ReplyEmailInput but deferred for user confirmation.
    Maintains the same thread as the original message.
    """

    message_id: str = Field(..., description="Original message ID to reply to")
    to: str = Field(..., description="Who the reply reaches, as the card shows it")
    cc: str = Field(default="", description="Who a reply to all copies, as the card shows it")
    subject: str = Field(..., description="Email subject (with Re: prefix)")
    body: str = Field(..., description="Reply message body")
    reply_all: bool = Field(default=False, description="Reply to all recipients")
    original_subject: str = Field(default="", description="Original email subject")
    original_from: str = Field(default="", description="Original sender")
    thread_id: str | None = Field(default=None, description="Thread ID to maintain")
    already_answered: bool = Field(
        default=False,
        description="The mailbox says the person already answered the original (ADR-379)",
    )
    answered_at: str | None = Field(
        default=None,
        description="When they did (ISO 8601 with its offset), when the mailbox dates it",
    )


class EmailForwardDraftInput(_EmailWithFiles):
    """
    Input for creating an email forward draft.

    Maps to ForwardEmailInput but deferred for user confirmation.
    Creates a new thread with the forwarded message.
    """

    message_id: str = Field(..., description="Original message ID to forward")
    to: str = Field(..., description="Forward recipient email")
    subject: str = Field(..., description="Email subject (with Fwd: prefix)")
    body: str | None = Field(default=None, description="Additional message to prepend")
    cc: str | None = Field(default=None, description="CC recipients")
    original_subject: str = Field(default="", description="Original email subject")
    original_from: str = Field(default="", description="Original sender")
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Attachment info for preview (filename, mime_type, size)",
    )


class EmailDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting an email draft.

    Maps to DeleteEmailInput but deferred for user confirmation.
    Email is moved to trash (soft delete, recoverable for 30 days).
    """

    message_id: str = Field(..., description="Message ID to delete")
    subject: str = Field(
        default="",
        description=(
            "Email subject for confirmation display. Empty when the email has "
            "none — the localized '(no subject)' fallback is applied at render "
            "time (drafts/preview_renderer.py), never stored."
        ),
    )
    from_addr: str = Field(default="", description="Sender email for confirmation display")
    date: str = Field(default="", description="Email date for confirmation display")
    thread_id: str | None = Field(default=None, description="Thread ID")

    def to_delete_email_args(self) -> dict[str, Any]:
        """Convert to args for trash_email execution."""
        return {
            "message_id": self.message_id,
        }


class EventOptionFields(BaseModel):
    """What an event is asked to say beyond its time; None keeps what it has (ADR-369)."""

    reminder_minutes: int | None = Field(
        default=None, description="Minutes before it starts; the client's NO_REMINDER for none"
    )
    busy: bool | None = Field(default=None, description="Whether its time shows as taken")
    recurrence: dict[str, Any] | None = Field(
        default=None, description="A new series' rule, as plain data"
    )
    recurrence_text: str | None = Field(
        default=None, description="The rule's sentence, in the person's language"
    )
    scope: str | None = Field(default=None, description="'series' reaches the whole series")
    moves_series: bool = Field(default=False, description="A whole series takes a new time")
    private: bool | None = Field(default=None, description="Whether its details are kept back")


class EventDraftInput(EventOptionFields, BaseDraftInput):
    """
    Input for creating a calendar event draft.

    Carries create_event_tool's arguments, deferred for user confirmation.
    """

    summary: str = Field(..., description="Event title")
    start_datetime: str = Field(..., description="Start datetime (ISO format)")
    end_datetime: str = Field(..., description="End datetime (ISO format)")
    description: str | None = Field(default=None, description="Event description")
    location: str | None = Field(default=None, description="Event location")
    attendees: list[str] = Field(default_factory=list, description="Attendee emails")
    timezone: str = Field(default=DEFAULT_USER_DISPLAY_TIMEZONE, description="Timezone")
    calendar_id: str | None = Field(
        default=None,
        description="Calendar ID to create event in. If None, uses user's default calendar preference.",
    )
    add_conference: bool = Field(
        default=False,
        description="Attach a video-conference link (Meet/Teams) at creation",
    )
    all_day: bool = Field(
        default=False,
        description="All-day event: the bounds are dates, the end exclusive (ADR-369)",
    )

    def to_create_event_args(self) -> dict[str, Any]:
        """Convert to args for create_event_tool."""
        return {
            "summary": self.summary,
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
            "description": self.description,
            "location": self.location,
            "attendees": self.attendees,
            "timezone": self.timezone,
            "calendar_id": self.calendar_id,
            "add_conference": self.add_conference,
            "all_day": self.all_day,
            "reminder_minutes": self.reminder_minutes,
            "busy": self.busy,
            "private": self.private,
        }


class EventUpdateDraftInput(EventOptionFields, BaseDraftInput):
    """
    Input for updating a calendar event draft.

    Carries update_event_tool's arguments, deferred for user confirmation.
    """

    event_id: str = Field(..., description="Event ID to update")
    summary: str | None = Field(default=None, description="New event title")
    start_datetime: str | None = Field(default=None, description="New start datetime (ISO format)")
    end_datetime: str | None = Field(default=None, description="New end datetime (ISO format)")
    description: str | None = Field(default=None, description="New event description")
    location: str | None = Field(default=None, description="New event location")
    attendees: list[str] | None = Field(default=None, description="New attendee emails")
    timezone: str = Field(default=DEFAULT_USER_DISPLAY_TIMEZONE, description="Timezone")
    calendar_id: str | None = Field(
        default=None,
        description="Calendar ID where the event is located. If None, uses user's default calendar preference.",
    )
    current_event: dict[str, Any] = Field(
        default_factory=dict,
        description="Current event data for comparison display",
    )
    all_day: bool | None = Field(
        default=None,
        description="True/False switches the event all-day/timed; None keeps its shape (ADR-369)",
    )
    add_conference: bool = Field(
        default=False, description="Add a video-call link to the event (ADR-369)"
    )

    def to_update_event_args(self) -> dict[str, Any]:
        """Convert to args for update_event execution."""
        return {
            "event_id": self.event_id,
            "summary": self.summary,
            "start_datetime": self.start_datetime,
            "end_datetime": self.end_datetime,
            "description": self.description,
            "location": self.location,
            "attendees": self.attendees,
            "timezone": self.timezone,
            "calendar_id": self.calendar_id,
            "all_day": self.all_day,
            "add_conference": self.add_conference,
            "reminder_minutes": self.reminder_minutes,
            "busy": self.busy,
            "private": self.private,
        }


class EventAnswerDraftInput(BaseDraftInput):
    """An invitation's answer, deferred for the person's confirmation: it leaves for someone."""

    event_id: str = Field(..., description="The event, an occurrence's own id within a series")
    response: str = Field(..., description="accepted, declined or tentative")
    summary: str | None = Field(default=None, description="Event title, as shown on the card")
    start_datetime: str | None = Field(default=None, description="Its start, as shown")
    organizer: str | None = Field(default=None, description="Who is told")
    calendar_id: str | None = Field(default=None, description="Its calendar")


class FileShareDraftInput(BaseDraftInput):
    """A file's sharing, deferred for the person's confirmation: the drive tells someone."""

    file_id: str = Field(..., description="The item")
    email: str = Field(..., description="Who it is shared with")
    role: str = Field(..., description="reader or writer")
    name: str | None = Field(default=None, description="Its name, as shown on the card")


class EventDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a calendar event draft.

    Carries delete_event_tool's arguments, deferred for user confirmation.
    Homogenized with EventUpdateDraftInput to enable draft type changes
    (e.g., user says "no, move it to May 23" on a delete HITL).
    """

    scope: str | None = Field(default=None, description="'series' reaches the whole series")

    event_id: str = Field(..., description="Event ID to delete")
    summary: str | None = Field(default=None, description="Event title")
    start_datetime: str | None = Field(default=None, description="Start datetime (ISO format)")
    end_datetime: str | None = Field(default=None, description="End datetime (ISO format)")
    description: str | None = Field(default=None, description="Event description")
    location: str | None = Field(default=None, description="Event location")
    attendees: list[str] | None = Field(default=None, description="Attendee emails")
    timezone: str = Field(default=DEFAULT_USER_DISPLAY_TIMEZONE, description="Timezone")
    calendar_id: str | None = Field(
        default=None,
        description="Calendar ID where the event is located. If None, uses user's default calendar preference.",
    )
    current_event: dict[str, Any] = Field(
        default_factory=dict,
        description="Current event data for confirmation display and type change",
    )
    send_updates: str = Field(
        default="all",
        description="How to notify attendees: all, externalOnly, none",
    )

    def to_delete_event_args(self) -> dict[str, Any]:
        """Convert to args for delete_event execution."""
        return {
            "event_id": self.event_id,
            "send_updates": self.send_updates,
            "calendar_id": self.calendar_id,
        }


class _ContactDetailInput(BaseDraftInput):
    """What a contact draft carries beyond a name, a company and notes (ADR-369, lot 9)."""

    given_name: str | None = Field(default=None, description="Given name")
    family_name: str | None = Field(default=None, description="Family name")
    job_title: str | None = Field(default=None, description="Job title")
    website: str | None = Field(default=None, description="Website")
    birthday: str | None = Field(default=None, description="Birthday, an ISO day")


class ContactDraftInput(_ContactDetailInput):
    """
    Input for creating a contact draft.

    Maps to CreateContactInput but deferred for user confirmation.
    """

    name: str = Field(..., description="Contact full name")
    email: str | None = Field(default=None, description="Contact email")
    phone: str | None = Field(default=None, description="Contact phone")
    organization: str | None = Field(default=None, description="Company name")
    notes: str | None = Field(default=None, description="Additional notes")


class ContactUpdateDraftInput(_ContactDetailInput):
    """
    Input for updating a contact draft.

    Maps to UpdateContactInput but deferred for user confirmation.
    """

    resource_name: str = Field(..., description="Contact resource name (people/c...)")
    name: str | None = Field(default=None, description="New contact name")
    email: str | None = Field(default=None, description="New contact email")
    phone: str | None = Field(default=None, description="New contact phone")
    organization: str | None = Field(default=None, description="New company name")
    notes: str | None = Field(default=None, description="New notes")
    address: str | None = Field(
        default=None, description="New address (e.g. '15 rue de la Paix, Paris 75001')"
    )
    clear_birthday: bool = Field(default=False, description="Take the birthday off")
    current_contact: dict[str, Any] = Field(
        default_factory=dict,
        description="Current contact data for comparison display",
    )


class ReminderDeleteDraftInput(BaseDraftInput):
    """Input for deleting a reminder draft.

    Deferred for user confirmation before actual cancellation.
    """

    reminder_id: str = Field(..., description="Reminder UUID to cancel")
    content: str = Field(default="", description="Reminder content for confirmation display")
    trigger_at: str = Field(default="", description="Trigger datetime for confirmation display")


class PhoneCallDraftInput(BaseDraftInput):
    """Input for an outbound agentic phone-call draft.

    Deferred for user confirmation before LIA actually places the call. The
    callee's number is already resolved at this point (never re-resolved at
    execution). ``date_window`` is the availability window the user stated
    (e.g. "2026-09-15 full day"). No code acts on it: the pre-fetch window is
    computed from settings alone (``telephony/service.py``), the call ignores
    it, and the confirmation card does not show it — only the model writing
    the confirmation question sees it among the draft's fields.
    """

    callee_name: str = Field(..., description="Display name of the person to call")
    callee_phone: str = Field(..., description="Resolved E.164 phone number of the callee")
    objective: str = Field(..., description="What LIA must accomplish on the call")
    date_window: str | None = Field(
        default=None,
        description=(
            "Optional availability window the user stated (e.g. '2026-09-15 full day'); "
            "no code acts on it: neither the availability pre-fetch nor the call reads it."
        ),
    )


class ContactDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a contact draft.

    Maps to DeleteContactInput but deferred for user confirmation.
    Homogenized with ContactUpdateDraftInput to enable draft type changes.
    """

    resource_name: str = Field(..., description="Contact resource name (people/c...)")
    name: str | None = Field(default=None, description="Contact name")
    email: str | None = Field(default=None, description="Contact email")
    phone: str | None = Field(default=None, description="Contact phone")
    organization: str | None = Field(default=None, description="Company name")
    notes: str | None = Field(default=None, description="Notes")
    address: str | None = Field(default=None, description="Address")
    current_contact: dict[str, Any] = Field(
        default_factory=dict,
        description="Current contact data for confirmation display and type change",
    )

    def to_delete_contact_args(self) -> dict[str, Any]:
        """Convert to args for delete_contact execution."""
        return {
            "resource_name": self.resource_name,
        }


class TaskDraftInput(BaseDraftInput):
    """
    Input for creating a task draft.

    Maps to CreateTaskInput but deferred for user confirmation.
    """

    title: str = Field(..., description="Task title")
    notes: str | None = Field(default=None, description="Task notes/description")
    due: str | None = Field(default=None, description="Due date (RFC 3339 format)")
    task_list_id: str = Field(default="@default", description="Task list ID")
    task_list_name: str | None = Field(
        default=None, description="The name of that list, which the card shows"
    )
    importance: str | None = Field(default=None, description="How much it matters (To Do)")
    reminder: str | None = Field(default=None, description="When it reminds (To Do)")
    repeat: str | None = Field(default=None, description="How it repeats (To Do)")
    steps: list[str] = Field(default_factory=list, description="Its first steps (To Do)")

    def to_create_task_args(self) -> dict[str, Any]:
        """Convert to args for create_task_tool."""
        return {
            "title": self.title,
            "notes": self.notes,
            "due": self.due,
            "task_list_id": self.task_list_id,
        }


class TaskUpdateDraftInput(BaseDraftInput):
    """
    Input for updating a task draft.

    Maps to UpdateTaskInput but deferred for user confirmation.
    """

    task_id: str = Field(..., description="Task ID to update")
    title: str | None = Field(default=None, description="New task title")
    notes: str | None = Field(default=None, description="New task notes")
    due: str | None = Field(default=None, description="New due date (RFC 3339 format)")
    status: str | None = Field(default=None, description="New status: needsAction or completed")
    task_list_id: str = Field(default="@default", description="Task list ID")
    current_task: dict[str, Any] = Field(
        default_factory=dict,
        description="Current task data for comparison display",
    )
    importance: str | None = Field(default=None, description="How much it matters (To Do)")
    reminder: str | None = Field(default=None, description="When it reminds (To Do)")
    repeat: str | None = Field(default=None, description="How it repeats (To Do)")
    clear_reminder: bool = Field(default=False, description="Remove the reminder (To Do)")
    clear_repeat: bool = Field(default=False, description="Remove the repetition (To Do)")
    clear_due: bool = Field(default=False, description="Remove the due date (never with a new one)")

    def to_update_task_args(self) -> dict[str, Any]:
        """Convert to args for update_task execution."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "notes": self.notes,
            "due": self.due,
            "status": self.status,
            "task_list_id": self.task_list_id,
            "clear_due": self.clear_due,
        }


class TaskDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a task draft.

    Maps to DeleteTaskInput but deferred for user confirmation.
    Homogenized with TaskUpdateDraftInput to enable draft type changes.
    """

    task_id: str = Field(..., description="Task ID to delete")
    title: str | None = Field(default=None, description="Task title")
    notes: str | None = Field(default=None, description="Task notes")
    due: str | None = Field(default=None, description="Due date (RFC 3339)")
    status: str | None = Field(default=None, description="Status: needsAction or completed")
    task_list_id: str = Field(default="@default", description="Task list ID")
    current_task: dict[str, Any] = Field(
        default_factory=dict,
        description="Current task data for confirmation display and type change",
    )

    def to_delete_task_args(self) -> dict[str, Any]:
        """Convert to args for delete_task execution."""
        return {
            "task_id": self.task_id,
            "task_list_id": self.task_list_id,
        }


class FileDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a Drive file draft.

    Maps to DeleteFileInput but deferred for user confirmation.
    """

    file_id: str = Field(..., description="Drive file ID to delete")
    file: dict[str, Any] = Field(
        default_factory=dict,
        description="File data for confirmation display",
    )

    def to_delete_file_args(self) -> dict[str, Any]:
        """Convert to args for delete_file execution."""
        return {
            "file_id": self.file_id,
        }


class LabelDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a Gmail label draft.

    Maps to delete_label but deferred for user confirmation.
    When the label has sublabels, they are included for informational display.
    """

    label_id: str = Field(..., description="Gmail label ID to delete")
    label_name: str = Field(..., description="Full label path (e.g., pro/capge/2024)")
    sublabels: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of sublabels that will also be deleted",
    )
    children_only: bool = Field(
        default=False,
        description="If True, only delete sublabels, keep parent",
    )

    def to_delete_label_args(self) -> dict[str, Any]:
        """Convert to args for delete_label execution."""
        return {
            "label_id": self.label_id,
            "children_only": self.children_only,
        }


# Type alias for any draft input
DraftInput = (
    EmailDraftInput
    | EmailReplyDraftInput
    | EmailForwardDraftInput
    | EmailDeleteDraftInput
    | EventDraftInput
    | EventUpdateDraftInput
    | EventDeleteDraftInput
    | EventAnswerDraftInput
    | ContactDraftInput
    | ContactUpdateDraftInput
    | ContactDeleteDraftInput
    | TaskDraftInput
    | TaskUpdateDraftInput
    | TaskDeleteDraftInput
    | FileDeleteDraftInput
    | LabelDeleteDraftInput
)


class Draft(BaseModel):
    """
    A draft command awaiting user confirmation.

    This is the full draft object stored in the registry.
    Contains both the input data and lifecycle metadata.

    Lifecycle methods return new copies (immutable pattern).
    """

    id: str = Field(
        default_factory=lambda: f"draft_{uuid4().hex[:12]}",
        description="Unique draft ID",
    )
    type: DraftType = Field(..., description="Type of draft")
    status: DraftStatus = Field(
        default=DraftStatus.PENDING,
        description="Current lifecycle status",
    )
    content: dict[str, Any] = Field(
        ...,
        description="Draft content (type-specific data)",
    )
    related_registry_ids: list[str] = Field(
        default_factory=list,
        description="Related registry items",
    )

    # Lifecycle timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When draft was created",
    )
    modified_at: datetime | None = Field(
        default=None,
        description="When draft was last modified",
    )
    executed_at: datetime | None = Field(
        default=None,
        description="When draft was executed",
    )

    # Execution result (after confirm)
    execution_result: dict[str, Any] | None = Field(
        default=None,
        description="Result of executing the draft",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message if execution failed",
    )

    # Source tracking for tracing
    source_tool: str | None = Field(
        default=None,
        description="Tool that created this draft",
    )
    source_step_id: str | None = Field(
        default=None,
        description="Execution step that created this draft",
    )

    model_config = {}  # datetime serializes to ISO format by default in Pydantic v2

    def mark_modified(self, new_content: dict[str, Any]) -> Draft:
        """Create a copy with updated content and MODIFIED status."""
        from src.core.card_composition import preserve_composition_binding

        return self.model_copy(
            update={
                "content": preserve_composition_binding(self.content, new_content),
                "status": DraftStatus.MODIFIED,
                "modified_at": datetime.now(UTC),
            }
        )

    def mark_confirmed(self) -> Draft:
        """Create a copy with CONFIRMED status."""
        return self.model_copy(
            update={
                "status": DraftStatus.CONFIRMED,
            }
        )

    def mark_executed(self, result: dict[str, Any]) -> Draft:
        """Create a copy with EXECUTED status and result."""
        return self.model_copy(
            update={
                "status": DraftStatus.EXECUTED,
                "executed_at": datetime.now(UTC),
                "execution_result": result,
            }
        )

    def mark_failed(self, error: str) -> Draft:
        """Create a copy with FAILED status and error."""
        return self.model_copy(
            update={
                "status": DraftStatus.FAILED,
                "error_message": error,
            }
        )

    def mark_cancelled(self) -> Draft:
        """Create a copy with CANCELLED status."""
        return self.model_copy(
            update={
                "status": DraftStatus.CANCELLED,
            }
        )

    def get_summary(
        self,
        user_language: str | None = None,
        user_timezone: str | None = None,
    ) -> str:
        """Get the one-line summary naming what this draft would do.

        Used in HITL questions and LLM summaries, in the 6 supported languages.
        Delegates to :func:`~src.domains.agents.drafts.summary_renderer.render_summary`,
        where every draft type has a registered renderer and a boot-time
        completeness assert — the cascade this replaced ended in an untranslated
        ``Draft (<value>)`` that 9 of the 26 types actually reached.

        Args:
            user_language: The reader's language; the declared one when absent
                (ADR-323).
            user_timezone: IANA timezone for datetime formatting (defaults to
                ``content.user_timezone``).

        Returns:
            The localized sentence.
        """
        from src.domains.agents.drafts.summary_renderer import render_summary

        return render_summary(self, resolve_language(user_language), user_timezone)

    def get_detailed_preview(
        self,
        user_language: str | None = None,
        user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
    ) -> str:
        """
        Get a detailed preview of the draft for user confirmation.

        Shows full email content (to, cc, subject, body) for verification.
        Used in HITL confirmation flow before execution. Rendering is
        delegated to the per-type dispatch table in
        ``drafts/preview_renderer.py`` (extracted 2026-07, audit cycle 3).

        Args:
            user_language: The labels' language; the declared one when absent
                (ADR-323).
            user_timezone: User's IANA timezone for datetime formatting

        Returns:
            Detailed multi-line preview string with all relevant fields.
        """
        # Local import: preview_renderer imports DraftType from this module.
        from src.domains.agents.drafts.preview_renderer import render_detailed_preview

        return render_detailed_preview(self, resolve_language(user_language), user_timezone)
