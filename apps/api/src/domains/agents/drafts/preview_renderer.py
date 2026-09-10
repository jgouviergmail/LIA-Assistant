"""Draft Detailed-Preview Renderer.

Renders the detailed HITL confirmation preview of a draft — the multi-line
string shown to the user (and embedded verbatim in the frontend confirmation
cards) before a draft is executed. Extracted from
``Draft.get_detailed_preview`` in ``drafts/models.py`` (2026-07 audit, cycle
3: cyclomatic complexity 93 concentrated in a models module), replacing the
per-type ``if``-cascade with a dispatch table of small per-type renderers.

Output vocabulary: ONE, and it is Markdown (ADR-276, lot 13). Every row is a
list item built by :func:`_row`, a text value is a paragraph built by
:func:`_block`, and the join is a plain newline. What it replaced was HTML —
``<br/>`` opening every row AND joining them, so every preview began with a
blank line and every field was separated by two. It read badly in the chat and
was read out verbatim on any surface that renders no markup; those surfaces now
flatten it with :func:`~src.domains.agents.display.plain_text.markdown_to_plain_text`.

The golden characterization net
(``tests/unit/domains/agents/drafts/test_detailed_preview_characterization.py``)
pins the exact output for every ``DraftType`` and every rendering branch. It is
regenerated ONLY on a deliberate change, old and new tables diffed line by line
— that is what proves a vocabulary change touched the form and nothing else.

Architecture invariants:
- Every ``DraftType`` value MUST have an entry in :data:`_PREVIEW_RENDERERS`.
  Enforced by :func:`assert_preview_renderer_completeness` (called from the
  lifespan startup, ADR-085 pattern, and by a unit test). The
  ``get_summary`` fallback in :func:`render_detailed_preview` is defense in
  depth only.
- Missing-value fallbacks are localized at RENDER time, never baked into the
  stored draft content: a subject-less email delete renders the
  ``no_subject`` label of ``DRAFT_PREVIEW_LABELS`` in the user's language, and
  a reminder delete with no content renders ``"?"`` like every other delete
  type. (Both were pinned as-is during the extraction, then fixed as separate
  reviewed changes — the golden net was regenerated for exactly those cases.)
- A field with NO value is not shown at all: a forward carrying no added
  message shows no message block, and an event with no times shows no
  ``Début`` over nothing. A label above emptiness states less than silence.

Created: 2026-07-11 (extraction #2 of the complexity-reduction series;
method: ADR-122 characterization-first decomposition)
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.drafts.markdown_grammar import (
    labelled_block,
    labelled_row,
    plain_row,
)
from src.domains.agents.drafts.models import DraftType

if TYPE_CHECKING:
    from src.domains.agents.drafts.models import Draft

# Formats an ISO datetime string for display, or "" for a falsy input. Bound
# to the user's language/timezone by render_detailed_preview().
_FormatDt = Callable[[str | None], str]

# One renderer per DraftType: (content, labels, format_dt) -> preview lines.
_PreviewRenderer = Callable[[dict[str, Any], dict[str, str], _FormatDt], list[str]]

#: A confirmation card is a question, not a payload dump.
_TOOL_CALL_MAX_ARGS = 6

#: One argument can be an entire email body: cap the VALUE too, not only the count.
_TOOL_CALL_MAX_VALUE_CHARS = 80


# =============================================================================
# THE VOCABULARY: what a preview is made of
# =============================================================================


def _row(lbl: dict[str, str], key: str, value: object) -> str:
    """One field of a preview: a Markdown list item.

    Binds the shared grammar to this surface's labels — the label under
    ``key`` and the language's own separator. The grammar itself lives in
    :mod:`~src.domains.agents.drafts.markdown_grammar`, shared with the
    execution-result renderer so a card and its outcome cannot speak two
    vocabularies (they did until ADR-276 lot 13's rule reached the second one).

    Args:
        lbl: The localized labels, which carry their language's punctuation.
        key: Which field this row is.
        value: What to show for it.

    Returns:
        The row.
    """
    return labelled_row(lbl[key], lbl["separator"], value)


def _note(text: str) -> str:
    """A line with no label: a statement, or one line of data.

    Args:
        text: The line, already localized or already rendered.

    Returns:
        The row, in the same list as the labelled ones.
    """
    return plain_row(text)


def _block(lbl: dict[str, str], key: str, text: str) -> str:
    """A field whose value is a TEXT: its own paragraph under a bold lead.

    Args:
        lbl: The localized labels.
        key: Which field this block is.
        text: The value, newlines and all.

    Returns:
        The block, carrying the blank lines that separate it from its
        neighbours — so the join stays a plain newline for every row.
    """
    return labelled_block(lbl[key], text)


def _first_block_index(lines: list[str]) -> int:
    """Where the rows end and the blocks begin.

    Args:
        lines: The preview lines built so far.

    Returns:
        The index of the first block, or the end of the list when there is
        none — so a row inserted there always lands among the rows.
    """
    return next((i for i, line in enumerate(lines) if line.startswith("\n")), len(lines))


# =============================================================================
# SHARED ROW HELPERS (update-type "modified ✏️ or preserved" pattern)
# =============================================================================


def _updated_row(
    lbl: dict[str, str], key: str, new_value: str | None, current_value: str
) -> str | None:
    """Render an update-preview row showing the new value or the current one.

    Args:
        lbl: The localized labels.
        key: Which field this row is.
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
    return _row(lbl, key, f"{value}{mark}")


def _updated_datetime_row(
    lbl: dict[str, str],
    key: str,
    new_raw: str | None,
    current_raw: str,
    format_dt: _FormatDt,
) -> str | None:
    """Render an update-preview datetime row (new value marked, else current).

    Args:
        lbl: The localized labels.
        key: Which field this row is.
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
    return _row(lbl, key, f"{value}{mark}")


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

    # Every field is optional to SHOW: a draft the model left half-filled is
    # still confirmed on what it holds, not on « Destinataire : » over nothing.
    if to:
        lines.append(_row(lbl, "to", to))
    if cc:
        lines.append(_row(lbl, "cc", cc))
    if bcc:
        lines.append(_row(lbl, "bcc", bcc))
    if subject:
        lines.append(_row(lbl, "subject", subject))
    if body:
        lines.append(_block(lbl, "body", body))
    return lines


def _render_email_forward(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an email forward preview: send fields plus attachments.

    The attachments row is inserted BEFORE the message, not appended after it:
    the body is a block that ends the preview, and a list item following it
    would open a second list under the words being approved.
    """
    lines = _render_email_send(content, lbl, format_dt)
    attachments = content.get("attachments", [])
    if attachments:
        att_names = [a.get("filename", a.get("name", "?")) for a in attachments]
        row = _row(lbl, "attachments", ", ".join(att_names))
        lines.insert(_first_block_index(lines), row)
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
        _row(lbl, "from", from_addr),
        _row(lbl, "subject", subject),
    ]
    if date:
        lines.append(_row(lbl, "date", date))
    return lines


