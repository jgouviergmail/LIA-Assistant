"""
Provider normalizers.

Convert native provider formats to the dict format expected by Google API clients,
enabling transparent provider switching in tools.

Supported providers:
- Apple iCloud: IMAP MailMessage, CalDAV VEVENT, CardDAV vCard
- Microsoft 365: Graph API messages, events, contacts, tasks
"""

from src.domains.connectors.clients.normalizers.calendar_normalizer import (
    normalize_calendar,
    normalize_vevent,
)
from src.domains.connectors.clients.normalizers.contacts_normalizer import (
    build_vcard,
    merge_vcard_fields,
    normalize_vcard,
)
from src.domains.connectors.clients.normalizers.email_normalizer import (
    convert_imap_query,
    normalize_imap_folder,
    normalize_imap_message,
)
from src.domains.connectors.clients.normalizers.microsoft_calendar_normalizer import (
    normalize_graph_calendar,
    normalize_graph_event,
)
from src.domains.connectors.clients.normalizers.microsoft_contacts_normalizer import (
    build_contact_body,
    build_contact_update_body,
    normalize_graph_contact,
)
from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
    build_search_filter,
    normalize_graph_folder,
    normalize_graph_message,
)
from src.domains.connectors.clients.normalizers.microsoft_tasks_normalizer import (
    build_task_body,
    normalize_graph_task,
    normalize_graph_task_list,
)

__all__ = [
    # Apple iCloud
    "build_vcard",
    "convert_imap_query",
    "merge_vcard_fields",
    "normalize_calendar",
    "normalize_imap_folder",
    "normalize_imap_message",
    "normalize_vcard",
    "normalize_vevent",
    # Microsoft 365
    "build_contact_body",
    "build_contact_update_body",
    "build_search_filter",
    "build_task_body",
    "normalize_graph_calendar",
    "normalize_graph_contact",
    "normalize_graph_event",
    "normalize_graph_folder",
    "normalize_graph_message",
    "normalize_graph_task",
    "normalize_graph_task_list",
]
