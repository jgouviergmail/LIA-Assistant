"""Draft Display Registry.

Centralized declarative configuration for post-execution rendering of every
``DraftType``. This is the single source of truth consumed by the response
node when formatting the result of a HITL draft confirmation (single or
batch). Adding a new ``DraftType`` requires adding an entry here — the
startup-time and CI assertions in :func:`assert_registry_completeness`
prevent the type from shipping without a display configuration.

The registry encodes four orthogonal concerns per draft type:

1. ``emoji`` — the domain emoji shown in the result header (composite emojis
   like trash+calendar are preserved to mark destructive variants).
2. ``item_label_fields`` / ``item_secondary_datetime_key`` — fields read from
   ``_draft_content`` to render each item line in a batch result, plus an
   optional datetime field appended for context.
3. ``detail_fields`` — ordered list of fields rendered in the single-confirm
   detailed view, with their row emoji and the i18n label key.
4. ``noun_key`` / ``verb_past_key`` — keys consumed by
   :func:`src.core.i18n_drafts.compose_result_header` to build the localized
   header (e.g. ``"3 rappels supprimés"``) with proper gender/number
   agreement per language.

Architecture invariants:
- Every ``DraftType`` value MUST have an entry in
  :data:`DRAFT_DISPLAY_REGISTRY`. Enforced by
  :func:`assert_registry_completeness` (called from ``main.py`` lifespan
  startup and by a unit test).
- ``noun_key`` and ``verb_past_key`` MUST reference entries that exist in
  ``DRAFT_RESULT_NOUNS`` / ``DRAFT_RESULT_VERBS_PAST`` for **all** supported
  languages. Enforced by ``test_display_registry.py``.

Created: 2026-05-17 (ADR-085: Draft Display Registry)
"""

from dataclasses import dataclass
from typing import NamedTuple

from src.domains.agents.drafts.models import DraftType


class DraftDisplayField(NamedTuple):
    """One field rendered in the single-confirm detailed view.

    Attributes:
        content_key: Key in the draft ``_draft_content`` dict. Nested keys
            are supported via dotted notation (e.g. ``"file.name"`` resolves
            to ``content["file"]["name"]``).
        emoji: Single-character emoji shown at the start of the row.
        label_key: Lookup key in ``DRAFT_PREVIEW_LABELS`` for the localized
            field label (e.g. ``"subject"``, ``"event"``, ``"date"``).
        is_datetime: When True, the value is formatted via
            :func:`src.core.time_utils.format_datetime_for_display` using the
            user's locale and timezone.
    """

    content_key: str
    emoji: str
    label_key: str
    is_datetime: bool = False


@dataclass(frozen=True)
class DraftDisplayConfig:
    """Declarative display configuration for one ``DraftType``.

    See module docstring for the rationale and invariants.

    Attributes:
        emoji: Domain emoji shown in the result header.
        item_label_fields: Priority-ordered tuple of keys tried to extract a
            human-readable label for each row in a batch result. The first
            non-empty match wins. Dotted notation is supported for nested
            dicts.
        item_secondary_datetime_key: Optional key whose value is appended to
            the batch row as a localized datetime (e.g. ``" — 16 mai à
            14h00"``). ``None`` disables the suffix.
        detail_fields: Ordered fields rendered in the single-confirm detailed
            view. May be empty for types that do not need a detailed payload.
        noun_key: Key in ``DRAFT_RESULT_NOUNS`` for the noun displayed in the
            header (e.g. ``"reminder"``, ``"email"``).
        verb_past_key: Key in ``DRAFT_RESULT_VERBS_PAST`` for the past
            participle (e.g. ``"deleted"``, ``"sent"``).
        item_recipient_field: Optional key whose value is shown as the
            recipient in a batch row for send-type drafts (email / reply /
            forward), rendered as ``"{Noun} {à} {recipient} : {label}"``. This
            surfaces the WHO of the action — the critical discriminating field
            when a batch sends to several people (two rows would otherwise be
            identical). ``None`` (the default) disables the recipient prefix;
            delete/create/update types leave it unset. Dotted notation is
            supported for nested dicts.
    """

    emoji: str
    item_label_fields: tuple[str, ...]
    item_secondary_datetime_key: str | None
    detail_fields: tuple[DraftDisplayField, ...]
    noun_key: str
    verb_past_key: str
    # Defaulted field MUST stay last (dataclass ordering): a non-default field
    # cannot follow a defaulted one. Every existing entry constructs the config
    # with keyword args, so this addition is backward-compatible.
    item_recipient_field: str | None = None


