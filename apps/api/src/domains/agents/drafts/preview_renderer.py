"""Draft Detailed-Preview Renderer.

Renders the detailed HITL confirmation preview of a draft — the multi-line
string shown to the user (and embedded verbatim in the frontend confirmation
cards) before a draft is executed. Extracted from
``Draft.get_detailed_preview`` in ``drafts/models.py`` (2026-07 audit, cycle
3: cyclomatic complexity 93 concentrated in a models module), replacing the
per-type ``if``-cascade with a dispatch table of small per-type renderers.

Output contract: BYTE-IDENTICAL to the pre-extraction implementation — the
golden characterization net
(``tests/unit/domains/agents/drafts/test_detailed_preview_characterization.py``)
pins the exact output for every ``DraftType`` and every rendering branch and
must pass unmodified.

Architecture invariants:
- Every ``DraftType`` value MUST have an entry in :data:`_PREVIEW_RENDERERS`.
  Enforced by :func:`assert_preview_renderer_completeness` (called from the
  lifespan startup, ADR-085 pattern, and by a unit test). The
  ``get_summary`` fallback in :func:`render_detailed_preview` is defense in
  depth only.
- Missing-value fallbacks are localized at RENDER time, never baked into the
  stored draft content: a subject-less email delete renders the
  ``no_subject`` label of ``DRAFT_PREVIEW_LABELS`` in the user's language, a
  forward body stored as ``None`` renders empty, and a reminder delete with
  no content renders ``"?"`` like every other delete type. (These three were
  pinned as-is during the extraction, then fixed as separate reviewed
  changes — the golden net was regenerated for exactly those cases.)

Created: 2026-07-11 (extraction #2 of the complexity-reduction series;
method: ADR-122 characterization-first decomposition)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.models import DraftType

if TYPE_CHECKING:
    from src.domains.agents.drafts.models import Draft

# Formats an ISO datetime string for display, or "" for a falsy input. Bound
# to the user's language/timezone by render_detailed_preview().
_FormatDt = Callable[[str | None], str]

# One renderer per DraftType: (content, labels, format_dt) -> preview lines.
_PreviewRenderer = Callable[[dict[str, Any], dict[str, str], _FormatDt], list[str]]


# =============================================================================
# SHARED ROW HELPERS (update-type "modified ✏️ or preserved" pattern)
# =============================================================================


def _updated_row(label: str, new_value: str | None, current_value: str) -> str | None:
    """Render an update-preview row showing the new value or the current one.

    Args:
        label: Localized field label.
        new_value: Value from the draft content (``None``/empty = unchanged).
        current_value: Value read from the current resource snapshot.

    Returns:
        The formatted row (suffixed with `` ✏️`` when the field is modified),
        or ``None`` when both values are empty and the row must be omitted.
    """
    value = new_value or current_value
    if not value:
        return None
    mark = " ✏️" if new_value else ""
    return f"<br/>**{label}**: {value}{mark}"


def _updated_datetime_row(
    label: str,
    new_raw: str | None,
    current_raw: str,
    format_dt: _FormatDt,
) -> str | None:
    """Render an update-preview datetime row (new value marked, else current).

    Args:
        label: Localized field label.
        new_raw: Raw ISO datetime from the draft content, if modified.
        current_raw: Raw ISO datetime from the current resource snapshot.
        format_dt: Localized datetime formatter.

    Returns:
        The formatted row, or ``None`` when neither value is set.
    """
    value = format_dt(new_raw) if new_raw else format_dt(current_raw) if current_raw else ""
    if not value:
        return None
    mark = " ✏️" if new_raw else ""
    return f"<br/>**{label}**: {value}{mark}"


def _first_item_value(items: list[dict[str, Any]], key: str, default: str = "") -> str:
    """Return ``items[0][key]`` with a default for empty lists or missing keys.

    Mirrors the Google People API shape (``names``, ``emailAddresses``, ...)
    where the first entry is the primary value.
    """
    return items[0].get(key, default) if items else default


# =============================================================================
# PER-TYPE RENDERERS
# =============================================================================


def _render_email_send(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render email send/reply previews (to, cc, bcc, subject, body)."""
    lines: list[str] = []
    to = content.get("to", "")
    cc = content.get("cc", "")
    bcc = content.get("bcc", "")
    subject = content.get("subject", "")
    # `or ""`: a body explicitly stored as None (forward without an added
    # message) must render empty, not as the literal string "None".
    body = content.get("body") or ""

    lines.append(f"<br/>**{lbl['to']}**: {to}")
    if cc:
        lines.append(f"<br/>**{lbl['cc']}**: {cc}")
    if bcc:
        lines.append(f"<br/>**{lbl['bcc']}**: {bcc}")
    lines.append(f"<br/>**{lbl['subject']}**: {subject}")
    lines.append(f"<br/>**{lbl['body']}**:<br/>{body}")
    return lines


