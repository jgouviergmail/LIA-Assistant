"""Draft summary renderer: the ONE line that names what is about to happen.

The summary titles a HITL confirmation — « 📄 Brouillon créé: <this> » — and is
what an LLM reads back when it explains a pending action. Extracted from the
``if``-cascade in ``Draft.get_summary`` (ADR-276, lot 13), for the reason its
sibling :mod:`~src.domains.agents.drafts.preview_renderer` was extracted before
it: a cascade ending in a fallback is a registry nobody can check.

And the fallback was reached. Measured 2026-09-09: **9 of the 26 draft types
had no branch at all** — a ticket deletion, a tool call, a spreadsheet write, a
message to a peer — so the confirmation asking the person to approve one read
``Draft (ticket_delete)``: a Python enum value, in English, in every language.

Two properties close that class of defect for good:

- **a dispatch table**, checked at boot by
  :func:`assert_summary_renderer_completeness` (ADR-085 pattern, exactly like
  :func:`~src.domains.agents.drafts.preview_renderer.assert_preview_renderer_completeness`)
  — a new ``DraftType`` with no entry refuses to start the application;
- **a renderer names a LABEL, it does not format one**: it returns the i18n key
  and its parameters, so no renderer can accidentally ship a language of its
  own, and the six translations stay where all the others live.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n_drafts import get_draft_summary_label
from src.domains.agents.drafts.models import DraftType

if TYPE_CHECKING:
    from src.domains.agents.drafts.models import Draft

# Formats an ISO datetime string for display, or "" for a falsy input. Bound
# to the user's language/timezone by render_summary().
_FormatDt = Callable[[str | None], str]

#: What a renderer answers: the i18n key of the sentence, and its parameters.
_SummarySpec = tuple[str, dict[str, str]]

#: One renderer per DraftType: (content, format_dt) -> (label key, parameters).
_SummaryRenderer = Callable[[dict[str, Any], _FormatDt], _SummarySpec]

#: What a missing value reads as, shared with the preview renderer's rows.
_UNKNOWN = "?"


def _text(content: dict[str, Any], key: str, default: str = _UNKNOWN) -> str:
    """Read one content field as text, with the shared fallback.

    Args:
        content: The draft content.
        key: The field to read.
        default: What an absent or empty field reads as.

    Returns:
        The field as a string, never empty.
    """
    value = content.get(key)
    if isinstance(value, (list, tuple, set, frozenset)):
        value = ", ".join(str(item) for item in value)
    text = str(value) if value not in (None, "") else ""
    return text or default


def _display_name(names: Any) -> str:
    """The primary display name of a Google People ``names`` list.

    Args:
        names: The list as stored — possibly absent, null, or empty.

    Returns:
        The first entry's display name, or the shared unknown mark.
    """
    if not names:
        return _UNKNOWN
    first = names[0]
    return first.get("displayName", _UNKNOWN) if isinstance(first, dict) else _UNKNOWN


# =============================================================================
# PER-TYPE RENDERERS
# =============================================================================


def _summarize_email(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """An email about to be sent."""
    return "email_to", {"to": _text(content, "to"), "subject": _text(content, "subject")}


def _summarize_email_reply(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A reply about to be sent."""
    return "email_reply_to", {"to": _text(content, "to"), "subject": _text(content, "subject")}