def _render_ticket_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a workboard ticket delete preview (title, steps that go with it).

    The "?" fallback keeps the delete-preview convention of the other types.
    The step count is shown only when there are steps: a person confirming
    the deletion of one ticket must not read a zero and wonder what it counts.
    """
    title = content.get("title") or "?"
    lines = [_row(lbl, "title", title)]
    children = int(content.get("children") or 0)
    if children:
        lines.append(_row(lbl, "steps", children))
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

    lines = [_row(lbl, "event", reminder_content)]
    if trigger_formatted:
        lines.append(_row(lbl, "date", trigger_formatted))
    return lines


def _render_event(content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt) -> list[str]:
    """Render an event creation preview (summary, times, place, attendees)."""
    summary = content.get("summary", "")
    start = format_dt(content.get("start_datetime", ""))
    end = format_dt(content.get("end_datetime", ""))
    location = content.get("location", "")
    description = content.get("description", "")
    attendees = content.get("attendees", [])

    # An event with no times is a draft the model left incomplete; « Début: »
    # over nothing states less than saying nothing at all.
    lines = [_row(lbl, "event", summary)]
    if start:
        lines.append(_row(lbl, "start", start))
    if end:
        lines.append(_row(lbl, "end", end))
    if location:
        lines.append(_row(lbl, "location", location))
    if attendees:
        lines.append(_row(lbl, "attendees", ", ".join(attendees)))
    if content.get("add_conference"):
        lines.append(_row(lbl, "video_conference", lbl["video_conference_included"]))
    if description:
        lines.append(_block(lbl, "body", description))
    return lines


def _render_event_update(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an event update preview: resulting state, modified fields marked."""
    current = content.get("current_event", {})
    summary = content.get("summary") or current.get("summary", "?")
    lines = [_row(lbl, "event", summary)]

    current_start = current.get("start", {}).get(
        "dateTime", current.get("start", {}).get("date", "")
    )
    start_row = _updated_datetime_row(
        lbl, "start", content.get("start_datetime"), current_start, format_dt
    )
    if start_row:
        lines.append(start_row)

    current_end = current.get("end", {}).get("dateTime", current.get("end", {}).get("date", ""))
    end_row = _updated_datetime_row(lbl, "end", content.get("end_datetime"), current_end, format_dt)
    if end_row:
        lines.append(end_row)

    location_row = _updated_row(
        lbl, "location", content.get("location"), current.get("location", "")
    )
    if location_row:
        lines.append(location_row)

    new_attendees = content.get("attendees")
    if new_attendees:
        lines.append(_row(lbl, "attendees", f"{', '.join(new_attendees)} ✏️"))
    elif current.get("attendees"):
        current_attendees = [a.get("email", a.get("displayName", "")) for a in current["attendees"]]
        if current_attendees:
            lines.append(_row(lbl, "attendees", ", ".join(current_attendees)))
    return lines


