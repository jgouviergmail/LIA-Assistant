"""What each provider accepts in the « Tools » section — declared once (ADR-369).

The page offers a gesture only when the active provider accepts it: whatever a
route would refuse, the page must be able to read beforehand (ADR-184). One
frozen table keyed by connector type answers that for every provider of every
tool, and the boot refuses a provider with no entry or an entry no tool has
(ADR-085): a silent fallback would offer a gesture the provider then refuses,
or hide one it accepts.

Per-lamp abilities (colour, colour temperature) are the bridge's, read with the
lamps; the descriptor holds what is true of a whole provider.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from src.core.constants import (
    APPLE_MAIL_MESSAGE_MAX_BYTES,
    EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
    GMAIL_SEND_MESSAGE_MAX_BYTES,
    MAIL_SIGNATURE_MAX_CHARS,
    OUTLOOK_INLINE_ATTACHMENT_MAX_BYTES,
    WORKBENCH_CALENDAR_IDS_MAX,
    WORKBENCH_CALENDAR_NAME_MAX_CHARS,
    WORKBENCH_CALENDAR_WINDOW_MAX_DAYS,
    WORKBENCH_CONTACT_ADDRESS_MAX_CHARS,
    WORKBENCH_CONTACT_HISTORY_MAX_ADDRESSES,
    WORKBENCH_CONTACT_HISTORY_MAX_PHONES,
    WORKBENCH_CONTACT_NAME_MAX_CHARS,
    WORKBENCH_CONTACT_NOTES_MAX_CHARS,
    WORKBENCH_CONTACT_PHOTO_MAX_BYTES,
    WORKBENCH_CONTACT_VALUE_MAX_CHARS,
    WORKBENCH_CONTACT_VALUES_MAX,
    WORKBENCH_CONTACTS_EXPORT_MAX,
    WORKBENCH_CONTACTS_IMPORT_MAX_BYTES,
    WORKBENCH_CONTACTS_IMPORT_MAX_CARDS,
    WORKBENCH_EVENT_ATTENDEES_MAX,
    WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS,
    WORKBENCH_EVENT_LOCATION_MAX_CHARS,
    WORKBENCH_EVENT_SERIES_MAX_COUNT,
    WORKBENCH_EVENT_SUMMARY_MAX_CHARS,
    WORKBENCH_FILE_NAME_MAX_CHARS,
    WORKBENCH_MAIL_ATTACHMENTS_MAX,
    WORKBENCH_MAIL_BODY_MAX_CHARS,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
    WORKBENCH_MAIL_RECIPIENT_MAX_CHARS,
    WORKBENCH_MAIL_RECIPIENTS_MAX,
    WORKBENCH_MAIL_SUBJECT_MAX_CHARS,
    WORKBENCH_TASK_NOTES_MAX_CHARS,
    WORKBENCH_TASK_TITLE_MAX_CHARS,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    GRAPH_ADDRESSES_PER_KIND_MAX,
    GRAPH_BUSINESS_PHONES_MAX,
    GRAPH_EMAILS_MAX,
    GRAPH_HOME_PHONES_MAX,
    GRAPH_MOBILE_PHONES_MAX,
)
from src.domains.connectors.models import CONNECTOR_FUNCTIONAL_CATEGORIES, ConnectorType
from src.infrastructure.email.outgoing import max_file_bytes


class WorkbenchTool(str, Enum):
    """The tools of the section, in rail order (spec §13)."""

    MAIL = "mail"
    CALENDAR = "calendar"
    TASKS = "tasks"
    CONTACTS = "contacts"
    FILES = "files"
    LIGHTS = "lights"


class WorkbenchFeature(str, Enum):
    """A gesture a provider may or may not accept (closed vocabulary)."""

    # Mail
    MARK_READ = "mark_read"
    DRAFTS = "drafts"
    HTML = "html"
    ATTACHMENTS = "attachments"
    #: The « with attachments » chip: IMAP's translator has no criterion for it.
    ATTACHMENT_FILTER = "attachment_filter"
    LABELS = "labels"
    #: Folders of the person's own created, renamed and deleted (Gmail's are labels).
    FOLDER_MANAGEMENT = "folder_management"
    #: Deleting for good. Gmail's needs ``https://mail.google.com/``, a scope LIA does
    #: not hold; it empties its own trash after 30 days.
    PERMANENT_DELETE = "permanent_delete"
    VACATION = "vacation"
    VACATION_SUBJECT = "vacation_subject"
    VACATION_OPEN_END = "vacation_open_end"
    FILTERS = "filters"
    FILTER_WORDS = "filter_words"
    #: The aliases a message may leave from: Gmail alone lists and honours them.
    SEND_AS = "send_as"
    # Calendar
    ALL_DAY = "all_day"
    CONFERENCE = "conference"
    NOTIFY_ATTENDEES = "notify_attendees"
    #: One occurrence of a series is changed or deleted alone (CalDAV names it by the
    #: series' uid, so a change there would reach every occurrence).
    OCCURRENCE_EDIT = "occurrence_edit"
    #: Moving an event to another calendar (a copy where the provider has no move).
    EVENT_MOVE = "event_move"
    #: Moving one that has guests: only a provider that moves rather than copies.
    EVENT_MOVE_WITH_GUESTS = "event_move_with_guests"
    #: Calendars of the person's own created, renamed and deleted.
    CALENDAR_MANAGEMENT = "calendar_management"
    # Tasks
    LIST_MANAGEMENT = "list_management"
    SUBTASKS = "subtasks"
    DUE_DATE_ONLY = "due_date_only"
    #: A task's own checklist (To Do; Google's subtasks are tasks of their own).
    TASK_STEPS = "task_steps"
    #: An importance, a reminder and a repetition: fields Google Tasks has none of.
    TASK_DETAILS = "task_details"
    #: A list's order: To Do's API gives a task no position.
    TASK_ORDER = "task_order"
    # Contacts
    MULTI_VALUED = "multi_valued"
    CONTACT_GROUPS = "contact_groups"
    OTHER_CONTACTS = "other_contacts"
    # Files
    EXPORT = "export"
    FILE_VIEWS = "file_views"
    # Lights
    SCENES = "scenes"


#: The functional category a tool's provider is resolved in (the ADR-304 door).
TOOL_CATEGORY: Final[dict[WorkbenchTool, str]] = {
    WorkbenchTool.MAIL: "email",
    WorkbenchTool.CALENDAR: "calendar",
    WorkbenchTool.TASKS: "tasks",
    WorkbenchTool.CONTACTS: "contacts",
    WorkbenchTool.FILES: "files",
}
#: A tool served by ONE connector, opened by its type: the bridge's credentials are a
#: shape the category door does not read (the smart-home category has a single member).
TOOL_SINGLE_TYPE: Final[dict[WorkbenchTool, ConnectorType]] = {
    WorkbenchTool.LIGHTS: ConnectorType.PHILIPS_HUE,
}

#: Every connector type that may serve each tool.
TOOL_PROVIDERS: Final[dict[WorkbenchTool, frozenset[ConnectorType]]] = {
    WorkbenchTool.MAIL: CONNECTOR_FUNCTIONAL_CATEGORIES["email"],
    WorkbenchTool.CALENDAR: CONNECTOR_FUNCTIONAL_CATEGORIES["calendar"],
    WorkbenchTool.TASKS: CONNECTOR_FUNCTIONAL_CATEGORIES["tasks"],
    WorkbenchTool.CONTACTS: CONNECTOR_FUNCTIONAL_CATEGORIES["contacts"],
    WorkbenchTool.FILES: CONNECTOR_FUNCTIONAL_CATEGORIES["files"],
    WorkbenchTool.LIGHTS: CONNECTOR_FUNCTIONAL_CATEGORIES["smart_home"],
}

_MAIL_COMMON: Final = frozenset(
    {
        WorkbenchFeature.MARK_READ,
        WorkbenchFeature.DRAFTS,
        WorkbenchFeature.HTML,
        WorkbenchFeature.ATTACHMENTS,
    }
)

#: What each provider accepts. Gmail and Outlook hold a responder and filters, and
#: what only Gmail's take is named apart (spec §6.3, lot 12).
PROVIDER_FEATURES: Final[dict[ConnectorType, frozenset[WorkbenchFeature]]] = {
    ConnectorType.GOOGLE_GMAIL: _MAIL_COMMON
    | {
        WorkbenchFeature.ATTACHMENT_FILTER,
        WorkbenchFeature.LABELS,
        WorkbenchFeature.VACATION,
        WorkbenchFeature.VACATION_SUBJECT,
        WorkbenchFeature.VACATION_OPEN_END,
        WorkbenchFeature.FILTERS,
        WorkbenchFeature.FILTER_WORDS,
        WorkbenchFeature.SEND_AS,
    },
    ConnectorType.MICROSOFT_OUTLOOK: _MAIL_COMMON
    | {
        WorkbenchFeature.ATTACHMENT_FILTER,
        WorkbenchFeature.FOLDER_MANAGEMENT,
        WorkbenchFeature.PERMANENT_DELETE,
        WorkbenchFeature.VACATION,
        WorkbenchFeature.FILTERS,
    },
    ConnectorType.APPLE_EMAIL: _MAIL_COMMON
    | {WorkbenchFeature.FOLDER_MANAGEMENT, WorkbenchFeature.PERMANENT_DELETE},
    ConnectorType.GOOGLE_CALENDAR: frozenset(
        {
            WorkbenchFeature.ALL_DAY,
            WorkbenchFeature.CONFERENCE,
            WorkbenchFeature.NOTIFY_ATTENDEES,
            WorkbenchFeature.OCCURRENCE_EDIT,
            WorkbenchFeature.EVENT_MOVE,
            WorkbenchFeature.EVENT_MOVE_WITH_GUESTS,
            WorkbenchFeature.CALENDAR_MANAGEMENT,
        }
    ),
    # Graph attaches a Teams link as the assistant's tool already asks it to (D2), and
    # tells attendees of every change on its own: no « notify » choice to offer.
    ConnectorType.MICROSOFT_CALENDAR: frozenset(
        {
            WorkbenchFeature.ALL_DAY,
            WorkbenchFeature.CONFERENCE,
            WorkbenchFeature.OCCURRENCE_EDIT,
            WorkbenchFeature.EVENT_MOVE,
            WorkbenchFeature.CALENDAR_MANAGEMENT,
        }
    ),
    # CalDAV carries no conference and leaves scheduling to the server.
    ConnectorType.APPLE_CALENDAR: frozenset(
        {
            WorkbenchFeature.ALL_DAY,
            WorkbenchFeature.EVENT_MOVE,
            WorkbenchFeature.CALENDAR_MANAGEMENT,
        }
    ),
    ConnectorType.GOOGLE_TASKS: frozenset(
        {
            WorkbenchFeature.LIST_MANAGEMENT,
            WorkbenchFeature.SUBTASKS,
            WorkbenchFeature.DUE_DATE_ONLY,
            WorkbenchFeature.TASK_ORDER,
        }
    ),
    ConnectorType.MICROSOFT_TASKS: frozenset(
        {
            WorkbenchFeature.LIST_MANAGEMENT,
            WorkbenchFeature.TASK_STEPS,
            WorkbenchFeature.TASK_DETAILS,
        }
    ),
    ConnectorType.GOOGLE_CONTACTS: frozenset(
        {
            WorkbenchFeature.MULTI_VALUED,
            WorkbenchFeature.CONTACT_GROUPS,
            WorkbenchFeature.OTHER_CONTACTS,
        }
    ),
    ConnectorType.MICROSOFT_CONTACTS: frozenset(
        {WorkbenchFeature.MULTI_VALUED, WorkbenchFeature.CONTACT_GROUPS}
    ),
    ConnectorType.APPLE_CONTACTS: frozenset(
        {WorkbenchFeature.MULTI_VALUED, WorkbenchFeature.CONTACT_GROUPS}
    ),
    # Exports are Google's documents': OneDrive keeps files, downloaded as they are.
    ConnectorType.MICROSOFT_ONEDRIVE: frozenset(),
    ConnectorType.GOOGLE_DRIVE: frozenset({WorkbenchFeature.EXPORT, WorkbenchFeature.FILE_VIEWS}),
    ConnectorType.PHILIPS_HUE: frozenset({WorkbenchFeature.SCENES}),
}

#: The text bounds the tasks routes refuse beyond (Google Tasks' documented maxima).
_TASK_TEXT_BOUNDS: Final = {
    "title_max_chars": WORKBENCH_TASK_TITLE_MAX_CHARS,
    "notes_max_chars": WORKBENCH_TASK_NOTES_MAX_CHARS,
}
#: A contact's parts (the routes refuse beyond; a provider may hold fewer values).
_CONTACT_BOUNDS: Final = {
    "name_max_chars": WORKBENCH_CONTACT_NAME_MAX_CHARS,
    "history_addresses": WORKBENCH_CONTACT_HISTORY_MAX_ADDRESSES,
    "history_phones": WORKBENCH_CONTACT_HISTORY_MAX_PHONES,
    "notes_max_chars": WORKBENCH_CONTACT_NOTES_MAX_CHARS,
    "value_max_chars": WORKBENCH_CONTACT_VALUE_MAX_CHARS,
    "address_max_chars": WORKBENCH_CONTACT_ADDRESS_MAX_CHARS,
    "values_max": WORKBENCH_CONTACT_VALUES_MAX,
    "photo_max_bytes": WORKBENCH_CONTACT_PHOTO_MAX_BYTES,
    "export_max_contacts": WORKBENCH_CONTACTS_EXPORT_MAX,
    "import_max_cards": WORKBENCH_CONTACTS_IMPORT_MAX_CARDS,
    "import_max_bytes": WORKBENCH_CONTACTS_IMPORT_MAX_BYTES,
}
#: A calendar window and an event's parts (the routes refuse beyond), and the shortest
#: query the guests' contact suggestions search (the recipients' matcher, below which it
#: searches nothing).
_CALENDAR_BOUNDS: Final = {
    "window_max_days": WORKBENCH_CALENDAR_WINDOW_MAX_DAYS,
    "calendars_max": WORKBENCH_CALENDAR_IDS_MAX,
    "calendar_name_max_chars": WORKBENCH_CALENDAR_NAME_MAX_CHARS,
    "summary_max_chars": WORKBENCH_EVENT_SUMMARY_MAX_CHARS,
    "location_max_chars": WORKBENCH_EVENT_LOCATION_MAX_CHARS,
    "description_max_chars": WORKBENCH_EVENT_DESCRIPTION_MAX_CHARS,
    "attendees_max": WORKBENCH_EVENT_ATTENDEES_MAX,
    "series_max_count": WORKBENCH_EVENT_SERIES_MAX_COUNT,
    "recipient_query_min_chars": EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
}
#: A file's or a folder's name (the routes refuse beyond).
_FILE_BOUNDS: Final = {"file_name_max_chars": WORKBENCH_FILE_NAME_MAX_CHARS}
#: The words a mail search takes, and a message's parts (the routes refuse beyond).
_MAIL_TEXT_BOUNDS: Final = {
    "search_max_chars": WORKBENCH_MAIL_QUERY_MAX_CHARS,
    "recipient_query_min_chars": EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
    "recipients_max": WORKBENCH_MAIL_RECIPIENTS_MAX,
    "recipient_max_chars": WORKBENCH_MAIL_RECIPIENT_MAX_CHARS,
    "subject_max_chars": WORKBENCH_MAIL_SUBJECT_MAX_CHARS,
    "body_max_chars": WORKBENCH_MAIL_BODY_MAX_CHARS,
    "attachments_max": WORKBENCH_MAIL_ATTACHMENTS_MAX,
    "signature_max_chars": MAIL_SIGNATURE_MAX_CHARS,
}


def _mail_bounds(attachments_max_bytes: int) -> dict[str, int]:
    """A mail provider's bounds: the shared ones, and what one message carries in files
    — derived as the client derives its own ``OUTGOING_FILE_MAX_BYTES`` (pinned equal)."""
    return {**_MAIL_TEXT_BOUNDS, "attachments_max_bytes": attachments_max_bytes}


#: Numeric limits the page must publish because something enforces them — the
#: very constants the client or the route refuses beyond (an Exchange contact's
#: slots: three e-mails, two business and two home phones, one mobile, one
#: address of each kind; a task's title and notes).
PROVIDER_BOUNDS: Final[dict[ConnectorType, dict[str, int]]] = {
    ConnectorType.GOOGLE_GMAIL: _mail_bounds(max_file_bytes(GMAIL_SEND_MESSAGE_MAX_BYTES)),
    ConnectorType.MICROSOFT_OUTLOOK: _mail_bounds(OUTLOOK_INLINE_ATTACHMENT_MAX_BYTES),
    ConnectorType.APPLE_EMAIL: _mail_bounds(max_file_bytes(APPLE_MAIL_MESSAGE_MAX_BYTES)),
    ConnectorType.GOOGLE_CALENDAR: _CALENDAR_BOUNDS,
    ConnectorType.MICROSOFT_CALENDAR: _CALENDAR_BOUNDS,
    ConnectorType.APPLE_CALENDAR: _CALENDAR_BOUNDS,
    ConnectorType.GOOGLE_TASKS: _TASK_TEXT_BOUNDS,
    ConnectorType.MICROSOFT_TASKS: _TASK_TEXT_BOUNDS,
    ConnectorType.GOOGLE_DRIVE: _FILE_BOUNDS,
    ConnectorType.MICROSOFT_ONEDRIVE: _FILE_BOUNDS,
    ConnectorType.GOOGLE_CONTACTS: _CONTACT_BOUNDS,
    ConnectorType.APPLE_CONTACTS: _CONTACT_BOUNDS,
    ConnectorType.MICROSOFT_CONTACTS: {
        **_CONTACT_BOUNDS,
        "emails_max": GRAPH_EMAILS_MAX,
        "business_phones_max": GRAPH_BUSINESS_PHONES_MAX,
        "home_phones_max": GRAPH_HOME_PHONES_MAX,
        "mobile_phones_max": GRAPH_MOBILE_PHONES_MAX,
        "addresses_per_kind_max": GRAPH_ADDRESSES_PER_KIND_MAX,
    },
}


def assert_descriptor_completeness() -> None:
    """Refuse to boot when a workbench provider has no entry, or a stray one exists.

    Raises:
        RuntimeError: Naming the connector types missing or not served by any tool.
    """
    served = frozenset().union(*TOOL_PROVIDERS.values())
    missing = sorted(kind.value for kind in served - set(PROVIDER_FEATURES))
    stray = sorted(kind.value for kind in set(PROVIDER_FEATURES) - served)
    if missing or stray:
        raise RuntimeError(
            "workbench descriptor incomplete (domains/workbench/features.py): "
            f"missing={missing} stray={stray}"
        )


assert_descriptor_completeness()