# =============================================================================
# REGISTRY
# =============================================================================
# One entry per DraftType. assert_registry_completeness() enforces exhaustivity.

DRAFT_DISPLAY_REGISTRY: dict[DraftType, DraftDisplayConfig] = {
    # ------------------------------------------------------------------ Email
    DraftType.EMAIL: DraftDisplayConfig(
        emoji="\U0001f4e7",  # 📧
        item_label_fields=("subject",),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("to", "\U0001f4e7", "to"),
            DraftDisplayField("cc", "\U0001f4cb", "cc"),
            DraftDisplayField("subject", "\U0001f4dd", "subject"),
            DraftDisplayField("body", "\U0001f4ac", "body"),
        ),
        noun_key="email",
        verb_past_key="sent",
        item_recipient_field="to",  # show WHO each email goes to in a batch row
    ),
    DraftType.EMAIL_REPLY: DraftDisplayConfig(
        emoji="↩️",  # ↩️
        item_label_fields=("subject",),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("to", "\U0001f4e7", "to"),
            DraftDisplayField("subject", "\U0001f4dd", "subject"),
            DraftDisplayField("body", "\U0001f4ac", "body"),
            DraftDisplayField("original_from", "↩️", "from"),
        ),
        noun_key="email",
        verb_past_key="sent",
        item_recipient_field="to",
    ),
    DraftType.EMAIL_FORWARD: DraftDisplayConfig(
        emoji="↪️",  # ↪️
        item_label_fields=("subject",),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("to", "\U0001f4e7", "to"),
            DraftDisplayField("cc", "\U0001f4cb", "cc"),
            DraftDisplayField("subject", "\U0001f4dd", "subject"),
            DraftDisplayField("body", "\U0001f4ac", "body"),
        ),
        noun_key="email",
        verb_past_key="sent",
        item_recipient_field="to",
    ),
    DraftType.EMAIL_DELETE: DraftDisplayConfig(
        emoji="\U0001f5d1️\U0001f4e7",  # 🗑️📧
        item_label_fields=("subject",),
        item_secondary_datetime_key="date",
        detail_fields=(
            DraftDisplayField("from_addr", "↩️", "from"),
            DraftDisplayField("subject", "\U0001f4dd", "subject"),
            DraftDisplayField("date", "\U0001f4c5", "date", is_datetime=True),
        ),
        noun_key="email",
        verb_past_key="deleted",
    ),
    # ------------------------------------------------------------------ Event
    DraftType.EVENT: DraftDisplayConfig(
        emoji="\U0001f4c5",  # 📅
        item_label_fields=("summary",),
        item_secondary_datetime_key="start_datetime",
        detail_fields=(
            DraftDisplayField("summary", "\U0001f4c5", "event"),
            DraftDisplayField("start_datetime", "\U0001f550", "start", is_datetime=True),
            DraftDisplayField("end_datetime", "\U0001f3c1", "end", is_datetime=True),
            DraftDisplayField("location", "\U0001f4cd", "location"),
            DraftDisplayField("attendees", "\U0001f465", "attendees"),
            DraftDisplayField("description", "\U0001f4dd", "body"),
        ),
        noun_key="event",
        verb_past_key="created",
    ),
    DraftType.EVENT_UPDATE: DraftDisplayConfig(
        emoji="\U0001f4dd\U0001f4c5",  # 📝📅
        item_label_fields=("summary",),
        item_secondary_datetime_key="start_datetime",
        detail_fields=(
            DraftDisplayField("summary", "\U0001f4c5", "event"),
            DraftDisplayField("start_datetime", "\U0001f550", "start", is_datetime=True),
            DraftDisplayField("end_datetime", "\U0001f3c1", "end", is_datetime=True),
            DraftDisplayField("location", "\U0001f4cd", "location"),
            DraftDisplayField("attendees", "\U0001f465", "attendees"),
        ),
        noun_key="event",
        verb_past_key="updated",
    ),
    DraftType.EVENT_DELETE: DraftDisplayConfig(
        emoji="\U0001f5d1️\U0001f4c5",  # 🗑️📅
        item_label_fields=("summary", "event.summary"),
        item_secondary_datetime_key="start_datetime",
        detail_fields=(
            DraftDisplayField("summary", "\U0001f4c5", "event"),
            DraftDisplayField("start_datetime", "\U0001f550", "start", is_datetime=True),
        ),
        noun_key="event",
        verb_past_key="deleted",
    ),
    # ---------------------------------------------------------------- Contact
    DraftType.CONTACT: DraftDisplayConfig(
        emoji="\U0001f464",  # 👤
        item_label_fields=("name",),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("name", "\U0001f464", "contact"),
            DraftDisplayField("email", "\U0001f4e7", "email"),
            DraftDisplayField("phone", "\U0001f4f1", "phone"),
            DraftDisplayField("organization", "\U0001f3e2", "organization"),
            DraftDisplayField("address", "\U0001f4cd", "location"),
            DraftDisplayField("notes", "\U0001f4dd", "body"),
        ),
        noun_key="contact",
        verb_past_key="created",
    ),
    DraftType.CONTACT_UPDATE: DraftDisplayConfig(
        emoji="\U0001f4dd\U0001f464",  # 📝👤
        item_label_fields=("name",),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("name", "\U0001f464", "contact"),
            DraftDisplayField("email", "\U0001f4e7", "email"),
            DraftDisplayField("phone", "\U0001f4f1", "phone"),
            DraftDisplayField("organization", "\U0001f3e2", "organization"),
        ),
        noun_key="contact",
        verb_past_key="updated",
    ),
    DraftType.CONTACT_DELETE: DraftDisplayConfig(
        emoji="\U0001f5d1️\U0001f464",  # 🗑️👤
        item_label_fields=("name", "contact.names.0.displayName"),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("name", "\U0001f464", "contact"),
            DraftDisplayField("email", "\U0001f4e7", "email"),
        ),
        noun_key="contact",
        verb_past_key="deleted",
    ),
    # ------------------------------------------------------------------- Task
    DraftType.TASK: DraftDisplayConfig(
        emoji="✅",  # ✅
        item_label_fields=("title",),
        item_secondary_datetime_key="due",
        detail_fields=(
            DraftDisplayField("title", "✅", "task"),
            DraftDisplayField("due", "\U0001f4c5", "due", is_datetime=True),
            DraftDisplayField("notes", "\U0001f4dd", "body"),
        ),
        noun_key="task",
        verb_past_key="created",
    ),
    DraftType.TASK_UPDATE: DraftDisplayConfig(
        emoji="\U0001f4dd✅",  # 📝✅
        item_label_fields=("title",),
        item_secondary_datetime_key="due",
        detail_fields=(
            DraftDisplayField("title", "✅", "task"),
            DraftDisplayField("due", "\U0001f4c5", "due", is_datetime=True),
            DraftDisplayField("notes", "\U0001f4dd", "body"),
        ),
        noun_key="task",
        verb_past_key="updated",
    ),
    DraftType.TASK_DELETE: DraftDisplayConfig(
        emoji="\U0001f5d1️✅",  # 🗑️✅
        item_label_fields=("title",),
        item_secondary_datetime_key="due",
        detail_fields=(
            DraftDisplayField("title", "✅", "task"),
            DraftDisplayField("due", "\U0001f4c5", "due", is_datetime=True),
        ),
        noun_key="task",
        verb_past_key="deleted",
    ),
    # --------------------------------------------------------- File / Label
    DraftType.FILE_DELETE: DraftDisplayConfig(
        emoji="\U0001f5d1️\U0001f4c1",  # 🗑️📁
        item_label_fields=("file.name", "name"),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("file.name", "\U0001f4c1", "file"),
            DraftDisplayField("file.mimeType", "\U0001f4dd", "type"),
        ),
        noun_key="file",
        verb_past_key="deleted",
    ),
    DraftType.LABEL_DELETE: DraftDisplayConfig(
        emoji="\U0001f5d1️\U0001f3f7️",  # 🗑️🏷️
        item_label_fields=("label_name",),
        item_secondary_datetime_key=None,
        detail_fields=(DraftDisplayField("label_name", "\U0001f3f7️", "label"),),
        noun_key="label",
        verb_past_key="deleted",
    ),
    # --------------------------------------------------------------- Reminder
    DraftType.REMINDER_DELETE: DraftDisplayConfig(
        emoji="\U0001f514",  # 🔔
        item_label_fields=("content",),
        item_secondary_datetime_key="trigger_at",
        detail_fields=(
            DraftDisplayField("content", "\U0001f514", "event"),
            DraftDisplayField("trigger_at", "\U0001f550", "date", is_datetime=True),
        ),
        noun_key="reminder",
        verb_past_key="deleted",
    ),
    # -------------------------------------------------------------- Telephony
    DraftType.PHONE_CALL: DraftDisplayConfig(
        emoji="\U0001f4de",  # 📞
        item_label_fields=("callee_name",),
        item_secondary_datetime_key=None,
        detail_fields=(
            DraftDisplayField("callee_name", "\U0001f4de", "callee"),
            DraftDisplayField("callee_phone", "\U0001f4f1", "phone"),
            DraftDisplayField("objective", "\U0001f3af", "objective"),
        ),
        noun_key="call",
        verb_past_key="placed",
    ),
}


