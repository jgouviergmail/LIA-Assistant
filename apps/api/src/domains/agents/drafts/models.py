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

from src.core.i18n_drafts import get_draft_preview_labels, get_draft_summary_label


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
    CONTACT = "contact"  # Contact creation draft (create_contact)
    CONTACT_UPDATE = "contact_update"  # Contact update draft (update_contact)
    CONTACT_DELETE = "contact_delete"  # Contact delete draft (delete_contact)
    TASK = "task"  # Task creation draft (create_task)
    TASK_UPDATE = "task_update"  # Task update draft (update_task)
    TASK_DELETE = "task_delete"  # Task delete draft (delete_task)
    FILE_DELETE = "file_delete"  # Drive file delete draft (delete_file)
    LABEL_DELETE = "label_delete"  # Gmail label delete draft (delete_label)


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
        default="fr",
        description="Language for HITL questions",
    )

    # User timezone for datetime formatting in HITL previews
    user_timezone: str = Field(
        default="Europe/Paris",
        description="User's IANA timezone for datetime display",
    )


class EmailDraftInput(BaseDraftInput):
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

    def to_send_email_args(self) -> dict[str, Any]:
        """Convert to args for send_email_tool."""
        return {
            "to": self.to,
            "subject": self.subject,
            "body": self.body,
            "cc": self.cc,
            "bcc": self.bcc,
            "is_html": self.is_html,
        }


class EmailReplyDraftInput(BaseDraftInput):
    """
    Input for creating an email reply draft.

    Maps to ReplyEmailInput but deferred for user confirmation.
    Maintains the same thread as the original message.
    """

    message_id: str = Field(..., description="Original message ID to reply to")
    to: str = Field(..., description="Recipient email (original sender)")
    subject: str = Field(..., description="Email subject (with Re: prefix)")
    body: str = Field(..., description="Reply message body")
    reply_all: bool = Field(default=False, description="Reply to all recipients")
    original_subject: str = Field(default="", description="Original email subject")
    original_from: str = Field(default="", description="Original sender")
    thread_id: str | None = Field(default=None, description="Thread ID to maintain")

    def to_reply_email_args(self) -> dict[str, Any]:
        """Convert to args for reply_email execution."""
        return {
            "message_id": self.message_id,
            "body": self.body,
            "reply_all": self.reply_all,
            "to": self.to,
        }


class EmailForwardDraftInput(BaseDraftInput):
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

    def to_forward_email_args(self) -> dict[str, Any]:
        """Convert to args for forward_email execution."""
        return {
            "message_id": self.message_id,
            "to": self.to,
            "body": self.body,
            "cc": self.cc,
        }


class EmailDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting an email draft.

    Maps to DeleteEmailInput but deferred for user confirmation.
    Email is moved to trash (soft delete, recoverable for 30 days).
    """

    message_id: str = Field(..., description="Message ID to delete")
    subject: str = Field(
        default="(sans objet)", description="Email subject for confirmation display"
    )
    from_addr: str = Field(default="", description="Sender email for confirmation display")
    date: str = Field(default="", description="Email date for confirmation display")
    thread_id: str | None = Field(default=None, description="Thread ID")

    def to_delete_email_args(self) -> dict[str, Any]:
        """Convert to args for trash_email execution."""
        return {
            "message_id": self.message_id,
        }


class EventDraftInput(BaseDraftInput):
    """
    Input for creating a calendar event draft.

    Maps to CreateEventInput but deferred for user confirmation.
    """

    summary: str = Field(..., description="Event title")
    start_datetime: str = Field(..., description="Start datetime (ISO format)")
    end_datetime: str = Field(..., description="End datetime (ISO format)")
    description: str | None = Field(default=None, description="Event description")
    location: str | None = Field(default=None, description="Event location")
    attendees: list[str] = Field(default_factory=list, description="Attendee emails")
    timezone: str = Field(default="Europe/Paris", description="Timezone")
    calendar_id: str | None = Field(
        default=None,
        description="Calendar ID to create event in. If None, uses user's default calendar preference.",
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
        }


class EventUpdateDraftInput(BaseDraftInput):
    """
    Input for updating a calendar event draft.

    Maps to UpdateEventInput but deferred for user confirmation.
    """

    event_id: str = Field(..., description="Event ID to update")
    summary: str | None = Field(default=None, description="New event title")
    start_datetime: str | None = Field(default=None, description="New start datetime (ISO format)")
    end_datetime: str | None = Field(default=None, description="New end datetime (ISO format)")
    description: str | None = Field(default=None, description="New event description")
    location: str | None = Field(default=None, description="New event location")
    attendees: list[str] | None = Field(default=None, description="New attendee emails")
    timezone: str = Field(default="Europe/Paris", description="Timezone")
    calendar_id: str | None = Field(
        default=None,
        description="Calendar ID where the event is located. If None, uses user's default calendar preference.",
    )
    current_event: dict[str, Any] = Field(
        default_factory=dict,
        description="Current event data for comparison display",
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
        }


class EventDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a calendar event draft.

    Maps to DeleteEventInput but deferred for user confirmation.
    """

    event_id: str = Field(..., description="Event ID to delete")
    event: dict[str, Any] = Field(
        default_factory=dict,
        description="Event data for confirmation display",
    )
    send_updates: str = Field(
        default="all",
        description="How to notify attendees: all, externalOnly, none",
    )
    calendar_id: str | None = Field(
        default=None,
        description="Calendar ID where the event is located. If None, uses user's default calendar preference.",
    )

    def to_delete_event_args(self) -> dict[str, Any]:
        """Convert to args for delete_event execution."""
        return {
            "event_id": self.event_id,
            "send_updates": self.send_updates,
            "calendar_id": self.calendar_id,
        }


class ContactDraftInput(BaseDraftInput):
    """
    Input for creating a contact draft.

    Maps to CreateContactInput but deferred for user confirmation.
    """

    name: str = Field(..., description="Contact full name")
    email: str | None = Field(default=None, description="Contact email")
    phone: str | None = Field(default=None, description="Contact phone")
    organization: str | None = Field(default=None, description="Company name")
    notes: str | None = Field(default=None, description="Additional notes")

    def to_create_contact_args(self) -> dict[str, Any]:
        """Convert to args for create_contact_tool."""
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "organization": self.organization,
            "notes": self.notes,
        }


class ContactUpdateDraftInput(BaseDraftInput):
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
    current_contact: dict[str, Any] = Field(
        default_factory=dict,
        description="Current contact data for comparison display",
    )

    def to_update_contact_args(self) -> dict[str, Any]:
        """Convert to args for update_contact execution."""
        return {
            "resource_name": self.resource_name,
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "organization": self.organization,
            "notes": self.notes,
            "address": self.address,
        }


class ContactDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a contact draft.

    Maps to DeleteContactInput but deferred for user confirmation.
    """

    resource_name: str = Field(..., description="Contact resource name (people/c...)")
    contact: dict[str, Any] = Field(
        default_factory=dict,
        description="Contact data for confirmation display",
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

    def to_update_task_args(self) -> dict[str, Any]:
        """Convert to args for update_task execution."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "notes": self.notes,
            "due": self.due,
            "status": self.status,
            "task_list_id": self.task_list_id,
        }


