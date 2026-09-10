"""What a person reads once they confirmed: the execution result (ADR-276 lot 13).

A draft is shown twice — the card that asks (``preview_renderer``) and this,
the outcome of what they approved. Lot 13 gave the card ONE vocabulary,
Markdown, and left this one in HTML: it opened every field with ``<br/>`` AND
joined the fields with ``\\n``, so the chat — which renders Markdown with no
hard-break plugin and keeps newlines — showed a blank line between every field
(measured on production, 2026-09-09), and any surface rendering neither
vocabulary read the tag out as typed.

Both surfaces now build their rows with
:mod:`~src.domains.agents.drafts.markdown_grammar`, so the same email cannot
read as a clean list before confirmation and as a stack of blank lines after.

Two rules the shape obeys, each paid for:

- **The renderer owns its own edges.** It used to open on ``\\n\\n`` and rely on
  its caller's ``.strip()``; a second caller would have inherited the blank
  lines. Nothing here opens or closes on whitespace.
- **A message that formats itself is left alone.** ``DRAFT_SUCCESS_MESSAGES``
  is mostly plain text, which the header emphasises — but ``phone_call`` ships
  its own ``**name**``, and wrapping that in another pair renders as broken
  markup. One predicate decides, rather than a special case per type.

This module reads ``DRAFT_DISPLAY_REGISTRY`` (ADR-085) for the per-``DraftType``
display configuration: domain emoji, label fields, optional contextual
datetime, detailed-view fields, plus the noun/verb keys that compose a localized
header like ``"3 rappels supprimés"`` with proper gender/number agreement.

Extracted from ``nodes/response_node.py`` (2026-09-10): the node is a
frozen-size, maximum-complexity hotspot and this is a presentation concern
belonging beside the preview it must agree with.
"""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import _, normalize_language
from src.core.i18n_drafts import (
    compose_result_header,
    get_draft_preview_labels,
)
from src.domains.agents.drafts.display import (
    get_draft_display_config,
    resolve_nested_value,
)
from src.domains.agents.drafts.markdown_grammar import (
    labelled_block,
    labelled_row,
    plain_row,
    readable,
)
from src.domains.agents.drafts.models import DraftAction
from src.infrastructure.observability.logging import get_logger

if TYPE_CHECKING:
    from src.core.i18n import Language
    from src.domains.agents.drafts.display import DraftDisplayConfig

__all__ = ["render_execution_result"]

logger = get_logger(__name__)

#: Body-like fields carry paragraphs; a confirmation states what was done, it
#: does not reproduce the whole message.
_TEXT_FIELDS = frozenset({"body", "description", "notes"})
_TEXT_FIELD_MAX_CHARS = 200

#: A batch row names its item; a 300-character title would push the outcome
#: off the screen.
_ITEM_LABEL_MAX_CHARS = 60

#: What the reader is told, per status.
_STATUS_MARKS = {
    "success": "✅",
    "cancelled": "🚫",
    "partial_error": "⚠️",
    "error": "❌",
}

_URL_PREFIXES = ("http://", "https://")


def _headline(domain_emoji: str, mark: str, message: str) -> str:
    """The first line: what happened, named once.

    The message is emphasised so it reads as the title of the rows under it —
    unless it already carries emphasis of its own, in which case a second pair
    would nest and render as literal asterisks (``phone_call``). An empty
    message emphasises nothing rather than emitting ``****``.

    Args:
        domain_emoji: The draft family's emoji, or ``""`` for an unknown type.
        mark: The outcome mark (✅ 🚫 ⚠️ ❌).
        message: The localized outcome sentence.

    Returns:
        The headline, with no leading or trailing whitespace.
    """
    text = message.strip()
    if text and "**" not in text:
        text = f"**{text}**"
    return " ".join(part for part in (domain_emoji, mark, text) if part)


def _detail_value(
    field: Any,
    draft: dict[str, Any],
    data: dict[str, Any],
    user_tz: str,
    user_lang: Language,
) -> str | None:
    """Resolve and format ONE detail field, or None when it has nothing to say.

    Args:
        field: The registry's :class:`DraftDisplayField`.
        draft: The stored draft content.
        data: The execution result's data dict (fallback source).
        user_tz: The person's IANA timezone.
        user_lang: Their language.

    Returns:
        The value as text, or None when the field is absent or blank — a label
        above emptiness states less than silence.
    """
    from src.core.time_utils import format_datetime_for_display

    value = (
        resolve_nested_value(draft, field.content_key)
        if "." in field.content_key
        else (draft.get(field.content_key) or data.get(field.content_key))
    )
    if value is None or not str(value).strip():
        return None

    # ``readable`` and not ``str``: a recipient list used to reach this
    # surface as ``['paul@example.org']`` while the confirmation CARD, which
    # shares this grammar, spelled it out. Same draft, two spellings.
    text = readable(value)
    if field.is_datetime and isinstance(value, str) and "T" in value:
        # Keep raw ISO if formatting fails.
        with suppress(ValueError, TypeError):
            text = format_datetime_for_display(value, user_tz, user_lang, include_time=True)

    last_key = field.content_key.rsplit(".", 1)[-1]
    if last_key in _TEXT_FIELDS and len(text) > _TEXT_FIELD_MAX_CHARS:
        text = text[:_TEXT_FIELD_MAX_CHARS] + "…"
    return text