# =============================================================================
# PUBLIC API
# =============================================================================


def get_draft_display_config(draft_type: str) -> DraftDisplayConfig | None:
    """Look up the display config for a draft type string.

    Resolution order:

    1. Exact match against a ``DraftType`` value.
    2. ``None`` if no entry matches (caller decides on fallback behavior).

    Args:
        draft_type: Draft type identifier (e.g. ``"reminder_delete"``,
            ``"email"``). Accepts any string for safety — unknown values
            return ``None`` rather than raising.

    Returns:
        The matching :class:`DraftDisplayConfig`, or ``None`` if the input
        does not correspond to a known ``DraftType``.

    Example:
        >>> cfg = get_draft_display_config("reminder_delete")
        >>> cfg.emoji
        '\U0001f514'
    """
    try:
        return DRAFT_DISPLAY_REGISTRY[DraftType(draft_type)]
    except (KeyError, ValueError):
        return None


def get_draft_emoji(draft_type: str) -> str:
    """Return the domain emoji for a draft type, or empty string if unknown.

    Thin convenience wrapper around :func:`get_draft_display_config` used by
    code that only needs the emoji (e.g.
    :meth:`HitlMessages.get_draft_emoji`).

    Args:
        draft_type: Draft type identifier.

    Returns:
        The configured emoji, or ``""`` for unknown types.
    """
    cfg = get_draft_display_config(draft_type)
    return cfg.emoji if cfg else ""