def _render_email_forward(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an email forward preview: send fields plus attachments."""
    lines = _render_email_send(content, lbl, format_dt)
    attachments = content.get("attachments", [])
    if attachments:
        att_names = [a.get("filename", a.get("name", "?")) for a in attachments]
        lines.append(f"<br/>**{lbl['attachments']}**: {', '.join(att_names)}")
    return lines


def _render_email_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an email delete preview (sender, subject, date)."""
    # The stored subject is the raw truth ("" when the email has none); the
    # localized fallback is applied here, at render time.
    subject = content.get("subject") or lbl["no_subject"]
    from_addr = content.get("from", content.get("from_addr", "?"))
    date_raw = content.get("date", "")
    date = format_dt(date_raw) if date_raw else ""

    lines = [
        f"<br/>**{lbl['from']}**: {from_addr}",
        f"<br/>**{lbl['subject']}**: {subject}",
    ]
    if date:
        lines.append(f"<br/>**{lbl['date']}**: {date}")
    return lines


def _render_reminder_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a reminder delete preview (content, trigger datetime)."""
    # "?" fallback keeps the delete-preview convention of the other types
    # (task/contact/file/event delete all render "?" for a missing label).
    reminder_content = content.get("content") or "?"
    trigger_at = content.get("trigger_at", "")
    trigger_formatted = format_dt(trigger_at) if trigger_at else ""

    lines = [f"<br/>**{lbl['event']}**: {reminder_content}"]
    if trigger_formatted:
        lines.append(f"<br/>**{lbl['date']}**: {trigger_formatted}")
    return lines


def _render_event(content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt) -> list[str]:
    """Render an event creation preview (summary, times, place, attendees)."""
    summary = content.get("summary", "")
    start = format_dt(content.get("start_datetime", ""))
    end = format_dt(content.get("end_datetime", ""))
    location = content.get("location", "")
    description = content.get("description", "")
    attendees = content.get("attendees", [])

    lines = [
        f"<br/>**{lbl['event']}**: {summary}",
        f"<br/>**{lbl['start']}**: {start}",
        f"<br/>**{lbl['end']}**: {end}",
    ]
    if location:
        lines.append(f"<br/>**{lbl['location']}**: {location}")
    if attendees:
        lines.append(f"<br/>**{lbl['attendees']}**: {', '.join(attendees)}")
    if description:
        lines.append(f"<br/>**{lbl['body']}**<br/>{description}")
    return lines


def _render_event_update(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an event update preview: resulting state, modified fields marked."""
    current = content.get("current_event", {})
    summary = content.get("summary") or current.get("summary", "?")
    lines = [f"<br/>**{lbl['event']}**: {summary}"]

    current_start = current.get("start", {}).get(
        "dateTime", current.get("start", {}).get("date", "")
    )
    start_row = _updated_datetime_row(
        lbl["start"], content.get("start_datetime"), current_start, format_dt
    )
    if start_row:
        lines.append(start_row)

    current_end = current.get("end", {}).get("dateTime", current.get("end", {}).get("date", ""))
    end_row = _updated_datetime_row(lbl["end"], content.get("end_datetime"), current_end, format_dt)
    if end_row:
        lines.append(end_row)

    location_row = _updated_row(
        lbl["location"], content.get("location"), current.get("location", "")
    )
    if location_row:
        lines.append(location_row)

    new_attendees = content.get("attendees")
    if new_attendees:
        lines.append(f"<br/>**{lbl['attendees']}**: {', '.join(new_attendees)} ✏️")
    elif current.get("attendees"):
        current_attendees = [a.get("email", a.get("displayName", "")) for a in current["attendees"]]
        if current_attendees:
            lines.append(f"<br/>**{lbl['attendees']}**: {', '.join(current_attendees)}")
    return lines


def _render_event_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an event delete preview (summary, start date)."""
    event = content.get("event", {})
    summary = event.get("summary", "?")
    start_raw = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
    start = format_dt(start_raw) if start_raw else ""

    lines = [f"<br/>**{lbl['event']}**: {summary}"]
    if start:
        lines.append(f"<br/>**{lbl['date']}**: {start}")
    return lines


def _render_contact(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a contact creation preview (name, email, phone, organization)."""
    name = content.get("name", "")
    email = content.get("email", "")
    phone = content.get("phone", "")
    organization = content.get("organization", "")

    lines = [f"<br/>**{lbl['contact']}**: {name}"]
    if email:
        lines.append(f"<br/>**{lbl['email']}**: {email}")
    if phone:
        lines.append(f"<br/>**{lbl['phone']}**: {phone}")
    if organization:
        lines.append(f"<br/>**{lbl['organization']}**: {organization}")
    return lines


def _render_contact_update(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a contact update preview: resulting state, modified fields marked."""
    current = content.get("current_contact", {})
    current_name = _first_item_value(current.get("names", []), "displayName", "?")
    new_name = content.get("name")
    name_value = new_name or current_name
    mark = " ✏️" if new_name else ""
    lines = [f"<br/>**{lbl['contact']}**: {name_value}{mark}"]

    email_row = _updated_row(
        lbl["email"],
        content.get("email"),
        _first_item_value(current.get("emailAddresses", []), "value"),
    )
    if email_row:
        lines.append(email_row)

    phone_row = _updated_row(
        lbl["phone"],
        content.get("phone"),
        _first_item_value(current.get("phoneNumbers", []), "value"),
    )
    if phone_row:
        lines.append(phone_row)

    organization_row = _updated_row(
        lbl["organization"],
        content.get("organization"),
        _first_item_value(current.get("organizations", []), "name"),
    )
    if organization_row:
        lines.append(organization_row)
    return lines


def _render_contact_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a contact delete preview (name, primary email)."""
    contact = content.get("contact", {})
    name = _first_item_value(contact.get("names", []), "displayName", "?")
    email = _first_item_value(contact.get("emailAddresses", []), "value")

    lines = [f"<br/>**{lbl['contact']}**: {name}"]
    if email:
        lines.append(f"<br/>**{lbl['email']}**: {email}")
    return lines


def _render_task(content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt) -> list[str]:
    """Render a task creation preview (title, due date, notes)."""
    title = content.get("title", "")
    notes = content.get("notes", "")
    due_raw = content.get("due", "")
    due = format_dt(due_raw) if due_raw else ""

    lines = [f"<br/>**{lbl['task']}**: {title}"]
    if due:
        lines.append(f"<br/>**{lbl['due']}**: {due}")
    if notes:
        lines.append(f"<br/>**{lbl['body']}**:<br/>{notes}")
    return lines


def _render_task_update(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a task update preview: resulting state, modified fields marked."""
    current = content.get("current_task", {})
    new_title = content.get("title")
    title_value = new_title or current.get("title", "?")
    mark = " ✏️" if new_title else ""
    lines = [f"<br/>**{lbl['task']}**: {title_value}{mark}"]

    due_row = _updated_datetime_row(
        lbl["due"], content.get("due"), current.get("due", ""), format_dt
    )
    if due_row:
        lines.append(due_row)

    notes_row = _updated_row(lbl["body"], content.get("notes"), current.get("notes", ""))
    if notes_row:
        lines.append(notes_row)
    return lines


def _render_task_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a task delete preview (title only)."""
    title = content.get("title", "?")
    return [f"<br/>**{lbl['task']}**: {title}"]


def _render_file_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Drive file delete preview (name, MIME type)."""
    file_data = content.get("file", {})
    name = file_data.get("name", "?")
    mime_type = file_data.get("mimeType", "")

    lines = [f"<br/>**{lbl['file']}**: {name}"]
    if mime_type:
        lines.append(f"<br/>**{lbl['type']}**: {mime_type}")
    return lines


def _render_label_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Gmail label delete preview (label, sublabels, truncated at 5)."""
    label_name = content.get("label_name", "?")
    sublabels = content.get("sublabels", [])
    children_only = content.get("children_only", False)

    lines: list[str] = []
    if children_only:
        lines.append(f"<br/>**{lbl['label_parent']}**: {label_name}")
        lines.append(f"<br/>**{lbl['sublabels_to_delete']}**: {len(sublabels)}")
    else:
        lines.append(f"<br/>**{lbl['label']}**: {label_name}")
        if sublabels:
            lines.append(f"<br/>**{lbl['sublabels_included']}**: {len(sublabels)}")
            sublabel_names = [s.get("name", "?") for s in sublabels[:5]]
            if len(sublabels) > 5:
                sublabel_names.append(f"... (+{len(sublabels) - 5})")
            lines.append(f"<br/>  {', '.join(sublabel_names)}")
    return lines


def _render_phone_call(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an outbound phone-call preview (callee, phone, objective)."""
    # "?" callee fallback matches the other types when the name is missing;
    # the phone/objective rows are omitted when empty, like optional fields
    # elsewhere. No datetime: a call is placed immediately on confirmation.
    callee = content.get("callee_name") or "?"
    phone = content.get("callee_phone", "")
    objective = content.get("objective", "")

    lines = [f"<br/>**{lbl['callee']}**: {callee}"]
    if phone:
        lines.append(f"<br/>**{lbl['phone']}**: {phone}")
    if objective:
        lines.append(f"<br/>**{lbl['objective']}**: {objective}")
    return lines


# =============================================================================
# REGISTRY
# =============================================================================
# One entry per DraftType. assert_preview_renderer_completeness() enforces
# exhaustivity at startup and in CI.

_PREVIEW_RENDERERS: dict[DraftType, _PreviewRenderer] = {
    DraftType.EMAIL: _render_email_send,
    DraftType.EMAIL_REPLY: _render_email_send,
    DraftType.EMAIL_FORWARD: _render_email_forward,
    DraftType.EMAIL_DELETE: _render_email_delete,
    DraftType.EVENT: _render_event,
    DraftType.EVENT_UPDATE: _render_event_update,
    DraftType.EVENT_DELETE: _render_event_delete,
    DraftType.CONTACT: _render_contact,
    DraftType.CONTACT_UPDATE: _render_contact_update,
    DraftType.CONTACT_DELETE: _render_contact_delete,
    DraftType.TASK: _render_task,
    DraftType.TASK_UPDATE: _render_task_update,
    DraftType.TASK_DELETE: _render_task_delete,
    DraftType.FILE_DELETE: _render_file_delete,
    DraftType.LABEL_DELETE: _render_label_delete,
    DraftType.REMINDER_DELETE: _render_reminder_delete,
    DraftType.PHONE_CALL: _render_phone_call,
}


# =============================================================================
# PUBLIC API
# =============================================================================


def render_detailed_preview(
    draft: Draft,
    user_language: str = "fr",
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> str:
    """Render the detailed preview of a draft for user confirmation.

    Shows the full draft content (e.g. email to/cc/subject/body) for
    verification in the HITL confirmation flow before execution. Dispatches
    to the per-type renderer registered in :data:`_PREVIEW_RENDERERS`.

    Args:
        draft: The draft to render.
        user_language: Language for labels (fr, en, es, de, it, zh-CN).
        user_timezone: User's IANA timezone for datetime formatting.

    Returns:
        Detailed multi-line preview string with all relevant fields, or the
        ``get_summary`` fallback for an unregistered draft type (defense in
        depth — the startup completeness assert makes this unreachable for
        ``DraftType`` values).
    """
    from src.core.time_utils import format_datetime_for_display

    def format_dt(dt_str: str | None) -> str:
        """Format an ISO datetime string for display."""
        if not dt_str:
            return ""
        return format_datetime_for_display(dt_str, user_timezone, user_language, include_time=True)

    renderer = _PREVIEW_RENDERERS.get(draft.type)
    if renderer is None:
        return draft.get_summary(user_language)

    lbl = get_draft_preview_labels(user_language)
    return "<br/>".join(renderer(draft.content, lbl, format_dt))


def assert_preview_renderer_completeness() -> None:
    """Assert every ``DraftType`` value has a registered preview renderer.

    Called from the lifespan startup so a missing entry refuses to boot the
    application (ADR-085 pattern, same as
    :func:`src.domains.agents.drafts.display.assert_registry_completeness`),
    and from a unit test so CI catches it before merge.

    Raises:
        AssertionError: If any ``DraftType`` value is missing from
            :data:`_PREVIEW_RENDERERS`, listing the missing types.
    """
    missing = {t for t in DraftType if t not in _PREVIEW_RENDERERS}
    if missing:
        names = ", ".join(sorted(t.value for t in missing))
        raise AssertionError(
            f"_PREVIEW_RENDERERS is missing {len(missing)} DraftType(s): {names}. "
            "Every DraftType must register a preview renderer — see "
            "src/domains/agents/drafts/preview_renderer.py."
        )


__all__ = [
    "assert_preview_renderer_completeness",
    "render_detailed_preview",
]