def _detail_rows(
    config: DraftDisplayConfig | None,
    draft: dict[str, Any],
    data: dict[str, Any],
    user_lang: Language,
    user_tz: str,
) -> list[str]:
    """One Markdown row per detail field the registry declares.

    Args:
        config: The type's display configuration, or None for an unknown type.
        draft: The stored draft content.
        data: The execution result's data dict.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        The rows, in registry order, plus the permalink row when one exists.
    """
    labels = get_draft_preview_labels(user_lang)
    separator = labels["separator"]
    rows: list[str] = []
    blocks: list[str] = []

    for field in config.detail_fields if config else ():
        text = _detail_value(field, draft, data, user_tz, user_lang)
        if text is None:
            continue
        label = labels.get(field.label_key, field.content_key)
        if text.startswith(_URL_PREFIXES):
            # A URL-valued field (a conference link) reads as a link, never as
            # a raw URL dump.
            rows.append(plain_row(f"{field.emoji} [{label}]({text})"))
        elif "\n" in text:
            # A value carrying its own paragraphs cannot live in a list item:
            # the second paragraph escapes the item and the list ends there.
            # The confirmation CARD already renders such a value as its own
            # block, so the outcome does too — otherwise the same mail reads
            # one way before confirmation and another after (measured on a
            # two-paragraph body, which is most of them).
            blocks.append(labelled_block(f"{field.emoji} {label}", text))
        else:
            rows.append(labelled_row(f"{field.emoji} {label}", separator, text))

    html_link = data.get("html_link")
    if html_link:
        link_label = _("Link", user_lang)
        rows.append(plain_row(f"🔗 [{link_label}]({html_link})"))
    # Blocks last: a row appended after one would land inside its paragraph.
    return rows + blocks


def _batch_locale(batch_results: list[dict[str, Any]]) -> tuple[Language, str]:
    """The language and timezone any item of the batch carries.

    Args:
        batch_results: The per-item results.

    Returns:
        ``(language, timezone)``, falling back to the app defaults.
    """
    raw_lang = "fr"
    user_tz = DEFAULT_USER_DISPLAY_TIMEZONE
    for item in batch_results:
        item_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        content = (item_data or {}).get("_draft_content") or {}
        raw_lang = content.get("user_language") or raw_lang
        user_tz = content.get("user_timezone") or user_tz
        if content.get("user_language") and content.get("user_timezone"):
            break
    return normalize_language(raw_lang), user_tz


def _item_label(config: DraftDisplayConfig | None, content: dict[str, Any]) -> str:
    """The human-readable name of ONE batch item.

    Args:
        config: The type's display configuration.
        content: That item's stored draft content.

    Returns:
        The label, whitespace-collapsed and bounded, or ``""`` when the
        registry's keys resolve to nothing.
    """
    for key in config.item_label_fields if config else ():
        value = resolve_nested_value(content, key) if "." in key else content.get(key)
        if value:
            label = " ".join(str(value).split())
            if len(label) > _ITEM_LABEL_MAX_CHARS:
                return label[: _ITEM_LABEL_MAX_CHARS - 3] + "..."
            return label
    return ""


def _item_secondary(
    config: DraftDisplayConfig | None,
    content: dict[str, Any],
    user_lang: Language,
    user_tz: str,
) -> str:
    """The contextual datetime appended to a batch row, when the type declares one.

    Args:
        config: The type's display configuration.
        content: That item's stored draft content.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        ``" — <formatted>"`` or ``""``.
    """
    from src.core.time_utils import format_value_if_datetime_string

    if config is None or not config.item_secondary_datetime_key:
        return ""
    key = config.item_secondary_datetime_key
    value = resolve_nested_value(content, key) if "." in key else content.get(key)
    if not value or not isinstance(value, str):
        return ""
    formatted = format_value_if_datetime_string(
        value,
        user_timezone=user_tz,
        locale=user_lang,
        include_time=True,
        include_day_name=False,
    )
    return f" — {formatted}" if formatted != value else ""


def _batch_rows(
    draft_type: str,
    config: DraftDisplayConfig | None,
    batch_results: list[dict[str, Any]],
    user_lang: Language,
    user_tz: str,
) -> list[str]:
    """One Markdown row per batch item, each marked with its own outcome.

    Args:
        draft_type: The draft type string (for the diagnostic log).
        config: The type's display configuration.
        batch_results: The per-item results.
        user_lang: The person's language.
        user_tz: Their IANA timezone.

    Returns:
        The rows, in batch order.
    """
    rows: list[str] = []
    for item in batch_results:
        item_data = item.get("data") if isinstance(item.get("data"), dict) else {}
        content = (item_data or {}).get("_draft_content") or {}
        mark = "✅" if item.get("status") == "success" else "❌"
        label = _item_label(config, content)
        if not label:
            logger.warning(
                "draft_result_format_empty_label",
                draft_type=draft_type,
                available_keys=sorted(content.keys()),
            )
            rows.append(plain_row(f"{mark} {item.get('message', '')}"))
            continue
        secondary = _item_secondary(config, content, user_lang, user_tz)
        rows.append(plain_row(f"{mark} **{label}**{secondary}"))
    return rows