def resolve_nested_value(content: dict, dotted_key: str) -> object | None:
    """Resolve a dotted key against a nested dict/list structure.

    Walks ``content`` following the dotted path. Numeric path segments are
    interpreted as list indices. Returns ``None`` if any segment is missing
    or the path leads to a non-traversable value.

    Args:
        content: The root dict to traverse.
        dotted_key: Path expression like ``"file.name"`` or
            ``"contact.names.0.displayName"``.

    Returns:
        The resolved value, or ``None`` if any segment cannot be resolved.

    Example:
        >>> resolve_nested_value({"file": {"name": "report.pdf"}}, "file.name")
        'report.pdf'
        >>> resolve_nested_value({"a": [{"b": 1}]}, "a.0.b")
        1
        >>> resolve_nested_value({"a": 1}, "a.b") is None
        True
    """
    current: object = content
    for segment in dotted_key.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list):
            try:
                idx = int(segment)
            except ValueError:
                return None
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                return None
        else:
            return None
        if current is None:
            return None
    return current


def assert_registry_completeness() -> None:
    """Assert every ``DraftType`` value has a display configuration.

    Called from ``main.py`` lifespan startup so a missing entry refuses to
    boot the application, and from a unit test so CI catches it before
    merge.

    Raises:
        AssertionError: If any ``DraftType`` value is missing from
            :data:`DRAFT_DISPLAY_REGISTRY`, listing the missing types.
    """
    missing = {t for t in DraftType if t not in DRAFT_DISPLAY_REGISTRY}
    if missing:
        names = ", ".join(sorted(t.value for t in missing))
        raise AssertionError(
            f"DRAFT_DISPLAY_REGISTRY is missing {len(missing)} DraftType(s): {names}. "
            "Every DraftType must declare a DraftDisplayConfig — see "
            "src/domains/agents/drafts/display.py."
        )


__all__ = [
    "DraftDisplayConfig",
    "DraftDisplayField",
    "DRAFT_DISPLAY_REGISTRY",
    "assert_registry_completeness",
    "get_draft_display_config",
    "get_draft_emoji",
    "resolve_nested_value",
]