def _summarize_email_forward(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A forward about to be sent."""
    return "email_forward_to", {"to": _text(content, "to"), "subject": _text(content, "subject")}


def _summarize_email_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """An email about to be deleted."""
    return "email_delete", {"subject": _text(content, "subject")}


def _summarize_event(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """An event about to be created."""
    start_raw = content.get("start_datetime", "")
    return "event_create", {
        "summary": _text(content, "summary"),
        "start": format_dt(start_raw) if start_raw else _UNKNOWN,
    }


def _summarize_event_update(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """An event about to be modified — its own title, else the current one."""
    summary = content.get("summary") or (content.get("current_event") or {}).get(
        "summary", _UNKNOWN
    )
    return "event_update", {"summary": str(summary)}


def _summarize_event_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """An event about to be deleted."""
    return "event_delete", {"summary": (content.get("event") or {}).get("summary", _UNKNOWN)}


def _summarize_contact(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A contact about to be created."""
    return "contact_create", {"name": _text(content, "name")}


def _summarize_contact_update(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A contact about to be modified — its own name, else the current one."""
    name = content.get("name") or _display_name(
        (content.get("current_contact") or {}).get("names", [])
    )
    return "contact_update", {"name": str(name)}


def _summarize_contact_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A contact about to be deleted."""
    return "contact_delete", {
        "name": _display_name((content.get("contact") or {}).get("names", []))
    }


def _summarize_task(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A task about to be created."""
    return "task_create", {"title": _text(content, "title")}


def _summarize_task_update(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A task about to be modified — its own title, else the current one."""
    title = content.get("title") or (content.get("current_task") or {}).get("title", _UNKNOWN)
    return "task_update", {"title": str(title)}


def _summarize_task_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A task about to be deleted."""
    return "task_delete", {"title": _text(content, "title")}


def _summarize_file_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A Drive file about to be deleted."""
    return "file_delete", {"name": (content.get("file") or {}).get("name", _UNKNOWN)}


def _summarize_label_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A Gmail label about to be deleted."""
    return "label_delete", {"name": _text(content, "label_name")}


def _summarize_reminder_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A reminder about to be deleted."""
    return "reminder_delete", {"content": _text(content, "content")}


def _summarize_phone_call(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A call about to be placed."""
    return "phone_call", {
        "name": _text(content, "callee_name"),
        "objective": _text(content, "objective"),
    }


def _summarize_scheduled_action(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A recurring automation about to be created."""
    return "scheduled_action", {"title": _text(content, "title")}


def _summarize_devops_task(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A task about to run on a remote server."""
    return "devops_task", {"server": _text(content, "server"), "task": _text(content, "task")}


def _summarize_peer_message(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A message about to be relayed to a connected peer."""
    return "peer_message", {"name": _text(content, "recipient_name")}


def _summarize_vacation_responder(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A holiday auto-reply about to be switched on, or off.

    Two sentences rather than one with a state in it: « will be disabled » has
    no subject to name, and a summary that reads « Absence: (none) » says less
    than the sentence it replaced.
    """
    if not content.get("enable", False):
        return "vacation_responder_off", {}
    return "vacation_responder_on", {"subject": _text(content, "subject")}


def _summarize_email_filter(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A Gmail filter about to be created.

    Named by what it MATCHES: a filter's identity for its author is the mail it
    catches, and the criteria are the one field it always carries.
    """
    criteria = content.get("criteria") or {}
    matched = criteria.get("from") or criteria.get("subject") or criteria.get("query") or _UNKNOWN
    return "email_filter", {"criteria": str(matched)}


def _summarize_tool_call(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A capability about to run unconfirmed (ADR-263).

    The label is what the person recognises (``era: cancel subscription``); the
    raw tool name is the fallback, and both are third-party text.
    """
    label = content.get("tool_label") or content.get("tool_name") or _UNKNOWN
    return "tool_call", {"tool": str(label)}


def _summarize_spreadsheet_write(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """Rows about to land in a spreadsheet."""
    return "spreadsheet_write", {
        "file": _text(content, "spreadsheet_title"),
        "sheet": _text(content, "sheet_name"),
    }


def _summarize_document_append(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """Text about to be appended to a document."""
    return "document_append", {"file": _text(content, "document_title")}


def _summarize_ticket_delete(content: dict[str, Any], format_dt: _FormatDt) -> _SummarySpec:
    """A workboard ticket about to be deleted."""
    return "ticket_delete", {"title": _text(content, "title")}


# =============================================================================
# DISPATCH
# =============================================================================

_SUMMARY_RENDERERS: dict[DraftType, _SummaryRenderer] = {
    DraftType.EMAIL: _summarize_email,
    DraftType.EMAIL_REPLY: _summarize_email_reply,
    DraftType.EMAIL_FORWARD: _summarize_email_forward,
    DraftType.EMAIL_DELETE: _summarize_email_delete,
    DraftType.EVENT: _summarize_event,
    DraftType.EVENT_UPDATE: _summarize_event_update,
    DraftType.EVENT_DELETE: _summarize_event_delete,
    DraftType.CONTACT: _summarize_contact,
    DraftType.CONTACT_UPDATE: _summarize_contact_update,
    DraftType.CONTACT_DELETE: _summarize_contact_delete,
    DraftType.TASK: _summarize_task,
    DraftType.TASK_UPDATE: _summarize_task_update,
    DraftType.TASK_DELETE: _summarize_task_delete,
    DraftType.FILE_DELETE: _summarize_file_delete,
    DraftType.LABEL_DELETE: _summarize_label_delete,
    DraftType.REMINDER_DELETE: _summarize_reminder_delete,
    DraftType.PHONE_CALL: _summarize_phone_call,
    DraftType.SCHEDULED_ACTION: _summarize_scheduled_action,
    DraftType.DEVOPS_TASK: _summarize_devops_task,
    DraftType.PEER_MESSAGE: _summarize_peer_message,
    DraftType.VACATION_RESPONDER: _summarize_vacation_responder,
    DraftType.EMAIL_FILTER: _summarize_email_filter,
    DraftType.TOOL_CALL: _summarize_tool_call,
    DraftType.SPREADSHEET_WRITE: _summarize_spreadsheet_write,
    DraftType.DOCUMENT_APPEND: _summarize_document_append,
    DraftType.TICKET_DELETE: _summarize_ticket_delete,
}


def render_summary(
    draft: Draft,
    user_language: str = "fr",
    user_timezone: str | None = None,
) -> str:
    """Render the one-line summary of a draft.

    Args:
        draft: The draft to name.
        user_language: Language for the sentence (fr, en, es, de, it, zh-CN).
        user_timezone: IANA timezone for datetime formatting; defaults to the
            one stored in the draft content, then to the instance default.

    Returns:
        The localized sentence, or the draft type's raw value for a type with
        no renderer — defense in depth only, since the startup completeness
        assert makes that unreachable for a ``DraftType``.
    """
    from src.core.time_utils import format_datetime_for_display

    timezone = user_timezone or draft.content.get("user_timezone", DEFAULT_USER_DISPLAY_TIMEZONE)

    def format_dt(dt_str: str | None) -> str:
        """Format an ISO datetime string for display."""
        if not dt_str:
            return ""
        return format_datetime_for_display(dt_str, timezone, user_language, include_time=True)

    renderer = _SUMMARY_RENDERERS.get(draft.type)
    if renderer is None:
        return f"Draft ({draft.type.value})"
    label_key, parameters = renderer(draft.content, format_dt)
    return get_draft_summary_label(label_key, user_language, **parameters)


def assert_summary_renderer_completeness() -> None:
    """Assert every ``DraftType`` value has a registered summary renderer.

    Called from the lifespan startup so a missing entry refuses to boot the
    application (ADR-085 pattern), and from a unit test so CI catches it first.

    Raises:
        AssertionError: If any ``DraftType`` is missing from
            :data:`_SUMMARY_RENDERERS`, listing the missing types.
    """
    missing = {t for t in DraftType if t not in _SUMMARY_RENDERERS}
    if missing:
        names = ", ".join(sorted(t.value for t in missing))
        raise AssertionError(
            f"_SUMMARY_RENDERERS is missing {len(missing)} DraftType(s): {names}. "
            "Every DraftType must register a summary renderer — see "
            "src/domains/agents/drafts/summary_renderer.py."
        )


__all__ = [
    "assert_summary_renderer_completeness",
    "render_summary",
]