def _render_batch(
    status: str,
    draft_type: str,
    domain_emoji: str,
    config: DraftDisplayConfig | None,
    data: dict[str, Any],
) -> str:
    """Render the batch (``CONFIRM_BATCH``) execution result.

    Args:
        status: Either ``"success"`` or ``"partial_error"``.
        draft_type: Draft type string from the execution result.
        domain_emoji: Pre-resolved emoji from the registry (or ``""``).
        config: Display config for the draft type, or None if unknown.
        data: Execution data carrying ``batch_results``, ``success_count`` and
            ``total_count``.

    Returns:
        The headline and one row per item.
    """
    batch_results = data.get("batch_results", []) or []
    success_count = data.get("success_count", 0)
    total_count = data.get("total_count", 0)
    user_lang, user_tz = _batch_locale(batch_results)

    if config is not None:
        header_text = compose_result_header(
            success_count=success_count,
            total_count=total_count,
            noun_key=config.noun_key,
            verb_past_key=config.verb_past_key,
            language=user_lang,
        )
    else:
        # Unknown draft type — the legacy bare "X/Y" header.
        header_text = f"{success_count}/{total_count}"

    mark = _STATUS_MARKS["success" if status == "success" else "partial_error"]
    rows = _batch_rows(draft_type, config, batch_results, user_lang, user_tz)
    return _joined(_headline(domain_emoji, mark, header_text), rows)


def _joined(headline: str, rows: list[str]) -> str:
    """Assemble a headline and its rows.

    Args:
        headline: The first line.
        rows: The Markdown rows, possibly empty.

    Returns:
        The headline alone, or the headline, one blank line, and the rows —
        never opening or closing on whitespace, since a block carries its own
        trailing newline.
    """
    if not rows:
        return headline
    return (headline + "\n\n" + "\n".join(rows)).rstrip()


def _render_single_success(
    domain_emoji: str,
    config: DraftDisplayConfig | None,
    message: str,
    data: dict[str, Any],
) -> str:
    """Render a single confirmed draft's success.

    Args:
        domain_emoji: The draft family's emoji.
        config: Display config for the draft type, or None if unknown.
        message: The localized success sentence.
        data: Execution data carrying ``_draft_content`` and any permalink.

    Returns:
        The headline and one row per detail field.
    """
    draft = data.get("_draft_content", {}) if isinstance(data, dict) else {}
    draft = draft if isinstance(draft, dict) else {}
    user_lang = normalize_language(draft.get("user_language") or "fr")
    user_tz = draft.get("user_timezone") or DEFAULT_USER_DISPLAY_TIMEZONE
    rows = _detail_rows(config, draft, data, user_lang, user_tz)
    return _joined(_headline(domain_emoji, _STATUS_MARKS["success"], message), rows)


def render_execution_result(result: dict[str, Any] | None) -> str:
    """What a person reads once a confirmed draft has run.

    Args:
        result: Draft execution result dict with:
            - status: ``"success"`` | ``"cancelled"`` | ``"error"`` |
              ``"partial_error"``
            - message: Localized message
            - draft_type: Type of draft (contact, event, email, reminder_delete…)
            - action: Optional, e.g. ``"confirm_batch"``
            - data: Result data dict (may contain ``html_link``,
              ``_draft_content``, ``batch_results``, ``success_count``,
              ``total_count``)

    Returns:
        Markdown, with no leading or trailing whitespace. ``""`` when there is
        nothing to say — an empty payload, or a status nobody declared.
    """
    if not result:
        return ""

    status = result.get("status", "unknown")
    message = result.get("message", "")
    draft_type = result.get("draft_type", "action")
    data = result.get("data", {}) if isinstance(result.get("data"), dict) else {}
    action = result.get("action", "")

    config = get_draft_display_config(draft_type)
    domain_emoji = config.emoji if config else ""

    if action == DraftAction.CONFIRM_BATCH.value and status in ("success", "partial_error"):
        return _render_batch(status, draft_type, domain_emoji, config, data)

    if status == "success":
        return _render_single_success(domain_emoji, config, message, data)

    if status == "partial_error":
        # Non-batch partial_error fallback (defensive — batch is handled above).
        counted = f"{data.get('success_count', 0)}/{data.get('total_count', 0)}"
        return _headline(domain_emoji, _STATUS_MARKS["partial_error"], f"{message} ({counted})")

    if status in ("cancelled", "error"):
        return _headline(domain_emoji, _STATUS_MARKS[status], message)

    return ""