def _render_event_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render an event delete preview (summary, start date)."""
    event = content.get("event", {})
    summary = event.get("summary", "?")
    start_raw = event.get("start", {}).get("dateTime", event.get("start", {}).get("date", ""))
    start = format_dt(start_raw) if start_raw else ""

    lines = [_row(lbl, "event", summary)]
    if start:
        lines.append(_row(lbl, "date", start))
    return lines


def _render_contact(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a contact creation preview (name, email, phone, organization)."""
    name = content.get("name", "")
    email = content.get("email", "")
    phone = content.get("phone", "")
    organization = content.get("organization", "")

    lines = [_row(lbl, "contact", name)]
    if email:
        lines.append(_row(lbl, "email", email))
    if phone:
        lines.append(_row(lbl, "phone", phone))
    if organization:
        lines.append(_row(lbl, "organization", organization))
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
    lines = [_row(lbl, "contact", f"{name_value}{mark}")]

    email_row = _updated_row(
        lbl,
        "email",
        content.get("email"),
        _first_item_value(current.get("emailAddresses", []), "value"),
    )
    if email_row:
        lines.append(email_row)

    phone_row = _updated_row(
        lbl,
        "phone",
        content.get("phone"),
        _first_item_value(current.get("phoneNumbers", []), "value"),
    )
    if phone_row:
        lines.append(phone_row)

    organization_row = _updated_row(
        lbl,
        "organization",
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

    lines = [_row(lbl, "contact", name)]
    if email:
        lines.append(_row(lbl, "email", email))
    return lines


def _render_task(content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt) -> list[str]:
    """Render a task creation preview (title, due date, notes)."""
    title = content.get("title", "")
    notes = content.get("notes", "")
    due_raw = content.get("due", "")
    due = format_dt(due_raw) if due_raw else ""

    lines = [_row(lbl, "task", title)]
    if due:
        lines.append(_row(lbl, "due", due))
    if notes:
        lines.append(_block(lbl, "body", notes))
    return lines


def _render_task_update(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a task update preview: resulting state, modified fields marked."""
    current = content.get("current_task", {})
    new_title = content.get("title")
    title_value = new_title or current.get("title", "?")
    mark = " ✏️" if new_title else ""
    lines = [_row(lbl, "task", f"{title_value}{mark}")]

    due_row = _updated_datetime_row(
        lbl, "due", content.get("due"), current.get("due", ""), format_dt
    )
    if due_row:
        lines.append(due_row)

    notes_row = _updated_row(lbl, "body", content.get("notes"), current.get("notes", ""))
    if notes_row:
        lines.append(notes_row)
    return lines


def _render_task_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a task delete preview (title only)."""
    title = content.get("title", "?")
    return [_row(lbl, "task", title)]


def _render_file_delete(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Drive file delete preview (name, MIME type)."""
    file_data = content.get("file", {})
    name = file_data.get("name", "?")
    mime_type = file_data.get("mimeType", "")

    lines = [_row(lbl, "file", name)]
    if mime_type:
        lines.append(_row(lbl, "type", mime_type))
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
        lines.append(_row(lbl, "label_parent", label_name))
        lines.append(_row(lbl, "sublabels_to_delete", len(sublabels)))
    else:
        lines.append(_row(lbl, "label", label_name))
        if sublabels:
            lines.append(_row(lbl, "sublabels_included", len(sublabels)))
            sublabel_names = [s.get("name", "?") for s in sublabels[:5]]
            if len(sublabels) > 5:
                sublabel_names.append(f"... (+{len(sublabels) - 5})")
            lines.append(_note(", ".join(sublabel_names)))
    return lines


def _argument_value(value: Any) -> str:
    """Render one tool argument as data the user can read.

    Two leaks this closes, both measured on a real MCP call: ``True``/``None``
    and ``{'k': 'v'}`` are PYTHON spellings on a card read by a human in six
    languages, and one argument can carry an entire email body — a card is a
    question, not a payload dump.

    Args:
        value: The argument value, straight from a third-party tool call.

    Returns:
        A short, language-neutral rendering; strings pass through, everything
        else takes its JSON spelling, and both are truncated.
    """
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError, ValueError:
            text = str(value)
    text = " ".join(text.split())
    if len(text) > _TOOL_CALL_MAX_VALUE_CHARS:
        text = f"{text[:_TOOL_CALL_MAX_VALUE_CHARS]}…"
    return text


def _render_tool_call(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a tool call awaiting confirmation (ADR-263).

    Shows WHAT will run and with WHICH arguments, because that is exactly what
    the user is being asked to allow. The values come from a third-party tool
    call, so they are rendered as data — one ``key: value`` per line, never
    interpreted — and the list is capped: a confirmation card is a question,
    not a payload dump.
    """
    tool_label = content.get("tool_label") or content.get("tool_name") or "?"
    lines = [_row(lbl, "tool", tool_label)]
    arguments = content.get("tool_args")
    if isinstance(arguments, dict) and arguments:
        shown = list(arguments.items())[:_TOOL_CALL_MAX_ARGS]
        rendered = ", ".join(f"{key}: {_argument_value(value)}" for key, value in shown)
        if len(arguments) > _TOOL_CALL_MAX_ARGS:
            rendered += ", …"
        lines.append(_row(lbl, "details", rendered))
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

    lines = [_row(lbl, "callee", callee)]
    if phone:
        lines.append(_row(lbl, "phone", phone))
    if objective:
        lines.append(_row(lbl, "objective", objective))
    return lines


def _render_devops_task(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a remote-server task preview (server, task, extra instructions).

    Everything that reaches the remote CLI is shown, in full and untruncated:
    a confirmation the user cannot read is not a confirmation.

    ``context`` matters as much as ``task``. It is produced by the model and
    lands in the CLI's ``--append-system-prompt``, so content the agent picked
    up from an untrusted source (an email, a web page, an MCP result) can steer
    the remote session through it. Hiding it would leave the one field an
    injection would use invisible to the person approving.

    No datetime — the task runs as soon as it is confirmed.
    """
    server = content.get("server") or "?"
    task = content.get("task", "")
    extra = content.get("context", "")

    lines = [_row(lbl, "server", server)]
    if task:
        lines.append(_row(lbl, "task", task))
    if extra:
        lines.append(_row(lbl, "context", extra))
    return lines


def _render_peer_message(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a relayed-message preview (recipient, full message — peers A3).

    The message is shown in full and untruncated: the recipient's assistant
    will convey exactly this intent, so the sender must be able to read every
    word they are approving. No datetime — delivery starts on confirmation.
    """
    recipient = content.get("recipient_name") or "?"
    message = content.get("message", "")

    lines = [_row(lbl, "recipient", recipient)]
    if message:
        lines.append(_block(lbl, "message", message))
    return lines


def _render_vacation_responder(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Gmail vacation-responder preview (lot I).

    Enable: subject, full body and the activation window — the auto-reply is
    sent verbatim to every correspondent, so the user must read every word
    they are approving. Disable: a single localized sentence stating the
    responder will be turned off (no other field is meaningful).

    Dates are plain YYYY-MM-DD strings chosen by the user (not datetimes), so
    they are shown as-is rather than through ``format_dt``.
    """
    if not content.get("enable", False):
        return [_note(lbl["vacation_disabled"])]

    lines: list[str] = []
    subject = content.get("subject", "")
    body = content.get("body", "")
    start_date = content.get("start_date", "")
    end_date = content.get("end_date", "")

    # The window first, the words last: the reply itself is a block, and a row
    # placed after it would open a second list under the text being approved.
    if subject:
        lines.append(_row(lbl, "subject", subject))
    if start_date:
        lines.append(_row(lbl, "start", start_date))
    if end_date:
        lines.append(_row(lbl, "end", end_date))
    if body:
        lines.append(_block(lbl, "body", body))
    return lines


_SPREADSHEET_PREVIEW_MAX_ROWS = 10


def _render_spreadsheet_write(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Sheets write preview (lot F phase write).

    Shows the file, the sheet, the target range (update mode) and the rows
    to write — pipe-joined, bounded to a readable page with the EXACT hidden
    remainder stated (count doctrine): the user must know what will land in
    their spreadsheet before confirming.
    """
    lines: list[str] = []
    title = content.get("spreadsheet_title", "")
    sheet = content.get("sheet_name", "")
    a1_range = content.get("a1_range", "")
    values = content.get("values") or []

    if title:
        lines.append(_row(lbl, "file", title))
    if sheet:
        lines.append(_row(lbl, "sheet", sheet))
    if content.get("mode") == "update" and a1_range:
        lines.append(_row(lbl, "range", a1_range))
    for row in values[:_SPREADSHEET_PREVIEW_MAX_ROWS]:
        rendered = " | ".join(str(cell) for cell in row)
        lines.append(_note(rendered))
    hidden = len(values) - _SPREADSHEET_PREVIEW_MAX_ROWS
    if hidden > 0:
        lines.append(_note(f"… (+{hidden})"))
    return lines


def _render_document_append(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Docs append preview (lot F phase write).

    The text is shown in FULL and untruncated: it lands verbatim in the
    user's document, so they must be able to read every word they approve.
    """
    lines: list[str] = []
    title = content.get("document_title", "")
    text = content.get("text", "")
    if title:
        lines.append(_row(lbl, "file", title))
    if text:
        lines.append(_block(lbl, "text", text))
    return lines


def _render_email_filter(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a Gmail filter creation preview (lot I).

    Criteria first (who it matches), then every requested action as a
    localized sentence — unrequested actions are not mentioned, so the user
    reads exactly what the filter will do and nothing else.
    """
    criteria = content.get("criteria") or {}
    lines: list[str] = []
    if criteria.get("from"):
        lines.append(_row(lbl, "from", criteria["from"]))
    if criteria.get("subject"):
        lines.append(_row(lbl, "subject", criteria["subject"]))
    if criteria.get("query"):
        lines.append(_row(lbl, "query", criteria["query"]))
    if content.get("label_name"):
        lines.append(_row(lbl, "label", content["label_name"]))
    if content.get("archive"):
        lines.append(_note(lbl["filter_archive"]))
    if content.get("mark_as_read"):
        lines.append(_note(lbl["filter_mark_read"]))
    return lines


def _render_scheduled_action(
    content: dict[str, Any], lbl: dict[str, str], format_dt: _FormatDt
) -> list[str]:
    """Render a recurring-automation preview (title, schedule, instruction).

    ``schedule_human`` is pre-localized at draft creation (the tool knows the
    user's locale); no datetime row — the schedule line carries the timing.
    """
    title = content.get("title") or "?"
    schedule = content.get("schedule_human", "")
    instruction = content.get("action_prompt", "")

    lines = [_row(lbl, "title", title)]
    if schedule:
        lines.append(_row(lbl, "schedule", schedule))
    if instruction:
        lines.append(_row(lbl, "instruction", instruction))
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
    DraftType.TICKET_DELETE: _render_ticket_delete,
    DraftType.PHONE_CALL: _render_phone_call,
    DraftType.TOOL_CALL: _render_tool_call,
    DraftType.SCHEDULED_ACTION: _render_scheduled_action,
    DraftType.DEVOPS_TASK: _render_devops_task,
    DraftType.PEER_MESSAGE: _render_peer_message,
    DraftType.VACATION_RESPONDER: _render_vacation_responder,
    DraftType.EMAIL_FILTER: _render_email_filter,
    DraftType.SPREADSHEET_WRITE: _render_spreadsheet_write,
    DraftType.DOCUMENT_APPEND: _render_document_append,
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
    # Stripped: a block carries its own blank lines, so a preview ending on
    # one would trail a gap — and every preview used to OPEN with one.
    return "\n".join(renderer(draft.content, lbl, format_dt)).strip()


def card_title(draft: Draft, user_language: str = "fr") -> str:
    """What a confirmation card is headed with: the thing's own name.

    Read from the display registry's ``item_label_fields`` — the same field a
    batch row is labelled by, so the chat, the ticket and a FOR_EACH list name
    a draft identically. A draft with nothing in that field is titled by its
    summary (« Email à ? ») rather than by a lone question mark.

    Args:
        draft: The draft to name.
        user_language: Language of the summary fallback.

    Returns:
        A one-line title, never empty.
    """
    from src.domains.agents.drafts.display import get_draft_display_config, resolve_nested_value
    from src.domains.agents.drafts.summary_renderer import render_summary

    config = get_draft_display_config(draft.type.value)
    for key in config.item_label_fields if config else ():
        value = resolve_nested_value(draft.content, key) if "." in key else draft.content.get(key)
        if value:
            return " ".join(str(value).split())
    return render_summary(draft, user_language)


def render_confirmation_card(
    draft: Draft,
    user_language: str = "fr",
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> str:
    """The card a person confirms: the thing's emoji and name over its preview.

    ONE author for the form (ADR-274's rule, applied to the HITL card in lot
    14): the model used to write this card under a prompt describing it, so
    its shape was whatever the model produced that day — measured 2026-09-09,
    fields spaced out as paragraphs and a `---` rendered as three characters —
    and the ticket then appended the renderer's own preview to it, showing the
    e-mail twice. The card is now rendered here, streamed before the model's
    first token, and the model is asked for the question alone.

    Args:
        draft: The draft to show.
        user_language: Language for the labels (fr, en, es, de, it, zh-CN).
        user_timezone: The person's IANA timezone for the dates.

    Returns:
        ``{emoji} **{title}**``, a blank line, the detailed preview — Markdown
        only, stripped at both ends.
    """
    from src.domains.agents.drafts.display import get_draft_emoji

    header = f"{get_draft_emoji(draft.type.value)} **{card_title(draft, user_language)}**".strip()
    preview = render_detailed_preview(draft, user_language, user_timezone)
    return f"{header}\n\n{preview}".strip()


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
    "card_title",
    "render_confirmation_card",
    "render_detailed_preview",
]