class TaskDeleteDraftInput(BaseDraftInput):
    """
    Input for deleting a task draft.

    Maps to DeleteTaskInput but deferred for user confirmation.
    """

    task_id: str = Field(..., description="Task ID to delete")
    title: str | None = Field(default=None, description="Task title for display")
    task_list_id: str = Field(default="@default", description="Task list ID")

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

    def mark_modified(self, new_content: dict[str, Any]) -> "Draft":
        """Create a copy with updated content and MODIFIED status."""
        return self.model_copy(
            update={
                "content": new_content,
                "status": DraftStatus.MODIFIED,
                "modified_at": datetime.now(UTC),
            }
        )

    def mark_confirmed(self) -> "Draft":
        """Create a copy with CONFIRMED status."""
        return self.model_copy(
            update={
                "status": DraftStatus.CONFIRMED,
            }
        )

    def mark_executed(self, result: dict[str, Any]) -> "Draft":
        """Create a copy with EXECUTED status and result."""
        return self.model_copy(
            update={
                "status": DraftStatus.EXECUTED,
                "executed_at": datetime.now(UTC),
                "execution_result": result,
            }
        )

    def mark_failed(self, error: str) -> "Draft":
        """Create a copy with FAILED status and error."""
        return self.model_copy(
            update={
                "status": DraftStatus.FAILED,
                "error_message": error,
            }
        )

    def mark_cancelled(self) -> "Draft":
        """Create a copy with CANCELLED status."""
        return self.model_copy(
            update={
                "status": DraftStatus.CANCELLED,
            }
        )

    def get_summary(
        self,
        user_language: str = "fr",
        user_timezone: str | None = None,
    ) -> str:
        """
        Get a human-readable summary of the draft.

        Used in HITL questions and LLM summaries.
        Supports multilingual output via centralized i18n.

        Supported languages: fr, en, es, de, it, zh-CN

        Args:
            user_language: Language code for i18n
            user_timezone: IANA timezone for datetime formatting (defaults to content.user_timezone)
        """
        from src.core.time_utils import format_datetime_for_display

        # Use provided timezone or fallback to content.user_timezone
        tz = user_timezone or self.content.get("user_timezone", "Europe/Paris")

        def format_dt(dt_str: str | None) -> str:
            """Format an ISO datetime string for display."""
            if not dt_str:
                return ""
            return format_datetime_for_display(dt_str, tz, user_language, include_time=True)

        if self.type == DraftType.EMAIL:
            return "<br/>" + get_draft_summary_label(
                "email_to",
                user_language,
                to=self.content.get("to", "?"),
                subject=self.content.get("subject", "?"),
            )

        elif self.type == DraftType.EMAIL_REPLY:
            return "<br/>" + get_draft_summary_label(
                "email_reply_to",
                user_language,
                to=self.content.get("to", "?"),
                subject=self.content.get("subject", "?"),
            )

        elif self.type == DraftType.EMAIL_FORWARD:
            return "<br/>" + get_draft_summary_label(
                "email_forward_to",
                user_language,
                to=self.content.get("to", "?"),
                subject=self.content.get("subject", "?"),
            )

        elif self.type == DraftType.EMAIL_DELETE:
            return "<br/>" + get_draft_summary_label(
                "email_delete",
                user_language,
                subject=self.content.get("subject", "?"),
            )

        elif self.type == DraftType.EVENT:
            start_raw = self.content.get("start_datetime", "")
            start = format_dt(start_raw) if start_raw else "?"
            return "<br/>" + get_draft_summary_label(
                "event_create",
                user_language,
                summary=self.content.get("summary", "?"),
                start=start,
            )

        elif self.type == DraftType.EVENT_UPDATE:
            summary = self.content.get("summary")
            if not summary:
                summary = self.content.get("current_event", {}).get("summary", "?")
            return "<br/>" + get_draft_summary_label(
                "event_update",
                user_language,
                summary=summary,
            )

        elif self.type == DraftType.EVENT_DELETE:
            event = self.content.get("event", {})
            return "<br/>" + get_draft_summary_label(
                "event_delete",
                user_language,
                summary=event.get("summary", "?"),
            )

        elif self.type == DraftType.CONTACT:
            return "<br/>" + get_draft_summary_label(
                "contact_create",
                user_language,
                name=self.content.get("name", "?"),
            )

        elif self.type == DraftType.CONTACT_UPDATE:
            name = self.content.get("name")
            if not name:
                names = self.content.get("current_contact", {}).get("names", [])
                name = names[0].get("displayName", "?") if names else "?"
            return "<br/>" + get_draft_summary_label(
                "contact_update",
                user_language,
                name=name,
            )

        elif self.type == DraftType.CONTACT_DELETE:
            names = self.content.get("contact", {}).get("names", [])
            name = names[0].get("displayName", "?") if names else "?"
            return "<br/>" + get_draft_summary_label(
                "contact_delete",
                user_language,
                name=name,
            )

        elif self.type == DraftType.TASK:
            return "<br/>" + get_draft_summary_label(
                "task_create",
                user_language,
                title=self.content.get("title", "?"),
            )

        elif self.type == DraftType.TASK_UPDATE:
            title = self.content.get("title")
            if not title:
                title = self.content.get("current_task", {}).get("title", "?")
            return "<br/>" + get_draft_summary_label(
                "task_update",
                user_language,
                title=title,
            )

        elif self.type == DraftType.TASK_DELETE:
            return "<br/>" + get_draft_summary_label(
                "task_delete",
                user_language,
                title=self.content.get("title", "?"),
            )

        elif self.type == DraftType.FILE_DELETE:
            file_data = self.content.get("file", {})
            return "<br/>" + get_draft_summary_label(
                "file_delete",
                user_language,
                name=file_data.get("name", "?"),
            )

        elif self.type == DraftType.LABEL_DELETE:
            return "<br/>" + get_draft_summary_label(
                "label_delete",
                user_language,
                name=self.content.get("label_name", "?"),
            )

        return f"Draft ({self.type.value})"

    def get_detailed_preview(
        self,
        user_language: str = "fr",
        user_timezone: str = "Europe/Paris",
    ) -> str:
        """
        Get a detailed preview of the draft for user confirmation.

        Shows full email content (to, cc, subject, body) for verification.
        Used in HITL confirmation flow before execution.

        Args:
            user_language: Language for labels (fr, en, es, de, it, zh-CN)
            user_timezone: User's IANA timezone for datetime formatting

        Returns:
            Detailed multi-line preview string with all relevant fields.
        """
        from src.core.time_utils import format_datetime_for_display

        def format_dt(dt_str: str | None) -> str:
            """Format an ISO datetime string for display."""
            if not dt_str:
                return ""
            return format_datetime_for_display(
                dt_str, user_timezone, user_language, include_time=True
            )

        lines: list[str] = []

        # Get localized labels from centralized i18n
        lbl = get_draft_preview_labels(user_language)

        # Email drafts (send, reply, forward)
        if self.type in (DraftType.EMAIL, DraftType.EMAIL_REPLY, DraftType.EMAIL_FORWARD):
            to = self.content.get("to", "")
            cc = self.content.get("cc", "")
            bcc = self.content.get("bcc", "")
            subject = self.content.get("subject", "")
            body = self.content.get("body", "")

            lines.append(f"<br/>**{lbl['to']}**: {to}")
            if cc:
                lines.append(f"<br/>**{lbl['cc']}**: {cc}")
            if bcc:
                lines.append(f"<br/>**{lbl['bcc']}**: {bcc}")
            lines.append(f"<br/>**{lbl['subject']}**: {subject}")
            lines.append(f"<br/>**{lbl['body']}**:<br/>{body}")

            # For forwards, mention attachments if present
            if self.type == DraftType.EMAIL_FORWARD:
                attachments = self.content.get("attachments", [])
                if attachments:
                    att_names = [a.get("filename", a.get("name", "?")) for a in attachments]
                    lines.append(f"<br/>**{lbl['attachments']}**: {', '.join(att_names)}")

        # Email delete
        elif self.type == DraftType.EMAIL_DELETE:
            subject = self.content.get("subject", "(sans objet)")
            from_addr = self.content.get("from", self.content.get("from_addr", "?"))
            date_raw = self.content.get("date", "")
            date = format_dt(date_raw) if date_raw else ""

            lines.append(f"<br/>**{lbl['from']}**: {from_addr}")
            lines.append(f"<br/>**{lbl['subject']}**: {subject}")
            if date:
                lines.append(f"<br/>**{lbl['date']}**: {date}")

        # Event creation
        elif self.type == DraftType.EVENT:
            summary = self.content.get("summary", "")
            start = format_dt(self.content.get("start_datetime", ""))
            end = format_dt(self.content.get("end_datetime", ""))
            location = self.content.get("location", "")
            description = self.content.get("description", "")
            attendees = self.content.get("attendees", [])

            lines.append(f"<br/>**{lbl['event']}**: {summary}")
            lines.append(f"<br/>**{lbl['start']}**: {start}")
            lines.append(f"<br/>**{lbl['end']}**: {end}")
            if location:
                lines.append(f"<br/>**{lbl['location']}**: {location}")
            if attendees:
                lines.append(f"<br/>**{lbl['attendees']}**: {', '.join(attendees)}")
            if description:
                lines.append(f"<br/>**{lbl['body']}**<br/>{description}")

        # Event update
        elif self.type == DraftType.EVENT_UPDATE:
            current = self.content.get("current_event", {})
            summary = self.content.get("summary") or current.get("summary", "?")
            changes = []

            if self.content.get("summary"):
                changes.append(f"<br/>{lbl['event']}: {self.content['summary']}")
            if self.content.get("start_datetime"):
                changes.append(f"<br/>{lbl['start']}: {format_dt(self.content['start_datetime'])}")
            if self.content.get("end_datetime"):
                changes.append(f"<br/>{lbl['end']}: {format_dt(self.content['end_datetime'])}")
            if self.content.get("location"):
                changes.append(f"<br/>{lbl['location']}: {self.content['location']}")
            if self.content.get("attendees"):
                changes.append(f"<br/>{lbl['attendees']}: {', '.join(self.content['attendees'])}")

            lines.append(f"<br/>**{lbl['event']}**: {summary}")
            if changes:
                lines.append(f"<br/>**{lbl['changes']}**:")
                for change in changes:
                    lines.append(f"<br/>  - {change}")

        # Event delete
        elif self.type == DraftType.EVENT_DELETE:
            event = self.content.get("event", {})
            summary = event.get("summary", "?")
            start_raw = event.get("start", {}).get(
                "dateTime", event.get("start", {}).get("date", "")
            )
            start = format_dt(start_raw) if start_raw else ""

            lines.append(f"<br/>**{lbl['event']}**: {summary}")
            if start:
                lines.append(f"<br/>**{lbl['date']}**: {start}")

        # Contact creation
        elif self.type == DraftType.CONTACT:
            name = self.content.get("name", "")
            email = self.content.get("email", "")
            phone = self.content.get("phone", "")
            organization = self.content.get("organization", "")

            lines.append(f"<br/>**{lbl['contact']}**: {name}")
            if email:
                lines.append(f"<br/>**{lbl['email']}**: {email}")
            if phone:
                lines.append(f"<br/>**{lbl['phone']}**: {phone}")
            if organization:
                lines.append(f"<br/>**{lbl['organization']}**: {organization}")

        # Contact update
        elif self.type == DraftType.CONTACT_UPDATE:
            current = self.content.get("current_contact", {})
            names = current.get("names", [])
            name = names[0].get("displayName", "?") if names else "?"
            changes = []

            if self.content.get("name"):
                changes.append(f"<br/>{lbl['contact']}: {self.content['name']}")
            if self.content.get("email"):
                changes.append(f"<br/>{lbl['email']}: {self.content['email']}")
            if self.content.get("phone"):
                changes.append(f"<br/>{lbl['phone']}: {self.content['phone']}")
            if self.content.get("organization"):
                changes.append(f"<br/>{lbl['organization']}: {self.content['organization']}")

            lines.append(f"<br/>**{lbl['contact']}**: {name}")
            if changes:
                lines.append(f"<br/>**{lbl['changes']}**:")
                for change in changes:
                    lines.append(f"  - {change}")

        # Contact delete
        elif self.type == DraftType.CONTACT_DELETE:
            contact = self.content.get("contact", {})
            names = contact.get("names", [])
            name = names[0].get("displayName", "?") if names else "?"
            emails = contact.get("emailAddresses", [])
            email = emails[0].get("value", "") if emails else ""

            lines.append(f"<br/>**{lbl['contact']}**: {name}")
            if email:
                lines.append(f"<br/>**{lbl['email']}**: {email}")

        # Task creation
        elif self.type == DraftType.TASK:
            title = self.content.get("title", "")
            notes = self.content.get("notes", "")
            due_raw = self.content.get("due", "")
            due = format_dt(due_raw) if due_raw else ""

            lines.append(f"<br/>**{lbl['task']}**: {title}")
            if due:
                lines.append(f"<br/>**{lbl['due']}**: {due}")
            if notes:
                lines.append(f"<br/>**{lbl['body']}**:<br/>{notes}")

        # Task update
        elif self.type == DraftType.TASK_UPDATE:
            current = self.content.get("current_task", {})
            title = self.content.get("title") or current.get("title", "?")
            changes = []

            if self.content.get("title"):
                changes.append(f"<br/>{lbl['task']}: {self.content['title']}")
            if self.content.get("due"):
                changes.append(f"<br/>{lbl['due']}: {format_dt(self.content['due'])}")
            if self.content.get("notes"):
                changes.append(f"<br/>{lbl['body']}: {self.content['notes']}")

            lines.append(f"<br/>**{lbl['task']}**: {title}")
            if changes:
                lines.append(f"<br/>**{lbl['changes']}**:")
                for change in changes:
                    lines.append(f"  - {change}")

        # Task delete
        elif self.type == DraftType.TASK_DELETE:
            title = self.content.get("title", "?")
            lines.append(f"<br/>**{lbl['task']}**: {title}")

        # File delete
        elif self.type == DraftType.FILE_DELETE:
            file_data = self.content.get("file", {})
            name = file_data.get("name", "?")
            mime_type = file_data.get("mimeType", "")

            lines.append(f"<br/>**{lbl['file']}**: {name}")
            if mime_type:
                lines.append(f"<br/>**{lbl['type']}**: {mime_type}")

        # Label delete
        elif self.type == DraftType.LABEL_DELETE:
            label_name = self.content.get("label_name", "?")
            sublabels = self.content.get("sublabels", [])
            children_only = self.content.get("children_only", False)

            if children_only:
                lines.append(f"<br/>**{lbl['label_parent']}**: {label_name}")
                lines.append(f"<br/>**{lbl['sublabels_to_delete']}**: {len(sublabels)}")
            else:
                lines.append(f"<br/>**{lbl['label']}**: {label_name}")
                if sublabels:
                    lines.append(f"<br/>**{lbl['sublabels_included']}**: {len(sublabels)}")
                    # Show first few sublabel names
                    sublabel_names = [s.get("name", "?") for s in sublabels[:5]]
                    if len(sublabels) > 5:
                        sublabel_names.append(f"... (+{len(sublabels) - 5})")
                    lines.append(f"<br/>  {', '.join(sublabel_names)}")

        # Fallback
        else:
            return self.get_summary(user_language)

        return "<br/>".join(lines)


class DraftActionRequest(BaseModel):
    """
    User action request on a draft.

    Sent from frontend when user clicks confirm/edit/cancel.
    """

    draft_id: str = Field(..., description="ID of the draft")
    action: DraftAction = Field(..., description="Action to take")

    # For EDIT action: new content
    updated_content: dict[str, Any] | None = Field(
        default=None,
        description="Updated content (for EDIT action)",
    )

    # User context
    user_message: str | None = Field(
        default=None,
        description="Optional user message/feedback",
    )


class DraftActionResult(BaseModel):
    """
    Result of a draft action.

    Returned after processing a DraftActionRequest.
    """

    draft_id: str = Field(..., description="ID of the draft")
    action: DraftAction = Field(..., description="Action that was taken")
    success: bool = Field(..., description="Whether action succeeded")
    new_status: DraftStatus = Field(..., description="New draft status")

    # For CONFIRM action: execution result
    execution_result: dict[str, Any] | None = Field(
        default=None,
        description="Result of execution (for CONFIRM)",
    )

    # Error info
    error_message: str | None = Field(
        default=None,
        description="Error message if failed",
    )

    # Updated draft (for EDIT action)
    updated_draft: Draft | None = Field(
        default=None,
        description="Updated draft object (for EDIT)",
    )
